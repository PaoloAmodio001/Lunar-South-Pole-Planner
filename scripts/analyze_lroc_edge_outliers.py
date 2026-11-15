from pathlib import Path
import csv

import numpy as np
import rasterio
from rasterio.windows import Window
from rasterio.warp import reproject, Resampling

LOLA = Path("data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif")
LROC = Path("data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.TIF")
CONF = Path("data/terrain/reference-lroc/source-check/NAC_DTM_ESALL_SR12_CONF_original.IMG")
OUTLIERS = Path("audit-reports/lola-lroc-conf4-outliers-20261114.csv")

OUTPUT = Path("audit-reports/lola-lroc-edge-analysis-20261114")
OUTPUT.mkdir(parents=True, exist_ok=True)

ZONES = {
    "A": (-4022.5, -6167.5),
    "B": (-1052.5, -7657.5),
    "C": (-1002.5, -7342.5),
}

HALF = 30
THRESHOLDS = [5, 10, 20, 50, 100]


def stats(delta):
    if delta.size == 0:
        return {
            "pixels": 0,
            "mae_m": None,
            "rmse_m": None,
            "max_abs_m": None,
        }

    absolute = np.abs(delta)
    return {
        "pixels": int(delta.size),
        "mae_m": float(np.mean(absolute)),
        "rmse_m": float(np.sqrt(np.mean(delta ** 2))),
        "max_abs_m": float(np.max(absolute)),
    }


def main():
    for path in (LOLA, LROC, CONF, OUTLIERS):
        if not path.is_file():
            raise FileNotFoundError(path)

    with OUTLIERS.open(newline="", encoding="utf-8") as f:
        outlier_rows = list(csv.DictReader(f))

    with rasterio.open(LOLA) as lo, \
         rasterio.open(LROC) as lr, \
         rasterio.open(CONF) as cf:

        # LOLA sulla propria griglia.
        lola_ma = lo.read(1, masked=True).astype(np.float64)
        lola = lola_ma.filled(np.nan)
        lola_valid = (
            ~np.ma.getmaskarray(lola_ma)
            & np.isfinite(lola)
        )

        # LROC ricampionato esattamente sulla griglia LOLA.
        lroc_ma = lr.read(1, masked=True)
        lroc_source = lroc_ma.filled(np.nan).astype(np.float32)

        lroc = np.full(
            (lo.height, lo.width),
            np.nan,
            dtype=np.float32,
        )

        reproject(
            source=lroc_source,
            destination=lroc,
            src_transform=lr.transform,
            src_crs=lr.crs,
            src_nodata=np.nan,
            dst_transform=lo.transform,
            dst_crs=lo.crs,
            dst_nodata=np.nan,
            resampling=Resampling.bilinear,
            init_dest_nodata=True,
        )

        lroc_valid = np.isfinite(lroc)

        # CONF sulla griglia LOLA.
        conf_source = cf.read(1, masked=False).astype(np.int16)
        conf = np.full(
            (lo.height, lo.width),
            -1,
            dtype=np.int16,
        )

        reproject(
            source=conf_source,
            destination=conf,
            src_transform=cf.transform,
            src_crs=cf.crs,
            src_nodata=None,
            dst_transform=lo.transform,
            dst_crs=lo.crs,
            dst_nodata=-1,
            resampling=Resampling.nearest,
            init_dest_nodata=True,
        )

        # Distanza euclidea locale dal centro del pixel LROC
        # non valido più vicino. Non richiede SciPy.
        pixel_x = abs(lo.transform.a)
        pixel_y = abs(lo.transform.e)
        halo = int(np.ceil(105 / min(pixel_x, pixel_y))) + 1

        def local_edge_distance(valid_window, center_shape):
            invalid = np.argwhere(~valid_window)
            result = np.full(center_shape, np.inf, dtype=np.float64)

            if invalid.size == 0:
                return result

            queries = np.indices(center_shape).reshape(2, -1).T + halo

            for start in range(0, len(queries), 128):
                q = queries[start:start + 128]
                dr = (q[:, None, 0] - invalid[None, :, 0]) * pixel_y
                dc = (q[:, None, 1] - invalid[None, :, 1]) * pixel_x
                distances = np.sqrt(dr * dr + dc * dc)
                result.ravel()[start:start + len(q)] = distances.min(axis=1)

            return result

        delta = lroc.astype(np.float64) - lola
        delta[~np.isfinite(delta)] = np.nan

        global_valid = (
            lola_valid
            & lroc_valid
            & (conf == 4)
        )

        print("========== COPERTURA GLOBALE ==========")
        print("Pixel LROC validi:", int(lroc_valid.sum()))
        print("Pixel CONF 4 validi:", int(global_valid.sum()))
        print("Dimensione pixel LOLA:", pixel_x, "x", pixel_y, "m")

        summary_rows = []
        outlier_distance_rows = []

        for name, (x, y) in ZONES.items():
            row, col = rasterio.transform.rowcol(lo.transform, x, y)

            window = Window(
                col - HALF,
                row - HALF,
                HALF * 2 + 1,
                HALF * 2 + 1,
            )

            rs = slice(row - HALF, row + HALF + 1)
            cs = slice(col - HALF, col + HALF + 1)

            zone_valid = global_valid[rs, cs]
            zone_delta = delta[rs, cs]

            # Finestra ampliata: 61x61 pixel centrali più halo.
            hr0 = max(0, row - HALF - halo)
            hc0 = max(0, col - HALF - halo)
            hr1 = min(lo.height, row + HALF + halo + 1)
            hc1 = min(lo.width, col + HALF + halo + 1)

            expanded_valid = lroc_valid[hr0:hr1, hc0:hc1]
            center_r0 = row - HALF - hr0
            center_c0 = col - HALF - hc0

            center_valid_window = expanded_valid[
                center_r0:center_r0 + 2 * HALF + 1,
                center_c0:center_c0 + 2 * HALF + 1,
            ]

            if center_valid_window.shape != zone_valid.shape:
                raise RuntimeError("Dimensioni finestra distanza incoerenti.")

            # Il centro della finestra ampliata può variare vicino ai bordi
            # del raster; qui le tre zone sono interne al raster.
            if center_r0 != halo or center_c0 != halo:
                raise RuntimeError("Halo incompleto: verifica i limiti raster.")

            zone_distance = local_edge_distance(
                expanded_valid,
                zone_valid.shape,
            )

            print(f"\n========== ZONA {name} ==========")
            print("Pixel CONF 4:", int(zone_valid.sum()))

            # Fasce esclusive: permettono di vedere l'andamento
            # dell'errore all'aumentare della distanza dal bordo.
            bands = [
                ("0-5", 0, 5),
                ("5-10", 5, 10),
                ("10-20", 10, 20),
                ("20-50", 20, 50),
                ("50-100", 50, 100),
                (">100", 100, float("inf")),
            ]

            for label, lower, upper in bands:
                mask = (
                    zone_valid
                    & (zone_distance > lower)
                    & (zone_distance <= upper)
                )

                values = zone_delta[mask]
                result = stats(values)

                item = {
                    "zone": name,
                    "distance_band_m": label,
                    **result,
                }
                summary_rows.append(item)

                print(
                    f"{label:>7} m | N={result['pixels']:4d} | "
                    f"MAE={result['mae_m']} | "
                    f"RMSE={result['rmse_m']} | "
                    f"MAX={result['max_abs_m']}"
                )

            # Conteggio cumulativo degli outlier originari.
            zone_outliers = [
                item for item in outlier_rows
                if (
                    abs(int(item["row"]) - row) <= HALF
                    and abs(int(item["col"]) - col) <= HALF
                )
            ]

            print("\nOutlier originari:", len(zone_outliers))

            for item in zone_outliers:
                rr = int(item["row"])
                cc = int(item["col"])
                local_r = rr - (row - HALF)
                local_c = cc - (col - HALF)
                d = float(zone_distance[local_r, local_c])

                record = {
                    "zone": name,
                    "row": rr,
                    "col": cc,
                    "x_m": item["x_lunar_projected_m"],
                    "y_m": item["y_lunar_projected_m"],
                    "difference_m": item["difference_lroc_minus_lola_m"],
                    "absolute_difference_m": item["absolute_difference_m"],
                    "distance_to_lroc_invalid_pixel_m": d,
                }
                outlier_distance_rows.append(record)

                print(
                    f"  row={rr} col={cc} "
                    f"|d|={float(item['absolute_difference_m']):.2f} m "
                    f"bordo={d:.2f} m"
                )

            for threshold in THRESHOLDS:
                count = sum(
                    float(item["distance_to_lroc_invalid_pixel_m"]) <= threshold
                    for item in outlier_distance_rows
                    if item["zone"] == name
                )
                print(
                    f"Outlier entro {threshold:3d} m dal bordo: "
                    f"{count}/{len(zone_outliers)}"
                )

        summary_path = OUTPUT / "edge_distance_statistics.csv"
        outlier_path = OUTPUT / "outlier_edge_distances.csv"

        for path, rows in (
            (summary_path, summary_rows),
            (outlier_path, outlier_distance_rows),
        ):
            if rows:
                with path.open("w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=list(rows[0].keys()),
                    )
                    writer.writeheader()
                    writer.writerows(rows)

        print("\n========== COMPLETATO ==========")
        print("Statistiche:", summary_path)
        print("Distanze outlier:", outlier_path)


if __name__ == "__main__":
    main()
