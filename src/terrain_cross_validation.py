# Last updated: 2026-11-15
"""Confronto incrociato dell'orizzonte e dell'illuminazione tra due DEM indipendenti.

LOLA (altimetria laser, 5 m/px, PGDA) e LROC NAC DTM SR12 (stereo fotogrammetria, 2 m/px) sono
prodotti con strumenti e metodi diversi. Per punti dentro la sovrapposizione si calcola il profilo
d'orizzonte con la stessa distanza massima su entrambi e si confrontano:

- lo scarto dell'elevazione dell'orizzonte per azimut;
- la frazione di tempo con Sole visibile in una finestra comune (stesse effemeridi locali).

Il confronto misura la coerenza tra dataset, non l'accuratezza assoluta: un errore comune ai due
(per esempio un DTM LROC controllato su LOLA) non viene rilevato. La distanza massima è limitata
dall'estensione del DTM LROC (5 km di lato), quindi l'orizzonte lontano non è confrontato.

Uso::

    python -m src.terrain_cross_validation --start 2026-11-15T00:00 --days 28
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np
import rasterio

from src.contact_windows import compute_windows, load_horizon
from src.horizon_analysis import calculate_and_write_horizon
from src.lunar_geometry import grid_azimuth_offset
from src.paths import PROJECT_ROOT

LOLA = PROJECT_ROOT / "data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif"
LROC = PROJECT_ROOT / "data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.TIF"
SCHEMA = "lunar-terrain-cross-validation/1.0"


def _points(bounds, count_per_side: int, margin_m: float) -> list[tuple[float, float]]:
    xs = np.linspace(bounds.left + margin_m, bounds.right - margin_m, count_per_side)
    ys = np.linspace(bounds.bottom + margin_m, bounds.top - margin_m, count_per_side)
    return [(float(x), float(y)) for y in ys for x in xs]


def _horizon(dem: Path, x: float, y: float, distance: float, step: float, out: Path) -> Path:
    with rasterio.open(dem) as ds:
        row, col = ds.index(x, y)
    return calculate_and_write_horizon(dem, row, col, observer_height_m=2.0,
                                       azimuth_step_deg=step, max_distance_m=distance,
                                       output_path=out)


def run(start_utc: datetime, days: float, points_per_side: int = 4, step_deg: float = 2.0,
        output_dir: Path | None = None) -> dict:
    output_dir = Path(output_dir or PROJECT_ROOT / "reports" / "validation")
    work = output_dir / "terrain_cross_validation"
    work.mkdir(parents=True, exist_ok=True)
    with rasterio.open(LROC) as ds:
        bounds, crs = ds.bounds, ds.crs
    margin = 600.0
    rows = []
    skipped = []
    for index, (x, y) in enumerate(_points(bounds, points_per_side, margin)):
        distance = min(x - bounds.left, bounds.right - x, y - bounds.bottom, bounds.top - y) - 10.0
        offset = grid_azimuth_offset(crs, x, y)
        lat, lon = offset["observer_latitude_deg"], offset["observer_longitude_east_deg"]
        try:
            lola = _horizon(LOLA, x, y, distance, step_deg, work / f"p{index}_lola.json")
            lroc = _horizon(LROC, x, y, distance, step_deg, work / f"p{index}_lroc.json")
        except ValueError as exc:  # quota non valida (nodata) in uno dei due DEM
            skipped.append({"point": index, "x_m": x, "y_m": y, "reason": str(exc)})
            continue
        az_a, el_a, _ = load_horizon(lola)
        az_b, el_b, _ = load_horizon(lroc)
        common = sorted(set(np.round(az_a, 6)) & set(np.round(az_b, 6)))
        a = {round(k, 6): v for k, v in zip(az_a, el_a)}
        b = {round(k, 6): v for k, v in zip(az_b, el_b)}
        diff = np.array([a[k] - b[k] for k in common])
        win_a = compute_windows(lola, offset["offset_deg"], lat, lon, start_utc, days * 24, 60)
        win_b = compute_windows(lroc, offset["offset_deg"], lat, lon, start_utc, days * 24, 60)
        agree = sum(sa["sun_visible"] == sb["sun_visible"]
                    for sa, sb in zip(win_a["samples"], win_b["samples"])) / len(win_a["samples"])
        rows.append({
            "point": index, "x_m": x, "y_m": y, "latitude_deg": lat, "longitude_east_deg": lon,
            "max_distance_m": distance, "azimuths_compared": len(common),
            "horizon_diff_deg": {"mean": float(diff.mean()), "rms": float(math.sqrt((diff ** 2).mean())),
                                 "max_abs": float(np.abs(diff).max())},
            "sun_visible_fraction": {"lola": win_a["summary"]["sun_visible_fraction"],
                                     "lroc": win_b["summary"]["sun_visible_fraction"]},
            "sun_visibility_agreement": agree,
        })
    rms = [r["horizon_diff_deg"]["rms"] for r in rows]
    agreement = [r["sun_visibility_agreement"] for r in rows]
    report = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "datasets": {"lola": str(LOLA.relative_to(PROJECT_ROOT)), "lroc": str(LROC.relative_to(PROJECT_ROOT))},
        "window": {"start_utc": start_utc.isoformat(), "days": days, "step_minutes": 60},
        "azimuth_step_deg": step_deg, "observer_height_m": 2.0,
        "points": rows,
        "skipped_points": skipped,
        "summary": {"points": len(rows), "skipped": len(skipped), "median_horizon_rms_deg": float(np.median(rms)),
                    "worst_horizon_rms_deg": float(max(rms)),
                    "median_sun_visibility_agreement": float(np.median(agreement)),
                    "worst_sun_visibility_agreement": float(min(agreement))},
        "scope": ("Coerenza tra due DEM indipendenti entro la sovrapposizione (orizzonte limitato a "
                  "pochi km). Non è un confronto con osservazioni di illuminazione."),
    }
    (output_dir / "terrain_cross_validation.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", required=True)
    parser.add_argument("--days", type=float, default=28)
    parser.add_argument("--points-per-side", type=int, default=4)
    args = parser.parse_args(argv)
    report = run(datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc), args.days,
                 args.points_per_side)
    for row in report["points"]:
        print(f"p{row['point']} rms={row['horizon_diff_deg']['rms']:.3f}° "
              f"sun LOLA={row['sun_visible_fraction']['lola']:.3f} LROC={row['sun_visible_fraction']['lroc']:.3f} "
              f"agree={row['sun_visibility_agreement']:.3f}")
    print(json.dumps(report["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
