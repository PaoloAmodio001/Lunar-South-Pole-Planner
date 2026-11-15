# Last updated: 2026-11-15
"""Autenticazione condivisa per la sezione MISSION PLANNERS.

Unico sistema di login della piattaforma: protegge soltanto la sezione
Pianificatori di missione (``/dashboard``, ``/mission-control`` e le API dei
pianificatori, vedi ``PROTECTED_PATHS``/``PROTECTED_PREFIXES`` in
``src/ui_web/app.py``). Il resto della piattaforma è pubblico.

Scelte di sicurezza (solo libreria standard, nessuna dipendenza aggiunta):

- password conservate **solo** come hash ``scrypt`` (N=2^15, r=8, p=1, sale
  casuale di 16 byte), confrontate con ``hmac.compare_digest``;
- nessuna credenziale predefinita: finché l'archivio utenti è vuoto la pagina
  di accesso mostra soltanto il modulo "Crea account amministratore"
  (``UserStore.create_first_user``), consentito una sola volta e in modo
  atomico; dopo la creazione resta solo il normale login;
- archivio utenti e sessioni **fuori dal repository**, in
  ``$LUNAR_AUTH_DIR`` oppure ``~/.config/lunar-mission-control/``, con
  permessi 0600 (directory 0700);
- token di sessione casuali (256 bit) consegnati solo in un cookie
  ``HttpOnly; SameSite=Strict``; su disco si salva soltanto lo SHA-256 del
  token, mai il token stesso. Il JavaScript non vede né token né password;
- scadenza per inattività e scadenza assoluta; le sessioni sopravvivono al
  riavvio del server (sessione persistente) e il logout le revoca;
- limitazione dei tentativi falliti per indirizzo IP e per nome utente.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
import time
from pathlib import Path

try:  # lock tra processi (server e auth_admin.py); assente solo su Windows
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

COOKIE_NAME = "lmc_session"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024

# scrypt: ~32 MiB di memoria per hash (128 * N * r).
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SCRYPT_MAXMEM = 64 * 1024 * 1024

DEFAULT_IDLE_MINUTES = 30
DEFAULT_ABSOLUTE_HOURS = 12

# Limitazione tentativi: oltre MAX_FAILURES errori nella finestra, blocco temporaneo.
MAX_FAILURES = 5
FAILURE_WINDOW_S = 15 * 60
LOCKOUT_S = 15 * 60


def default_auth_dir() -> Path:
    env = os.environ.get("LUNAR_AUTH_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME", "").strip() or str(Path.home() / ".config")
    return Path(base).expanduser() / "lunar-mission-control"


def _env_number(name, default, minimum, maximum):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return min(maximum, max(minimum, value))


# --------------------------------------------------------------------------- #
# Hash delle password
# --------------------------------------------------------------------------- #
def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def hash_password(password: str) -> str:
    if not isinstance(password, str) or not password:
        raise ValueError("Password vuota.")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                            p=SCRYPT_P, dklen=SCRYPT_DKLEN, maxmem=SCRYPT_MAXMEM)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        # Parametri plausibili: evita hash malevoli che esauriscono la memoria.
        if not (2 ** 14 <= n <= 2 ** 20 and 1 <= r <= 16 and 1 <= p <= 4):
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                                dklen=len(expected), maxmem=max(SCRYPT_MAXMEM, 256 * n * r))
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


def validate_new_password(password: str, username: str = "") -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("Password troppo lunga.")
    if username and password.lower() == username.lower():
        raise ValueError("La password non può coincidere con il nome utente.")


# --------------------------------------------------------------------------- #
# Archivio su file (scrittura atomica, permessi restrittivi)
# --------------------------------------------------------------------------- #
def _ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, type(default)) else default
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError):
        return default


def _write_json_private(path: Path, data) -> None:
    _ensure_private_dir(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class FirstUserError(ValueError):
    """Creazione del primo account rifiutata; ``code`` è un identificatore stabile."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class UserStore:
    """Utenti in ``users.json``: {"users": {nome: {"password_hash", "created_utc", ...}}}."""

    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory else default_auth_dir()
        self.path = self.directory / "users.json"
        self._lock = threading.Lock()

    def _load(self):
        data = _read_json(self.path, {})
        users = data.get("users") if isinstance(data, dict) else None
        return users if isinstance(users, dict) else {}

    @contextlib.contextmanager
    def _exclusive(self):
        """Lock esclusivo sull'archivio: thread del server e altri processi (CLI)."""
        with self._lock:
            fd = None
            if fcntl is not None:
                _ensure_private_dir(self.directory)
                fd = os.open(str(self.directory / "users.lock"), os.O_RDWR | os.O_CREAT, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fd is not None:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                    finally:
                        os.close(fd)

    def _load_strict(self):
        """Utenti presenti, oppure None se il file esiste ma non è leggibile/valido."""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        users = data.get("users", {})
        return users if isinstance(users, dict) else None

    def create_first_user(self, username: str, password: str) -> None:
        """Crea il primo account (amministratore) solo se l'archivio è vuoto.

        Atomica: verifica e scrittura avvengono sotto lo stesso lock esclusivo,
        quindi due richieste concorrenti non possono creare due amministratori.
        Un archivio presente ma illeggibile non viene mai sovrascritto.
        """
        username = username or ""
        password = password or ""
        if not USERNAME_RE.match(username):
            raise FirstUserError("username", "Nome utente non valido: 3-32 caratteri tra lettere, cifre, _ . -")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise FirstUserError("password_short",
                                 f"La password deve avere almeno {MIN_PASSWORD_LENGTH} caratteri.")
        if len(password) > MAX_PASSWORD_LENGTH:
            raise FirstUserError("password_long", "Password troppo lunga.")
        if password.lower() == username.lower():
            raise FirstUserError("password_same", "La password non può coincidere con il nome utente.")
        with self._exclusive():
            existing = self._load_strict()
            if existing is None:
                raise FirstUserError("store_unreadable",
                                     f"Archivio utenti illeggibile: {self.path}")
            if existing:
                raise FirstUserError("already_configured", "Esiste già un account.")
            now = _utc_now()
            entry = {
                "created_utc": now,
                "role": "admin",
                "password_hash": hash_password(password),
                "password_changed_utc": now,
                "password_version": secrets.token_hex(8),
            }
            _write_json_private(self.path, {"schema": "lunar-auth-users/1.0",
                                            "users": {username: entry}})

    def has_users(self) -> bool:
        return bool(self._load())

    def list_users(self):
        return sorted(self._load())

    def get(self, username):
        entry = self._load().get(username)
        return entry if isinstance(entry, dict) else None

    def set_password(self, username: str, password: str, *, create: bool) -> None:
        if not USERNAME_RE.match(username or ""):
            raise ValueError("Nome utente non valido: 3-32 caratteri tra lettere, cifre, _ . -")
        validate_new_password(password, username)
        with self._exclusive():
            users = self._load()
            if create and username in users:
                raise ValueError(f"L'utente {username!r} esiste già.")
            if not create and username not in users:
                raise ValueError(f"L'utente {username!r} non esiste.")
            entry = users.get(username, {"created_utc": _utc_now()})
            entry["password_hash"] = hash_password(password)
            entry["password_changed_utc"] = _utc_now()
            entry["password_version"] = secrets.token_hex(8)
            users[username] = entry
            _write_json_private(self.path, {"schema": "lunar-auth-users/1.0", "users": users})

    def remove(self, username: str) -> bool:
        with self._exclusive():
            users = self._load()
            if username not in users:
                return False
            del users[username]
            _write_json_private(self.path, {"schema": "lunar-auth-users/1.0", "users": users})
            return True


def _utc_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------------------- #
# Sessioni
# --------------------------------------------------------------------------- #
def _token_id(token: str) -> str:
    return hashlib.sha256(token.encode("ascii", "ignore")).hexdigest()


class AuthManager:
    """Login, sessioni e limitazione dei tentativi. Thread-safe."""

    def __init__(self, directory: Path | None = None, *, idle_minutes=None,
                 absolute_hours=None, secure_cookie=None):
        self.users = UserStore(directory)
        self.directory = self.users.directory
        self.sessions_path = self.directory / "sessions.json"
        self.idle_s = 60 * (idle_minutes if idle_minutes is not None else _env_number(
            "LUNAR_SESSION_IDLE_MINUTES", DEFAULT_IDLE_MINUTES, 5, 24 * 60))
        self.absolute_s = 3600 * (absolute_hours if absolute_hours is not None else _env_number(
            "LUNAR_SESSION_MAX_HOURS", DEFAULT_ABSOLUTE_HOURS, 1, 24 * 30))
        if secure_cookie is None:
            secure_cookie = os.environ.get("LUNAR_COOKIE_SECURE", "") not in ("", "0")
        self.secure_cookie = bool(secure_cookie)
        self._lock = threading.Lock()
        self._sessions_mtime = None
        self._sessions = self._load_sessions()
        self._failures = {}   # chiave -> [timestamps]
        self._locked_until = {}
        self._last_persist = 0.0
        # Hash fittizio: tempo di verifica costante anche per utenti inesistenti.
        self._dummy_hash = hash_password(secrets.token_urlsafe(16))

    # -- persistenza ------------------------------------------------------- #
    def _sessions_file_mtime(self):
        try:
            return self.sessions_path.stat().st_mtime_ns
        except OSError:
            return None

    def _load_sessions(self):
        self._sessions_mtime = self._sessions_file_mtime()
        data = _read_json(self.sessions_path, {})
        sessions = data.get("sessions") if isinstance(data, dict) else None
        if not isinstance(sessions, dict):
            return {}
        now = time.time()
        return {
            sid: s for sid, s in sessions.items()
            if isinstance(s, dict) and s.get("expires_at", 0) > now
            and now - s.get("last_seen", 0) < self.idle_s
        }

    def _persist(self, force=False):
        now = time.time()
        if not force and now - self._last_persist < 60:
            return
        self._last_persist = now
        try:
            _write_json_private(self.sessions_path,
                                {"schema": "lunar-auth-sessions/1.0", "sessions": self._sessions})
            self._sessions_mtime = self._sessions_file_mtime()
        except OSError:
            pass  # le sessioni restano valide in memoria

    def _reload_if_changed(self):
        """Ricarica le sessioni se il file è stato modificato da fuori (CLI revoke)."""
        current = self._sessions_file_mtime()
        if current is not None and current != self._sessions_mtime:
            self._sessions = self._load_sessions()

    # -- limitazione tentativi ---------------------------------------------- #
    def _is_locked(self, key, now):
        until = self._locked_until.get(key, 0)
        return until > now

    def lockout_remaining(self, client_ip, username):
        now = time.time()
        with self._lock:
            remaining = max(self._locked_until.get(("ip", client_ip), 0),
                            self._locked_until.get(("user", username), 0)) - now
        return max(0, int(remaining))

    def _record_failure(self, key, now):
        recent = [t for t in self._failures.get(key, []) if now - t < FAILURE_WINDOW_S]
        recent.append(now)
        self._failures[key] = recent
        if len(recent) >= MAX_FAILURES:
            self._locked_until[key] = now + LOCKOUT_S
            self._failures[key] = []

    # -- API pubblica -------------------------------------------------------- #
    @property
    def configured(self) -> bool:
        return self.users.has_users()

    def login(self, username: str, password: str, client_ip: str):
        """Restituisce (token, None) oppure (None, codice_errore).

        Codici: ``not_configured``, ``locked``, ``invalid``.
        """
        username = (username or "").strip()
        password = password or ""
        if not self.configured:
            return None, "not_configured"
        now = time.time()
        with self._lock:
            if self._is_locked(("ip", client_ip), now) or self._is_locked(("user", username), now):
                return None, "locked"
        entry = self.users.get(username) if USERNAME_RE.match(username) else None
        stored = entry.get("password_hash") if entry else None
        ok = verify_password(password[:MAX_PASSWORD_LENGTH], stored or self._dummy_hash)
        ok = ok and stored is not None
        with self._lock:
            if not ok:
                self._record_failure(("ip", client_ip), now)
                self._record_failure(("user", username), now)
                return None, "invalid"
            self._failures.pop(("user", username), None)
            token = secrets.token_urlsafe(32)
            self._reload_if_changed()
            self._sessions[_token_id(token)] = {
                "user": username, "created_at": now, "last_seen": now,
                "expires_at": now + self.absolute_s,
                # Versione della password: un cambio password invalida la sessione.
                "pwd_stamp": entry.get("password_version"),
            }
            self._persist(force=True)
        return token, None

    def validate(self, token: str | None, touch: bool = True):
        """Restituisce (sessione, None) oppure (None, 'missing'|'expired').

        ``touch=False`` per i controlli automatici (stato, polling): verificano la
        sessione senza rinnovarne la scadenza per inattività.
        """
        if not token or len(token) > 128:
            return None, "missing"
        sid = _token_id(token)
        now = time.time()
        with self._lock:
            self._reload_if_changed()
            session = self._sessions.get(sid)
            if session is None:
                return None, "expired"
            if session["expires_at"] <= now or now - session["last_seen"] >= self.idle_s:
                del self._sessions[sid]
                self._persist(force=True)
                return None, "expired"
            # Un utente rimosso, o con password cambiata, perde subito l'accesso.
            user = self.users.get(session["user"])
            if user is None or user.get("password_version") != session.get("pwd_stamp"):
                del self._sessions[sid]
                self._persist(force=True)
                return None, "expired"
            if touch:
                session["last_seen"] = now
                self._persist()
            return dict(session), None

    def logout(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            if self._sessions.pop(_token_id(token), None) is not None:
                self._persist(force=True)

    def revoke_user(self, username: str) -> int:
        with self._lock:
            self._reload_if_changed()
            victims = [sid for sid, s in self._sessions.items() if s.get("user") == username]
            for sid in victims:
                del self._sessions[sid]
            self._persist(force=True)
        return len(victims)

    # -- cookie -------------------------------------------------------------- #
    def session_cookie(self, token: str) -> str:
        parts = [f"{COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Strict",
                 f"Max-Age={int(self.absolute_s)}"]
        if self.secure_cookie:
            parts.append("Secure")
        return "; ".join(parts)

    def clear_cookie(self) -> str:
        parts = [f"{COOKIE_NAME}=", "Path=/", "HttpOnly", "SameSite=Strict", "Max-Age=0"]
        if self.secure_cookie:
            parts.append("Secure")
        return "; ".join(parts)


def token_from_cookie_header(header: str | None) -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == COOKIE_NAME and value:
            return value.strip()
    return None


def safe_next_path(value: str | None, default: str = "/dashboard") -> str:
    """Accetta solo percorsi locali (evita open redirect)."""
    if not value or not isinstance(value, str):
        return default
    if not value.startswith("/") or value.startswith("//") or "\\" in value:
        return default
    if any(ord(c) < 0x20 for c in value) or len(value) > 512:
        return default
    return value
