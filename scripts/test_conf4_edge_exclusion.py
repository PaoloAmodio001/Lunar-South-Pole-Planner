from pathlib import Path
import csv
import json

import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling

LOLA = Path("data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif")
LROC = Path("data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.TIF")
CONF = Path("data/terrain/reference-lroc/source-check/NAC_DTM_ESALL_SR12_CONF_original.IMG")

OUTLIERS = Path("audit-reports/lola-lroc-conf4-outliers-20261114.csv")
OUTPUT = Path("audit-reports/lola-lroc-edge-exclusion-test-20261114")

ZONES = {
    "A": (-4022.5, -6167.5),
    "B": (-1052.5, -7657.5),
    "C": (-1002.5, -7342.5),
}

HALF = 30
EDGE_LIMIT_M = 10.0
SEARCH_RADIUS_M = 105.0


def stats(values):
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]

    if values.size == 0:
        return {
            "pixels": 0,
            "mae_m": None,
            "rmse_m": None,
            "max_abs_m": None,
            "over_10m": 0,
            "over_50m": 0,
            "over_100m": 0,
        }

    absolute = np.abs(values)
    return {
        "pixels": int(values.size),
        "mae_m": float(np.mean(absolute)),
        "rmse_m": float(np.sqrt(np.mean(values ** 2))),
        "max_abs_m": float(np.max(absolute)),
        "over_10m": int(np.count_nonzero(absolute > 10)),
        "over_50m": int(np.count_nonzero(absolute > 50)),
        "over_100m": int(np.count_nonzero(absolute > 100)),
    }


def edge_distances(valid_window, shape, halo, pixel_x, pixel_y):
    invalid = np.argwhere(~valid_window)
    result = np.full(shape, np.inf, dtype=np.float64)

    if invalid.size == 0:
        return result

    queries = np.indices(shape).reshape(2, -1).T + halo

    for start in range(0, len(queries), 128):
        q = queries[start:start + 128]
        dr = (q[:, None, 0] - invalid[None, :, 0]) * pixel_y
        dc = (q[:, None, 1] - invalid[None, :, 1]) * pixel_x
        distances = np.sqrt(dr * dr + dc * dc)
        result.ravel()[start:start + len(q)] = distances.min(axis=1)

    return result


def main():
    for path in (LOLA, LROC, CONF, OUTLIERS):
        if not path.is_file():
            raise FileNotFoundError(path)

    OUTPUT.mkdir(parents=True, exist_ok=True)

    with OUTLIERS.open(newline="", encoding="utf-8") as f:
        original_outliers = list(csv.DictReader(f))

    results = {
        "schema": "lola-lroc-conf4-edge-exclusion-test/1.0",
        "purpose": "Diagnostic test only; no permanent masking or source modification.",
        "edge_threshold_m": EDGE_LIMIT_M,
        "distance_definition": "Distance between pixel centres on the LOLA target grid and nearest invalid resampled LROC pixel centre.",
        "zones": {},
    }

    with rasterio.open(LOLA) as lo, \
         rasterio.open(LROC) as lr, \
         rasterio.open(CONF) as cf:

        pixel_x = abs(lo.transform.a)
        pixel_y = abs(lo.transform.e)
        halo = int(np.ceil(SEARCH_RADIUS_M / min(pixel_x, pixel_y))) + 1

        for name, (x, y) in ZONES.items():
            row, col = rasterio.transform.rowcol(lo.transform, x, y)

            r0, r1 = row - HALF, row + HALF + 1
            c0, c1 = col - HALF, col + HALF + 1

            if r0 - halo < 0 or c0 - halo < 0:
                raise RuntimeError(f"Finestra incompleta nella zona {name}")
            if r1 + halo > lo.height or c1 + halo > lo.width:
                raise RuntimeError(f"Finestra incompleta nella zona {name}")

            # Finestra LOLA.
            window = rasterio.windows.Window(
                c0, r0, 2 * HALF + 1, 2 * HALF + 1
            )
            lola_ma = lo.read(1, window=window, masked=True).astype(np.float64)
            lola = lola_ma.filled(np.nan)
            lola_valid = (
                ~np.ma.getmaskarray(lola_ma) & np.isfinite(lola)
            )

            # LROC ricampionato sulla finestra LOLA.
            transform = lo.window_transform(window)
            lroc_source_ma = lr.read(1, masked=True)
            lroc_source = lroc_source_ma.filled(np.nan).astype(np.float32)

            lroc = np.full(lola.shape, np.nan, dtype=np.float32)
            reproject(
                source=lroc_source,
                destination=lroc,
                src_transform=lr.transform,
                src_crs=lr.crs,
                src_nodata=np.nan,
                dst_transform=transform,
                dst_crs=lo.crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
                init_dest_nodata=True,
            )

            # CONF originale, nearest-neighbour.
            conf_source = cf.read(1, masked=False).astype(np.int16)
            conf = np.full(lola.shape, -1, dtype=np.int16)
            reproject(
                source=conf_source,
                destination=conf,
                src_transform=cf.transform,
                src_crs=cf.crs,
                src_nodata=None,
                dst_transform=transform,
                dst_crs=lo.crs,
                dst_nodata=-1,
                resampling=Resampling.nearest,
                init_dest_nodata=True,
            )

            # Distanza dal pixel LROC non valido più vicino.
            expanded_window = rasterio.windows.Window(
                c0 - halo,
                r0 - halo,
                2 * HALF + 1 + 2 * halo,
                2 * HALF + 1 + 2 * halo,
            )
            expanded_transform = lo.window_transform(expanded_window)

            expanded_lola_ma = lo.read(
                1, window=expanded_window, masked=True
            )
            expanded_shape = expanded_lola_ma.shape

            expanded_lroc = np.full(
                expanded_shape, np.nan, dtype=np.float32
            )
            reproject(
                source=lroc_source,
                destination=expanded_lroc,
                src_transform=lr.transform,
                src_crs=lr.crs,
                src_nodata=np.nan,
                dst_transform=expanded_transform,
                dst_crs=lo.crs,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
                init_dest_nodata=True,
            )

            distance = edge_distances(
                np.isfinite(expanded_lroc),
                lola.shape,
                halo,
                pixel_x,
                pixel_y,
            )

            valid = lola_valid & np.isfinite(lroc) & (conf >= 0)
            delta = lroc.astype(np.float64) - lola

            conf4 = valid & (conf == 4)
            conf14 = valid & (conf == 14)
            far_from_edge = distance > EDGE_LIMIT_M

            conf4_all = stats(delta[conf4])
            conf4_filtered = stats(delta[conf4 & far_from_edge])
            conf14_all = stats(delta[conf14])
            conf14_far = stats(delta[conf14 & far_from_edge])

            zone_outliers = []
            for item in original_outliers:
                rr = int(item["row"])
                cc = int(item["col"])
                if abs(rr - row) <= HALF and abs(cc - col) <= HALF:
                    local_r = rr - r0
                    local_c = cc - c0
                    d = float(distance[local_r, local_c])
                    zone_outliers.append({
                        "row": rr,
                        "col": cc,
                        "absolute_difference_m": float(
                            item["absolute_difference_m"]
                        ),
                        "distance_to_invalid_lroc_pixel_m": d,
                        "excluded_by_10m_test": d <= EDGE_LIMIT_M,
                    })

            results["zones"][name] = {
                "center_projected_m": {"x": x, "y": y},
                "conf4_before": conf4_all,
                "conf4_after_temporary_10m_exclusion": conf4_filtered,
                "conf4_pixels_temporarily_excluded": int(
                    np.count_nonzero(conf4 & ~far_from_edge)
                ),
                "conf14_before": conf14_all,
                "conf14_farther_than_10m": conf14_far,
                "conf14_pixels_within_10m": int(
                    np.count_nonzero(conf14 & ~far_from_edge)
                ),
                "original_outliers": len(zone_outliers),
                "outliers_excluded_by_10m_test": sum(
                    item["excluded_by_10m_test"] for item in zone_outliers
                ),
                "outliers_remaining": [
                    item for item in zone_outliers
                    if not item["excluded_by_10m_test"]
                ],
                "outlier_details": zone_outliers,
            }

            print(f"\n===== ZONA {name} =====")
            print("CONF4 prima:", conf4_all)
            print("CONF4 dopo esclusione temporanea:", conf4_filtered)
            print("CONF4 esclusi:", results["zones"][name][
                "conf4_pixels_temporarily_excluded"
            ])
            print("CONF14 prima:", conf14_all)
            print("CONF14 oltre 10 m:", conf14_far)
            print("Outlier rimossi dal test:",
                  results["zones"][name]["outliers_excluded_by_10m_test"],
                  "/", len(zone_outliers))
            print("Outlier residui:",
                  len(results["zones"][name]["outliers_remaining"]))

    json_path = OUTPUT / "conf4-edge-exclusion-results.json"
    csv_path = OUTPUT / "conf4-edge-exclusion-summary.csv"

    json_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        fields = [
            "zone",
            "group",
            "pixels",
            "mae_m",
            "rmse_m",
            "max_abs_m",
            "over_10m",
            "over_50m",
            "over_100m",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for zone, data in results["zones"].items():
            for group, key in (
                ("CONF4_before", "conf4_before"),
                ("CONF4_after_10m", "conf4_after_temporary_10m_exclusion"),
                ("CONF14_before", "conf14_before"),
                ("CONF14_after_10m", "conf14_farther_than_10m"),
            ):
                writer.writerow({
                    "zone": zone,
                    "group": group,
                    **data[key],
                })

    print("\n===== TEST COMPLETATO =====")
    print("JSON:", json_path)
    print("CSV:", csv_path)
    print("Nessun raster sorgente è stato modificato.")


if __name__ == "__main__":
    main()
