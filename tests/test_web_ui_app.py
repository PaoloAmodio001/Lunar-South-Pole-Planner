"""Test F0 — stabilizzazione della Web UI (src/ui_web/app.py)."""
import http.client
import importlib.util
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "src" / "ui_web" / "app.py"


def _load_app():
    spec = importlib.util.spec_from_file_location("lunar_web_ui_app", APP_PATH)
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


def _get(port, path, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request(method, path)
    resp = conn.getresponse()
    body = resp.read() if method == "GET" else b""
    conn.close()
    return resp, body


def test_app_module_does_not_import_pyside6():
    # PySide6 deve essere importato solo dentro _run_desktop (modalità --desktop).
    source = APP_PATH.read_text(encoding="utf-8")
    import_lines = [l for l in source.splitlines()
                    if l.lstrip().startswith(("import PySide6", "from PySide6"))]
    assert import_lines, "import PySide6 atteso nella modalità desktop"
    assert all(l.startswith("        ") for l in import_lines), import_lines


def test_root_serves_index(server):
    resp, body = _get(server, "/")
    assert resp.status == 200
    assert resp.getheader("Content-Type").startswith("text/html")
    assert b'"three": "/vendor/three/build/three.module.js"' in body
    assert b'src="/main.js"' in body


def test_legacy_index_url_redirects(server):
    resp, _ = _get(server, "/src/ui_web/index.html")
    assert resp.status == 302
    assert resp.getheader("Location") == "/"


@pytest.mark.parametrize("path", [
    "/main.js",
    "/vendor/three/build/three.module.js",
    "/vendor/three/build/three.core.js",
    "/vendor/three/examples/jsm/loaders/GLTFLoader.js",
    "/vendor/three/examples/jsm/utils/BufferGeometryUtils.js",
    "/vendor/three/examples/jsm/utils/SkeletonUtils.js",
])
def test_frontend_js_served(server, path):
    resp, body = _get(server, path)
    assert resp.status == 200, path
    assert resp.getheader("Content-Type").startswith("text/javascript")
    assert len(body) > 0


def test_main_js_imports_resolve_to_vendor(server):
    _, body = _get(server, "/main.js")
    text = body.decode("utf-8")
    assert "node_modules" not in text
    assert "from 'three'" in text
    assert "from 'three/addons/loaders/GLTFLoader.js'" in text


@pytest.mark.skipif(
    not (PROJECT_ROOT / "data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb").is_file(),
    reason="Modello GLB non presente",
)
def test_globe_model_available(server):
    resp, _ = _get(server, "/data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb", method="HEAD")
    assert resp.status == 200
    assert resp.getheader("Content-Type") == "model/gltf-binary"


@pytest.mark.parametrize("path", [
    "/src/ui_web/app.py",
    "/src/ui_web/main.js",
    "/src/ui_web/node_modules/three/build/three.module.js",
    "/src/mission_orchestrator.py",
    "/mission_config.example.json",
    "/requirements.txt",
    "/.git/config",
    "/.env",
    "/backups/",
    "/audit-reports/",
    "/audit-reports/lroc-quality-mask-20261114T181357Z.json",
    "/data/",
    "/data/terrain/global/",
    "/vendor/three/",
    "/vendor/three/LICENSE",
    "/vendor/three/../../app.py",
    "/vendor/three/%2e%2e/%2e%2e/app.py",
    "/vendor/three/..%2f..%2fapp.py",
    "/vendor/three/build/../../../app.py",
    "//etc/passwd",
    "/../../etc/passwd",
])
def test_unauthorized_paths_rejected(server, path):
    resp, body = _get(server, path)
    assert resp.status == 404, path
    assert b"Risorsa non trovata" in body


def test_head_on_unauthorized_path_rejected(server):
    resp, _ = _get(server, "/src/ui_web/app.py", method="HEAD")
    assert resp.status == 404


def test_lroc_endpoint(server):
    resp, _ = _get(server, "/api/terrain/lroc-quality")
    expected = 200 if app.find_latest_lroc_report() is not None else 404
    assert resp.status == expected


def test_find_latest_lroc_report_ignores_date_in_name(tmp_path):
    assert app.find_latest_lroc_report(tmp_path) is None
    (tmp_path / "lroc-quality-mask-20250101T000000Z.json").write_text("{}")
    (tmp_path / "lroc-quality-mask-20271231T235959Z.json").write_text("{}")
    (tmp_path / "unrelated-20991231.json").write_text("{}")
    latest = app.find_latest_lroc_report(tmp_path)
    assert latest.name == "lroc-quality-mask-20271231T235959Z.json"


def test_parse_args_defaults_and_env(monkeypatch):
    for var in ("LUNAR_UI_HOST", "LUNAR_UI_PORT", "LUNAR_UI_NO_BROWSER"):
        monkeypatch.delenv(var, raising=False)
    args = app.parse_args([])
    assert (args.host, args.port, args.no_browser, args.desktop) == ("127.0.0.1", 8765, False, False)
    monkeypatch.setenv("LUNAR_UI_PORT", "9123")
    monkeypatch.setenv("LUNAR_UI_NO_BROWSER", "1")
    args = app.parse_args([])
    assert args.port == 9123 and args.no_browser
    assert app.parse_args(["--host", "localhost", "--port", "9000"]).port == 9000
    with pytest.raises(SystemExit):
        app.parse_args(["--port", "70000"])


def test_port_in_use_reports_clear_error(capsys):
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    try:
        code = app.main(["--port", str(port), "--no-browser"])
    finally:
        blocker.close()
    assert code == 2
    err = capsys.readouterr().err
    assert f"porta {port}" in err and "già in uso" in err


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_ready(port, proc, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            resp, _ = _get(port, "/")
            return resp.status == 200
        except OSError:
            time.sleep(0.2)
    return False


@pytest.mark.parametrize("block_pyside", [False, True])
def test_subprocess_launch_from_foreign_cwd(tmp_path, block_pyside):
    """Avvio reale da una directory diversa (tmp), anche con PySide6 non importabile."""
    port = _free_port()
    env = dict(os.environ, LUNAR_UI_NO_BROWSER="1")
    if block_pyside:
        blocker = tmp_path / "block"
        blocker.mkdir()
        (blocker / "PySide6.py").write_text("raise ImportError('PySide6 bloccato dal test')\n")
        env["PYTHONPATH"] = str(blocker)
    proc = subprocess.Popen(
        [sys.executable, str(APP_PATH), "--port", str(port)],
        cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        assert _wait_ready(port, proc), proc.stderr.read().decode() if proc.poll() is not None else "timeout"
        resp, _ = _get(port, "/vendor/three/build/three.module.js")
        assert resp.status == 200
        resp, _ = _get(port, "/src/ui_web/app.py")
        assert resp.status == 404
    finally:
        proc.terminate()
        proc.wait(timeout=10)
