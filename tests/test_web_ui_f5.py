"""Test F5 — consolidamento architetturale (fonti uniche, duplicazioni rimosse)."""
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread

import pytest

import src.paths as paths
from src.astronomy import SITES
from src.mission_orchestrator import CONFIG_PATH_KEYS
from src.ui_web import mission_runner, science_api
from tests.test_web_ui_mission import app, _request

UI = paths.PROJECT_ROOT / "src" / "ui_web"
MAIN_JS = (UI / "main.js").read_text(encoding="utf-8")
INDEX = (UI / "index.html").read_text(encoding="utf-8")
DEM = paths.PROJECT_ROOT / "data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif"


# --- Fonte unica per la radice del progetto -------------------------------- #
def test_single_project_root():
    assert mission_runner.PROJECT_ROOT is paths.PROJECT_ROOT
    assert science_api.PROJECT_ROOT is paths.PROJECT_ROOT
    assert app.PROJECT_ROOT is paths.PROJECT_ROOT


# --- Chiavi di percorso: definite una sola volta nel motore ------------------ #
def test_path_keys_shared_with_engine():
    assert mission_runner.READ_PATH_KEYS is CONFIG_PATH_KEYS
    assert "plan_json" in mission_runner.READ_PATH_KEYS


@pytest.mark.parametrize("value", ["/etc/passwd", "../outside.json", "src/secret.json"])
def test_plan_json_now_validated(value):
    result = mission_runner.validate_config(
        {"energy": {"enabled": True, "plan_json": value}}, check_site_identity=False)
    assert not result["valid"]
    assert any(e.startswith("energy.plan_json") for e in result["errors"])


@pytest.mark.skipif(not DEM.is_file(), reason="DEM Site04 non disponibile")
def test_preflight_uses_engine_resolution_from_external_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config = json.loads((paths.PROJECT_ROOT / "mission_config.example.json").read_text())
    result = mission_runner.validate_config(config)
    assert result["valid"], result["errors"]
    assert result["site_identity"]["status"] == "validated"
    # percorsi mostrati relativi al progetto, come prima di F5
    assert result["site_identity"]["rasters_checked"][0]["raster_path"].startswith("data/")


# --- Frontend: duplicazioni rimosse ---------------------------------------- #
def test_frontend_has_no_hardcoded_site_coordinates():
    for lat, lon in SITES.values():
        assert str(lat) not in MAIN_JS and str(lon) not in MAIN_JS
    assert "fetch('/api/sites'" in MAIN_JS


def test_frontend_site_names_match_backend():
    select = re.search(r'<select id="site">(.*?)</select>', INDEX).group(1)
    assert re.findall(r"<option>([^<]+)</option>", select) == list(SITES)


def test_frontend_analytics_fallback_and_dead_code_removed():
    assert "calculateMissionAnalytics" not in MAIN_JS
    assert "drawChart" not in MAIN_JS and "charts()" not in MAIN_JS
    assert "Analytics non forniti dal server" in MAIN_JS


# --- Backend: gli analytics arrivano sempre dal server --------------------- #
class _Obs:
    def __init__(self, t, el, az):
        self.time_utc, self.elevation_deg, self.azimuth_deg = t, el, az


@pytest.fixture
def port(monkeypatch):
    def fake_query(target, lat, lon, start, hours, step):
        base = datetime(2026, 11, 1, tzinfo=timezone.utc)
        el = 8.0 if target == "10" else 6.0
        return [_Obs((base + timedelta(hours=h)).strftime("%Y-%b-%d %H:%M"), el, 90.0)
                for h in range(hours)]
    monkeypatch.setattr(app, "query_observations", fake_query)
    srv = app.create_server("127.0.0.1", 0)
    Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def test_ephemerides_always_include_backend_analytics(port):
    status, data, _ = _request(
        port, "GET", "/api/ephemerides?site=Shackleton&start=2026-11-01T00:00&hours=6")
    assert status == 200
    assert data["analytics"]["schema"] == "lunar-ephemeris-analytics/1.0"


def test_sites_endpoint_is_the_frontend_source(port):
    status, data, _ = _request(port, "GET", "/api/sites")
    assert {s["name"] for s in data["sites"]} == set(SITES)
