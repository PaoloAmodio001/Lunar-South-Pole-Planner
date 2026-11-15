# Last updated: 2026-11-15
"""Collegamento tra Lunar South Pole Planner e P-System.

Due livelli, entrambi supportati:

1. ``MissionJournal`` (invariato): journal JSONL locale con riconciliazione deterministica. Non
   decide i conflitti; li segnala come ``manual_resolution_required``.
2. ``PSystemBridge`` (nuovo): collegamento reale a un comitato di nodi P-System tramite il suo SDK.
   Ogni evento del planner diventa un *mission record* firmato (``sdk/mission.py`` di P-System):
   ha un'identità crittografica del nodo che lo produce, un'entità, una versione logica e il digest
   del contenuto. P-System lo verifica, decide una sola versione per ogni ``(mittente, nonce)``,
   sincronizza le decisioni tra i nodi e restituisce un certificato di quorum che il planner verifica
   con un light client (``ChainVerifier``) prima di usare il dato.

Store-and-forward: il journal del ``Wallet`` di P-System registra ogni evento *prima* di firmarlo.
Finché un evento non ha un certificato, ``flush`` lo reinvia identico (operazione sempre sicura in
P-System); dopo un riavvio i non confermati si ritrovano con ``Wallet.unfinished``.

Il codice di P-System non è copiato: viene importato dalla sua directory (``PSYSTEM_HOME`` o
``psystem_home`` in configurazione, predefinita ``~/Github P-system``).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
import uuid


# ---------------------------------------------------------------------------
# Livello 1: journal locale (compatibilità)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissionEvent:
    event_id: str
    node_id: str
    entity_id: str
    event_type: str
    logical_clock: int
    payload: dict
    created_unix: float
    def to_dict(self): return asdict(self)


class MissionJournal:
    def __init__(self, path: str | Path, node_id: str, bridge: "PSystemBridge | None" = None):
        if not node_id.strip(): raise ValueError("node_id obbligatorio")
        self.path, self.node_id = Path(path), node_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = 0
        self.bridge = bridge
        self.published = []
        for e in self.read_events(): self.clock=max(self.clock,e.logical_clock)

    def read_events(self):
        if not self.path.exists(): return []
        events=[]
        for number,line in enumerate(self.path.read_text(encoding="utf-8").splitlines(),1):
            if not line.strip(): continue
            try: events.append(MissionEvent(**json.loads(line)))
            except (ValueError, TypeError, KeyError) as exc: raise ValueError(f"Evento journal non valido alla riga {number}: {exc}") from exc
        return events

    def append(self, entity_id: str, event_type: str, payload: dict) -> MissionEvent:
        if not entity_id.strip() or not event_type.strip(): raise ValueError("entity_id ed event_type obbligatori")
        if not isinstance(payload,dict): raise ValueError("payload deve essere un oggetto")
        self.clock += 1
        event=MissionEvent(str(uuid.uuid4()),self.node_id,entity_id,event_type,self.clock,payload,time.time())
        with self.path.open("a",encoding="utf-8") as f: f.write(json.dumps(event.to_dict(),sort_keys=True,ensure_ascii=False)+"\n")
        if self.bridge is not None:
            # Il journal locale resta la copia di lavoro; P-System riceve lo stesso evento firmato.
            self.published.append(self.bridge.publish(
                self.node_id, entity_id, kind_for_event_type(event_type),
                {"event_type": event_type, "journal_event_id": event.event_id,
                 "logical_clock": event.logical_clock, "payload": payload}))
        return event

    @staticmethod
    def reconcile(event_lists):
        """Deduplica per event_id e ordina in modo ripetibile; non fonde conflitti."""
        unique={}
        for events in event_lists:
            for e in events:
                item=e if isinstance(e,MissionEvent) else MissionEvent(**e)
                unique.setdefault(item.event_id,item)
        ordered=sorted(unique.values(),key=lambda e:(e.logical_clock,e.node_id,e.event_id))
        latest={}
        conflicts=[]
        for e in ordered:
            prior=latest.get(e.entity_id)
            if prior and prior.logical_clock == e.logical_clock and prior.payload != e.payload:
                conflicts.append({"entity_id":e.entity_id,"event_ids":[prior.event_id,e.event_id],"status":"manual_resolution_required"})
            if prior is None or (e.logical_clock,e.node_id,e.event_id) > (prior.logical_clock,prior.node_id,prior.event_id): latest[e.entity_id]=e
        return {"events": [e.to_dict() for e in ordered], "latest_by_entity": {k:v.to_dict() for k,v in latest.items()}, "conflicts": conflicts, "connected_to_remote_psystem": False, "warning": "Riconciliazione locale del journal JSONL; per le decisioni di P-System usare PSystemBridge.reconciled_view()."}


def kind_for_event_type(event_type: str) -> str:
    """Tipo di record P-System per un event_type del planner."""
    lowered = event_type.lower()
    for prefix, kind in (("telemetry", "telemetry"), ("observation", "observation"),
                         ("plan", "plan"), ("command", "command"), ("status", "status"),
                         ("step_", "status"), ("mission_", "report"), ("result", "result")):
        if lowered.startswith(prefix):
            return kind
    return "result"


# ---------------------------------------------------------------------------
# Livello 2: P-System reale
# ---------------------------------------------------------------------------

DEFAULT_PSYSTEM_HOME = Path.home() / "Github P-system"


class PSystemUnavailable(RuntimeError):
    """SDK di P-System non importabile o nessun nodo raggiungibile."""


def load_psystem_sdk(home: str | Path | None = None):
    """Importa l'SDK di P-System dalla sua directory e restituisce i moduli usati."""
    root = Path(home or os.environ.get("PSYSTEM_HOME") or DEFAULT_PSYSTEM_HOME).expanduser()
    if not (root / "sdk" / "mission.py").is_file():
        raise PSystemUnavailable(f"SDK P-System con mission records non trovato in {root}")
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from crypto.identity import Identity
        from network.deployment import read_genesis
        from sdk import client, mission
    except ImportError as exc:
        raise PSystemUnavailable(f"Import dell'SDK P-System non riuscito: {exc}") from exc
    return {"Identity": Identity, "read_genesis": read_genesis, "client": client,
            "mission": mission, "root": root}


@dataclass
class BridgeConfig:
    node_urls: list[str]
    genesis_path: str
    state_dir: str
    psystem_home: str | None = None
    api_token: str | None = None
    timeout_s: float = 10.0
    tls_ca: str | None = None

    @classmethod
    def from_dict(cls, data: dict, root: Path | None = None) -> "BridgeConfig":
        base = Path(root) if root else Path.cwd()
        def resolve(value):
            if value is None:
                return None
            path = Path(value).expanduser()
            return str(path if path.is_absolute() else base / path)
        urls = data.get("node_urls") or []
        if not urls:
            raise ValueError("psystem.node_urls: almeno un nodo richiesto")
        return cls(node_urls=list(urls), genesis_path=resolve(data["genesis_path"]),
                   state_dir=resolve(data.get("state_dir", "reports/psystem_bridge")),
                   psystem_home=resolve(data.get("psystem_home")),
                   api_token=data.get("api_token"), timeout_s=float(data.get("timeout_s", 10.0)))


class LinkDown(ConnectionError):
    """Il collegamento verso P-System non è disponibile in questo momento."""


class DirectLink:
    """Collegamento sempre disponibile (rete locale o terrestre)."""

    def deliver(self, operation):
        return operation()


_OUTBOX = """
CREATE TABLE IF NOT EXISTS outbox (
    event_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    nonce INTEGER NOT NULL,
    entity TEXT NOT NULL,
    kind TEXT NOT NULL,
    version INTEGER NOT NULL,
    body_sha256 TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_utc TEXT NOT NULL,
    submitted_utc TEXT,
    certified_utc TEXT,
    decided_event_id TEXT,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS versions (
    node_id TEXT NOT NULL,
    entity TEXT NOT NULL,
    version INTEGER NOT NULL,
    PRIMARY KEY (node_id, entity)
);
"""

# Stati di un evento nell'outbox.
PENDING = "pending"            # firmato e registrato, non ancora accettato da un nodo
SUBMITTED = "submitted"        # accettato da un nodo: raccolta dei voti in corso
CERTIFIED = "certified"        # certificato di quorum verificato con il light client
SUPERSEDED = "superseded"      # il protocollo ha deciso un'altra versione per lo stesso nonce
REFUSED = "refused"            # un nodo l'ha rifiutato (firma, lock, limiti); si ritenta


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class PSystemBridge:
    """Pubblica eventi del planner come mission record P-System e legge quelli certificati."""

    def __init__(self, config: BridgeConfig, clock=None):
        self.config = config
        self.sdk = load_psystem_sdk(config.psystem_home)
        self.clock = clock or _now_utc
        self.state_dir = Path(config.state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        genesis = self.sdk["read_genesis"](Path(config.genesis_path))
        self.verifier = self.sdk["client"].ChainVerifier(genesis.committee, genesis.governance)
        self._db = sqlite3.connect(self.state_dir / "bridge.sqlite", isolation_level=None)
        self._db.execute("PRAGMA synchronous = FULL")
        self._db.executescript(_OUTBOX)
        self._wallets = {}
        self._signed = {}
        self.connected = False
        self.contacts = []

    # -- identità dei nodi di missione ------------------------------------------------

    def _wallet(self, node_id: str):
        wallet = self._wallets.get(node_id)
        if wallet is not None:
            return wallet
        if not node_id or "/" in node_id or node_id.startswith("."):
            raise ValueError(f"node_id non valido: {node_id!r}")
        directory = self.state_dir / "nodes" / node_id
        directory.mkdir(parents=True, exist_ok=True)
        key = directory / "identity.key"
        Identity = self.sdk["Identity"]
        if key.is_file():
            identity = Identity.load(key)
        else:
            identity = Identity.create()
            identity.save(key)
        mission = self.sdk["mission"]
        wallet = self.sdk["client"].Wallet(identity, directory / "records.sqlite",
                                           asset=mission.record_asset(identity.identity_id))
        self._wallets[node_id] = wallet
        for signed in wallet.unfinished(0):
            self._signed[signed.transfer.event_id()] = signed
        return wallet

    def account_of(self, node_id: str) -> str:
        return self._wallet(node_id).account

    def nodes(self) -> dict:
        directory = self.state_dir / "nodes"
        names = sorted(p.name for p in directory.iterdir()) if directory.is_dir() else []
        return {name: self.account_of(name) for name in names}

    # -- produzione -------------------------------------------------------------------

    def _next_version(self, node_id: str, entity: str) -> int:
        row = self._db.execute("SELECT version FROM versions WHERE node_id=? AND entity=?",
                               (node_id, entity)).fetchone()
        return 1 if row is None else row[0] + 1

    def publish(self, node_id: str, entity: str, kind: str, body: dict,
                version: int | None = None, produced_utc: str | None = None,
                parents: list[str] | tuple[str, ...] = ()) -> dict:
        """Firma e registra un record. Non lo invia: ``flush`` lo fa quando il collegamento c'è.

        ``parents`` sono gli id degli eventi da cui questo dipende (archi del DAG causale): P-System
        lo esegue solo dopo di loro, su ogni nodo, qualunque sia l'ordine di arrivo.
        """
        mission = self.sdk["mission"]
        wallet = self._wallet(node_id)
        version = self._next_version(node_id, entity) if version is None else int(version)
        record = mission.MissionRecord(entity=entity, kind=kind, version=version, body=body,
                                       origin=wallet.account, produced_utc=produced_utc or self.clock())
        signed = mission.sign_record(wallet, record, parents=tuple(sorted(set(parents))))
        event = signed.transfer
        event_id = event.event_id()
        self._signed[event_id] = signed
        self._db.execute("BEGIN IMMEDIATE")
        self._db.execute(
            "INSERT OR IGNORE INTO outbox (event_id, node_id, sender, nonce, entity, kind, version, "
            "body_sha256, status, created_utc) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (event_id, node_id, event.sender, event.nonce, entity, kind, version,
             mission.body_digest(body), PENDING, record.produced_utc))
        self._db.execute("INSERT INTO versions (node_id, entity, version) VALUES (?,?,?) "
                         "ON CONFLICT(node_id, entity) DO UPDATE SET version=MAX(version, excluded.version)",
                         (node_id, entity, version))
        self._db.execute("COMMIT")
        return {"event_id": event_id, "node_id": node_id, "sender": event.sender,
                "nonce": event.nonce, "entity": entity, "kind": kind, "version": version,
                "parents": list(event.parents), "status": PENDING}

    def adopt(self, node_id: str, signed) -> str:
        """Registra nell'outbox un evento firmato fuori dal wallet (per esempio un backup ripristinato)."""
        mission = self.sdk["mission"]
        event = signed.transfer
        record = mission.MissionRecord.from_data(event.data)
        event_id = event.event_id()
        self._signed[event_id] = signed
        self._db.execute(
            "INSERT OR IGNORE INTO outbox (event_id, node_id, sender, nonce, entity, kind, version, "
            "body_sha256, status, created_utc) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (event_id, node_id, event.sender, event.nonce, record.entity, record.kind,
             record.version, mission.body_digest(record.body), PENDING, record.produced_utc))
        return event_id

    # -- trasmissione -----------------------------------------------------------------

    def _client(self, url: str):
        return self.sdk["client"].Client(url, token=self.config.api_token, timeout=self.config.timeout_s)

    def _rows(self, statuses: tuple[str, ...], node_id: str | None = None):
        marks = ",".join("?" * len(statuses))
        query = f"SELECT event_id, node_id, sender, nonce FROM outbox WHERE status IN ({marks})"
        args = list(statuses)
        if node_id is not None:
            query += " AND node_id = ?"
            args.append(node_id)
        return self._db.execute(query + " ORDER BY node_id, nonce", args).fetchall()

    def _signed_event(self, node_id: str, event_id: str):
        if event_id not in self._signed:
            self._wallet(node_id)
        return self._signed.get(event_id)

    def flush(self, node_id: str | None = None, link=None, urls: list[str] | None = None) -> dict:
        """Invia gli eventi non ancora accettati, in ordine di nonce. Restituisce un riepilogo."""
        link = link or DirectLink()
        ApiError = self.sdk["client"].ApiError
        sent = refused = deferred = 0
        for event_id, owner, _sender, _nonce in self._rows((PENDING, REFUSED), node_id):
            signed = self._signed_event(owner, event_id)
            if signed is None:
                continue
            outcome = None
            for url in urls or self.config.node_urls:
                try:
                    link.deliver(lambda: self._client(url).submit(signed))
                    outcome = ("ok", None)
                    self.connected = True
                    break
                except ApiError as error:
                    outcome = ("refused", f"{error.status}: {error.body}")
                    self.connected = True
                    if error.status != 409:
                        continue
                    break
                except (LinkDown, OSError) as error:
                    outcome = ("down", f"{type(error).__name__}: {error}")
                    continue
            self._db.execute("UPDATE outbox SET attempts = attempts + 1 WHERE event_id=?", (event_id,))
            if outcome and outcome[0] == "ok":
                sent += 1
                self._db.execute("UPDATE outbox SET status=?, submitted_utc=?, last_error=NULL WHERE event_id=?",
                                 (SUBMITTED, self.clock(), event_id))
            elif outcome and outcome[0] == "refused":
                refused += 1
                self._db.execute("UPDATE outbox SET status=?, last_error=? WHERE event_id=?",
                                 (REFUSED, outcome[1], event_id))
            else:
                deferred += 1
                self._db.execute("UPDATE outbox SET last_error=? WHERE event_id=?",
                                 (None if outcome is None else outcome[1], event_id))
                # Store-and-forward: senza collegamento gli eventi successivi aspettano.
                break
        return {"sent": sent, "refused": refused, "deferred": deferred}

    def confirm(self, link=None, url: str | None = None) -> dict:
        """Verifica i certificati degli eventi inviati; individua le versioni sostituite."""
        link = link or DirectLink()
        mission = self.sdk["mission"]
        client = self._client(url or self.config.node_urls[0])
        certified = superseded = waiting = 0
        for event_id, owner, sender, nonce in self._rows((SUBMITTED, REFUSED, PENDING)):
            try:
                page = link.deliver(lambda: client.records(sender=sender, limit=500))
            except (LinkDown, OSError):
                break
            decided = None
            after = 0
            while True:
                for item in page["records"]:
                    found = mission.certified_record(item["certificate"], self.verifier)
                    if found.nonce == nonce:
                        decided = found
                if not page["records"] or page["next"] == after:
                    break
                after = page["next"]
                page = link.deliver(lambda: client.records(sender=sender, after=after, limit=500))
            if decided is None:
                waiting += 1
            elif decided.event_id == event_id:
                certified += 1
                self._db.execute("UPDATE outbox SET status=?, certified_utc=?, decided_event_id=? WHERE event_id=?",
                                 (CERTIFIED, self.clock(), event_id, event_id))
            else:
                superseded += 1
                self._db.execute("UPDATE outbox SET status=?, certified_utc=?, decided_event_id=? WHERE event_id=?",
                                 (SUPERSEDED, self.clock(), decided.event_id, event_id))
        return {"certified": certified, "superseded": superseded, "waiting": waiting}

    # -- lettura ----------------------------------------------------------------------

    def pull(self, link=None, url: str | None = None) -> list[dict]:
        """Tutti i record certificati che un nodo ha eseguito, verificati con il light client."""
        link = link or DirectLink()
        mission = self.sdk["mission"]
        client = self._client(url or self.config.node_urls[0])
        records, after = [], 0
        while True:
            page = link.deliver(lambda: client.records(after=after, limit=500))
            self.connected = True
            for item in page["records"]:
                try:
                    found = mission.certified_record(item["certificate"], self.verifier)
                except mission.RecordError as error:
                    records.append({"event_id": item.get("event_id"), "integrity": "rejected",
                                    "reason": str(error)})
                    continue
                records.append({**found.provenance(), "kind": found.record.kind,
                                "produced_utc": found.record.produced_utc,
                                "body": found.record.body, "integrity": "verified"})
            if not page["records"] or page["next"] == after:
                return records
            after = page["next"]

    def reconciled_view(self, records: list[dict] | None = None, link=None, url: str | None = None) -> dict:
        """Vista riconciliata: ultima versione certificata di ogni entità per ogni produttore."""
        records = self.pull(link, url) if records is None else records
        nodes = {account: name for name, account in self.nodes().items()}
        valid = [r for r in records if r.get("integrity") == "verified"]
        latest, version_conflicts = {}, []
        by_slot = {}
        for record in valid:
            slot = (record["origin"], record["entity"], record["version"])
            previous = by_slot.get(slot)
            if previous is not None and previous["body_sha256"] != record["body_sha256"]:
                version_conflicts.append({
                    "entity": record["entity"], "origin": record["origin"], "version": record["version"],
                    "event_ids": [previous["event_id"], record["event_id"]],
                    "resolution": "higher_nonce_wins",
                })
            by_slot[slot] = record if previous is None or record["nonce"] > previous["nonce"] else previous
            key = (record["entity"], record["origin"])
            current = latest.get(key)
            if current is None or (record["version"], record["nonce"]) > (current["version"], current["nonce"]):
                latest[key] = record
        outbox = [dict(zip(("event_id", "node_id", "entity", "version", "status", "attempts",
                            "created_utc", "submitted_utc", "certified_utc", "decided_event_id", "last_error"), row))
                  for row in self._db.execute(
                      "SELECT event_id, node_id, entity, version, status, attempts, created_utc, "
                      "submitted_utc, certified_utc, decided_event_id, last_error FROM outbox ORDER BY created_utc")]
        return {
            "schema": "lunar-psystem-reconciled-view/1.0",
            "generated_utc": _now_utc(),
            "connected_to_remote_psystem": self.connected,
            "committee_verified_with": "ChainVerifier (genesis committee and governance)",
            "records_verified": len(valid),
            "records_rejected": len(records) - len(valid),
            "latest_by_entity": [
                {**{k: v for k, v in r.items() if k != "body"}, "producer": nodes.get(r["origin"], r["origin"]),
                 "body": r["body"]}
                for _, r in sorted(latest.items())
            ],
            "protocol_conflicts": [o for o in outbox if o["status"] == SUPERSEDED],
            "version_conflicts": version_conflicts,
            "outbox": outbox,
            "outbox_summary": {status: sum(1 for o in outbox if o["status"] == status)
                               for status in (PENDING, SUBMITTED, CERTIFIED, SUPERSEDED, REFUSED)},
        }

    def node_status(self, link=None) -> list[dict]:
        link = link or DirectLink()
        found = []
        for url in self.config.node_urls:
            try:
                status = link.deliver(lambda: self._client(url).status())
                self.connected = True
                found.append({"url": url, "reachable": True, **{k: status.get(k) for k in (
                    "node_id", "epoch", "executed", "state_root", "halted", "conflicted", "peers")}})
            except Exception as error:  # nodo spento o collegamento assente
                found.append({"url": url, "reachable": False, "error": f"{type(error).__name__}: {error}"})
        return found

    def close(self) -> None:
        for wallet in self._wallets.values():
            wallet.close()
        self._db.close()
