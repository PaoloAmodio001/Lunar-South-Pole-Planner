# Last updated: 2026-11-15
"""Punto di ingresso ufficiale della piattaforma Lunar South Pole Planner: piattaforma
pubblica (/) e sezione riservata Pianificatori di missione (/dashboard, /mission-control).

Uso:
    ./start.sh                                  # avvio consigliato (venv + controlli)
    python src/ui_web/app.py                    # server locale + browser (default)
    python src/ui_web/app.py --port 9000        # porta alternativa
    python src/ui_web/app.py --no-browser       # solo server
    python src/ui_web/app.py --desktop          # finestra desktop PySide6 (opzionale)

Variabili d'ambiente equivalenti: LUNAR_UI_HOST, LUNAR_UI_PORT, LUNAR_UI_NO_BROWSER=1.
Autenticazione (unico login, solo per i Pianificatori di missione): src/ui_web/auth.py.
Il server espone soltanto le risorse elencate in una whitelist esplicita.
"""
import html
import argparse
import hmac
import errno
import ipaddress
import json
import os
import re
import secrets
import shutil
import signal
import sys
import time
import webbrowser
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread, Timer
from urllib.parse import urlparse, parse_qs, unquote, quote

UI_DIR = Path(__file__).resolve().parent
# Bootstrap minimo per l'avvio come script; poi la radice viene da src.paths (F5).
if str(UI_DIR.parents[1]) not in sys.path:
    sys.path.insert(0, str(UI_DIR.parents[1]))

from src.paths import PROJECT_ROOT

from src.astronomy import SITES, query_observations, AstronomyError, probe_horizons
from src.mission_planning import find_operational_windows
from src.mission_planner import MissionConfig, rank_operational_windows
from src.mission_analytics import summarize_ephemerides
from src.communications import calculate_link_budget
from src.thermal_model import simulate_single_node_thermal
from src.ui_web import mission_runner
from src.ui_web.mission_runner import ConfigError, MissionBusyError
from src.ui_web import science_api
from src.ui_web.auth import (AuthManager, FirstUserError, MIN_PASSWORD_LENGTH, USERNAME_RE,
                             token_from_cookie_header, safe_next_path)

MISSIONS = mission_runner.MissionManager()
MISSION_RUN_RE = re.compile(
    r"^/api/mission/runs/([0-9a-f]{32})(?:/(report|artifacts/([A-Za-z0-9_\-]{1,64})))?$")
MISSION_CONFIG_RE = re.compile(r"^/api/mission/configs/([A-Za-z0-9_\-]{1,64})$")
ARTIFACT_TYPES = {
    ".json": "application/json; charset=utf-8",
    ".jsonl": "application/x-ndjson; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".csv": "text/csv; charset=utf-8",
}

DEFAULT_HOST = "127.0.0.1"
PORT = 8765  # porta predefinita (nome mantenuto per compatibilità)

AUDIT_REPORTS_DIR = PROJECT_ROOT / "audit-reports"
LROC_REPORT_GLOB = "lroc-quality-mask-*.json"

# --- Risorse statiche consentite (whitelist esplicita) -----------------------
VENDOR_THREE_DIR = UI_DIR / "vendor" / "three"
VENDOR_THREE_PREFIX = "/vendor/three/"
# Asset grafici della UI (F9, decisione D-F1): sola lettura, estensioni limitate.
UI_ASSETS_DIR = UI_DIR / "ui"
UI_ASSETS_PREFIX = "/ui/"
UI_ASSETS_SUFFIXES = {".css", ".js", ".woff2", ".svg"}
STATIC_ROUTES = {
    "/": UI_DIR / "index.html",
    "/index.html": UI_DIR / "index.html",
    "/mission-control": UI_DIR / "index.html",
    "/dashboard": UI_DIR / "dashboard.html",
    "/dashboard.js": UI_DIR / "dashboard.js",
    "/session.js": UI_DIR / "session.js",
    "/main.js": UI_DIR / "main.js",
    "/mission.js": UI_DIR / "mission.js",
    "/science.js": UI_DIR / "science.js",
    "/data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb":
        PROJECT_ROOT / "data" / "terrain" / "global" / "Moon_NASA_LRO_8k_Topo_Small.glb",
}
LEGACY_REDIRECTS = {
    "/src/ui_web/index.html": "/",
    "/src/ui_web/": "/",
}
LOGIN_PAGE = UI_DIR / "login.html"
# Ambito dell'autenticazione: SOLO la sezione riservata "Pianificatori di missione"
# (MISSION PLANNERS), con un unico login. La piattaforma pubblica — homepage, profili
# Pubblico ed Educatore, globo e le API che usa (/api/health, /api/sites,
# /api/ephemerides, /api/services) — resta accessibile senza account.
# Richiedono la sessione (controllo lato server, pagine -> /login, API -> 401):
#   /dashboard        ingresso della sezione Pianificatori di missione
#   /mission-control  Lunar Mission Control Planner
#   /api/auth/session utente della sessione
#   API dei pianificatori: Mission Engine, strumenti scientifici, comunicazioni,
#   termica e terreno (PROTECTED_PREFIXES).
PROTECTED_PATHS = {"/dashboard", "/mission-control",
                   "/api/auth/session"}
PROTECTED_PREFIXES = ("/api/mission/", "/api/science/", "/api/communications/",
                      "/api/thermal/", "/api/terrain/")


def is_protected_path(path):
    return path in PROTECTED_PATHS or path.startswith(PROTECTED_PREFIXES)
# Token CSRF del modulo "Crea account amministratore" (double-submit: cookie
# HttpOnly limitato a /auth/setup + campo nascosto), in aggiunta al controllo Origin.
SETUP_CSRF_COOKIE = "lmc_setup_csrf"
SETUP_CSRF_MAX_AGE_S = 30 * 60
SETUP_ERRORS = {
    "origin": "Richiesta rifiutata: origine non consentita.",
    "csrf": "Modulo scaduto o non valido: riprova.",
    "invalid": "Richiesta non valida.",
    "username": "Nome utente non valido: 3-32 caratteri tra lettere, cifre, _ . -",
    "password_short": f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri.",
    "password_long": "Password troppo lunga (massimo 1024 caratteri).",
    "password_same": "La password non può coincidere con il nome utente.",
    "mismatch": "Le due password non coincidono.",
    "store_unreadable": "Archivio utenti presente ma illeggibile: per sicurezza non viene "
                        "sovrascritto. Controlla il file users.json nella cartella di configurazione.",
}
# Richieste automatiche di stato: verificano la sessione senza rinnovarla, così la
# scadenza per inattività funziona anche con una pagina aperta che interroga il server.
PASSIVE_PATHS = {"/api/health", "/api/services", "/api/auth/session"}

# Classificazione degli errori di NASA/JPL Horizons (src.astronomy.AstronomyError.kind).
EPHEMERIS_ERRORS = {
    "timeout": (504, "jpl_timeout"),
    "dns": (503, "jpl_unreachable"),
    "connection": (503, "jpl_unreachable"),
    "http": (502, "jpl_http_error"),
    "upstream_error": (502, "jpl_rejected"),
    "invalid_response": (502, "jpl_invalid_response"),
    "data": (502, "jpl_invalid_response"),
}
JPL_PROBE_TTL_S = 60

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".glb": "model/gltf-binary",
    ".css": "text/css; charset=utf-8",
    ".woff2": "font/woff2",
    ".svg": "image/svg+xml",
}


def find_latest_lroc_report(directory=None):
    """Restituisce il report qualità LROC più recente, o None.

    I nomi seguono lo schema ``lroc-quality-mask-<timestamp ISO compatto>.json``:
    l'ordinamento lessicografico corrisponde a quello cronologico; a parità
    si usa la data di modifica del file.
    """
    directory = Path(directory) if directory is not None else AUDIT_REPORTS_DIR
    candidates = [p for p in directory.glob(LROC_REPORT_GLOB) if p.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: (p.name, p.stat().st_mtime))


def resolve_static(url_path):
    """Mappa un percorso URL a un file consentito; None se non autorizzato."""
    if url_path in STATIC_ROUTES:
        target = STATIC_ROUTES[url_path]
        return target if target.is_file() else None
    if url_path.startswith(VENDOR_THREE_PREFIX):
        relative = url_path[len(VENDOR_THREE_PREFIX):]
        if not relative.endswith(".js") or "\\" in relative or "\x00" in relative:
            return None
        base = VENDOR_THREE_DIR.resolve()
        target = (base / relative).resolve()
        if base not in target.parents or not target.is_file():
            return None
        return target
    if url_path.startswith(UI_ASSETS_PREFIX):
        relative = url_path[len(UI_ASSETS_PREFIX):]
        if "\\" in relative or "\x00" in relative:
            return None
        base = UI_ASSETS_DIR.resolve()
        target = (base / relative).resolve()
        if (base not in target.parents or target.suffix.lower() not in UI_ASSETS_SUFFIXES
                or not target.is_file()):
            return None
        return target
    return None


def attach_window_ranking(windows, windows_payload, sun_values, earth_values):
    """F11: aggiunge a ogni finestra il ranking di src.mission_planner.

    Algoritmo invariato (rank_operational_windows) con le priorità predefinite
    di MissionConfig (scienza 5, ingegneria 5). Punteggio euristico, non
    qualificato per il volo: misura solo elevazioni medie e durata relativa.
    """
    defaults = MissionConfig(site="", start_date_utc="")
    ranked = rank_operational_windows(windows, sun_values, earth_values, defaults)
    by_start = {item["start_index"]: item for item in ranked}
    for window, payload in zip(windows, windows_payload):
        item = by_start.get(int(window.start_index))
        if item is None:
            continue
        payload["ranking"] = {
            key: item[key] for key in (
                "rank", "score", "science_score", "engineering_score",
                "duration_score", "sun_mean_elevation_deg",
                "earth_mean_elevation_deg", "score_method")
        }
        payload["ranking"]["science_priority"] = defaults.science_priority
        payload["ranking"]["engineering_priority"] = defaults.engineering_priority
    return windows_payload


class Handler(BaseHTTPRequestHandler):
    server_version = "LunarWebUI/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def send_static(self, url_path, head_only=False):
        if url_path in LEGACY_REDIRECTS:
            self.send_response(302)
            self.send_header("Location", LEGACY_REDIRECTS[url_path])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        target = resolve_static(url_path)
        if target is None:
            return self.send_json(404, {"status": "error", "error": "Risorsa non trovata."})
        content_type = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
        try:
            stat = target.stat()
            size = stat.st_size
        except OSError:
            return self.send_json(404, {"status": "error", "error": "Risorsa non trovata."})
        if target.suffix.lower() == ".html":
            # Le pagine non vanno mai in cache: un browser che ripristina la sessione
            # non deve mostrare una dashboard "viva" (modello 3D dalla cache) quando il
            # backend è spento, causa dei falsi "NetworkError" sulle API.
            try:
                body = target.read_bytes()
            except OSError:
                return self.send_json(404, {"status": "error", "error": "Risorsa non trovata."})
            return self.send_bytes(200, body, content_type, head_only=head_only)
        # F11: validatore debole (dimensione + mtime). "no-cache" resta: il browser
        # rivalida sempre, ma un file invariato (es. GLB da 81,5 MB) torna 304 senza corpo.
        etag = f'W/"{size:x}-{stat.st_mtime_ns:x}"'
        last_modified = self.date_time_string(int(stat.st_mtime))
        if etag in [tag.strip() for tag in self.headers.get("If-None-Match", "").split(",")]:
            self.send_response(304)
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", last_modified)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return
        try:
            stream = target.open("rb")
        except OSError:
            return self.send_json(404, {"status": "error", "error": "Risorsa non trovata."})
        with stream:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", last_modified)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head_only:
                try:
                    shutil.copyfileobj(stream, self.wfile, 1024 * 1024)
                except (BrokenPipeError, ConnectionResetError):
                    pass

    def do_HEAD(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            return self.send_json(405, {"status": "error", "error": "Metodo non consentito."})
        if self.require_session(parsed) is None:
            return
        return self.send_static(unquote(parsed.path), head_only=True)

    def send_json(self, status, payload, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, status, body, content_type, head_only=False, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if not head_only:
            self.wfile.write(body)

    def redirect(self, location, extra_headers=None):
        self.send_response(303 if self.command == "POST" else 302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        items = extra_headers.items() if isinstance(extra_headers, dict) else (extra_headers or [])
        for key, value in items:
            self.send_header(key, value)
        self.end_headers()

    # --- Autenticazione (sezione MISSION PLANNERS) ------------------------- #
    @property
    def auth(self):
        """AuthManager del server; None solo per server creati senza autenticazione
        (uso programmatico/test). L'avvio da main() la attiva sempre."""
        return getattr(self.server, "auth", None)


    def client_ip(self):
        return self.client_address[0] if self.client_address else "?"

    def current_session(self):
        if self.auth is None:
            return {"user": None}, None
        token = token_from_cookie_header(self.headers.get("Cookie"))
        passive = urlparse(self.path).path in PASSIVE_PATHS
        return self.auth.validate(token, touch=not passive)

    def require_session(self, parsed):
        """Per i percorsi della sezione riservata restituisce la sessione oppure None dopo
        aver risposto (401 o redirect al login). Tutti gli altri percorsi sono pubblici."""
        path = parsed.path
        if not is_protected_path(path):
            return {"user": None, "public": True}
        session, reason = self.current_session()
        if session is not None:
            return session
        expired = reason == "expired"
        if path.startswith("/api/"):
            self.send_json(401, {
                "status": "error",
                "error_code": "session_expired" if expired else "auth_required",
                "error": ("Sessione scaduta: accedere di nuovo." if expired
                          else "Autenticazione richiesta."),
                "login_url": "/login",
            })
            return None
        target = path + (f"?{parsed.query}" if parsed.query else "")
        location = f"/login?next={quote(target, safe='/')}" + ("&expired=1" if expired else "")
        self.redirect(location)
        return None

    def own_origins(self):
        host = self.headers.get("Host", "")
        origins = {f"http://{host}", f"https://{host}"}
        return origins

    def origin_allowed(self):
        """Protezione CSRF: le richieste POST devono provenire dalla piattaforma stessa."""
        origin = self.headers.get("Origin")
        if origin is None:
            # Browser senza header Origin: si accetta solo se non è una richiesta cross-site.
            return self.headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "same-site", "none")
        return origin in self.own_origins()

    def _cookie(self, name):
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name and value:
                return value.strip()
        return None

    def _setup_cookie(self, value, max_age):
        parts = [f"{SETUP_CSRF_COOKIE}={value}", "Path=/auth/setup", "HttpOnly",
                 "SameSite=Strict", f"Max-Age={max_age}"]
        if self.auth is not None and self.auth.secure_cookie:
            parts.append("Secure")
        return "; ".join(parts)

    @staticmethod
    def _keep_block(page, keep, drop):
        """Lascia nella pagina solo il blocco <!--KEEP_START-->...<!--KEEP_END-->."""
        page = re.sub(rf"<!--{drop}_START-->.*?<!--{drop}_END-->", "", page, flags=re.S)
        return page.replace(f"<!--{keep}_START-->", "").replace(f"<!--{keep}_END-->", "")

    # Riquadro "Credenziali di accesso" della pagina di login: solo testo informativo,
    # non modifica né legge il sistema di autenticazione. Viene inserito lato server
    # soltanto in ambiente locale/demo, così nella versione pubblica non compare
    # nemmeno nel sorgente HTML. LUNAR_DEMO_CREDENTIALS=1 lo forza (demo),
    # =0 lo disattiva sempre; senza variabile vale il rilevamento locale.
    DEMO_CREDENTIALS = ("admin", "123456789101112")
    _LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}

    def _show_demo_credentials(self):
        flag = os.environ.get("LUNAR_DEMO_CREDENTIALS", "").strip().lower()
        if flag in ("0", "false", "no", "off"):
            return False
        if flag in ("1", "true", "yes", "on"):
            return True
        # Rilevamento locale: server in ascolto su loopback, client loopback, Host
        # locale e nessuna intestazione di proxy/tunnel (es. ngrok, reverse proxy).
        if not _is_loopback(str(self.server.server_address[0])):
            return False
        if not _is_loopback(self.client_ip()):
            return False
        if any(self.headers.get(h) for h in ("X-Forwarded-For", "X-Forwarded-Host",
                                             "Forwarded", "X-Real-IP")):
            return False
        host = (self.headers.get("Host") or "").strip().lower()
        hostname = host[1:host.index("]")] if host.startswith("[") and "]" in host \
            else host.rsplit(":", 1)[0]
        return hostname in self._LOCAL_HOSTNAMES

    def _demo_credentials_html(self):
        if not self._show_demo_credentials():
            return ""
        user, password = (html.escape(v, quote=True) for v in self.DEMO_CREDENTIALS)
        return ('<aside class="login-demo" aria-label="Credenziali di accesso (ambiente demo)">'
                '<p class="login-demo-title">Credenziali di accesso</p>'
                f'<dl><dt>Username:</dt><dd><code>{user}</code></dd>'
                f'<dt>Password:</dt><dd><code>{password}</code></dd></dl></aside>')

    def render_login(self, query):
        try:
            page = LOGIN_PAGE.read_text(encoding="utf-8")
        except OSError:
            return self.send_json(500, {"status": "error", "error": "Pagina di login assente."})
        auth = self.auth
        next_path = safe_next_path((query.get("next") or [None])[0])
        notices = []
        extra_headers = None
        setup_mode = auth is not None and not auth.configured
        if setup_mode:
            # Primo accesso: solo il modulo di creazione dell'account amministratore.
            page = self._keep_block(page, "SETUP", "LOGIN")
            setup_error = (query.get("setup_error") or [None])[0]
            if setup_error in SETUP_ERRORS:
                notices.append(("error", SETUP_ERRORS[setup_error]))
            prefill = (query.get("u") or [""])[0]
            if not USERNAME_RE.match(prefill):
                prefill = ""
            csrf_token = secrets.token_urlsafe(32)
            extra_headers = {"Set-Cookie": self._setup_cookie(csrf_token, SETUP_CSRF_MAX_AGE_S)}
            page = (page.replace("__CSRF__", csrf_token)
                        .replace("__USERNAME__", html.escape(prefill, quote=True))
                        .replace("__MINLEN__", str(MIN_PASSWORD_LENGTH)))
        else:
            page = self._keep_block(page, "LOGIN", "SETUP")
            if (query.get("setup_error") or [None])[0] == "already_configured":
                notices.append(("warn", "Esiste già un account: accedi con le tue credenziali."))
            error = (query.get("error") or [None])[0]
            if error == "invalid":
                notices.append(("error", "Nome utente o password non corretti."))
            elif error == "locked":
                notices.append(("error", "Troppi tentativi non riusciti: accesso temporaneamente "
                                         "bloccato (15 minuti)."))
            elif error == "origin":
                notices.append(("error", "Richiesta di accesso rifiutata: origine non consentita."))
            if (query.get("expired") or [None])[0]:
                notices.append(("warn", "La sessione è scaduta. Accedi di nuovo."))
            if (query.get("logged_out") or [None])[0]:
                notices.append(("ok", "Disconnessione completata."))
        notice_html = "".join(
            f'<p class="login-notice" data-kind="{kind}" role="{"alert" if kind == "error" else "status"}">{text}</p>'
            for kind, text in notices)
        demo_html = "" if setup_mode else self._demo_credentials_html()
        page = (page.replace("<!--LOGIN_NOTICES-->", notice_html)
                    .replace("<!--DEMO_CREDENTIALS-->", demo_html)
                    .replace("__NEXT__", html.escape(next_path, quote=True)))
        return self.send_bytes(200, page.encode("utf-8"), CONTENT_TYPES[".html"],
                               extra_headers=extra_headers)

    def handle_setup_post(self):
        """Crea il primo account amministratore (solo con archivio utenti vuoto)."""
        auth = self.auth
        if auth is None:
            return self.redirect("/dashboard")
        if auth.configured:
            # Endpoint chiuso: non consente di creare ulteriori account.
            return self.redirect("/login?setup_error=already_configured")
        if not self.origin_allowed():
            return self.redirect("/login?setup_error=origin")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 8192:
            return self.redirect("/login?setup_error=invalid")
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True)
        field = lambda name: (form.get(name) or [""])[0]  # noqa: E731
        username = field("username").strip()
        password = field("password")
        confirm = field("password_confirm")
        next_path = safe_next_path(field("next") or None)

        def fail(code):
            prefill = f"&u={quote(username)}" if USERNAME_RE.match(username) else ""
            return self.redirect(f"/login?setup_error={code}{prefill}&next={quote(next_path, safe='/')}")

        cookie_token = self._cookie(SETUP_CSRF_COOKIE) or ""
        form_token = field("csrf_token")
        if not cookie_token or not form_token or len(form_token) > 128 or \
                not hmac.compare_digest(cookie_token.encode(), form_token.encode()):
            return fail("csrf")
        if password != confirm:
            return fail("mismatch")
        try:
            auth.users.create_first_user(username, password)
        except FirstUserError as exc:
            if exc.code == "already_configured":
                return self.redirect("/login?setup_error=already_configured")
            return fail(exc.code if exc.code in SETUP_ERRORS else "invalid")
        except OSError:
            return fail("store_unreadable")
        # Accesso immediato con il normale meccanismo di sessione.
        clear = ("Set-Cookie", self._setup_cookie("", 0))
        token, _ = auth.login(username, password, self.client_ip())
        if token is None:
            return self.redirect("/login", [clear])
        return self.redirect(next_path, [clear, ("Set-Cookie", auth.session_cookie(token))])

    def handle_login_post(self):
        auth = self.auth
        if auth is None:
            return self.redirect("/dashboard")
        if not self.origin_allowed():
            return self.redirect("/login?error=origin")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 8192:
            return self.redirect("/login?error=invalid")
        form = parse_qs(self.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True)
        username = (form.get("username") or [""])[0]
        password = (form.get("password") or [""])[0]
        next_path = safe_next_path((form.get("next") or [None])[0])
        token, error = auth.login(username, password, self.client_ip())
        if token is None:
            if error == "invalid":
                time.sleep(0.5)  # rallenta i tentativi automatici
            return self.redirect(f"/login?error={error}&next={quote(next_path, safe='/')}")
        return self.redirect(next_path, {"Set-Cookie": auth.session_cookie(token)})

    def handle_logout_post(self):
        auth = self.auth
        if auth is None:
            return self.redirect("/")
        if not self.origin_allowed():
            return self.send_json(403, {"status": "error", "error": "Origine non consentita."})
        auth.logout(token_from_cookie_header(self.headers.get("Cookie")))
        # Il logout chiude solo la sezione riservata: si torna alla piattaforma pubblica.
        return self.redirect("/", {"Set-Cookie": auth.clear_cookie()})

    # --- Stato dei servizi -------------------------------------------------- #
    def jpl_status(self, refresh=False):
        cache = getattr(self.server, "jpl_probe_cache", None)
        now = time.monotonic()
        if not refresh and cache and now - cache[0] < JPL_PROBE_TTL_S:
            return cache[1]
        result = probe_horizons()
        self.server.jpl_probe_cache = (now, result)
        return result

    def handle_services(self, query):
        # Pubblico (lo usa anche la piattaforma pubblica per il ripristino JPL):
        # stato della sessione solo con sessione valida; senza
        # sessione la sonda JPL non viene forzata e resta in cache per JPL_PROBE_TTL_S.
        session, _ = self.current_session()
        refresh = (query.get("refresh") or ["0"])[0] == "1" and session is not None
        payload = {
            "status": "ok",
            "backend": {"available": True, "server_time_utc": datetime.now(timezone.utc).isoformat()},
            "jpl_horizons": self.jpl_status(refresh),
            "authenticated": session is not None,
        }
        if session is None:
            return self.send_json(200, payload)
        payload["session"] = {"user": session.get("user"),
                              "idle_timeout_minutes": (self.auth.idle_s / 60) if self.auth else None}
        return self.send_json(200, payload)

    def read_json_body(self, limit=1_000_000):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > limit:
            raise ValueError(f"Body JSON mancante o troppo grande (max {limit} byte).")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Il body deve essere un oggetto JSON.")
        return payload

    def send_file(self, path, content_type, filename):
        try:
            size = path.stat().st_size
            stream = path.open("rb")
        except OSError:
            return self.send_json(404, {"status": "error", "error": "Risorsa non trovata."})
        with stream:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
            self.end_headers()
            try:
                shutil.copyfileobj(stream, self.wfile, 1024 * 1024)
            except (BrokenPipeError, ConnectionResetError):
                pass

    @staticmethod
    def mission_config_from_payload(payload):
        """Configurazione dal catalogo (per id) oppure caricata dal browser."""
        if "config_id" in payload:
            config_id = payload["config_id"]
            if not isinstance(config_id, str):
                raise ConfigError("config_id non valido.")
            config = mission_runner.load_catalog_config(config_id)
            return config, mission_runner.CONFIG_CATALOG[config_id]["label"]
        if "config" in payload:
            name = payload.get("filename") or "configurazione caricata"
            name = re.sub(r"[^A-Za-z0-9._ -]", "_", str(name))[:80]
            return payload["config"], f"upload: {name}"
        raise ConfigError("Specificare 'config_id' oppure 'config'.")

    def handle_mission_post(self, path):
        try:
            payload = self.read_json_body()
            config, label = self.mission_config_from_payload(payload)
            if path == "/api/mission/validate":
                validation = mission_runner.validate_config(config)
                return self.send_json(200, {"status": "ok", "config_label": label,
                                            "validation": validation})
            validation = mission_runner.validate_config(config)
            if not validation["valid"]:
                return self.send_json(400, {"status": "error",
                                            "error": "Configurazione non valida.",
                                            "validation": validation})
            job = MISSIONS.start(config, label)
            return self.send_json(202, {"status": "ok", "run_id": job["id"],
                                        "status_url": f"/api/mission/runs/{job['id']}",
                                        "validation": validation})
        except MissionBusyError as exc:
            return self.send_json(409, {"status": "error", "error": str(exc),
                                        "running_id": exc.running_id})
        except (ConfigError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"status": "error", "error": str(exc)})
        except Exception as exc:
            return self.send_json(500, {"status": "error",
                                        "error": f"Avvio missione non riuscito: {exc}"})

    def handle_mission_get(self, path):
        if path == "/api/mission/configs":
            return self.send_json(200, {"status": "ok", "configs": mission_runner.list_configs()})
        match = MISSION_CONFIG_RE.match(path)
        if match:
            try:
                config = mission_runner.load_catalog_config(match.group(1))
            except ConfigError as exc:
                return self.send_json(404, {"status": "error", "error": str(exc)})
            return self.send_json(200, {"status": "ok", "config": config})
        if path == "/api/mission/runs":
            return self.send_json(200, {"status": "ok", "running_id": MISSIONS.running_id,
                                        "runs": MISSIONS.list_runs()})
        match = MISSION_RUN_RE.match(path)
        if not match:
            return self.send_json(404, {"status": "error", "error": "Endpoint non trovato."})
        run_id, sub, artifact_key = match.groups()
        try:
            if sub is None:
                return self.send_json(200, {"status": "ok", "run": MISSIONS.status_payload(run_id)})
            if sub == "report":
                target = MISSIONS._run_dir(run_id) / "output" / "mission_report.json"
                if not target.is_file():
                    return self.send_json(404, {"status": "error",
                                                "error": "Report non (ancora) disponibile."})
                return self.send_file(target, ARTIFACT_TYPES[".json"], "mission_report.json")
            target = MISSIONS.artifact_file(run_id, artifact_key)
            if target is None:
                return self.send_json(404, {"status": "error", "error": "Risorsa non trovata."})
            return self.send_file(target, ARTIFACT_TYPES.get(target.suffix.lower(),
                                                             "application/octet-stream"),
                                  target.name)
        except KeyError:
            return self.send_json(404, {"status": "error", "error": "Esecuzione non trovata."})
        except (OSError, json.JSONDecodeError) as exc:
            return self.send_json(500, {"status": "error",
                                        "error": f"Lettura risultati non riuscita: {exc}"})

    def handle_mission_status(self, query):
        """Alias F3: stato dell'esecuzione indicata (?id=) o di quella in corso/più recente."""
        run_id = (query.get("id") or [None])[0]
        if run_id is None:
            run_id = MISSIONS.running_id
            if run_id is None:
                runs = MISSIONS.list_runs(limit=1)
                run_id = runs[0]["id"] if runs else None
        if run_id is None:
            return self.send_json(200, {"status": "ok", "running_id": None, "run": None})
        try:
            payload = MISSIONS.status_payload(run_id)
        except KeyError:
            return self.send_json(404, {"status": "error", "error": "Esecuzione non trovata."})
        return self.send_json(200, {"status": "ok", "running_id": MISSIONS.running_id,
                                    "run": payload})

    def handle_science_post(self, path):
        """F4: endpoint sottili sui moduli scientifici (vedi science_api)."""
        try:
            payload = self.read_json_body(limit=64 * 1024)
            result = science_api.POST_ROUTES[path](payload)
            return self.send_json(200, {"status": "ok", **result})
        except science_api.ScienceNotFound as exc:
            return self.send_json(404, {"status": "error", "error": str(exc)})
        except science_api.ScienceBusy as exc:
            return self.send_json(503, {"status": "error", "error": str(exc)})
        except science_api.ScienceUpstreamError as exc:
            return self.send_json(502, {"status": "error", "error": str(exc)})
        except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            # include ScienceInputError e le validazioni dei moduli originali
            return self.send_json(400, {"status": "error", "error": str(exc)})
        except FileNotFoundError as exc:
            return self.send_json(404, {"status": "error", "error": str(exc)})
        except Exception as exc:
            return self.send_json(500, {"status": "error",
                                        "error": f"Calcolo non riuscito: {type(exc).__name__}"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/auth/login":
            return self.handle_login_post()
        if parsed.path == "/auth/setup":
            return self.handle_setup_post()
        if parsed.path == "/auth/logout":
            return self.handle_logout_post()
        # Le API POST dei pianificatori richiedono la sessione (require_session);
        # per tutte resta il controllo dell'origine (CSRF).
        if self.require_session(parsed) is None:
            return
        if self.auth is not None and not self.origin_allowed():
            return self.send_json(403, {"status": "error", "error_code": "origin_forbidden",
                                        "error": "Origine della richiesta non consentita."})
        if parsed.path in science_api.POST_ROUTES:
            return self.handle_science_post(parsed.path)
        if parsed.path in ("/api/mission/validate", "/api/mission/runs"):
            return self.handle_mission_post(parsed.path)
        if parsed.path == "/api/mission/run":  # alias F3 di /api/mission/runs
            return self.handle_mission_post("/api/mission/runs")
        routes = {
            "/api/communications/link-budget": calculate_link_budget,
            "/api/thermal/simulate": simulate_single_node_thermal,
        }
        operation = routes.get(parsed.path)
        if operation is None:
            return self.send_json(404, {"status": "error", "error": "Endpoint non trovato."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1_000_000:
                raise ValueError("Body JSON mancante o troppo grande (max 1 MB).")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Il body deve essere un oggetto JSON.")
            result = operation(**payload)
            return self.send_json(200, {"status": "ok", "result": result})
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            return self.send_json(400, {"status": "error", "error": str(exc)})
        except Exception as exc:
            return self.send_json(500, {"status": "error", "error": f"Calcolo non riuscito: {exc}"})

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            # Pubblico e minimale: permette alla UI di distinguere "backend spento"
            # (errore di rete) da "sessione scaduta" (401) senza esporre dati.
            session, _ = self.current_session()
            return self.send_json(200, {"status": "ok", "backend": "ok",
                                        "authenticated": session is not None,
                                        "auth_enabled": self.auth is not None})
        if parsed.path == "/login":
            return self.render_login(parse_qs(parsed.query))
        session = self.require_session(parsed)
        if session is None:
            return
        if parsed.path == "/api/services":
            return self.handle_services(parse_qs(parsed.query))
        if parsed.path == "/api/auth/session":
            return self.send_json(200, {"status": "ok", "user": session.get("user"),
                                        "auth_enabled": self.auth is not None})
        if parsed.path == "/api/science/rasters":
            return self.send_json(200, {"status": "ok", **science_api.list_rasters()})
        if parsed.path == "/api/sites":
            return self.send_json(200, {"status": "ok", "source": "src.astronomy.SITES", "sites": [
                {"name": name, "latitude_deg": lat, "longitude_east_deg": lon}
                for name, (lat, lon) in SITES.items()]})
        if parsed.path == "/api/mission/status":
            return self.handle_mission_status(parse_qs(parsed.query))
        if parsed.path == "/api/mission/reports":
            return self.send_json(200, {"status": "ok", "reports": MISSIONS.list_reports()})
        if parsed.path.startswith("/api/mission/"):
            return self.handle_mission_get(parsed.path)
        if parsed.path == "/api/terrain/lroc-quality":
            report_path = find_latest_lroc_report()
            if report_path is None:
                return self.send_json(404, {
                    "status": "error",
                    "error": "Report qualità LROC non trovato."
                })
            try:
                with report_path.open("r", encoding="utf-8") as stream:
                    payload = json.load(stream)
                return self.send_json(200, payload)
            except FileNotFoundError:
                return self.send_json(404, {
                    "status": "error",
                    "error": "Report qualità LROC non trovato."
                })
            except (OSError, json.JSONDecodeError) as exc:
                return self.send_json(500, {
                    "status": "error",
                    "error": f"Lettura report LROC non riuscita: {exc}"
                })

        if parsed.path != "/api/ephemerides":
            return self.send_static(unquote(parsed.path))

        try:
            q = parse_qs(parsed.query)
            site = q.get("site", ["Shackleton"])[0]
            if site not in SITES:
                raise ValueError(f"Sito non riconosciuto: {site}")

            start_text = q.get("start", [""])[0]
            if not start_text:
                raise ValueError("Seleziona la data e l'ora di inizio UTC.")

            start = datetime.fromisoformat(start_text)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            start = start.astimezone(timezone.utc)

            hours = int(q.get("hours", ["48"])[0])
            min_sun = float(q.get("min_sun", ["5"])[0])
            min_earth = float(q.get("min_earth", ["5"])[0])

            if not 1 <= hours <= 720:
                raise ValueError("La durata deve essere compresa tra 1 e 720 ore.")
            if not -90 <= min_sun <= 90 or not -90 <= min_earth <= 90:
                raise ValueError("Le soglie di elevazione devono essere tra -90° e 90°.")

            latitude, longitude = SITES[site]

            # Coordinate e periodo sono quelli selezionati nell'interfaccia (sito,
            # inizio UTC, durata): nessun valore sostitutivo o dimostrativo.
            sun = query_observations(
                "10", latitude, longitude, start, hours=hours, step="1h"
            )
            earth = query_observations(
                "399", latitude, longitude, start, hours=hours, step="1h"
            )

            # Le due serie devono riferirsi agli stessi istanti.
            earth_by_time = {o.time_utc: o for o in earth}
            common_times = [o.time_utc for o in sun if o.time_utc in earth_by_time]
            if not common_times:
                raise AstronomyError(
                    "Nessun timestamp comune tra le effemeridi di Sole e Terra.",
                    kind="data",
                )

            sun_by_time = {o.time_utc: o for o in sun}
            sun_values = [sun_by_time[t].elevation_deg for t in common_times]
            earth_values = [earth_by_time[t].elevation_deg for t in common_times]

            windows = find_operational_windows(
                sun_values,
                earth_values,
                min_sun_elevation_deg=min_sun,
                min_earth_elevation_deg=min_earth,
            )

            observations_payload = [{
                "time_utc": t,
                "sun_elevation_deg": sun_by_time[t].elevation_deg,
                "sun_azimuth_deg": sun_by_time[t].azimuth_deg,
                "earth_elevation_deg": earth_by_time[t].elevation_deg,
                "earth_azimuth_deg": earth_by_time[t].azimuth_deg,
            } for t in common_times]
            windows_payload = [{
                "start_utc": common_times[w.start_index],
                "end_utc": common_times[w.end_index],
                "duration_samples": w.duration_samples,
                "sample_step_hours": 1,
                "sampled_span_hours": max(0, w.duration_samples - 1),
                "sun_threshold_deg": min_sun,
                "earth_threshold_deg": min_earth,
                "min_sun_elevation_deg": round(min(sun_values[w.start_index:w.end_index + 1]), 2),
                "min_earth_elevation_deg": round(min(earth_values[w.start_index:w.end_index + 1]), 2),
            } for w in windows]
            attach_window_ranking(windows, windows_payload, sun_values, earth_values)
            analytics = summarize_ephemerides(
                observations_payload,
                min_sun_elevation_deg=min_sun,
                min_earth_elevation_deg=min_earth,
                windows=windows_payload,
            )

            return self.send_json(200, {
                "status": "ok",
                "source": "NASA/JPL Horizons",
                "site": site,
                "latitude_deg": latitude,
                "longitude_east_deg": longitude,
                "start_utc": start.isoformat(),
                "duration_hours": hours,
                "step": "1h",
                "thresholds": {
                    "sun_elevation_deg": min_sun,
                    "earth_elevation_deg": min_earth,
                },
                "observations": observations_payload,
                "windows": windows_payload,
                "analytics": analytics,
                "notice": (
                    "Finestre geometriche preliminari. Non verificano "
                    "ostruzioni del terreno, budget radio o sicurezza di atterraggio."
                ),
            })

        except AstronomyError as exc:
            kind = getattr(exc, "kind", "invalid_response")
            http_status, code = EPHEMERIS_ERRORS.get(kind, (502, "jpl_invalid_response"))
            self.server.jpl_probe_cache = None  # lo stato JPL va ricontrollato
            return self.send_json(http_status, {
                "status": "error",
                "error_code": code,
                "source": "NASA/JPL Horizons",
                "error": str(exc),
                "retryable": kind in ("timeout", "dns", "connection", "http"),
            })
        except (ValueError, TypeError) as exc:
            return self.send_json(400, {"status": "error", "error_code": "invalid_request",
                                        "error": str(exc)})
        except Exception as exc:
            return self.send_json(500, {
                "status": "error",
                "error_code": "backend_error",
                "error": f"Errore interno del backend durante il calcolo: {type(exc).__name__}: {exc}",
            })


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Lunar South Pole Planner — Web UI (server locale + browser).",
    )
    parser.add_argument("--host", default=os.environ.get("LUNAR_UI_HOST", DEFAULT_HOST),
                        help=f"Indirizzo di ascolto (predefinito: {DEFAULT_HOST}).")
    parser.add_argument("--port", type=int, default=int(os.environ.get("LUNAR_UI_PORT", PORT)),
                        help=f"Porta TCP (predefinita: {PORT}).")
    parser.add_argument("--no-browser", action="store_true",
                        default=os.environ.get("LUNAR_UI_NO_BROWSER", "") not in ("", "0"),
                        help="Non aprire automaticamente il browser.")
    parser.add_argument("--desktop", action="store_true",
                        help="Apre la UI in una finestra desktop PySide6 (opzionale).")
    args = parser.parse_args(argv)
    if not 0 < args.port < 65536:
        parser.error("La porta deve essere compresa tra 1 e 65535.")
    return args


def _is_loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def create_server(host, port, auth=None):
    """Crea il server HTTP; solleva OSError se la porta non è disponibile.

    ``auth`` è l'AuthManager della sezione MISSION PLANNERS. ``main()`` lo passa
    sempre; ``auth=None`` (nessuna autenticazione) è riservato all'uso
    programmatico locale, ad esempio la suite di test esistente.
    """
    server = ThreadingHTTPServer((host, port), Handler)
    server.auth = auth
    server.jpl_probe_cache = None
    return server


def _run_desktop(url, server, server_thread):
    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtWidgets import QApplication, QMainWindow
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as exc:
        print(f"[ERRORE] Modalità desktop non disponibile: PySide6 non installato ({exc}).\n"
              f"         Avvia senza --desktop per usare il browser: {url}", file=sys.stderr)
        return 3

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(True)

    window = QMainWindow()
    window.setWindowTitle("LUNAR // Mission Control")
    window.resize(1600, 1000)

    view = QWebEngineView(window)
    view.setUrl(QUrl(url))
    window.setCentralWidget(view)

    # Mantiene riferimenti espliciti agli oggetti per tutta la vita dell'app.
    app._lunar_window = window
    app._lunar_view = view
    app._lunar_server = server
    app._lunar_server_thread = server_thread

    window.show()
    return app.exec()


def main(argv=None):
    args = parse_args(argv)
    try:
        auth = AuthManager()
    except OSError as exc:
        print(f"[ERRORE] Archivio di autenticazione non accessibile: {exc}", file=sys.stderr)
        return 2
    try:
        server = create_server(args.host, args.port, auth=auth)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(f"[ERRORE] La porta {args.port} su {args.host} è già in uso.\n"
                  f"         Chiudi l'altra istanza oppure scegli un'altra porta:\n"
                  f"         python src/ui_web/app.py --port {args.port + 1}", file=sys.stderr)
            return 2
        print(f"[ERRORE] Impossibile avviare il server su {args.host}:{args.port}: {exc}",
              file=sys.stderr)
        return 2

    bound_host, bound_port = server.server_address[:2]
    display_host = "127.0.0.1" if bound_host in ("0.0.0.0", "") else bound_host
    if ":" in display_host:
        display_host = f"[{display_host}]"
    url = f"http://{display_host}:{bound_port}/"

    if not _is_loopback(args.host):
        print(f"[ATTENZIONE] Server in ascolto su {args.host}: la piattaforma è raggiungibile da "
              "altre macchine. Il login è attivo ma il traffico è HTTP in chiaro: usare una rete "
              "fidata o un reverse proxy HTTPS (e LUNAR_COOKIE_SECURE=1).", file=sys.stderr)
    if not auth.configured:
        print("[INFO] Nessun account configurato: la piattaforma pubblica è già utilizzabile.\n"
              "       Per i Pianificatori di missione apri /dashboard nel browser\n"
              "       e crea l'account amministratore (archivio: "
              f"{auth.users.path}).")


    # SIGTERM (kill, chiusura della sessione) esegue la stessa pulizia di Ctrl+C
    # (arresto del Mission Engine e chiusura del server).
    def _terminate(signum, frame):
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, _terminate)
        if hasattr(signal, "SIGHUP"):
            signal.signal(signal.SIGHUP, _terminate)
    except ValueError:
        pass  # non nel thread principale (uso programmatico)

    server_thread = Thread(target=server.serve_forever, name="lunar-http-server", daemon=True)
    server_thread.start()
    print(f"Lunar South Pole Planner — piattaforma pubblica su {url}  · Pianificatori di missione "
          f"(login) su {url}dashboard  (Ctrl+C per terminare)",
          flush=True)

    try:
        if args.desktop:
            return _run_desktop(url, server, server_thread)
        if not args.no_browser:
            Timer(0.5, webbrowser.open, args=(url,)).start()
        server_thread.join()
        return 0
    except KeyboardInterrupt:
        print("\nArresto del server.", flush=True)
        return 0
    finally:
        MISSIONS.shutdown()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)


if __name__ == "__main__":
    raise SystemExit(main())
