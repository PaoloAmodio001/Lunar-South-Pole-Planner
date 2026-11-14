# Last updated: 2026-11-15
"""F4 — Endpoint sottili sui moduli scientifici esistenti.

Nessun algoritmo è implementato qui: ogni funzione valida l'input, sceglie un
raster da un catalogo fisso (mai percorsi forniti dal browser), chiama il
modulo scientifico originale e ne restituisce l'output così com'è, con la
provenienza dichiarata.

Moduli riutilizzati: data_quality.audit_raster,
terrain_metrics.analyze_local_terrain, horizon_analysis.calculate_and_write_horizon,
rover_planning.plan_rover_path, rover_energy.estimate_route_energy,
site_comparison.compare_candidate_sites.
"""
from __future__ import annotations

import json
import math
import tempfile
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.paths import PROJECT_ROOT

# Catalogo fisso dei raster consultabili dalla Web UI (id → metadati).
RASTERS = {
    "lola_site04": {
        "label": "LOLA Site04 DEM 5 m/px (official-lola)",
        "path": PROJECT_ROOT / "data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif",
        "kind": "DEM",
        "planning": True,
    },
    "lroc_nac_sr12": {
        "label": "LROC NAC DTM ESALL_SR12 (reference-lroc)",
        "path": PROJECT_ROOT / "data/terrain/reference-lroc/NAC_DTM_ESALL_SR12.TIF",
        "kind": "DTM",
        "planning": False,
    },
}

# Limiti di input per contenere i tempi di calcolo; non modificano gli algoritmi.
MAX_RADIUS_PX = 250
MAX_HORIZON_DISTANCE_M = 20000.0
MIN_AZIMUTH_STEP_DEG = 0.5
MAX_COMPARISON_HOURS = 168

# Al massimo due calcoli scientifici contemporanei: il server resta reattivo.
_SLOTS = threading.BoundedSemaphore(2)


class ScienceInputError(ValueError):
    """Input non valido (HTTP 400)."""


class ScienceNotFound(LookupError):
    """Raster sconosciuto o non presente (HTTP 404)."""


class ScienceBusy(RuntimeError):
    """Troppi calcoli in corso (HTTP 503)."""


class ScienceUpstreamError(RuntimeError):
    """Servizio esterno non raggiungibile (HTTP 502)."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _rel(path):
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT.resolve()))
    except (ValueError, OSError):
        return str(path)


def _clean(value):
    """JSON standard: NaN/inf → None (nessun valore inventato)."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _envelope(module, function, raster_id, result, notes=()):
    entry = RASTERS.get(raster_id) if raster_id else None
    return _clean({
        "provenance": {
            "module": module,
            "function": function,
            "raster_id": raster_id,
            "raster": _rel(entry["path"]) if entry else None,
            "computed_utc": _now(),
            "result_type": "diagnostica preliminare dal modulo originale; non certificata",
        },
        "notes": list(notes),
        "result": result,
    })


def _raster(raster_id, *, planning=False):
    entry = RASTERS.get(raster_id)
    if entry is None:
        raise ScienceNotFound(f"Raster sconosciuto: {raster_id!r}.")
    if planning and not entry["planning"]:
        raise ScienceInputError(f"Il raster {raster_id} non è abilitato per questa analisi.")
    if not entry["path"].is_file():
        raise ScienceNotFound(f"Raster non presente in locale: {_rel(entry['path'])}.")
    return entry["path"]


def _int(payload, key, lo=None, hi=None, default=None):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScienceInputError(f"{key} deve essere un intero.")
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ScienceInputError(f"{key} fuori intervallo [{lo}, {hi}].")
    return value


def _float(payload, key, lo=None, hi=None, default=None):
    value = payload.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ScienceInputError(f"{key} deve essere un numero finito.")
    value = float(value)
    if (lo is not None and value < lo) or (hi is not None and value > hi):
        raise ScienceInputError(f"{key} fuori intervallo [{lo}, {hi}].")
    return value


def _rc(payload, key):
    value = payload.get(key)
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in value)):
        raise ScienceInputError(f"{key} deve essere [riga, colonna] con interi non negativi.")
    return int(value[0]), int(value[1])


def _raster_shape(path):
    import rasterio
    with rasterio.open(path) as ds:
        return ds.height, ds.width


def _check_cell(path, row, col, label="cella"):
    height, width = _raster_shape(path)
    if not (0 <= row < height and 0 <= col < width):
        raise ScienceInputError(
            f"{label} ({row}, {col}) fuori dal raster ({height} righe × {width} colonne).")


class _slot:
    def __enter__(self):
        if not _SLOTS.acquire(blocking=False):
            raise ScienceBusy("Calcoli scientifici già in corso: riprovare tra poco.")

    def __exit__(self, *exc):
        _SLOTS.release()
        return False


# --------------------------------------------------------------------------- #
# Endpoint
# --------------------------------------------------------------------------- #
def list_rasters():
    items = []
    for raster_id, entry in RASTERS.items():
        exists = entry["path"].is_file()
        item = {"id": raster_id, "label": entry["label"], "kind": entry["kind"],
                "path": _rel(entry["path"]), "available": exists,
                "rover_planning": entry["planning"]}
        if exists:
            item["rows"], item["cols"] = _raster_shape(entry["path"])
        items.append(item)
    return {"rasters": items}


def dem_audit(payload):
    from src.data_quality import audit_raster
    raster_id = payload.get("raster_id")
    path = _raster(raster_id)
    with _slot():
        audit = asdict(audit_raster(path))
    audit["path"] = _rel(audit.get("path", path))
    return _envelope("src.data_quality", "audit_raster", raster_id, audit,
                     ["Audit dei metadati e delle quote; nessun file modificato.",
                      "Non certifica l'allineamento geodetico fisico."])


def local_terrain(payload):
    from src.terrain_metrics import analyze_local_terrain
    raster_id = payload.get("raster_id")
    path = _raster(raster_id)
    row = _int(payload, "row", lo=0)
    col = _int(payload, "col", lo=0)
    radius = _int(payload, "radius_pixels", lo=1, hi=MAX_RADIUS_PX, default=10)
    _check_cell(path, row, col)
    with _slot():
        metrics = asdict(analyze_local_terrain(path, row, col, radius))
    metrics["raster_path"] = _rel(metrics.get("raster_path", path))
    return _envelope("src.terrain_metrics", "analyze_local_terrain", raster_id, metrics)


def horizon_profile(payload):
    from src.horizon_analysis import calculate_and_write_horizon
    raster_id = payload.get("raster_id")
    path = _raster(raster_id)
    row = _int(payload, "row", lo=0)
    col = _int(payload, "col", lo=0)
    height = _float(payload, "observer_height_m", lo=0.0, hi=100.0, default=1.0)
    step = _float(payload, "azimuth_step_deg", lo=MIN_AZIMUTH_STEP_DEG, hi=45.0, default=2.0)
    distance = _float(payload, "max_distance_m", lo=1.0, hi=MAX_HORIZON_DISTANCE_M,
                      default=5000.0)
    _check_cell(path, row, col, "osservatore")
    with _slot(), tempfile.TemporaryDirectory(prefix="lunar-horizon-") as tmp:
        out = calculate_and_write_horizon(
            dem_path=path, row=row, col=col, observer_height_m=height,
            azimuth_step_deg=step, max_distance_m=distance,
            output_path=Path(tmp) / "horizon_profile.json",
        )
        profile = json.loads(Path(out).read_text(encoding="utf-8"))
    profile["source_dem"] = _rel(profile.get("source_dem", path))
    return _envelope("src.horizon_analysis", "calculate_and_write_horizon", raster_id, profile,
                     ["Azimut negli assi della griglia raster, non nord geografico certificato."])


ENERGY_KEYS = ("mass_kg", "rolling_resistance_coefficient", "drivetrain_efficiency",
               "auxiliary_power_w", "mission_duration_hours", "battery_capacity_wh")


def rover_plan(payload):
    import numpy as np
    import rasterio
    from src.rover_planning import plan_rover_path

    raster_id = payload.get("raster_id", "lola_site04")
    path = _raster(raster_id, planning=True)
    start = _rc(payload, "start_rc")
    goal = _rc(payload, "goal_rc")
    max_slope = _float(payload, "max_slope_deg", lo=0.1, hi=89.0, default=20.0)
    energy_per_m = _float(payload, "energy_wh_per_m", lo=0.0, hi=1e6, default=0.02)
    budget = payload.get("energy_budget_wh")
    budget = float("inf") if budget is None else _float(payload, "energy_budget_wh", lo=0.0)
    allow_diagonal = bool(payload.get("allow_diagonal", True))
    energy_cfg = payload.get("energy")
    if energy_cfg is not None:
        if not isinstance(energy_cfg, dict):
            raise ScienceInputError("energy deve essere un oggetto.")
        missing = [k for k in ENERGY_KEYS if energy_cfg.get(k) is None]
        if missing:
            raise ScienceInputError(
                "Stima energetica: parametri del rover mancanti: " + ", ".join(missing)
                + ". Nessun valore predefinito viene inventato.")
    _check_cell(path, *start, "partenza")
    _check_cell(path, *goal, "arrivo")

    with _slot():
        # Stessa preparazione del DEM usata da main.py e dall'orchestratore.
        with rasterio.open(path) as ds:
            dem = ds.read(1, masked=True).astype(np.float64).filled(np.nan)
            pixel_x = float(abs(ds.transform.a))
            pixel_y = float(abs(ds.transform.e))
        plan = plan_rover_path(
            dem, start, goal,
            pixel_size_x_m=pixel_x, pixel_size_y_m=pixel_y,
            max_slope_deg=max_slope, energy_wh_per_m=energy_per_m,
            energy_budget_wh=budget, allow_diagonal=allow_diagonal,
        )
        result = plan.to_dict()
        result.update({
            "dem_path": _rel(path), "dem_shape": list(dem.shape),
            "pixel_size_x_m": pixel_x, "pixel_size_y_m": pixel_y,
            "coordinates": "DEM row/column only; geodetic frame not validated",
            "inputs": {"start_rc": list(start), "goal_rc": list(goal),
                       "max_slope_deg": max_slope, "energy_wh_per_m": energy_per_m,
                       "energy_budget_wh": None if math.isinf(budget) else budget,
                       "allow_diagonal": allow_diagonal},
        })
        energy = None
        if energy_cfg is not None:
            from src.rover_energy import estimate_route_energy
            with tempfile.TemporaryDirectory(prefix="lunar-rover-") as tmp:
                plan_json = Path(tmp) / "rover_plan.json"
                # dem_path assoluto: rover_energy riapre il DEM (indipendenza dalla cwd, F2).
                plan_json.write_text(json.dumps(_clean({**result, "dem_path": str(path)})),
                                     encoding="utf-8")
                energy = estimate_route_energy(
                    plan_json,
                    mass_kg=_float(energy_cfg, "mass_kg", lo=0.0),
                    rolling_resistance_coefficient=_float(
                        energy_cfg, "rolling_resistance_coefficient", lo=0.0),
                    drivetrain_efficiency=_float(energy_cfg, "drivetrain_efficiency",
                                                 lo=0.0, hi=1.0),
                    auxiliary_power_w=_float(energy_cfg, "auxiliary_power_w", lo=0.0),
                    mission_duration_hours=_float(energy_cfg, "mission_duration_hours", lo=0.0),
                    battery_capacity_wh=_float(energy_cfg, "battery_capacity_wh", lo=0.0),
                    reserve_percent=_float(energy_cfg, "reserve_percent", lo=0.0, hi=100.0,
                                           default=20.0),
                    output_path=Path(tmp) / "rover_energy_assessment.json",
                )
                energy.pop("output_path", None)
                # Percorsi del file temporaneo: sostituiti con la provenienza reale.
                energy["route_plan"] = "piano calcolato in questa richiesta (non salvato)"
                energy["dem_path"] = _rel(path)
    notes = ["Percorso su griglia DEM (A*); non certifica la sicurezza del transito."]
    if energy is None:
        notes.append("Stima energetica dettagliata non richiesta: servono i parametri reali "
                     "del rover (rover_energy).")
    return _envelope("src.rover_planning" + (" + src.rover_energy" if energy else ""),
                     "plan_rover_path" + (" + estimate_route_energy" if energy else ""),
                     raster_id, {"plan": result, "energy_assessment": energy}, notes)


def site_comparison(payload):
    from src.astronomy import SITES, AstronomyError
    from src.site_comparison import compare_candidate_sites

    start_text = payload.get("start_utc")
    if not isinstance(start_text, str) or not start_text:
        raise ScienceInputError("start_utc obbligatorio (ISO 8601).")
    try:
        start = datetime.fromisoformat(start_text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScienceInputError(f"start_utc non valido: {exc}") from exc
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    hours = _int(payload, "hours", lo=1, hi=MAX_COMPARISON_HOURS, default=48)
    with _slot():
        try:
            report = compare_candidate_sites(SITES, start, hours=hours)
        except AstronomyError as exc:
            raise ScienceUpstreamError(f"NASA/JPL Horizons non disponibile: {exc}") from exc
        except OSError as exc:
            raise ScienceUpstreamError(f"Rete non disponibile: {exc}") from exc
    return _envelope("src.site_comparison", "compare_candidate_sites", None, report,
                     ["Richiede la rete (NASA/JPL Horizons): non disponibile offline."])


POST_ROUTES = {
    "/api/science/dem-audit": dem_audit,
    "/api/science/terrain": local_terrain,
    "/api/science/horizon": horizon_profile,
    "/api/science/rover-plan": rover_plan,
    "/api/science/site-comparison": site_comparison,
}
