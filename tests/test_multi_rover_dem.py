"""Pianificazione della flotta su DEM: percorsi reali, energia, sovrapposizioni."""
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from src.multi_rover import plan_fleet_on_dem

CRS = "+proj=stere +lat_0=-90 +lat_ts=-90 +lon_0=0 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"


def dem_with_wall(tmp_path, gap_row=None):
    data = np.zeros((40, 40), dtype=np.float32)
    data[:, 20] = 100.0  # parete verticale insuperabile
    if gap_row is not None:
        data[gap_row, 20] = 0.0
    path = tmp_path / "dem.tif"
    with rasterio.open(path, "w", driver="GTiff", height=40, width=40, count=1, dtype="float32",
                       crs=CRS, transform=from_origin(-1000, 1000, 5, 5)) as ds:
        ds.write(data, 1)
    return path


def rover(rid, start, energy=100.0, caps=()):
    return {"id": rid, "start_rc": list(start), "available_energy_wh": energy,
            "energy_wh_per_m": 0.1, "max_slope_deg": 20.0, "capabilities": list(caps)}


def test_routes_go_through_the_gap_and_not_the_wall(tmp_path):
    result = plan_fleet_on_dem(dem_with_wall(tmp_path, gap_row=35), [rover("r1", (5, 5))],
                               [{"id": "t", "target_rc": [5, 35], "priority": 1}])
    path = result["assignments"][0]["path_rc"]
    crossing = [p for p in path if p[1] == 20]
    assert crossing and all(p[0] == 35 for p in crossing)
    # Il percorso reale è molto più lungo della linea d'aria (150 m).
    assert result["assignments"][0]["route_distance_m"] > 250


def test_no_route_leaves_the_task_unassigned(tmp_path):
    result = plan_fleet_on_dem(dem_with_wall(tmp_path), [rover("r1", (5, 5))],
                               [{"id": "t", "target_rc": [5, 35], "priority": 1}])
    assert result["assignments"] == []
    assert result["unassigned_tasks"][0]["reason"] == "no_feasible_route_or_energy"


def test_energy_budget_is_a_constraint(tmp_path):
    result = plan_fleet_on_dem(dem_with_wall(tmp_path, gap_row=35), [rover("r1", (5, 5), energy=5.0)],
                               [{"id": "t", "target_rc": [5, 35], "priority": 1}])
    assert result["unassigned_tasks"][0]["reason"] == "no_feasible_route_or_energy"


def test_the_nearest_capable_rover_wins_and_moves(tmp_path):
    dem = dem_with_wall(tmp_path, gap_row=35)
    result = plan_fleet_on_dem(dem, [rover("near", (5, 10)), rover("far", (30, 2)), rover("cam", (6, 10), caps=["camera"])],
                               [{"id": "a", "target_rc": [5, 15], "priority": 2},
                                {"id": "b", "target_rc": [10, 15], "priority": 1, "required_capabilities": ["camera"]}])
    by_task = {a["task_id"]: a["rover_id"] for a in result["assignments"]}
    assert by_task == {"a": "near", "b": "cam"}
    final = {r["rover_id"]: r["final_position_rc"] for r in result["rovers"]}
    assert final["near"] == [5, 15] and final["far"] == [30, 2]


def test_shared_cells_between_routes_are_reported(tmp_path):
    dem = dem_with_wall(tmp_path, gap_row=35)
    result = plan_fleet_on_dem(dem, [rover("r1", (30, 5), caps=["drill"]), rover("r2", (39, 5), caps=["camera"])],
                               [{"id": "a", "target_rc": [30, 35], "priority": 2, "required_capabilities": ["drill"]},
                                {"id": "b", "target_rc": [39, 35], "priority": 1, "required_capabilities": ["camera"]}])
    assert len(result["assignments"]) == 2
    assert result["route_overlaps"] and result["route_overlaps"][0]["shared_cells"] >= 1


def test_start_outside_the_dem_is_refused(tmp_path):
    with pytest.raises(ValueError):
        plan_fleet_on_dem(dem_with_wall(tmp_path), [rover("r1", (99, 5))], [])
