# Last updated: 2026-11-15
"""Un comitato P-System reale, avviato dal planner con la CLI ufficiale ``psystem``.

Ogni nodo è un processo separato con il proprio store SQLite, la propria chiave e TLS mutuo verso gli
altri, esattamente come in ``P-System/docs/OPERATIONS.md``. Nessun canale simulato: i nodi si
collegano direttamente su 127.0.0.1. Serve ai test di integrazione e a un'installazione locale.

Richiede un interprete Python con le dipendenze di P-System (``P-System/.venv``) e la libreria Lean
compilata del nodo (``formal/lean/.lake/build/lib/libPSystem_PSystem.so``).
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import signal
import socket
import subprocess

from src.psystem_adapter import DEFAULT_PSYSTEM_HOME


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@dataclass
class ClusterNode:
    name: str
    port: int = 0
    api_port: int = 0
    directory: Path | None = None
    process: subprocess.Popen | None = None


@dataclass
class PSystemCluster:
    base: Path
    names: list[str]
    f: int = 1
    psystem_home: Path = DEFAULT_PSYSTEM_HOME
    python: str | None = None

    def __post_init__(self):
        self.base = Path(self.base)
        self.psystem_home = Path(self.psystem_home)
        self.python = self.python or str(self.psystem_home / ".venv" / "bin" / "python")
        if len(self.names) != 3 * self.f + 1:
            raise ValueError(f"il comitato deve avere 3f+1 = {3 * self.f + 1} nodi")
        self.nodes = {name: ClusterNode(name, free_port(), free_port()) for name in self.names}
        self.genesis_path = self.base / "genesis.json"

    def _cli(self, *args: str) -> str:
        result = subprocess.run([self.python, "-m", "network.cli", *args], cwd=self.psystem_home,
                                capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"psystem {' '.join(args[:2])}: {result.stderr.strip()[-800:]}")
        return result.stdout

    def create(self) -> "PSystemCluster":
        self.base.mkdir(parents=True, exist_ok=True)
        self._cli("authority", "init", str(self.base / "ca"))
        governance = []
        for i in range(3):
            governance.append(json.loads(self._cli("key", "generate", str(self.base / f"gov{i}.key")))["public_key"])
        members = []
        for node in self.nodes.values():
            node.directory = self.base / node.name
            node.directory.mkdir()
            self._cli("authority", "issue", str(self.base / "ca"), "--node-id", node.name,
                      "--out", str(node.directory))
            members.append(json.loads(self._cli("key", "generate", str(node.directory / "identity.key")))["public_key"])
        args = ["genesis", str(self.genesis_path), "--f", str(self.f)]
        for member in members:
            args += ["--member", member]
        for key in governance:
            args += ["--governance", key]
        args += ["--governance-threshold", "2"]
        self.genesis = json.loads(self._cli(*args))
        for node in self.nodes.values():
            self._write_config(node)
        return self

    def peer_port(self, a: str, b: str) -> int:
        return self.nodes[b].port

    def _write_config(self, node: ClusterNode) -> None:
        peers = "".join(
            f'\n[[peers]]\nnode_id = "{other}"\nhost = "127.0.0.1"\nport = {self.peer_port(node.name, other)}\n'
            for other in self.names if other != node.name)
        (node.directory / "node.toml").write_text(
            f'''node_id = "{node.name}"
host = "127.0.0.1"
port = {node.port}
identity_key = "identity.key"
tls_certificate = "{node.name}.crt"
tls_key = "{node.name}.key"
tls_authority = "../ca/ca.crt"
genesis = "../genesis.json"
store = "votes.sqlite"
sync_interval = 0.5

[api]
port = {node.api_port}
{peers}''', encoding="utf-8")

    def start(self, name: str, create: bool = True) -> None:
        node = self.nodes[name]
        args = [self.python, "-m", "network.cli", "node", "--config", str(node.directory / "node.toml")]
        if create:
            args.append("--create-store")
        log = (node.directory / "node.log").open("a")
        node.process = subprocess.Popen(args, cwd=self.psystem_home, stdout=subprocess.PIPE,
                                        stderr=log, text=True, env={**os.environ})
        line = node.process.stdout.readline()
        if not line:
            raise RuntimeError(f"nodo {name} non avviato: {(node.directory / 'node.log').read_text()[-1500:]}")

    def start_all(self) -> "PSystemCluster":
        for name in self.names:
            self.start(name)
        return self

    def kill(self, name: str) -> None:
        node = self.nodes[name]
        if node.process is not None:
            node.process.send_signal(signal.SIGKILL)
            node.process.wait(timeout=10)
            node.process = None

    def url(self, name: str) -> str:
        return f"http://127.0.0.1:{self.nodes[name].api_port}"

    def stop(self) -> None:
        for node in self.nodes.values():
            if node.process is not None:
                node.process.terminate()
                try:
                    node.process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    node.process.kill()
                    node.process.wait(timeout=10)
                node.process = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stop()


def main(argv=None) -> int:
    """Avvia un comitato locale di 4 nodi e resta in esecuzione fino a Ctrl+C."""
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Comitato P-System locale per il planner")
    parser.add_argument("--dir", default="reports/psystem_local")
    parser.add_argument("--psystem-home", default=None)
    args = parser.parse_args(argv)
    base = Path(args.dir)
    if base.exists() and any(base.iterdir()):
        raise SystemExit(f"{base} non è vuota: scegliere un'altra directory")
    cluster = PSystemCluster(base, ["ground-0", "ground-1", "ground-2", "base"],
                             psystem_home=Path(args.psystem_home) if args.psystem_home else DEFAULT_PSYSTEM_HOME)
    cluster.create().start_all()
    print(json.dumps({"genesis_path": str(cluster.genesis_path),
                      "node_urls": [cluster.url(n) for n in cluster.names]}, indent=1), flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        cluster.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
