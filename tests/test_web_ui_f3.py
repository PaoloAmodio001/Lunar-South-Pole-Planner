"""Test F3 — endpoint della specifica originale (alias sottili su F1)."""
import pytest

from src.astronomy import SITES
from src.ui_web.mission_runner import MissionManager
from tests.test_web_ui_mission import (  # riuso fixture e helper F1
    MINIMAL, FAILING_STEP, app, delayed_orchestrator, _request,
)
from threading import Thread


@pytest.fixture
def server(tmp_path, monkeypatch):
    mgr = MissionManager(runs_dir=tmp_path / "runs", command_factory=delayed_orchestrator(1.0))
    monkeypatch.setattr(app, "MISSIONS", mgr)
    srv = app.create_server("127.0.0.1", 0)
    Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], mgr
    mgr.shutdown()
    srv.shutdown()
    srv.server_close()


def test_sites_from_astronomy(server):
    port, _ = server
    status, data, _ = _request(port, "GET", "/api/sites")
    assert status == 200 and data["source"] == "src.astronomy.SITES"
    assert {s["name"]: (s["latitude_deg"], s["longitude_east_deg"])
            for s in data["sites"]} == {k: tuple(v) for k, v in SITES.items()}


def test_status_and_reports_empty(server):
    port, _ = server
    assert _request(port, "GET", "/api/mission/status")[1] == {
        "status": "ok", "running_id": None, "run": None}
    assert _request(port, "GET", "/api/mission/reports")[1] == {"status": "ok", "reports": []}


def test_run_alias_lifecycle(server):
    port, mgr = server
    status, data, _ = _request(port, "POST", "/api/mission/run", {"config": MINIMAL})
    assert status == 202
    run_id = data["run_id"]

    status, data, _ = _request(port, "GET", "/api/mission/status")
    assert status == 200 and data["running_id"] == run_id
    assert data["run"]["state"] == "running" and "%" not in data["run"]["progress"]

    # duplicato bloccato anche tramite alias
    status, data, _ = _request(port, "POST", "/api/mission/run", {"config": MINIMAL})
    assert status == 409 and data["running_id"] == run_id

    mgr.wait(run_id, timeout=60)
    status, data, _ = _request(port, "GET", f"/api/mission/status?id={run_id}")
    assert data["run"]["state"] == "completed"
    assert data["run"]["result"]["engine_status"] == "completed"

    status, data, _ = _request(port, "GET", "/api/mission/reports")
    assert [r["run_id"] for r in data["reports"]] == [run_id]
    report = data["reports"][0]
    assert report["engine_status"] == "completed"
    status, body, _ = _request(port, "GET", report["report_url"])
    assert status == 200 and body["status"] == "completed"


def test_failure_visible_through_status(server):
    port, mgr = server
    run_id = _request(port, "POST", "/api/mission/run", {"config": FAILING_STEP})[1]["run_id"]
    mgr.wait(run_id, timeout=60)
    run = _request(port, "GET", "/api/mission/status")[1]["run"]
    assert run["state"] == "completed_with_errors"
    steps = run["result"]["steps"]
    assert steps[0]["status"] == "failed" and "FileNotFoundError" in steps[0]["error"]


@pytest.mark.parametrize("path", [
    "/api/mission/status?id=../../etc/passwd",
    "/api/mission/status?id=" + "0" * 32,
])
def test_status_rejects_bad_ids(server, path):
    port, _ = server
    assert _request(port, "GET", path)[0] == 404


def test_run_alias_rejects_invalid_config(server):
    port, mgr = server
    status, data, _ = _request(port, "POST", "/api/mission/run",
                               {"config": {"site_selection": {"dem_path": "/etc/passwd"}}})
    assert status == 400 and mgr.running_id is None


def test_panel_has_reports_list(server):
    port, _ = server
    status, body, _ = _request(port, "GET", "/")
    assert b'id="missionReports"' in body
    status, body, _ = _request(port, "GET", "/mission.js")
    assert b"/api/mission/reports" in body
