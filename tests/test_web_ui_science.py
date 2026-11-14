"""Test F4 — endpoint scientifici sottili (src/ui_web/science_api.py).

Ogni endpoint viene confrontato con la chiamata diretta al modulo originale.
"""
import json
from dataclasses import asdict
from pathlib import Path
from threading import Thread

import pytest

from src.paths import PROJECT_ROOT
from src.ui_web import science_api
from tests.test_web_ui_mission import app, _request

DEM_REL = "data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif"
DEM = PROJECT_ROOT / DEM_REL
needs_dem = pytest.mark.skipif(not DEM.is_file(), reason="DEM Site04 non disponibile")
VOLATILE = {"generated_utc"}

# Valori dello step rover_path dell'orchestratore con mission_config.example.json
# (baseline F1/F2): start [120,113], goal [100,100], 20°, 0.02 Wh/m, budget 1e5.
EXAMPLE_ROVER = {"start_rc": [120, 113], "goal_rc": [100, 100], "max_slope_deg": 20.0,
                 "energy_wh_per_m": 0.02, "energy_budget_wh": 100000.0}
ROVER_PARAMS = {"mass_kg": 50.0, "rolling_resistance_coefficient": 0.2,
                "drivetrain_efficiency": 0.8, "auxiliary_power_w": 20.0,
                "mission_duration_hours": 2.0, "battery_capacity_wh": 500.0}


def _strip(d):
    return {k: v for k, v in d.items() if k not in VOLATILE}


@pytest.fixture(scope="module")
def port():
    srv = app.create_server("127.0.0.1", 0)
    Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


# --- Catalogo e accesso ----------------------------------------------------- #
def test_rasters_catalog(port):
    status, data, _ = _request(port, "GET", "/api/science/rasters")
    assert status == 200
    ids = {r["id"]: r for r in data["rasters"]}
    assert set(ids) == {"lola_site04", "lroc_nac_sr12"}
    assert ids["lola_site04"]["path"] == DEM_REL
    assert ids["lola_site04"]["rover_planning"] and not ids["lroc_nac_sr12"]["rover_planning"]


@pytest.mark.parametrize("raster_id", ["../../etc/passwd", "/etc/passwd", DEM_REL, None, 3])
def test_unknown_raster_rejected(port, raster_id):
    status, data, _ = _request(port, "POST", "/api/science/dem-audit", {"raster_id": raster_id})
    assert status == 404 and "Raster sconosciuto" in data["error"]


@pytest.mark.parametrize("path", ["/src/ui_web/science_api.py", "/science_api.py",
                                  "/api/science/unknown"])
def test_no_unauthorized_access(port, path):
    assert _request(port, "GET", path)[0] == 404


def test_static_science_js_and_section(port):
    status, body, resp = _request(port, "GET", "/science.js")
    assert status == 200 and resp.getheader("Content-Type").startswith("text/javascript")
    assert b"/api/science/" in body
    _, body, _ = _request(port, "GET", "/")
    assert b'id="scienceSection"' in body and b'src="/science.js"' in body


def test_busy_returns_503(port):
    assert science_api._SLOTS.acquire(blocking=False)
    assert science_api._SLOTS.acquire(blocking=False)
    try:
        status, data, _ = _request(port, "POST", "/api/science/dem-audit",
                                   {"raster_id": "lola_site04"})
    finally:
        science_api._SLOTS.release()
        science_api._SLOTS.release()
    assert status in (503, 404)  # 404 solo se il DEM non è presente in locale
    if DEM.is_file():
        assert "in corso" in data["error"]


# --- Audit DEM -------------------------------------------------------------- #
@needs_dem
def test_dem_audit_matches_module(port):
    from src.data_quality import audit_raster
    status, data, _ = _request(port, "POST", "/api/science/dem-audit", {"raster_id": "lola_site04"})
    assert status == 200
    assert data["provenance"]["module"] == "src.data_quality"
    direct = asdict(audit_raster(DEM))
    direct["path"] = DEM_REL
    assert data["result"] == json.loads(json.dumps(science_api._clean(direct)))


# --- Terreno locale --------------------------------------------------------- #
@needs_dem
def test_terrain_matches_module(port):
    from src.terrain_metrics import analyze_local_terrain
    status, data, _ = _request(port, "POST", "/api/science/terrain",
                               {"raster_id": "lola_site04", "row": 1600, "col": 1599,
                                "radius_pixels": 10})
    assert status == 200
    direct = asdict(analyze_local_terrain(DEM, 1600, 1599, 10))
    direct["raster_path"] = DEM_REL
    expected = json.loads(json.dumps(science_api._clean(direct)))
    assert _strip(data["result"]) == _strip(expected)


@needs_dem
@pytest.mark.parametrize("body, fragment", [
    ({"row": 99999, "col": 1}, "fuori dal raster"),
    ({"row": -1, "col": 1}, "fuori intervallo"),
    ({"row": 1.5, "col": 1}, "intero"),
    ({"row": True, "col": 1}, "intero"),
    ({"row": 10, "col": 10, "radius_pixels": 9999}, "fuori intervallo"),
])
def test_terrain_invalid_input(port, body, fragment):
    status, data, _ = _request(port, "POST", "/api/science/terrain",
                               {"raster_id": "lola_site04", **body})
    assert status == 400 and fragment in data["error"]


# --- Orizzonte -------------------------------------------------------------- #
@needs_dem
def test_horizon_matches_module(port, tmp_path):
    from src.horizon_analysis import calculate_and_write_horizon
    params = dict(row=1600, col=1599, observer_height_m=1.0, azimuth_step_deg=15.0,
                  max_distance_m=1000.0)
    status, data, _ = _request(port, "POST", "/api/science/horizon",
                               {"raster_id": "lola_site04", **params})
    assert status == 200
    direct = json.loads(Path(calculate_and_write_horizon(
        dem_path=DEM, output_path=tmp_path / "h.json", **params)).read_text())
    for d in (direct, data["result"]):
        d.pop("generated_utc"); d.pop("source_dem")
    assert data["result"] == direct
    assert len(direct["samples"]) == 24


@needs_dem
def test_horizon_limits(port):
    status, data, _ = _request(port, "POST", "/api/science/horizon",
                               {"raster_id": "lola_site04", "row": 1600, "col": 1599,
                                "max_distance_m": 1e9})
    assert status == 400 and "fuori intervallo" in data["error"]


# --- Percorso rover + energia ---------------------------------------------- #
@needs_dem
def test_rover_plan_matches_orchestrator_baseline(port):
    status, data, _ = _request(port, "POST", "/api/science/rover-plan",
                               {"raster_id": "lola_site04", **EXAMPLE_ROVER})
    assert status == 200
    plan = data["result"]["plan"]
    assert plan["distance_m"] == pytest.approx(133.99494936611666, abs=0)
    assert plan["estimated_energy_wh"] == pytest.approx(2.6798989873223333, abs=0)
    assert plan["max_slope_deg"] == pytest.approx(19.799291107416934, abs=0)
    assert plan["cells_expanded"] == 558 and len(plan["path_rc"]) == 22
    assert data["result"]["energy_assessment"] is None
    assert any("parametri reali" in n for n in data["notes"])


@needs_dem
def test_rover_energy_requires_real_parameters(port):
    status, data, _ = _request(port, "POST", "/api/science/rover-plan",
                               {"raster_id": "lola_site04", **EXAMPLE_ROVER,
                                "energy": {"mass_kg": 50.0}})
    assert status == 400 and "mancanti" in data["error"]


@needs_dem
def test_rover_energy_matches_module_from_external_cwd(port, tmp_path, monkeypatch):
    from src.rover_energy import estimate_route_energy
    monkeypatch.chdir(tmp_path)  # F2: nessuna dipendenza dalla cwd
    status, data, _ = _request(port, "POST", "/api/science/rover-plan",
                               {"raster_id": "lola_site04", **EXAMPLE_ROVER,
                                "energy": ROVER_PARAMS})
    assert status == 200, data
    energy = data["result"]["energy_assessment"]
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({**data["result"]["plan"], "dem_path": str(DEM)}))
    direct = estimate_route_energy(plan_file, output_path=tmp_path / "e.json", **ROVER_PARAMS)
    assert energy["energy_wh"] == direct["energy_wh"]
    assert energy["distance_m"] == direct["distance_m"]
    assert energy["dem_path"] == DEM_REL
    # nulla scritto nella cwd oltre ai file del confronto diretto
    assert sorted(x.name for x in tmp_path.iterdir()) == ["e.json", "plan.json"]


@needs_dem
@pytest.mark.parametrize("body, code", [
    ({"raster_id": "lroc_nac_sr12", **EXAMPLE_ROVER}, 400),
    ({"raster_id": "lola_site04", "start_rc": [1], "goal_rc": [2, 2]}, 400),
    ({"raster_id": "lola_site04", "start_rc": [0, 0], "goal_rc": [99999, 0]}, 400),
])
def test_rover_invalid(port, body, code):
    assert _request(port, "POST", "/api/science/rover-plan", body)[0] == code


# --- Confronto siti (rete) ------------------------------------------------- #
def test_site_comparison_offline_reports_errors_without_values(port, monkeypatch):
    import src.site_comparison as sc
    from src.astronomy import AstronomyError

    def offline(*args, **kwargs):
        raise AstronomyError("Horizons request failed: rete non disponibile (test)")
    monkeypatch.setattr(sc, "query_observations", offline)
    status, data, _ = _request(port, "POST", "/api/science/site-comparison",
                               {"start_utc": "2026-11-01T00:00:00+00:00", "hours": 12})
    assert status == 200
    sites = data["result"]["sites"]
    assert len(sites) == 3
    for site in sites:
        assert "rete non disponibile" in site["error"]
        assert site["matched_samples"] == 0
    assert any("rete" in n for n in data["notes"])


@pytest.mark.parametrize("body", [{}, {"start_utc": "ieri"}, {"start_utc": "2026-11-01", "hours": 999}])
def test_site_comparison_invalid(port, body):
    assert _request(port, "POST", "/api/science/site-comparison", body)[0] == 400
