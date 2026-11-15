"""Test F9 passo 1: prefisso statico /ui/ (D-F1), token, base e font self-hosted (D-F4)."""
import http.client
import importlib.util
import re
from pathlib import Path
from threading import Thread

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_DIR = PROJECT_ROOT / "src" / "ui_web"
APP_PATH = UI_DIR / "app.py"


def _load_app():
    spec = importlib.util.spec_from_file_location("lunar_web_ui_app_f9", APP_PATH)
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


@pytest.mark.parametrize("path,content_type", [
    ("/ui/tokens.css", "text/css"),
    ("/ui/base.css", "text/css"),
    ("/ui/fonts/archivo-latin.woff2", "font/woff2"),
    ("/ui/fonts/archivo-latin-ext.woff2", "font/woff2"),
])
def test_ui_assets_served(server, path, content_type):
    resp, body = _get(server, path)
    assert resp.status == 200, path
    assert resp.getheader("Content-Type").startswith(content_type)
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert body


def test_fonts_are_woff2():
    for name in ("archivo-latin.woff2", "archivo-latin-ext.woff2"):
        assert (UI_DIR / "ui" / "fonts" / name).read_bytes()[:4] == b"wOF2"
    assert "SIL Open Font License" in (UI_DIR / "ui" / "fonts" / "OFL.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("path", [
    "/ui/",
    "/ui/fonts/",
    "/ui/fonts/OFL.txt",            # estensione non consentita
    "/ui/fonts/SOURCE.md",
    "/ui/missing.css",
    "/ui/../app.py",
    "/ui/%2e%2e/app.py",
    "/ui/..%2fapp.py",
    "/ui/fonts/../../app.py",
    "/ui/../index.html",
    "/ui/../../paths.py",
    "/ui/..%5capp.py",
    "/ui/tokens.css%00.js",
])
def test_ui_prefix_rejects_unauthorized(server, path):
    resp, body = _get(server, path)
    assert resp.status == 404, path
    assert b"Risorsa non trovata" in body


def test_resolve_static_ui_suffix_whitelist(tmp_path, monkeypatch):
    # Anche un file reale dentro ui/ con estensione non consentita non viene servito.
    (tmp_path / "x.py").write_text("print(1)")
    (tmp_path / "ok.css").write_text("a{}")
    monkeypatch.setattr(app, "UI_ASSETS_DIR", tmp_path)
    assert app.resolve_static("/ui/x.py") is None
    assert app.resolve_static("/ui/ok.css") == (tmp_path / "ok.css").resolve()


def test_index_links_v2_stylesheets(server):
    resp, body = _get(server, "/")
    html = body.decode("utf-8")
    assert re.search(r'<html lang="it" data-ui="v2">', html)
    tokens = html.index('href="/ui/tokens.css"')
    base = html.index('href="/ui/base.css"')
    # I fogli v2 vengono dopo gli stili inline esistenti e i token prima della base.
    assert html.rindex("</style>") < tokens < base < html.index("</head>")


def test_base_css_scoped_to_v2():
    css = (UI_DIR / "ui" / "base.css").read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    selectors = [s.strip() for s in re.findall(r"([^{}@]+)\{", body)]
    selectors = [s for s in selectors if not s.startswith(("(", "media"))]  # condizioni @media
    for group in selectors:
        top_level = re.sub(r"\([^()]*\)", "()", group)  # ignora le virgole dentro :is(...)
        for sel in top_level.split(","):
            assert sel.strip().startswith('[data-ui="v2"]'), sel


def test_tokens_css_defines_only_custom_properties_and_fonts():
    css = re.sub(r"/\*.*?\*/", "", (UI_DIR / "ui" / "tokens.css").read_text(encoding="utf-8"), flags=re.S)
    blocks = [b.strip() for b in re.findall(r"([^{}]+)\{", css)]
    assert set(blocks) == {"@font-face", ":root"}
    root = re.search(r":root\s*\{(.*?)\}", css, re.S).group(1)
    for decl in filter(None, (d.strip() for d in root.split(";"))):
        assert decl.startswith("--ui-"), decl
