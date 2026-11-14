# Last updated: 2026-11-14
"""Punto di ingresso ufficiale della Web UI di Lunar South Pole Planner.

Uso:
    python src/ui_web/app.py                    # server locale + browser (default)
    python src/ui_web/app.py --port 9000        # porta alternativa
    python src/ui_web/app.py --no-browser       # solo server
    python src/ui_web/app.py --desktop          # finestra desktop PySide6 (opzionale)

Variabili d'ambiente equivalenti: LUNAR_UI_HOST, LUNAR_UI_PORT, LUNAR_UI_NO_BROWSER=1.
Il server espone soltanto le risorse elencate in una whitelist esplicita.
"""
import argparse
import errno
import ipaddress
import json
import os
import re
import shutil
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread, Timer
from urllib.parse import urlparse, parse_qs, unquote

PROJECT_ROOT = Path(__file__).resolve().parents[2]
UI_DIR = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.astronomy import SITES, query_observations, AstronomyError
from src.mission_planning import find_operational_windows
from src.mission_analytics import summarize_ephemerides
from src.communications import calculate_link_budget
from src.thermal_model import simulate_single_node_thermal
from src.ui_web import mission_runner
from src.ui_web.mission_runner import ConfigError, MissionBusyError

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
STATIC_ROUTES = {
    "/": UI_DIR / "index.html",
    "/index.html": UI_DIR / "index.html",
    "/main.js": UI_DIR / "main.js",
    "/mission.js": UI_DIR / "mission.js",
    "/data/terrain/global/Moon_NASA_LRO_8k_Topo_Small.glb":
        PROJECT_ROOT / "data" / "terrain" / "global" / "Moon_NASA_LRO_8k_Topo_Small.glb",
}
LEGACY_REDIRECTS = {
    "/src/ui_web/index.html": "/",
    "/src/ui_web/": "/",
}
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".glb": "model/gltf-binary",
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
    return None


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
            size = target.stat().st_size
            stream = target.open("rb")
        except OSError:
            return self.send_json(404, {"status": "error", "error": "Risorsa non trovata."})
        with stream:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-cache")
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
        return self.send_static(unquote(parsed.path), head_only=True)

    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

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

    def do_POST(self):
        parsed = urlparse(self.path)
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
                    "Nessun timestamp comune tra le effemeridi di Sole e Terra."
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

        except (ValueError, TypeError) as exc:
            return self.send_json(400, {"status": "error", "error": str(exc)})
        except Exception as exc:
            return self.send_json(502, {
                "status": "error",
                "error": f"Calcolo astronomico non disponibile: {exc}",
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


def create_server(host, port):
    """Crea il server HTTP; solleva OSError se la porta non è disponibile."""
    return ThreadingHTTPServer((host, port), Handler)


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
        server = create_server(args.host, args.port)
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
        print(f"[ATTENZIONE] Server in ascolto su {args.host}: la UI è raggiungibile da altre "
              "macchine della rete e non prevede autenticazione.", file=sys.stderr)

    server_thread = Thread(target=server.serve_forever, name="lunar-http-server", daemon=True)
    server_thread.start()
    print(f"Lunar South Pole Planner — Web UI attiva su {url}  (Ctrl+C per terminare)",
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
