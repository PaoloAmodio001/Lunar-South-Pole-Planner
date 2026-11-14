"""Test F2 — indipendenza del flusso di missione dalla directory di avvio."""
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

import src.paths as paths
from src.paths import PROJECT_ROOT, resolve_project_path
from src.mission_orchestrator import (
    resolve_config_file,
    resolve_config_paths,
    run_mission_workflow,
    validate_mission_site_identity,
)
from src.mission_report import build_mission_report, write_mission_report

REAL_DEM_REL = "data/terrain/official-lola/Site04_final_adj_5mpp_surf.tif"
needs_real = pytest.mark.skipif(not (PROJECT_ROOT / REAL_DEM_REL).is_file(),
                                reason="DEM Site04 non disponibile")
ORCHESTRATOR = PROJECT_ROOT / "src" / "mission_orchestrator.py"
RASTER_SECTION = "terrain"


# --- PROJECT_ROOT e risoluzione elementare ---------------------------------- #
def test_project_root_is_repository_root():
    assert (PROJECT_ROOT / "src" / "mission_orchestrator.py").is_file()
    assert PROJECT_ROOT.is_absolute()


def test_resolve_relative_absolute_none(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_project_path("data/x.tif") == PROJECT_ROOT / "data/x.tif"
    assert resolve_project_path(Path("reports")) == PROJECT_ROOT / "reports"
    absolute = tmp_path / "abs.tif"
    assert resolve_project_path(str(absolute)) == absolute
    assert resolve_project_path(None) is None
    assert resolve_project_path("~/x").is_absolute()
    assert resolve_project_path("a", root=tmp_path) == tmp_path / "a"


# --- Configurazione --------------------------------------------------------- #
def test_resolve_config_paths_only_path_keys(tmp_path):
    absolute = str(tmp_path / "dem.tif")
    config = {
        "output_dir": "reports/mission",
        "site_selection": {"dem_path": "data/a.tif", "report_name": "site_ranking.json",
                           "lola_density_path": "data/d.tif", "max_slope_deg": 15.0},
        "rover_path": {"dem_path": absolute, "start_rc": [1, 2]},
        "energy": {"enabled": False, "plan_json": "reports/rover_plan.json"},
        "journal": {"enabled": False, "path": "reports/mission/events.jsonl",
                    "node_id": "n"},
        "mission_report": {"site_name": "Shackleton"},
        "illumination": {"horizon_json": "reports/mission/horizon_profile.json",
                         "grid_azimuth_offset_deg": "from_horizon_profile"},
        "lunar_geometry": {"dem_path": None},
    }
    original = json.loads(json.dumps(config))
    resolved = resolve_config_paths(config)

    assert config == original  # nessuna mutazione dell'input
    assert resolved["output_dir"] == str(PROJECT_ROOT / "reports/mission")
    assert resolved["site_selection"]["dem_path"] == str(PROJECT_ROOT / "data/a.tif")
    assert resolved["site_selection"]["lola_density_path"] == str(PROJECT_ROOT / "data/d.tif")
    assert resolved["rover_path"]["dem_path"] == absolute  # assoluto invariato
    assert resolved["energy"]["plan_json"] == str(PROJECT_ROOT / "reports/rover_plan.json")
    assert resolved["journal"]["path"] == str(PROJECT_ROOT / "reports/mission/events.jsonl")
    assert resolved["illumination"]["horizon_json"] == str(
        PROJECT_ROOT / "reports/mission/horizon_profile.json")
    # valori non-percorso invariati
    assert resolved["site_selection"]["report_name"] == "site_ranking.json"
    assert resolved["site_selection"]["max_slope_deg"] == 15.0
    assert resolved["rover_path"]["start_rc"] == [1, 2]
    assert resolved["mission_report"] == {"site_name": "Shackleton"}
    assert resolved["illumination"]["grid_azimuth_offset_deg"] == "from_horizon_profile"
    assert resolved["lunar_geometry"]["dem_path"] is None


def test_resolve_config_file_cwd_first_then_project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "local.json").write_text("{}")
    assert resolve_config_file("local.json") == tmp_path / "local.json"
    # non presente nella cwd -> relativo a PROJECT_ROOT
    assert resolve_config_file("mission_config.example.json") == \
        PROJECT_ROOT / "mission_config.example.json"
    absolute = tmp_path / "abs.json"
    assert resolve_config_file(str(absolute)) == absolute


# --- Workflow da directory esterna ----------------------------------------- #
def _write_config(directory, config):
    path = directory / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def test_workflow_from_external_cwd_absolute_output(tmp_path, monkeypatch):
    work = tmp_path / "elsewhere"
    work.mkdir()
    out = tmp_path / "out"
    config_path = _write_config(tmp_path, {"output_dir": str(out),
                                           "mission_report": {"enabled": False}})
    monkeypatch.chdir(work)
    report = run_mission_workflow(config_path)
    assert report["status"] == "completed"
    assert (out / "mission_report.json").is_file()
    assert list(work.iterdir()) == []  # nulla scritto nella cwd


def test_workflow_relative_output_dir_anchored_to_project_root(tmp_path, monkeypatch):
    rel = f"reports/_f2_test_{uuid.uuid4().hex}"
    target = PROJECT_ROOT / rel
    config_path = _write_config(tmp_path, {"output_dir": rel,
                                           "mission_report": {"enabled": False}})
    monkeypatch.chdir(tmp_path)
    try:
        report = run_mission_workflow(config_path)
        assert Path(report["report_path"]) == target / "mission_report.json"
        assert (target / "mission_report.json").is_file()
        assert not (tmp_path / "reports").exists()
    finally:
        shutil.rmtree(target, ignore_errors=True)


def test_missing_relative_input_reported_with_project_path(tmp_path, monkeypatch):
    # Un file con lo stesso nome relativo esiste nella cwd: NON deve essere usato.
    work = tmp_path / "elsewhere"
    (work / "data").mkdir(parents=True)
    (work / "data" / "__f2_missing__.tif").write_bytes(b"not a raster")
    config_path = _write_config(tmp_path, {
        "output_dir": str(tmp_path / "out"),
        "mission_report": {"enabled": False},
        "site_selection": {"dem_path": "data/__f2_missing__.tif"},
    })
    monkeypatch.chdir(work)
    report = run_mission_workflow(config_path)
    step = report["steps"]["site_selection"]
    assert report["status"] == "completed_with_errors"
    assert step["status"] == "failed"
    assert step["error_type"] == "FileNotFoundError"
    assert str(PROJECT_ROOT / "data/__f2_missing__.tif") in step["error"]
    assert str(work) not in step["error"]


def test_missing_config_file_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        run_mission_workflow("__f2_no_such_config__.json")


@needs_real
def test_site_identity_relative_raster_from_external_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    summary = validate_mission_site_identity({
        "mission_report": {"site_name": "Shackleton"},
        "site_selection": {"dem_path": REAL_DEM_REL},
    })
    assert summary["status"] == "validated"
    assert summary["rasters_checked"][0]["raster_path"] == str(PROJECT_ROOT / REAL_DEM_REL)


# --- mission_report --------------------------------------------------------- #
def test_mission_report_defaults_use_project_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # cwd senza dati: i raster vanno cercati in PROJECT_ROOT
    report = build_mission_report(site_name="Shackleton", planning_date="2026-10-25",
                                  horizon_hours=48)
    lola = report[RASTER_SECTION]["rasters"]["LOLA"]
    assert lola["path"] == REAL_DEM_REL
    assert lola["exists"] is (PROJECT_ROOT / REAL_DEM_REL).is_file()


def test_write_mission_report_relative_dir(tmp_path, monkeypatch):
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    work = tmp_path / "cwd"
    work.mkdir()
    monkeypatch.setattr(paths, "PROJECT_ROOT", fake_root)
    monkeypatch.chdir(work)
    report = build_mission_report(site_name="Shackleton", planning_date="2026-10-25",
                                  horizon_hours=48, project_root=fake_root)
    json_path, md_path = write_mission_report(report, "out")
    assert json_path == fake_root / "out" / "mission_status_report.json"
    assert md_path.is_file() and not (work / "out").exists()


# --- CLI da /tmp e directory esterne --------------------------------------- #
def _run_cli(args, cwd, env_extra=None):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, *args], cwd=cwd, env=env,
                          capture_output=True, text=True, timeout=300)


def test_cli_script_from_external_cwd(tmp_path):
    config_path = _write_config(tmp_path, {"output_dir": str(tmp_path / "out"),
                                           "mission_report": {"enabled": False}})
    result = _run_cli([str(ORCHESTRATOR), str(config_path)], cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "completed"
    assert (tmp_path / "out" / "mission_report.json").is_file()


def test_cli_module_with_pythonpath_from_external_cwd(tmp_path):
    config_path = _write_config(tmp_path, {"output_dir": str(tmp_path / "out"),
                                           "mission_report": {"enabled": False}})
    result = _run_cli(["-m", "src.mission_orchestrator", str(config_path)],
                      cwd=tmp_path, env_extra={"PYTHONPATH": str(PROJECT_ROOT)})
    assert result.returncode == 0, result.stdout + result.stderr


@needs_real
def test_cli_example_like_config_from_tmp(tmp_path):
    """Config con percorsi relativi del progetto, avviata da una cwd esterna."""
    config = json.loads((PROJECT_ROOT / "mission_config.example.json").read_text())
    config["output_dir"] = str(tmp_path / "out")
    config_path = _write_config(tmp_path, config)
    result = _run_cli([str(ORCHESTRATOR), str(config_path)], cwd=tmp_path)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed_preliminary"
    assert all(s["status"] == "success" for s in payload["steps"].values())
