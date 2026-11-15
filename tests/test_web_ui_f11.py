"""Test F11: rivalidazione HTTP dei file statici (ETag/304) e ranking delle finestre."""
import http.client
import importlib.util
from pathlib import Path
from threading import Thread

import pytest

from src.mission_planning import find_operational_windows
from src.mission_planner import MissionConfig, rank_operational_windows

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "src" / "ui_web" / "app.py"
GLB = "/data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb"


def _load_app():
    spec = importlib.util.spec_from_file_location("lunar_web_ui_app_f11", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


app = _load_app()


@pytest.fixture(scope="module")
def server():
    srv = app.create_server("127.0.0.1", 0)
    thread = Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def _request(port, path, method="GET", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    conn.request(method, path, headers=headers or {})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp, body


@pytest.mark.parametrize("path", ["/", "/ui/tokens.css", GLB])
def test_static_has_validators_and_revalidates(server, path):
    head, _ = _request(server, path, "HEAD")
    assert head.status == 200
    etag = head.getheader("ETag")
    assert etag and etag.startswith('W/"')
    assert head.getheader("Last-Modified")
    assert head.getheader("Cache-Control") == "no-cache"
    resp, body = _request(server, path, "GET", {"If-None-Match": etag})
    assert resp.status == 304
    assert body == b""


def test_stale_etag_returns_full_body(server):
    resp, body = _request(server, "/ui/tokens.css", "GET", {"If-None-Match": 'W/"0-0"'})
    assert resp.status == 200
    assert body


def test_api_stays_no_store(server):
    resp, _ = _request(server, "/api/sites")
    assert resp.getheader("Cache-Control") == "no-store"
    assert resp.getheader("ETag") is None


def test_window_ranking_matches_mission_planner():
    sun = [1, 10, 20, 30, 2, 1, 40, 45, 1]
    earth = [10, 10, 10, 10, 10, 10, 30, 30, 10]
    windows = find_operational_windows(sun, earth)
    payload = [{"start_index": w.start_index} for w in windows]
    app.attach_window_ranking(windows, payload, sun, earth)
    expected = rank_operational_windows(windows, sun, earth, MissionConfig(site="", start_date_utc=""))
    assert len(windows) == 2
    for item in expected:
        ranking = next(p["ranking"] for p in payload if p["start_index"] == item["start_index"])
        assert ranking["rank"] == item["rank"]
        assert ranking["score"] == item["score"]
        assert "not flight-qualified" in ranking["score_method"]
    assert sorted(p["ranking"]["rank"] for p in payload) == [1, 2]


def test_window_ranking_empty():
    assert app.attach_window_ranking([], [], [], []) == []


def test_index_has_ranking_column():
    html = (PROJECT_ROOT / "src" / "ui_web" / "index.html").read_text(encoding="utf-8")
    assert "Rank · punteggio" in html
