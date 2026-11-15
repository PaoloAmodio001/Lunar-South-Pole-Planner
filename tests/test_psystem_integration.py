"""Integrazione reale Planner ↔ P-System: quattro processi P-System avviati sul PC, TLS mutuo.

Nessun canale simulato: il planner parla con i nodi via l'API HTTP di P-System e verifica i
certificati con il light client. Richiede P-System (PSYSTEM_HOME o ~/Github P-system) con il suo
.venv e la libreria Lean del nodo compilata; altrimenti i test vengono saltati.
"""
import json
import shutil
import time
from pathlib import Path

import pytest

from src.psystem_adapter import (CERTIFIED, PENDING, SUPERSEDED, BridgeConfig, MissionJournal,
                                 PSystemBridge, PSystemUnavailable, load_psystem_sdk)
from src.psystem_cluster import PSystemCluster

try:
    SDK = load_psystem_sdk()
    READY = (SDK["root"] / ".venv" / "bin" / "python").is_file() and (
        SDK["root"] / "formal/lean/.lake/build/lib/libPSystem_PSystem.so").is_file()
except PSystemUnavailable:
    SDK, READY = None, False

pytestmark = pytest.mark.skipif(not READY, reason="P-System non disponibile su questo PC")
NODES = ["ground-0", "ground-1", "ground-2", "base"]


@pytest.fixture(scope="module")
def cluster(tmp_path_factory):
    made = PSystemCluster(tmp_path_factory.mktemp("psystem"), NODES, psystem_home=SDK["root"])
    made.create().start_all()
    yield made
    made.stop()


def bridge(cluster, state_dir, urls=None):
    return PSystemBridge(BridgeConfig(urls or [cluster.url(n) for n in NODES],
                                      str(cluster.genesis_path), str(state_dir)))


def settle(b, seconds=30):
    deadline = time.monotonic() + seconds
    while True:
        b.flush()
        result = b.confirm()
        if result["waiting"] == 0 or time.monotonic() > deadline:
            # Totali dell'outbox: confirm() conta solo ciò che cambia in quella chiamata.
            return b.reconciled_view([])["outbox_summary"]
        time.sleep(0.2)


def test_planner_results_are_certified_and_every_node_agrees(cluster, tmp_path):
    b = bridge(cluster, tmp_path / "planner")
    try:
        b.publish("planner-ground", "site:Site04", "result", {"top_candidate_rc": [1600, 1599], "score": 0.93})
        b.publish("rover-1", "rover-1", "telemetry", {"pos_rc": [120, 113], "energy_used_wh": 1.4})
        assert settle(b)["certified"] == 2
        views = {name: b.reconciled_view(url=cluster.url(name)) for name in NODES}
        ids = {name: sorted(r["event_id"] for r in v["latest_by_entity"]) for name, v in views.items()}
        assert len({tuple(v) for v in ids.values()}) == 1
        view = views["base"]
        assert view["connected_to_remote_psystem"] is True
        assert view["records_rejected"] == 0
        rover = [r for r in view["latest_by_entity"] if r["entity"] == "rover-1"][0]
        assert rover["producer"] == "rover-1" and rover["version"] == 1
        assert rover["body"] == {"pos_rc": [120, 113], "energy_used_wh": 1.4}
        assert rover["integrity"] == "verified" and rover["certificate_votes"] >= 3
        roots = {s["state_root"] for s in b.node_status()}
        assert len(roots) == 1
    finally:
        b.close()


def test_versions_increase_per_entity_and_the_latest_wins(cluster, tmp_path):
    b = bridge(cluster, tmp_path / "planner")
    try:
        for soc in (0.9, 0.8, 0.7):
            b.publish("rover-2", "rover-2:power", "telemetry", {"soc": soc})
        assert settle(b)["certified"] == 3
        latest = [r for r in b.reconciled_view()["latest_by_entity"] if r["entity"] == "rover-2:power"]
        assert latest[0]["version"] == 3 and latest[0]["body"] == {"soc": 0.7}
    finally:
        b.close()


def test_the_journal_publishes_through_the_bridge(cluster, tmp_path):
    b = bridge(cluster, tmp_path / "planner")
    try:
        journal = MissionJournal(tmp_path / "events.jsonl", "planner-ground", bridge=b)
        journal.append("mission-step:site_selection", "step_success", {"candidates": 20})
        assert settle(b)["certified"] == 1
        body = [r for r in b.reconciled_view()["latest_by_entity"]
                if r["entity"] == "mission-step:site_selection"][0]["body"]
        assert body["event_type"] == "step_success" and body["payload"] == {"candidates": 20}
    finally:
        b.close()


def test_two_versions_signed_with_one_key_are_decided_once(cluster, tmp_path):
    """Un'unità ripristinata da un journal vecchio firma un'altra versione dello stesso nonce."""
    primary = bridge(cluster, tmp_path / "primary", [cluster.url("base")])
    try:
        primary._wallet("rover-3")
        node_dir = tmp_path / "primary" / "nodes" / "rover-3"
        restored = tmp_path / "restored" / "nodes" / "rover-3-backup"
        restored.mkdir(parents=True)
        shutil.copy2(node_dir / "identity.key", restored / "identity.key")
        shutil.copy2(node_dir / "records.sqlite", restored / "records.sqlite")
        first = primary.publish("rover-3", "rover-3", "telemetry", {"pos_rc": [10, 10]})

        identity = SDK["Identity"].load(restored / "identity.key")
        mission = SDK["mission"]
        wallet = SDK["client"].Wallet(identity, restored / "records.sqlite",
                                      asset=mission.record_asset(identity.identity_id))
        signed = mission.sign_record(wallet, mission.MissionRecord(
            "rover-3", "telemetry", 1, {"pos_rc": [99, 99]}, wallet.account, "2026-11-15T12:00:00+00:00"))
        wallet.close()
        assert signed.transfer.nonce == first["nonce"]
        backup = bridge(cluster, tmp_path / "restored", [cluster.url("ground-0")])
        try:
            second = backup.adopt("rover-3-backup", signed)
            # Le due versioni arrivano a nodi diversi quasi insieme.
            primary.flush()
            backup.flush()
            settle(primary, 60)
            settle(backup, 60)
            states = sorted([primary.reconciled_view()["outbox"][0]["status"],
                             backup.reconciled_view()["outbox"][0]["status"]])
            assert states == [CERTIFIED, SUPERSEDED]
            decided = {o["decided_event_id"] for o in primary.reconciled_view()["outbox"]
                       + backup.reconciled_view()["outbox"]}
            assert len(decided) == 1 and decided <= {first["event_id"], second}
            # Ogni nodo esegue la stessa versione.
            for name in NODES:
                found = [r for r in primary.pull(url=cluster.url(name)) if r["entity"] == "rover-3"]
                assert [r["event_id"] for r in found] == list(decided)
            assert not any(s["halted"] for s in primary.node_status())
        finally:
            backup.close()
    finally:
        primary.close()


def test_events_wait_in_the_outbox_until_a_node_is_reachable(cluster, tmp_path):
    state = tmp_path / "planner"
    offline = PSystemBridge(BridgeConfig(["http://127.0.0.1:9"], str(cluster.genesis_path), str(state)))
    try:
        entry = offline.publish("sensor-1", "sensor-1:illumination", "observation", {"sun_clearance_deg": 1.25})
        assert offline.flush()["deferred"] == 1
        assert offline.reconciled_view([])["outbox_summary"][PENDING] == 1
    finally:
        offline.close()
    # Un nuovo processo con la stessa directory riprende l'outbox durevole e consegna.
    online = bridge(cluster, state)
    try:
        assert settle(online)["certified"] == 1
        assert online.reconciled_view()["outbox"][0]["event_id"] == entry["event_id"]
    finally:
        online.close()


def test_a_node_that_was_down_recovers_the_decisions_it_missed(cluster, tmp_path):
    cluster.kill("ground-2")
    b = bridge(cluster, tmp_path / "planner", [cluster.url("ground-0"), cluster.url("base")])
    try:
        for k in range(4):
            b.publish("base", "base:power", "telemetry", {"sample": k})
        assert settle(b)["certified"] == 4
        expected = {r["event_id"] for r in b.pull(url=cluster.url("ground-0"))}
        cluster.start("ground-2", create=False)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if {r["event_id"] for r in b.pull(url=cluster.url("ground-2"))} == expected:
                    break
            except OSError:
                pass
            time.sleep(0.3)
        assert {r["event_id"] for r in b.pull(url=cluster.url("ground-2"))} == expected
        assert len({s["state_root"] for s in b.node_status()}) == 1
    finally:
        b.close()


def test_a_record_with_a_forged_certificate_is_rejected(cluster, tmp_path):
    b = bridge(cluster, tmp_path / "planner")
    try:
        b.publish("planner-ground", "plan:traverse", "plan", {"waypoints": [[1, 2], [3, 4]]})
        settle(b)
        item = SDK["client"].Client(cluster.url("ground-0")).records(sender=b.account_of("planner-ground"))["records"][0]
        certificate = item["certificate"]
        certificate["votes"] = certificate["votes"][:1]  # sotto il quorum
        with pytest.raises(SDK["mission"].RecordError):
            SDK["mission"].certified_record(certificate, b.verifier)
    finally:
        b.close()


def test_the_orchestrator_publishes_its_run_and_reports_provenance(cluster, tmp_path):
    from src.mission_orchestrator import run_mission_workflow

    output = tmp_path / "output"
    config = {
        "output_dir": str(output),
        "psystem": {"enabled": True, "node_id": "planner-ground",
                    "node_urls": [cluster.url("ground-1"), cluster.url("base")],
                    "genesis_path": str(cluster.genesis_path), "state_dir": str(tmp_path / "bridge"),
                    "confirm_timeout_s": 60},
        "mission_report": {"enabled": True, "site_name": "Shackleton", "planning_date": "2026-11-15",
                           "horizon_hours": 48},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    result = run_mission_workflow(path)
    sync = result["steps"]["psystem_sync"]
    assert sync["status"] == "success", sync
    assert sync["result"]["connected_to_remote_psystem"] is True
    assert sync["result"]["certified"] == sync["result"]["published"] >= 1
    status = json.loads((output / "mission_status_report.json").read_text())
    section = status["psystem_integration"]
    assert section["connected_to_remote_psystem"] is True
    assert section["records_rejected"] == 0
    assert any(p["entity"].startswith("mission-run:") for p in section["provenance"])
    view = json.loads((output / "psystem_reconciled_view.json").read_text())
    run = [r for r in view["latest_by_entity"] if r["entity"].startswith("mission-run:")][0]
    steps = [r["event_id"] for r in view["latest_by_entity"]
             if r["entity"].startswith("mission-step:") and r["body"].get("run_id") == result["run_id"]]
    assert set(run["parents"]) == set(steps) and steps
    assert status["psystem_journal"]["remote_node_connected"] is True
    assert "Record certificati dal comitato P-System" in (output / "mission_status_report.md").read_text()


def test_causal_dag_is_executed_in_dependency_order_whatever_the_arrival(cluster, tmp_path):
    """Rover → base → centro di controllo: tre produttori, eventi collegati da archi causali.

    Il figlio (il piano del centro di controllo) arriva ai nodi prima dei genitori; ogni nodo
    lo esegue comunque dopo di loro e tutti convergono allo stesso stato.
    """
    rover = bridge(cluster, tmp_path / "rover", [cluster.url("base")])
    base = bridge(cluster, tmp_path / "base", [cluster.url("base")])
    control = bridge(cluster, tmp_path / "control", [cluster.url("ground-0")])
    try:
        telemetry = rover.publish("rover-7", "rover-7", "telemetry", {"pos_rc": [40, 41]})
        observation = base.publish("base-7", "base-7:illumination", "observation",
                                   {"sun_clearance_deg": 2.1}, parents=[telemetry["event_id"]])
        plan = control.publish("control-7", "plan:rover-7", "plan", {"next_rc": [60, 70]},
                               parents=[telemetry["event_id"], observation["event_id"]])
        assert plan["parents"] == sorted([telemetry["event_id"], observation["event_id"]])
        # Ordine di arrivo inverso rispetto alle dipendenze.
        control.flush()
        time.sleep(0.5)
        base.flush()
        time.sleep(0.5)
        rover.flush()
        for b in (rover, base, control):
            assert settle(b, 60)[CERTIFIED] == 1
        for name in NODES:
            client = SDK["client"].Client(cluster.url(name))
            order = [item["event_id"] for item in client.records()["records"]]
            assert order.index(telemetry["event_id"]) < order.index(observation["event_id"]) < order.index(plan["event_id"])
        decided = [r for r in control.pull(url=cluster.url("ground-2")) if r["entity"] == "plan:rover-7"][0]
        assert decided["parents"] == plan["parents"]
        assert len({s["state_root"] for s in control.node_status()}) == 1
    finally:
        for b in (rover, base, control):
            b.close()
