# Last updated: 2026-11-15
"""Coordinamento multi-rover: allocazione dei task e pianificazione della flotta sul DEM.

- ``allocate_tasks``: allocazione di alto livello in un frame metrico locale (distanze euclidee).
- ``plan_fleet_on_dem``: allocazione con percorsi A* reali sul DEM, budget energetico per rover,
  sovrapposizioni tra percorsi e finestre di contatto con la Terra alla destinazione.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any
import numpy as np


def _finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name}: valore numerico richiesto") from exc
    if not math.isfinite(number):
        raise ValueError(f"{name}: il valore deve essere finito")
    if minimum is not None and number < minimum:
        raise ValueError(f"{name}: il valore minimo è {minimum}")
    return number


def _xy(value: Any, name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} deve essere [x, y] nel medesimo frame metrico locale")
    return (_finite_number(value[0], f"{name}[0]"), _finite_number(value[1], f"{name}[1]"))


def allocate_tasks(rovers: list[dict], tasks: list[dict], *, output_path: str | Path | None = None) -> dict:
    """Assegna task ai rover con capacità, budget energetico e bilanciamento carico.

    Rover schema: id, position_xy, capabilities, available_energy_wh,
    energy_wh_per_m (optional, default 0).
    Task schema: id, position_xy, required_capabilities (optional), priority,
    estimated_energy_wh (optional, default 0).
    """
    if not isinstance(rovers, list) or not rovers:
        raise ValueError("Specificare almeno un rover")
    if not isinstance(tasks, list):
        raise ValueError("tasks deve essere una lista")
    rover_state = {}
    for i, rover in enumerate(rovers):
        if not isinstance(rover, dict):
            raise ValueError(f"Rover #{i+1} non valido")
        rid = str(rover.get("id", "")).strip()
        if not rid or rid in rover_state:
            raise ValueError(f"ID rover mancante o duplicato: {rid!r}")
        caps = rover.get("capabilities", [])
        if not isinstance(caps, list) or not all(isinstance(c, str) for c in caps):
            raise ValueError(f"{rid}.capabilities deve essere una lista di stringhe")
        rover_state[rid] = {
            "id": rid,
            "position": _xy(rover.get("position_xy", [0, 0]), f"{rid}.position_xy"),
            "capabilities": set(caps),
            "initial_energy_wh": _finite_number(rover.get("available_energy_wh", 0), f"{rid}.available_energy_wh", minimum=0),
            "remaining_energy_wh": _finite_number(rover.get("available_energy_wh", 0), f"{rid}.available_energy_wh", minimum=0),
            "energy_wh_per_m": _finite_number(rover.get("energy_wh_per_m", 0), f"{rid}.energy_wh_per_m", minimum=0),
            "assigned_task_ids": [],
            "distance_m": 0.0,
            "energy_reserved_wh": 0.0,
        }

    normalized_tasks = []
    seen_task_ids = set()
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise ValueError(f"Task #{i+1} non valido")
        tid = str(task.get("id", "")).strip()
        if not tid or tid in seen_task_ids:
            raise ValueError(f"ID task mancante o duplicato: {tid!r}")
        seen_task_ids.add(tid)
        required = task.get("required_capabilities", [])
        if not isinstance(required, list) or not all(isinstance(c, str) for c in required):
            raise ValueError(f"{tid}.required_capabilities deve essere una lista di stringhe")
        normalized_tasks.append({
            "id": tid,
            "position": _xy(task.get("position_xy", [0, 0]), f"{tid}.position_xy"),
            "required_capabilities": set(required),
            "priority": _finite_number(task.get("priority", 1), f"{tid}.priority", minimum=0),
            "task_energy_wh": _finite_number(task.get("estimated_energy_wh", 0), f"{tid}.estimated_energy_wh", minimum=0),
            "description": str(task.get("description", "")),
        })

    # Priorità più alta prima; gli ID rendono i pareggi ripetibili.
    normalized_tasks.sort(key=lambda t: (-t["priority"], t["id"]))
    assignments, unassigned = [], []
    for task in normalized_tasks:
        candidates = []
        capability_candidates = []
        for rover in rover_state.values():
            if not task["required_capabilities"].issubset(rover["capabilities"]):
                continue
            capability_candidates.append(rover)
            x0, y0 = rover["position"]
            x1, y1 = task["position"]
            distance = math.hypot(x1 - x0, y1 - y0)
            travel_energy = distance * rover["energy_wh_per_m"]
            total_energy = task["task_energy_wh"] + travel_energy
            if total_energy > rover["remaining_energy_wh"]:
                continue
            # Favorisce la distanza breve e il rover meno carico; energia è un vincolo.
            load_ratio = (rover["initial_energy_wh"] - rover["remaining_energy_wh"]) / max(rover["initial_energy_wh"], 1.0)
            cost = distance * (1.0 + load_ratio) + total_energy * 0.01
            candidates.append((cost, rover["id"], distance, travel_energy, total_energy))
        if not candidates:
            if not capability_candidates:
                reason = "no_rover_with_required_capabilities"
            else:
                reason = "insufficient_energy_budget"
            unassigned.append({"task_id": task["id"], "reason": reason})
            continue
        _, rid, distance, travel_energy, total_energy = min(candidates, key=lambda c: (c[0], c[1]))
        rover = rover_state[rid]
        rover["remaining_energy_wh"] -= total_energy
        rover["energy_reserved_wh"] += total_energy
        rover["distance_m"] += distance
        rover["position"] = task["position"]
        rover["assigned_task_ids"].append(task["id"])
        assignments.append({
            "task_id": task["id"], "rover_id": rid,
            "distance_from_previous_position_m": round(distance, 3),
            "travel_energy_estimate_wh": round(travel_energy, 3),
            "task_energy_estimate_wh": round(task["task_energy_wh"], 3),
            "total_energy_reserved_wh": round(total_energy, 3),
            "priority": task["priority"], "status": "assigned",
            "description": task["description"],
        })

    rover_summary = []
    for rover in sorted(rover_state.values(), key=lambda r: r["id"]):
        rover_summary.append({
            "rover_id": rover["id"],
            "assigned_task_ids": rover["assigned_task_ids"],
            "distance_sum_m": round(rover["distance_m"], 3),
            "energy_reserved_wh": round(rover["energy_reserved_wh"], 3),
            "remaining_energy_wh": round(rover["remaining_energy_wh"], 3),
            "capabilities": sorted(rover["capabilities"]),
            "final_position_xy": [round(rover["position"][0], 3), round(rover["position"][1], 3)],
        })
    result = {
        "schema": "lunar-multi-rover-allocation/1.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "local_high_level_plan",
        "rover_count": len(rover_state), "task_count": len(normalized_tasks),
        "assigned_count": len(assignments), "unassigned_count": len(unassigned),
        "assignments": assignments, "unassigned_tasks": unassigned,
        "rovers": rover_summary,
        "limitations": [
            "Posizioni espresse in un frame metrico locale comune; non vengono trasformate da coordinate geografiche lunari.",
            "La distanza è euclidea in linea d'aria, non un percorso calcolato sul DEM.",
            "I consumi sono stime basate su energy_wh_per_m e sui consumi task forniti dall'utente.",
            "Non vengono pianificati link radio, finestre di illuminazione, collision avoidance o sincronizzazione distribuita.",
            "Gli eventi possono essere registrati nel journal locale; nessun nodo P-System remoto è collegato.",
        ],
    }
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        result["output_path"] = str(path)
    return result


# ---------------------------------------------------------------------------
# Pianificazione della flotta sul DEM (2026-11-15)
# ---------------------------------------------------------------------------

def plan_fleet_on_dem(dem_path: str | Path, rovers: list[dict], tasks: list[dict], *,
                      communications: dict | None = None,
                      output_path: str | Path | None = None) -> dict:
    """Assegna task e calcola i percorsi reali di più rover sullo stesso DEM.

    Rover: id, start_rc, available_energy_wh, energy_wh_per_m, max_slope_deg, capabilities.
    Task: id, target_rc, priority, required_capabilities, estimated_energy_wh,
    requires_earth_contact (bool).

    Per ogni task, in ordine di priorità, si calcola il percorso A* (``rover_planning``) da ogni rover
    idoneo alla destinazione; vince il percorso più corto che rientra nell'energia residua. Il rover si
    sposta poi alla destinazione. Con ``communications`` (latitude/longitude non servono: ricavate dal
    CRS; start_utc, hours, step_minutes, horizon_max_distance_m, link_budget) i task che richiedono il
    contatto con la Terra ricevono le finestre di visibilità calcolate dalla destinazione (orizzonte DEM +
    effemeridi locali); senza finestre il task non viene assegnato.
    """
    import rasterio
    from src.rover_planning import plan_rover_path

    path = Path(dem_path)
    if not path.is_file():
        raise FileNotFoundError(f"DEM non trovato: {path}")
    if not isinstance(rovers, list) or not rovers:
        raise ValueError("Specificare almeno un rover")
    with rasterio.open(path) as ds:
        dem = ds.read(1, masked=True).filled(np.nan).astype(float)
        px, py = abs(ds.transform.a), abs(ds.transform.e)
        crs, transform = ds.crs, ds.transform

    def rc(value, name):
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError(f"{name} deve essere [riga, colonna]")
        r, c = int(value[0]), int(value[1])
        if not (0 <= r < dem.shape[0] and 0 <= c < dem.shape[1]):
            raise ValueError(f"{name} fuori dal DEM")
        return r, c

    state = {}
    for rover in rovers:
        rid = str(rover.get("id", "")).strip()
        if not rid or rid in state:
            raise ValueError(f"ID rover mancante o duplicato: {rid!r}")
        state[rid] = {
            "id": rid, "position": rc(rover.get("start_rc"), f"{rid}.start_rc"),
            "capabilities": set(rover.get("capabilities", [])),
            "remaining_wh": _finite_number(rover.get("available_energy_wh"), f"{rid}.available_energy_wh", minimum=0),
            "initial_wh": _finite_number(rover.get("available_energy_wh"), f"{rid}.available_energy_wh", minimum=0),
            "wh_per_m": _finite_number(rover.get("energy_wh_per_m"), f"{rid}.energy_wh_per_m", minimum=0),
            "max_slope_deg": _finite_number(rover.get("max_slope_deg", 20.0), f"{rid}.max_slope_deg", minimum=0),
            "routes": [], "distance_m": 0.0,
        }
    ordered = []
    for task in tasks:
        tid = str(task.get("id", "")).strip()
        if not tid:
            raise ValueError("ID task mancante")
        ordered.append({**task, "id": tid, "target": rc(task.get("target_rc"), f"{tid}.target_rc"),
                        "priority": _finite_number(task.get("priority", 1), f"{tid}.priority", minimum=0),
                        "task_wh": _finite_number(task.get("estimated_energy_wh", 0), f"{tid}.estimated_energy_wh", minimum=0)})
    ordered.sort(key=lambda t: (-t["priority"], t["id"]))

    def contact_for(target):
        if communications is None:
            return None
        from datetime import datetime as _dt
        from src.contact_windows import compute_windows
        from src.horizon_analysis import calculate_and_write_horizon
        from src.lunar_geometry import grid_azimuth_offset
        x, y = rasterio.transform.xy(transform, target[0], target[1], offset="center")
        orientation = grid_azimuth_offset(crs, float(x), float(y))
        work = Path(communications.get("work_dir", "reports/fleet_horizons"))
        work.mkdir(parents=True, exist_ok=True)
        horizon = calculate_and_write_horizon(
            path, target[0], target[1], observer_height_m=communications.get("antenna_height_m", 1.5),
            azimuth_step_deg=communications.get("azimuth_step_deg", 2.0),
            max_distance_m=communications.get("horizon_max_distance_m", 5000.0),
            output_path=work / f"horizon_r{target[0]}_c{target[1]}.json")
        windows = compute_windows(horizon, orientation["offset_deg"], orientation["observer_latitude_deg"],
                                  orientation["observer_longitude_east_deg"],
                                  _dt.fromisoformat(communications["start_utc"]), communications["hours"],
                                  communications.get("step_minutes", 60), link=communications.get("link_budget"))
        return {"earth_visible_fraction": windows["summary"]["earth_visible_fraction"],
                "contact_fraction": windows["summary"]["contact_fraction"],
                "contact_windows": windows["contact_windows"],
                "one_way_light_time_s": windows["summary"]["one_way_light_time_s"]}

    assignments, unassigned = [], []
    for task in ordered:
        eligible = [r for r in state.values() if set(task.get("required_capabilities", [])) <= r["capabilities"]]
        if not eligible:
            unassigned.append({"task_id": task["id"], "reason": "no_rover_with_required_capabilities"})
            continue
        contact = contact_for(task["target"]) if task.get("requires_earth_contact") else None
        if contact is not None and not contact["contact_windows"]:
            unassigned.append({"task_id": task["id"], "reason": "no_earth_contact_at_target",
                               "communications": contact})
            continue
        options, reasons = [], []
        for rover in eligible:
            try:
                plan = plan_rover_path(dem, rover["position"], task["target"], pixel_size_x_m=px,
                                       pixel_size_y_m=py, max_slope_deg=rover["max_slope_deg"],
                                       energy_wh_per_m=rover["wh_per_m"])
            except ValueError as exc:
                reasons.append(f"{rover['id']}: {exc}")
                continue
            total = plan.estimated_energy_wh + task["task_wh"]
            if total > rover["remaining_wh"]:
                reasons.append(f"{rover['id']}: energia {total:.1f} Wh oltre {rover['remaining_wh']:.1f} Wh")
                continue
            options.append((plan.distance_m, rover["id"], plan, total))
        if not options:
            unassigned.append({"task_id": task["id"], "reason": "no_feasible_route_or_energy", "details": reasons})
            continue
        _, rid, plan, total = min(options, key=lambda o: (o[0], o[1]))
        rover = state[rid]
        rover["remaining_wh"] -= total
        rover["distance_m"] += plan.distance_m
        rover["routes"].append(plan.path_rc)
        rover["position"] = task["target"]
        assignments.append({
            "task_id": task["id"], "rover_id": rid, "priority": task["priority"],
            "route_distance_m": round(plan.distance_m, 2), "route_cells": len(plan.path_rc),
            "route_max_slope_deg": round(plan.max_slope_deg, 2),
            "travel_energy_wh": round(plan.estimated_energy_wh, 3), "task_energy_wh": task["task_wh"],
            "total_energy_wh": round(total, 3), "remaining_energy_wh": round(rover["remaining_wh"], 3),
            "path_rc": [list(p) for p in plan.path_rc], "communications": contact,
        })

    cells = {rid: {tuple(p) for route in r["routes"] for p in route} for rid, r in state.items()}
    names = sorted(cells)
    shared = [{"rovers": [a, b], "shared_cells": len(cells[a] & cells[b])}
              for i, a in enumerate(names) for b in names[i + 1:] if cells[a] & cells[b]]
    result = {
        "schema": "lunar-multi-rover-dem-plan/1.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "dem": str(path), "pixel_size_m": [px, py],
        "assignments": assignments, "unassigned_tasks": unassigned,
        "rovers": [{"rover_id": r["id"], "final_position_rc": list(r["position"]),
                    "distance_m": round(r["distance_m"], 2),
                    "energy_used_wh": round(r["initial_wh"] - r["remaining_wh"], 3),
                    "remaining_energy_wh": round(r["remaining_wh"], 3)} for r in state.values()],
        "route_overlaps": shared,
        "limitations": [
            "Energia di trazione = distanza × consumo costante per metro (rover_planning).",
            "Le sovrapposizioni tra percorsi sono spaziali: la sequenza temporale dei movimenti non è pianificata.",
            "Il contatto con la Terra è geometrico (orizzonte DEM + effemeridi) più bilancio di collegamento di primo ordine.",
        ],
    }
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        result["output_path"] = str(out)
    return result
