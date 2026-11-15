# Last updated: 2026-11-15
"""Validazione incrociata delle effemeridi: Skyfield/SPICE locale contro NASA/JPL Horizons.

Due fonti indipendenti per la stessa grandezza (azimut/elevazione apparenti di Sole e Terra visti da
un sito lunare): Horizons (servizio JPL, effemeridi correnti) e il calcolo locale di
``src/local_ephemeris.py`` (DE421 + orientamento lunare PA DE421 + frame MOON_ME). Il confronto
misura scarti massimi, medi e RMS e li confronta con soglie dichiarate in anticipo.

Uso::

    python -m src.ephemeris_validation --start 2026-11-15T00:00 --hours 336 --step 6h

Le risposte di Horizons vengono salvate accanto al report per poter ripetere il confronto offline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from src.astronomy import SITES, query_observations
from src.local_ephemeris import observe, provenance
from src.paths import PROJECT_ROOT

SCHEMA = "lunar-ephemeris-validation/1.0"
# Tolleranze fissate prima della misura. 0.01° = 36": molto sotto la risoluzione angolare di un
# profilo d'orizzonte DEM (passo 2°) e sotto il diametro apparente del Sole (~0.53°).
TOLERANCE_ELEVATION_DEG = 0.01
TOLERANCE_AZIMUTH_DEG = 0.01
TOLERANCE_DISTANCE_REL = 1e-6
TARGETS = {"10": "Sun", "399": "Earth"}


def _wrap180(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def compare(reference: list, local: list) -> dict:
    """Scarti tra due liste di Observation allineate per tempo."""
    by_time = {item.time_utc[:16]: item for item in local}
    rows = []
    for ref in reference:
        mine = by_time.get(ref.time_utc[:16])
        if mine is None:
            continue
        d_el = mine.elevation_deg - ref.elevation_deg
        # L'azimut perde significato vicino allo zenit; i siti polari non lo raggiungono.
        d_az = _wrap180(mine.azimuth_deg - ref.azimuth_deg)
        d_rel = None
        if ref.distance_au and mine.distance_au:
            d_rel = (mine.distance_au - ref.distance_au) / ref.distance_au
        rows.append({"time_utc": ref.time_utc, "d_elevation_deg": d_el,
                     "d_azimuth_deg": d_az, "d_distance_rel": d_rel,
                     "reference_elevation_deg": ref.elevation_deg})
    if not rows:
        raise ValueError("Nessun istante in comune tra riferimento e calcolo locale.")

    def stats(key):
        values = [abs(r[key]) for r in rows if r[key] is not None]
        if not values:
            return None
        return {"max_abs": max(values), "mean_abs": sum(values) / len(values),
                "rms": math.sqrt(sum(v * v for v in values) / len(values)), "n": len(values)}

    return {"samples": len(rows), "elevation_deg": stats("d_elevation_deg"),
            "azimuth_deg": stats("d_azimuth_deg"), "distance_rel": stats("d_distance_rel"),
            "rows": rows}


def run_validation(start_utc: datetime, hours: int, step: str, sites: dict | None = None,
                   output_dir: Path | None = None) -> dict:
    sites = sites or SITES
    output_dir = Path(output_dir or PROJECT_ROOT / "reports" / "validation")
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    raw = {}
    for site, (lat, lon) in sites.items():
        for code, name in TARGETS.items():
            reference = query_observations(code, lat, lon, start_utc, hours=hours, step=step)
            times = [datetime.fromisoformat(o.time_utc) for o in reference]
            local = observe(code, lat, lon, times)
            stats = compare(reference, local)
            passed = (stats["elevation_deg"]["max_abs"] <= TOLERANCE_ELEVATION_DEG
                      and stats["azimuth_deg"]["max_abs"] <= TOLERANCE_AZIMUTH_DEG
                      and (stats["distance_rel"] is None
                           or stats["distance_rel"]["max_abs"] <= TOLERANCE_DISTANCE_REL))
            raw[f"{site}:{name}"] = [o.__dict__ for o in reference]
            results.append({"site": site, "latitude_deg": lat, "longitude_east_deg": lon,
                            "target": name, "within_tolerance": passed,
                            **{k: v for k, v in stats.items() if k != "rows"}})
    report = {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "reference": {"source": "NASA/JPL Horizons API", "quantities": "4,20 (apparent az/el, range)",
                      "center": "coord@301", "coord_type": "GEODETIC (sphere: planetocentric)"},
        "local": provenance(),
        "window": {"start_utc": start_utc.isoformat(), "hours": hours, "step": step},
        "tolerances": {"elevation_deg": TOLERANCE_ELEVATION_DEG, "azimuth_deg": TOLERANCE_AZIMUTH_DEG,
                       "distance_rel": TOLERANCE_DISTANCE_REL},
        "results": results,
        "all_within_tolerance": all(r["within_tolerance"] for r in results),
        "scope": ("Valida la geometria Sole/Terra calcolata localmente rispetto a Horizons. Non valida "
                  "orizzonte DEM, ombre del terreno o georeferenziazione del raster."),
    }
    stamp = start_utc.strftime("%Y%m%dT%H%M")
    (output_dir / f"ephemeris_validation_{stamp}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (output_dir / f"horizons_reference_{stamp}.json").write_text(
        json.dumps(raw, indent=1), encoding="utf-8")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--start", required=True, help="UTC, es. 2026-11-15T00:00")
    parser.add_argument("--hours", type=int, default=336)
    parser.add_argument("--step", default="6h")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)
    start = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    report = run_validation(start, args.hours, args.step, output_dir=args.output_dir)
    for row in report["results"]:
        print(f"{row['site']:<17} {row['target']:<6} n={row['samples']:<4} "
              f"max|dEl|={row['elevation_deg']['max_abs']:.2e}° max|dAz|={row['azimuth_deg']['max_abs']:.2e}°")
    print("entro le tolleranze:", report["all_within_tolerance"])
    return 0 if report["all_within_tolerance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
