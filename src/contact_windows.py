# Last updated: 2026-11-15
"""Finestre di illuminazione e di contatto Terra–Luna per un osservatore su un DEM.

Combina tre ingredienti già presenti e validati separatamente:

1. il profilo d'orizzonte del DEM (``horizon_analysis``), in azimut di griglia;
2. l'offset nord geografico → nord di griglia ricavato dal CRS (``lunar_geometry.grid_azimuth_offset``);
3. le posizioni apparenti di Sole e Terra (``local_ephemeris``, validato contro Horizons da
   ``ephemeris_validation``).

Per ogni istante: il corpo è visibile se la sua elevazione supera l'orizzonte del terreno nella sua
direzione più un margine. Una finestra di contatto richiede anche, se fornito, che il bilancio di
collegamento (``communications.calculate_link_budget``) chiuda alla distanza di quell'istante.
Per il Sole viene riportata anche la frazione di disco visibile (diametro apparente ~0.53°),
approssimata linearmente sul profilo locale.

Limiti dichiarati: orizzonte campionato fino a ``max_distance_m`` del profilo; nessuna diffrazione
radio sul bordo del terreno; la geometria dell'antenna terrestre (stazioni DSN) non è modellata, la
Terra è trattata come un punto.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np

from src.communications import calculate_link_budget
from src.local_ephemeris import light_time_s, observe, time_grid, provenance
from src.lunar_geometry import geographic_to_grid_azimuth

SCHEMA = "lunar-contact-windows/1.0"
SUN_RADIUS_KM = 695_700.0
AU_KM = 149_597_870.7


def load_horizon(horizon_json: str | Path) -> tuple[np.ndarray, np.ndarray, dict]:
    profile = json.loads(Path(horizon_json).read_text(encoding="utf-8"))
    az, el = [], []
    for sample in profile.get("samples", []):
        a, h = sample.get("grid_azimuth_deg"), sample.get("horizon_elevation_deg")
        if a is not None and h is not None and math.isfinite(a) and math.isfinite(h):
            az.append(float(a) % 360.0)
            el.append(float(h))
    if len(az) < 3:
        raise ValueError("Profilo d'orizzonte con meno di 3 campioni validi.")
    order = np.argsort(az)
    return np.asarray(az)[order], np.asarray(el)[order], profile


def horizon_at(az: np.ndarray, el: np.ndarray, grid_azimuth_deg: float) -> float:
    az_ext = np.concatenate(([az[-1] - 360.0], az, [az[0] + 360.0]))
    el_ext = np.concatenate(([el[-1]], el, [el[0]]))
    return float(np.interp(grid_azimuth_deg % 360.0, az_ext, el_ext))


def _windows(times: list[str], flags: list[bool], step_minutes: float) -> list[dict]:
    windows, start = [], None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        if (not flag or i == len(flags) - 1) and start is not None:
            end = i if flag else i - 1
            windows.append({"start_utc": times[start], "end_utc": times[end],
                            "samples": end - start + 1,
                            "duration_h": (end - start) * step_minutes / 60.0,
                            "open_at_start_of_series": start == 0,
                            "open_at_end_of_series": end == len(flags) - 1})
            start = None
    return windows


def compute_windows(horizon_json: str | Path, offset_deg: float, latitude_deg: float,
                    longitude_east_deg: float, start_utc: datetime, hours: float,
                    step_minutes: float = 30.0, min_clearance_deg: float = 0.0,
                    link: dict | None = None) -> dict:
    """Serie temporale e finestre di illuminazione (Sole) e contatto (Terra)."""
    az, el, profile = load_horizon(horizon_json)
    times = time_grid(start_utc, hours, step_minutes)
    sun = observe("sun", latitude_deg, longitude_east_deg, times)
    earth = observe("earth", latitude_deg, longitude_east_deg, times)
    rows = []
    for t, s, e in zip(times, sun, earth):
        s_grid = geographic_to_grid_azimuth(s.azimuth_deg, offset_deg)
        e_grid = geographic_to_grid_azimuth(e.azimuth_deg, offset_deg)
        s_hor = horizon_at(az, el, s_grid)
        e_hor = horizon_at(az, el, e_grid)
        sun_radius_deg = math.degrees(math.asin(SUN_RADIUS_KM / (s.distance_au * AU_KM)))
        clearance = s.elevation_deg - s_hor
        disk = min(1.0, max(0.0, (clearance + sun_radius_deg) / (2 * sun_radius_deg)))
        earth_visible = (e.elevation_deg - e_hor) > min_clearance_deg
        budget = None
        link_ok = earth_visible
        if link is not None:
            distance_km = e.distance_au * AU_KM
            budget = calculate_link_budget(distance_km=distance_km, **link)
            link_ok = earth_visible and budget["link_margin_db"] >= budget["required_margin_db"]
        rows.append({
            "time_utc": t.astimezone(timezone.utc).isoformat(),
            "sun_elevation_deg": s.elevation_deg, "sun_azimuth_deg": s.azimuth_deg,
            "sun_terrain_horizon_deg": s_hor, "sun_clearance_deg": clearance,
            "sun_disk_visible_fraction": disk, "sun_visible": clearance > min_clearance_deg,
            "earth_elevation_deg": e.elevation_deg, "earth_azimuth_deg": e.azimuth_deg,
            "earth_terrain_horizon_deg": e_hor, "earth_clearance_deg": e.elevation_deg - e_hor,
            "earth_visible": earth_visible,
            "earth_distance_km": e.distance_au * AU_KM,
            "one_way_light_time_s": light_time_s(e.distance_au),
            "link_margin_db": None if budget is None else budget.get("link_margin_db"),
            "contact": link_ok,
        })
    stamps = [r["time_utc"] for r in rows]
    illumination = _windows(stamps, [r["sun_visible"] for r in rows], step_minutes)
    contact = _windows(stamps, [r["contact"] for r in rows], step_minutes)
    n = len(rows)
    return {
        "schema": SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "site": {"latitude_deg": latitude_deg, "longitude_east_deg": longitude_east_deg,
                 "horizon_profile": str(horizon_json), "observer": profile.get("observer")},
        "azimuth_mapping": {"offset_deg": offset_deg,
                            "convention": "grid_azimuth = (geographic_azimuth + offset) mod 360"},
        "ephemeris": provenance(),
        "series": {"start_utc": stamps[0], "end_utc": stamps[-1], "step_minutes": step_minutes,
                   "samples": n},
        "min_clearance_deg": min_clearance_deg,
        "link": link,
        "summary": {
            "sun_visible_fraction": sum(r["sun_visible"] for r in rows) / n,
            "mean_sun_disk_fraction": sum(r["sun_disk_visible_fraction"] for r in rows) / n,
            "earth_visible_fraction": sum(r["earth_visible"] for r in rows) / n,
            "contact_fraction": sum(r["contact"] for r in rows) / n,
            "illumination_windows": len(illumination), "contact_windows": len(contact),
            "one_way_light_time_s": {"min": min(r["one_way_light_time_s"] for r in rows),
                                     "max": max(r["one_way_light_time_s"] for r in rows)},
        },
        "illumination_windows": illumination,
        "contact_windows": contact,
        "samples": rows,
        "limits": [
            "Orizzonte limitato alla distanza massima del profilo DEM.",
            "Terra trattata come punto: stazioni di terra, loro visibilità e copertura DSN non modellate.",
            "Nessuna diffrazione radio sul bordo del terreno; nessuna penombra oltre la frazione di disco lineare.",
        ],
    }


def write_windows(result: dict, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
