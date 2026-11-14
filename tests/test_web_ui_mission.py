"""Test F1 — integrazione Web UI → Mission Orchestrator.

Le esecuzioni usano il VERO orchestratore (``python -m src.mission_orchestrator``)
con configurazioni sintetiche minime; nessun dato scientifico viene scaricato.
"""
import http.client
import importlib.util
import json
import sys
import time
from pathlib import Path
from threading import Thread

import pytest

from src.ui_web import mission_runner
from src.ui_web.mission_runner import (
    ConfigError, MissionBusyError, MissionManager, validate_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "src" / "ui_web" / "app.py"
EXAMPLE = PROJECT_ROOT / "mission_config.example.json"
EXAMPLE_DATA = PROJECT_ROOT / "data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif"

MINIMAL = {"mission_report": {"enabled": False}}
FAILING_STEP = {"mission_report": {"enabled": False},
                "site_selection": {"dem_path": "data/__f1_test_missing__.tif"}}


def _load_app():
    spec = importlib.util.spec_from_file_location("lunar_web_ui_app_f1", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app = _load_app()


def delayed_orchestrator(delay_s):
    """Comando che esegue il vero orchestratore dopo un ritardo (test non bloccante)."""
    def factory(config_path):
        code = ("import runpy, sys, time; time.sleep(%r); "
                "sys.argv = ['mission_orchestrator', %r]; "
                "runpy.run_module('src.mission_orchestrator', run_name='__main__')"
                % (delay_s, str(config_path)))
        return [sys.executable, "-c", code]
    return factory


@pytest.fixture
def manager(tmp_path):
    mgr = MissionManager(runs_dir=tmp_path / "runs")
    yield mgr
    mgr.shutdown()


# 1 / 7 — Validazione e configurazioni non valide --------------------------- #
def test_minimal_config_is_valid():
    result = validate_config(MINIMAL)
    assert result["valid"], result["errors"]


@pytest.mark.parametrize("config, fragment", [
    ([], "oggetto JSON"),
    ({"site_selection": "x"}, "deve essere un oggetto"),
    ({"site_selection": {"dem_path": "/etc/passwd"}}, "relativi"),
    ({"site_selection": {"dem_path": "data/../../etc/passwd"}}, "'..'"),
    ({"site_selection": {"dem_path": "src/mission_orchestrator.py"}}, "data/"),
    ({"site_selection": {"dem_path": "~/x.tif"}}, "relativi"),
    ({"site_selection": {"dem_path": 42}}, "non testuale"),
    ({"site_selection": {"report_name": "../escape.json"}}, "nome di file"),
    ({"site_selection": {"report_name": ".hidden"}}, "nome di file"),
    ({"journal": {"enabled": True, "path": "data/events.jsonl"}}, "reports/"),
    ({"journal": {"enabled": True, "path": "/tmp/events.jsonl"}}, "relativi"),
    ({"x": float("nan")}, "JSON standard"),
])
def test_invalid_configs_rejected(config, fragment):
    result = validate_config(config, check_site_identity=False)
    assert not result["valid"]
    assert any(fragment in e for e in result["errors"]), result["errors"]


def test_missing_input_is_warning_not_error():
    result = validate_config(FAILING_STEP)
    assert result["valid"]
    assert any("file non trovato" in w for w in result["warnings"])


def test_oversized_config_rejected():
    big = {"fleet": {"enabled": False, "tasks": ["x" * 1024] * 300}}
    result = validate_config(big, check_site_identity=False)
    assert not result["valid"] and "troppo grande" in result["errors"][0]


def test_site_identity_conflict_rejected():
    config = {"mission_report": {"site_name": "Shackleton"},
              "local_site_analysis": {"enabled": True, "site_name": "Nobile"}}
    result = validate_config(config)
    assert not result["valid"]
    assert any("identità del sito" in e for e in result["errors"])


@pytest.mark.skipif(not EXAMPLE_DATA.is_file(), reason="Dati locali assenti")
def test_example_config_valid_with_site_identity():
    result = validate_config(json.loads(EXAMPLE.read_text(encoding="utf-8")))
    assert result["valid"], result["errors"]
    assert result["site_identity"]["status"] == "validated"


def test_catalog_does_not_accept_paths():
    with pytest.raises(ConfigError):
        mission_runner.load_catalog_config("../mission_config.example.json")


# 2 / 4 / 5 — Avvio reale, stato, risultati -------------------------------- #
def test_real_orchestrator_completed(manager):
    job = manager.start(MINIMAL, "test")
    assert job["state"] == "running"
    final = manager.wait(job["id"], timeout=60)
    assert final["state"] == "completed"
    assert final["engine_status"] == "completed"
    assert final["exit_code"] == 0
    report = manager.read_report(job["id"])
    assert report["schema"] == "lunar-mission-orchestration/1.0"
    payload = manager.status_payload(job["id"])
    assert payload["result"]["engine_run_id"] == report["run_id"]
    assert payload["result"]["site_ranking"]["available"] is False
    names = {n["name"] for n in payload["result"]["not_executed"]}
    assert "mission_report" in names  # disabilitata: mostrata come non eseguita
    # config effettiva salvata con output_dir dedicato
    saved = json.loads((manager.runs_dir / job["id"] / "config.json").read_text())
    assert saved["output_dir"].endswith(f"{job['id']}/output")
    assert manager.running_id is None


def test_real_orchestrator_completed_with_errors(manager):
    job = manager.start(FAILING_STEP, "test")
    final = manager.wait(job["id"], timeout=60)
    assert final["state"] == "completed_with_errors"
    assert final["exit_code"] == 1
    steps = manager.status_payload(job["id"])["result"]["steps"]
    assert steps == [{"name": "site_selection", "status": "failed",
                      "error": "FileNotFoundError: DEM non trovato: "
                               f"{PROJECT_ROOT / 'data/__f1_test_missing__.tif'}"}]
    ranking = manager.status_payload(job["id"])["result"]["site_ranking"]
    assert ranking["available"] is False and "fallito" in ranking["reason"]


# 6 — Eccezioni ------------------------------------------------------------- #
def test_engine_crash_reported_as_failed(tmp_path):
    def crash(_config_path):
        return [sys.executable, "-c", "raise RuntimeError('motore esploso')"]
    mgr = MissionManager(runs_dir=tmp_path / "runs", command_factory=crash)
    job = mgr.start(MINIMAL, "test")
    final = mgr.wait(job["id"], timeout=30)
    assert final["state"] == "failed"
    assert final["engine_status"] is None
    payload = mgr.status_payload(job["id"])
    assert "motore esploso" in payload["stderr_tail"]
    assert payload["result"] is None
    assert mgr.running_id is None  # il lock viene rilasciato


def test_orchestrator_exception_reported_as_failed(tmp_path):
    """Eccezione sollevata dal vero orchestratore (config illeggibile) → failed."""
    def broken_config(config_path):
        config_path.write_text("[]", encoding="utf-8")
        return [sys.executable, "-m", "src.mission_orchestrator", str(config_path)]
    mgr = MissionManager(runs_dir=tmp_path / "runs", command_factory=broken_config)
    final = mgr.wait(mgr.start(MINIMAL, "test")["id"], timeout=60)
    assert final["state"] == "failed" and final["exit_code"] == 2
    assert "Errore di configurazione" in final["failure_reason"]


def test_spawn_failure_releases_lock(tmp_path):
    def missing(_config_path):
        return [str(tmp_path / "no-such-binary")]
    mgr = MissionManager(runs_dir=tmp_path / "runs", command_factory=missing)
    with pytest.raises(OSError):
        mgr.start(MINIMAL, "test")
    assert mgr.running_id is None


def test_invalid_config_not_started(manager):
    with pytest.raises(ConfigError):
        manager.start({"site_selection": {"dem_path": "/etc/passwd"}}, "test")
    assert manager.running_id is None
    assert manager.list_runs() == []


def test_interrupted_run_reported_as_failed(tmp_path):
    runs = tmp_path / "runs"
    run_id = "a" * 32
    (runs / run_id).mkdir(parents=True)
    (runs / run_id / "job.json").write_text(json.dumps(
        {"id": run_id, "state": "running", "created_utc": "x"}))
    job = MissionManager(runs_dir=runs).get(run_id)
    assert job["state"] == "failed" and "riavviato" in job["failure_reason"]


# 8 — Avvii duplicati ------------------------------------------------------- #
def test_duplicate_start_rejected(tmp_path):
    mgr = MissionManager(runs_dir=tmp_path / "runs", command_factory=delayed_orchestrator(1.0))
    job = mgr.start(MINIMAL, "test")
    with pytest.raises(MissionBusyError) as info:
        mgr.start(MINIMAL, "test")
    assert info.value.running_id == job["id"]
    assert mgr.wait(job["id"], timeout=60)["state"] == "completed"
    second = mgr.start(MINIMAL, "test")  # dopo il termine è di nuovo possibile
    assert mgr.wait(second["id"], timeout=60)["state"] == "completed"


# 9 — Accesso controllato ai report ---------------------------------------- #
def test_artifact_outside_run_dir_not_served(manager):
    job = manager.start(MINIMAL, "test")
    manager.wait(job["id"], timeout=60)
    report_path = manager.runs_dir / job["id"] / "output" / "mission_report.json"
    report = json.loads(report_path.read_text())
    report["artifacts"] = {
        "escape": str(PROJECT_ROOT / "mission_config.example.json"),
        "relative_escape": "../../../../mission_config.example.json",
        "inside": str(report_path),
    }
    report_path.write_text(json.dumps(report))
    assert manager.artifact_file(job["id"], "escape") is None
    assert manager.artifact_file(job["id"], "relative_escape") is None
    assert manager.artifact_file(job["id"], "missing") is None
    assert manager.artifact_file(job["id"], "inside") == report_path.resolve()
    arts = {a["key"]: a for a in manager.status_payload(job["id"])["result"]["artifacts"]}
    assert arts["escape"]["downloadable"] is False and arts["escape"]["url"] is None


@pytest.mark.parametrize("bad", ["../x", "", "A" * 32, "0" * 31, "0" * 32 + "/.."])
def test_run_id_format_enforced(manager, bad):
    with pytest.raises(KeyError):
        manager.get(bad)


# 3 / 9 / 10 — HTTP: server non bloccato, endpoint, compatibilità F0 -------- #
@pytest.fixture
def http_server(tmp_path, monkeypatch):
    mgr = MissionManager(runs_dir=tmp_path / "runs", command_factory=delayed_orchestrator(1.5))
    monkeypatch.setattr(app, "MISSIONS", mgr)
    srv = app.create_server("127.0.0.1", 0)
    Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1], mgr
    mgr.shutdown()
    srv.shutdown()
    srv.server_close()


def _request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Content-Type": "application/json"} if body is not None else {}
    conn.request(method, path, body=json.dumps(body) if body is not None else None,
                 headers=headers)
    resp = conn.getresponse()
    raw = resp.read()
    conn.close()
    try:
        data = json.loads(raw)
    except ValueError:
        data = raw
    return resp.status, data, resp


def test_http_mission_lifecycle(http_server):
    port, mgr = http_server
    status, data, _ = _request(port, "POST", "/api/mission/validate", {"config": MINIMAL})
    assert status == 200 and data["validation"]["valid"]

    status, data, _ = _request(port, "POST", "/api/mission/runs",
                               {"config": MINIMAL, "filename": "<script>.json"})
    assert status == 202
    run_id = data["run_id"]

    # Il server risponde mentre la missione è in esecuzione (non bloccante).
    t0 = time.monotonic()
    status, data, _ = _request(port, "GET", f"/api/mission/runs/{run_id}")
    assert status == 200 and data["run"]["state"] == "running"
    assert "non espone avanzamento" in data["run"]["progress"]
    assert "%" not in data["run"]["progress"]
    assert data["run"]["config_label"] == "upload: _script_.json"
    status, _, _ = _request(port, "GET", "/main.js")
    assert status == 200
    assert time.monotonic() - t0 < 1.0

    status, data, _ = _request(port, "POST", "/api/mission/runs", {"config": MINIMAL})
    assert status == 409 and data["running_id"] == run_id

    status, data, _ = _request(port, "GET", "/api/mission/runs")
    assert data["running_id"] == run_id

    mgr.wait(run_id, timeout=60)
    status, data, _ = _request(port, "GET", f"/api/mission/runs/{run_id}")
    assert data["run"]["state"] == "completed"
    assert data["run"]["result"]["engine_status"] == "completed"
    assert "pid" not in data["run"]

    status, report, resp = _request(port, "GET", f"/api/mission/runs/{run_id}/report")
    assert status == 200 and report["status"] == "completed"
    assert resp.getheader("Content-Type").startswith("application/json")


@pytest.mark.parametrize("body, code", [
    ({"config": {"site_selection": {"dem_path": "/etc/passwd"}}}, 400),
    ({"config_id": "../../etc/passwd"}, 400),
    ({"config_id": "nope"}, 400),
    ({}, 400),
    ({"config": []}, 400),
])
def test_http_invalid_start(http_server, body, code):
    port, mgr = http_server
    status, data, _ = _request(port, "POST", "/api/mission/runs", body)
    assert status == code and data["status"] == "error"
    assert mgr.running_id is None


@pytest.mark.parametrize("path", [
    "/api/mission/runs/../../mission_config.example.json",
    "/api/mission/runs/" + "0" * 32,
    "/api/mission/runs/" + "0" * 32 + "/report",
    "/api/mission/runs/" + "0" * 32 + "/artifacts/..",
    "/api/mission/runs/" + "0" * 32 + "/artifacts/a%2F..%2F..",
    "/api/mission/configs/..%2F..%2Fetc",
    "/api/mission/anything",
    "/reports/web_runs/",
    "/src/ui_web/mission_runner.py",
])
def test_http_unauthorized_mission_paths(http_server, path):
    port, _ = http_server
    status, _, _ = _request(port, "GET", path)
    assert status == 404, path


def test_http_configs_catalog(http_server):
    port, _ = http_server
    status, data, _ = _request(port, "GET", "/api/mission/configs")
    assert status == 200
    assert [c["id"] for c in data["configs"]] == ["example"]
    assert "path" not in data["configs"][0]
    if EXAMPLE.is_file():
        status, data, _ = _request(port, "GET", "/api/mission/configs/example")
        assert status == 200 and data["config"] == json.loads(EXAMPLE.read_text())


def test_ui_assets_served(http_server):
    port, _ = http_server
    status, body, resp = _request(port, "GET", "/mission.js")
    assert status == 200 and resp.getheader("Content-Type").startswith("text/javascript")
    status, body, _ = _request(port, "GET", "/")
    assert b'id="missionEngineSection"' in body and b'src="/mission.js"' in body


# Prova end-to-end con configurazione di esempio e dati locali -------------- #
@pytest.mark.skipif(not EXAMPLE_DATA.is_file(), reason="Dati locali assenti")
def test_e2e_example_config(manager):
    config = mission_runner.load_catalog_config("example")
    job = manager.start(config, "example")
    final = manager.wait(job["id"], timeout=300)
    assert final["state"] in ("completed", "completed_with_errors")
    result = manager.status_payload(job["id"])["result"]
    assert result["engine_status"] == final["engine_status"]
    ranking = result["site_ranking"]
    assert ranking["available"]
    assert ranking["lola_quality_affects_score"] is False
    scores = [c["score_0_100"] for c in ranking["top_candidates"]]
    assert scores == sorted(scores, reverse=True)
