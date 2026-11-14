# Last updated: 2026-11-14
"""Integrazione Web UI → Mission Orchestrator (F1).

Questo modulo NON contiene logica scientifica. Si limita a:
- validare (in modo conservativo) una configurazione di missione;
- eseguire il vero orchestratore (``python -m src.mission_orchestrator``) in un
  sottoprocesso con ``cwd=PROJECT_ROOT``, come da CLI ufficiale;
- tracciare lo stato dell'esecuzione e restituire i risultati realmente scritti
  dal motore in ``mission_report.json``.

Perché un sottoprocesso: l'orchestratore risolve tutti i percorsi (DEM, output,
``Path.cwd()``) rispetto alla directory corrente ed è sincrono e senza callback
di avanzamento. Eseguirlo in un processo separato con cwd fissata evita
``os.chdir`` nel server multi-thread, non blocca il server e isola eventuali
crash del motore.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / "reports" / "web_runs"
RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_CONFIG_BYTES = 256 * 1024
TAIL_BYTES = 8 * 1024

# Configurazioni selezionabili dal browser: solo identificativi, mai percorsi.
CONFIG_CATALOG = {
    "example": {
        "label": "mission_config.example.json (configurazione di esempio)",
        "path": PROJECT_ROOT / "mission_config.example.json",
    },
}

# Chiavi che l'orchestratore legge come percorsi di input.
READ_PATH_KEYS = {
    "dem_path", "lola_path", "lroc_path", "confidence_path", "density_path",
    "error_path", "lola_density_path", "lola_error_path", "horizon_json",
    "raster_path", "comparison_path",
}
ALLOWED_READ_ROOTS = ("data", "reports")
ALLOWED_WRITE_ROOTS = ("reports",)

# Specchio (solo informativo) delle regole di attivazione dell'orchestratore:
# True  → la sezione viene eseguita se presente, indipendentemente da "enabled";
# "default_on" → eseguita salvo enabled=false; altrimenti richiede enabled=true.
ALWAYS_RUN_SECTIONS = {
    "descent_hazard_detection", "site_selection", "lola_lroc_quality", "rover_path",
}
DEFAULT_ON_SECTIONS = {"mission_report"}
OPT_IN_SECTIONS = {
    "astronomy", "illumination", "local_site_analysis", "confidence_validation",
    "data_quality", "horizon_analysis", "visibility_analysis", "site_assessment",
    "lunar_geometry", "descent_risk_map", "energy", "fleet", "journal",
}
KNOWN_TOP_LEVEL = ALWAYS_RUN_SECTIONS | DEFAULT_ON_SECTIONS | OPT_IN_SECTIONS | {"output_dir"}

# Stati finali dell'orchestratore (mission_report.json → "status").
SUCCESS_STATUSES = {"completed", "completed_preliminary", "completed_with_warnings"}
ERROR_STATUSES = {"completed_with_errors"}


class ConfigError(ValueError):
    """Configurazione non utilizzabile (formato o sicurezza)."""


class MissionBusyError(RuntimeError):
    def __init__(self, running_id):
        super().__init__("Una missione è già in esecuzione.")
        self.running_id = running_id


# --------------------------------------------------------------------------- #
# Configurazione
# --------------------------------------------------------------------------- #
def list_configs():
    return [
        {"id": cid, "label": entry["label"], "available": entry["path"].is_file()}
        for cid, entry in CONFIG_CATALOG.items()
    ]


def load_catalog_config(config_id):
    entry = CONFIG_CATALOG.get(config_id)
    if entry is None:
        raise ConfigError(f"Configurazione sconosciuta: {config_id!r}.")
    try:
        data = json.loads(entry["path"].read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"File di configurazione assente: {entry['path'].name}.") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JSON non valido in {entry['path'].name}: {exc}") from exc
    return data


def section_activation(name, cfg):
    """Restituisce True se l'orchestratore eseguirà la sezione."""
    if not isinstance(cfg, dict):
        return False
    if name in ALWAYS_RUN_SECTIONS:
        return True
    if name in DEFAULT_ON_SECTIONS:
        return bool(cfg.get("enabled", True))
    return bool(cfg.get("enabled", False))


def _safe_relative(value, roots):
    """Percorso relativo, senza '..', dentro PROJECT_ROOT/<root>. Ritorna Path assoluto."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("percorso vuoto o non testuale")
    if "\x00" in value or "\\" in value:
        raise ConfigError("caratteri non ammessi nel percorso")
    pure = PurePosixPath(value)
    if pure.is_absolute() or value.startswith("~"):
        raise ConfigError("sono ammessi solo percorsi relativi al progetto")
    if any(part == ".." for part in pure.parts):
        raise ConfigError("'..' non ammesso")
    if not pure.parts or pure.parts[0] not in roots:
        raise ConfigError(f"il percorso deve iniziare con {' o '.join(r + '/' for r in roots)}")
    resolved = (PROJECT_ROOT / pure).resolve()
    base = PROJECT_ROOT.resolve()
    if base not in resolved.parents:
        raise ConfigError("il percorso esce dal progetto")
    return resolved


def validate_config(config, *, check_site_identity=True):
    """Validazione preventiva. Non modifica la configurazione.

    Restituisce ``{"valid", "errors", "warnings", "sections", "site_identity"}``.
    Gli errori bloccano l'avvio; gli avvisi (es. file di input mancanti) no:
    in quel caso lo step dell'orchestratore fallirà e verrà riportato come tale.
    """
    errors, warnings, sections = [], [], []
    result = {"valid": False, "errors": errors, "warnings": warnings,
              "sections": sections, "site_identity": None}

    if not isinstance(config, dict):
        errors.append("La configurazione deve essere un oggetto JSON.")
        return result
    try:
        size = len(json.dumps(config, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    except (TypeError, ValueError) as exc:
        errors.append(f"Configurazione non serializzabile in JSON standard: {exc}")
        return result
    if size > MAX_CONFIG_BYTES:
        errors.append(f"Configurazione troppo grande ({size} byte, max {MAX_CONFIG_BYTES}).")
        return result

    for key in config:
        if key not in KNOWN_TOP_LEVEL:
            warnings.append(f"Sezione sconosciuta '{key}': ignorata dall'orchestratore.")
    if "output_dir" in config:
        warnings.append("output_dir viene sostituito dalla Web UI con una cartella "
                        "dedicata all'esecuzione (reports/web_runs/<id>/output).")

    for name, cfg in config.items():
        if name == "output_dir":
            continue
        if cfg is not None and not isinstance(cfg, dict):
            if name in KNOWN_TOP_LEVEL:
                errors.append(f"La sezione '{name}' deve essere un oggetto JSON.")
            continue
        if not isinstance(cfg, dict):
            continue
        active = section_activation(name, cfg) if name in KNOWN_TOP_LEVEL else False
        if name in KNOWN_TOP_LEVEL:
            sections.append({"name": name, "active": active})
        for key, value in cfg.items():
            where = f"{name}.{key}"
            if key in READ_PATH_KEYS and value is not None:
                try:
                    resolved = _safe_relative(value, ALLOWED_READ_ROOTS)
                except ConfigError as exc:
                    errors.append(f"{where}: {exc}.")
                    continue
                if active and not resolved.is_file():
                    warnings.append(f"{where}: file non trovato ({value}); "
                                    "lo step fallirà se lo richiede.")
            elif key == "report_name" and value is not None:
                if (not isinstance(value, str) or not value or value in (".", "..")
                        or value.startswith(".") or "/" in value or "\\" in value
                        or "\x00" in value):
                    errors.append(f"{where}: deve essere un semplice nome di file.")
            elif name == "journal" and key == "path" and value is not None:
                try:
                    _safe_relative(value, ALLOWED_WRITE_ROOTS)
                except ConfigError as exc:
                    errors.append(f"{where}: {exc}.")

    if errors:
        return result

    if check_site_identity:
        result["site_identity"] = _preflight_site_identity(config, errors)
        if errors:
            return result

    result["valid"] = True
    return result


def _preflight_site_identity(config, errors):
    """Esegue il controllo preventivo dell'orchestratore stesso.

    ``validate_mission_site_identity`` apre i raster con percorsi relativi alla
    cwd; qui i percorsi (già validati) vengono resi assoluti su una COPIA.
    """
    from src.lunar_geometry import SiteIdentityError
    from src.mission_orchestrator import validate_mission_site_identity

    absolute = json.loads(json.dumps(config))
    for cfg in absolute.values():
        if isinstance(cfg, dict):
            for key, value in list(cfg.items()):
                if key in READ_PATH_KEYS and isinstance(value, str):
                    cfg[key] = str(PROJECT_ROOT / value)
    try:
        summary = validate_mission_site_identity(absolute)
    except SiteIdentityError as exc:
        errors.append(f"Controllo identità del sito: {exc}")
        return None
    except Exception as exc:  # raster illeggibile, ecc.
        errors.append(f"Controllo identità del sito non eseguibile: "
                      f"{type(exc).__name__}: {exc}")
        return None
    for item in summary.get("rasters_checked", []):
        if isinstance(item.get("raster_path"), str):
            try:
                item["raster_path"] = str(Path(item["raster_path"]).relative_to(PROJECT_ROOT))
            except ValueError:
                pass
    return summary


def config_fingerprint(config):
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Esecuzione
# --------------------------------------------------------------------------- #
def _now():
    return datetime.now(timezone.utc).isoformat()


def _tail(path, limit=TAIL_BYTES):
    try:
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - limit))
            return stream.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _relative_to_project(path):
    try:
        return str(Path(path).resolve().relative_to(PROJECT_ROOT.resolve()))
    except (ValueError, OSError):
        return str(path)


class MissionManager:
    """Gestisce una sola missione alla volta (prevenzione avvii concorrenti)."""

    def __init__(self, runs_dir=RUNS_DIR, command_factory=None, python=sys.executable):
        self.runs_dir = Path(runs_dir)
        self._lock = threading.Lock()
        self._jobs = {}
        self._running_id = None
        self._processes = {}
        self._python = python
        self._command_factory = command_factory or self._default_command

    def _default_command(self, config_path):
        return [self._python, "-m", "src.mission_orchestrator", str(config_path)]

    # -- persistenza ------------------------------------------------------- #
    def _run_dir(self, run_id):
        if not RUN_ID_RE.match(run_id or ""):
            raise KeyError(run_id)
        return self.runs_dir / run_id

    def _save(self, job):
        target = self._run_dir(job["id"]) / "job.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(target)

    def get(self, run_id):
        run_dir = self._run_dir(run_id)
        with self._lock:
            job = self._jobs.get(run_id)
            if job is not None:
                return dict(job)
        path = run_dir / "job.json"
        if not path.is_file():
            raise KeyError(run_id)
        job = json.loads(path.read_text(encoding="utf-8"))
        if job.get("state") == "running":
            # Server riavviato durante l'esecuzione: esito non osservato.
            job["state"] = "failed"
            job["failure_reason"] = ("Esecuzione interrotta: il server Web è stato "
                                     "riavviato prima del termine.")
        return job

    def list_runs(self, limit=20):
        runs = []
        if self.runs_dir.is_dir():
            for path in self.runs_dir.iterdir():
                if RUN_ID_RE.match(path.name) and (path / "job.json").is_file():
                    try:
                        job = self.get(path.name)
                    except (KeyError, OSError, json.JSONDecodeError):
                        continue
                    runs.append({k: job.get(k) for k in (
                        "id", "state", "engine_status", "config_label",
                        "created_utc", "finished_utc")})
        runs.sort(key=lambda j: j.get("created_utc") or "", reverse=True)
        return runs[:limit]

    @property
    def running_id(self):
        with self._lock:
            return self._running_id

    # -- avvio ------------------------------------------------------------- #
    def start(self, config, config_label):
        validation = validate_config(config)
        if not validation["valid"]:
            raise ConfigError("; ".join(validation["errors"]))

        with self._lock:
            if self._running_id is not None:
                raise MissionBusyError(self._running_id)
            run_id = uuid.uuid4().hex
            self._running_id = run_id

        try:
            run_dir = self._run_dir(run_id)
            output_dir = run_dir / "output"
            output_dir.mkdir(parents=True, exist_ok=False)
            effective = dict(config)
            effective["output_dir"] = _relative_to_project(output_dir)
            config_path = run_dir / "config.json"
            config_path.write_text(json.dumps(effective, indent=2, ensure_ascii=False),
                                   encoding="utf-8")
            job = {
                "id": run_id,
                "state": "running",
                "engine_status": None,
                "config_label": config_label,
                "config_sha256": config_fingerprint(config),
                "config_path": _relative_to_project(config_path),
                "output_dir": _relative_to_project(output_dir),
                "created_utc": _now(),
                "started_monotonic": time.monotonic(),
                "finished_utc": None,
                "exit_code": None,
                "failure_reason": None,
                "validation_warnings": validation["warnings"],
            }
            stdout = (run_dir / "stdout.log").open("wb")
            stderr = (run_dir / "stderr.log").open("wb")
            try:
                process = subprocess.Popen(
                    self._command_factory(config_path),
                    cwd=str(PROJECT_ROOT), stdout=stdout, stderr=stderr,
                    stdin=subprocess.DEVNULL,
                )
            finally:
                stdout.close()
                stderr.close()
            job["pid"] = process.pid
            with self._lock:
                self._jobs[run_id] = job
                self._processes[run_id] = process
            self._save(job)
        except Exception:
            with self._lock:
                self._running_id = None
            raise

        threading.Thread(target=self._watch, args=(run_id, process),
                         name=f"mission-{run_id[:8]}", daemon=True).start()
        return dict(job)

    def _watch(self, run_id, process):
        exit_code = process.wait()
        run_dir = self._run_dir(run_id)
        report_path = run_dir / "output" / "mission_report.json"
        update = {"exit_code": exit_code, "finished_utc": _now()}
        engine_status = None
        if report_path.is_file():
            try:
                engine_status = json.loads(report_path.read_text(encoding="utf-8")).get("status")
            except (OSError, json.JSONDecodeError) as exc:
                update["failure_reason"] = f"mission_report.json illeggibile: {exc}"
        update["engine_status"] = engine_status
        if engine_status in SUCCESS_STATUSES:
            update["state"] = "completed"
        elif engine_status in ERROR_STATUSES:
            update["state"] = "completed_with_errors"
        else:
            update["state"] = "failed"
            if not update.get("failure_reason"):
                message = (_tail(run_dir / "stdout.log", 2000).strip()
                           or _tail(run_dir / "stderr.log", 2000).strip())
                update["failure_reason"] = (
                    f"L'orchestratore non ha prodotto un report valido "
                    f"(exit code {exit_code}). {message}".strip())
        with self._lock:
            job = self._jobs.get(run_id, {})
            job.update(update)
            self._processes.pop(run_id, None)
            if self._running_id == run_id:
                self._running_id = None
            snapshot = dict(job)
        self._save(snapshot)

    def wait(self, run_id, timeout=None):
        """Attende il termine (uso nei test)."""
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            job = self.get(run_id)
            if job["state"] != "running":
                return job
            if deadline is not None and time.monotonic() > deadline:
                raise TimeoutError(run_id)
            time.sleep(0.05)

    def shutdown(self):
        with self._lock:
            processes = list(self._processes.values())
        for process in processes:
            if process.poll() is None:
                process.terminate()

    # -- risultati --------------------------------------------------------- #
    def status_payload(self, run_id):
        job = self.get(run_id)
        payload = {k: v for k, v in job.items() if k not in ("started_monotonic", "pid")}
        if job["state"] == "running":
            started = job.get("started_monotonic")
            payload["elapsed_s"] = (round(time.monotonic() - started, 1)
                                    if isinstance(started, (int, float)) else None)
            payload["progress"] = ("Missione in esecuzione. L'orchestratore non espone "
                                   "avanzamento intermedio.")
            return payload
        payload["result"] = self.result_summary(run_id)
        if job["state"] == "failed":
            payload["stdout_tail"] = _tail(self._run_dir(run_id) / "stdout.log")
            payload["stderr_tail"] = _tail(self._run_dir(run_id) / "stderr.log")
        return payload

    def read_report(self, run_id):
        path = self._run_dir(run_id) / "output" / "mission_report.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def result_summary(self, run_id):
        """Riassunto fedele del report del motore; nessun valore ricalcolato."""
        report = self.read_report(run_id)
        if report is None:
            return None
        config = {}
        try:
            config = json.loads((self._run_dir(run_id) / "config.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

        steps = []
        for name, step in (report.get("steps") or {}).items():
            entry = {"name": name, "status": step.get("status")}
            if step.get("status") == "failed":
                entry["error"] = f"{step.get('error_type', '')}: {step.get('error', '')}"
            result = step.get("result")
            if isinstance(result, dict):
                entry["result_status"] = result.get("status")
            steps.append(entry)
        executed = {s["name"] for s in steps}
        if "mission_status_json" in (report.get("artifacts") or {}):
            executed.add("mission_report")  # registrato come artifact, non come step
        not_executed = []
        for name, cfg in config.items():
            if name in KNOWN_TOP_LEVEL and name != "output_dir" and name not in executed:
                reason = ("disabilitata nella configurazione"
                          if not section_activation(name, cfg)
                          else "attiva ma senza step registrato nel report")
                not_executed.append({"name": name, "reason": reason})

        artifacts = []
        for key, path in (report.get("artifacts") or {}).items():
            resolved = self._artifact_path(run_id, path)
            artifacts.append({
                "key": key,
                "path": _relative_to_project(path) if path else None,
                "downloadable": resolved is not None,
                "url": (f"/api/mission/runs/{run_id}/artifacts/{key}"
                        if resolved is not None else None),
            })

        return {
            "engine_run_id": report.get("run_id"),
            "engine_status": report.get("status"),
            "generated_utc": report.get("generated_utc"),
            "site_identity": report.get("site_identity"),
            "steps": steps,
            "not_executed": not_executed,
            "warnings": report.get("warnings", []),
            "artifacts": artifacts,
            "report_url": f"/api/mission/runs/{run_id}/report",
            "report_path": _relative_to_project(
                self._run_dir(run_id) / "output" / "mission_report.json"),
            "configuration": config,
            "site_ranking": self._site_ranking(run_id, report),
            "step_results": {
                name: step.get("result") for name, step in (report.get("steps") or {}).items()
                if name != "site_selection" and isinstance(step.get("result"), dict)
            },
        }

    def _site_ranking(self, run_id, report):
        step = (report.get("steps") or {}).get("site_selection")
        if not step:
            return {"available": False, "reason": "Step site_selection non eseguito."}
        if step.get("status") != "success":
            return {"available": False,
                    "reason": f"Step site_selection fallito: {step.get('error', '')}"}
        path = self._artifact_path(run_id, (report.get("artifacts") or {}).get("site_selection"))
        if path is None:
            return {"available": False, "reason": "File site_ranking non disponibile."}
        data = json.loads(path.read_text(encoding="utf-8"))
        candidates = []
        for rank, c in enumerate(data.get("top_candidates", []), start=1):
            score = c.get("score") or {}
            lq = c.get("lola_quality") or {}
            candidates.append({
                "rank": rank,
                "name": c.get("name"),
                "grid_row": c.get("grid_row"),
                "grid_col": c.get("grid_col"),
                "score_0_100": score.get("score_0_100"),
                "components_0_100": score.get("components_0_100"),
                "terrain_class": c.get("terrain_class"),
                "terrain_metrics": c.get("terrain_metrics"),
                "missing_metrics": c.get("missing_metrics"),
                "lola_quality": {
                    "status": lq.get("status"),
                    "positive_return_fraction": (lq.get("ldec") or {}).get(
                        "positive_return_fraction"),
                    "toterr": lq.get("toterr"),
                },
            })
        return {
            "available": True,
            "status": data.get("status"),
            "ranking_method": data.get("ranking_method"),
            "thresholds": data.get("thresholds"),
            "eligible_count": data.get("eligible_count"),
            "rejected_count": data.get("rejected_count"),
            "terrain_class_counts": (data.get("terrain_class_summary") or {}).get("counts"),
            "lola_quality_affects_score": (data.get("lola_quality_validation") or {}).get(
                "affects_score"),
            "warnings": data.get("warnings", []),
            "top_candidates": candidates,
        }

    def _artifact_path(self, run_id, path):
        """Solo file prodotti dentro la cartella di output di QUESTA esecuzione."""
        if not path:
            return None
        base = (self._run_dir(run_id) / "output").resolve()
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            return None
        if base not in candidate.parents or not candidate.is_file():
            return None
        return candidate

    def artifact_file(self, run_id, key):
        report = self.read_report(run_id)
        if report is None:
            return None
        return self._artifact_path(run_id, (report.get("artifacts") or {}).get(key))
