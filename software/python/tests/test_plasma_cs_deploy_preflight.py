from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/plasma_cs_deploy_preflight.py"
spec = importlib.util.spec_from_file_location("plasma_cs_deploy_preflight", SCRIPT)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def write_journal(root: Path, name: str, schema: str, field: str, records: list) -> None:
    (root / name).write_text(json.dumps({"schema": schema, field: records}))


def fake_http(url: str) -> dict:
    if url.endswith("/api/health/live"):
        return {"ok": True, "manager": "alive"}
    if url.endswith("/api/status"):
        return {"ppu": {"execution": {
            "busy": False, "active_job_count": 0,
            "owner_kind": None, "owner_id": None,
        }}}
    raise AssertionError(url)


@pytest.fixture()
def state(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(preflight, "http_json", fake_http)
    write_journal(tmp_path, "programming-batches.json",
                  "plasma.manager.programming-batch-journal.v1", "batches", [])
    write_journal(tmp_path, "bundle-programming-runs.json",
                  "plasma.manager.bundle-programming-journal.v1", "runs", [])
    data = json.loads((tmp_path / "bundle-programming-runs.json").read_text())
    data["starts"] = []
    (tmp_path / "bundle-programming-runs.json").write_text(json.dumps(data))
    return tmp_path


def check(state: Path) -> dict:
    return preflight.check(state, "http://127.0.0.1:18280", "http://ppu:18080")


def test_idle_preflight_passes_with_no_journal_mutation(state: Path) -> None:
    before = {x.name: x.read_bytes() for x in state.iterdir()}
    result = check(state)
    assert result["result"] == "PASS"
    assert result["ppu_execution"] == "IDLE"
    assert result["admission_quiesce"] == "NOT_IMPLEMENTED"
    assert {x.name: x.read_bytes() for x in state.iterdir()} == before


@pytest.mark.parametrize("outcome,execution", [
    (None, "RUNNING"), ("OUTCOME_UNKNOWN", "COMPLETED")
])
def test_v2_batch_unresolved_blocks(state: Path, outcome, execution) -> None:
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2", "batches", [{
                      "batch_id": "abc", "state": "running" if outcome is None else "finished",
                      "execution_status": execution, "outcome": outcome,
                      "units": [{"outcome": outcome, "attempts": []}],
                  }])
    with pytest.raises(preflight.Blocked, match="unresolved/running"):
        check(state)


def test_legacy_completed_batch_passes(state: Path) -> None:
    write_journal(state, "programming-batches.json",
                  "plasma.manager.programming-batch-journal.v1", "batches", [{
                      "batch_id": "old", "ppu_alias": "z2", "site_id": 2,
                      "state": "finished", "outcome": "PASS",
                      "attempts": [{"outcome": "PASS"}],
                  }])
    assert check(state)["journal"]["batches"] == 1


def test_legacy_stopped_batch_blocks(state: Path) -> None:
    write_journal(state, "programming-batches.json",
                  "plasma.manager.programming-batch-journal.v1", "batches", [{
                      "batch_id": "old", "ppu_alias": "z2", "site_id": 2,
                      "state": "finished", "outcome": "STOPPED", "attempts": [],
                  }])
    with pytest.raises(preflight.Blocked, match="requires reconciliation"):
        check(state)


@pytest.mark.parametrize("run", [
    {"run_id": "x", "outcome": None},
    {"run_id": "x", "outcome": "OUTCOME_UNKNOWN", "acknowledged": False},
])
def test_unresolved_run_blocks(state: Path, run: dict) -> None:
    write_journal(state, "bundle-programming-runs.json",
                  "plasma.manager.bundle-programming-journal.v1", "runs", [run])
    data = json.loads((state / "bundle-programming-runs.json").read_text())
    data["starts"] = []
    (state / "bundle-programming-runs.json").write_text(json.dumps(data))
    with pytest.raises(preflight.Blocked, match="Run"):
        check(state)


def test_ppu_busy_blocks(state: Path, monkeypatch) -> None:
    def busy(url: str) -> dict:
        value = fake_http(url)
        if url.endswith("/api/status"):
            value["ppu"]["execution"]["busy"] = True
        return value
    monkeypatch.setattr(preflight, "http_json", busy)
    with pytest.raises(preflight.Blocked, match="active/unknown execution owner"):
        check(state)


def test_unobservable_ppu_blocks(state: Path, monkeypatch) -> None:
    def broken(url: str) -> dict:
        return {"ok": True, "manager": "alive"} if url.endswith("/api/health/live") else {"ppu": {}}
    monkeypatch.setattr(preflight, "http_json", broken)
    with pytest.raises(preflight.Blocked, match="not observable"):
        check(state)


def test_corrupted_journal_blocks(state: Path) -> None:
    (state / "programming-batches.json").write_text("{invalid")
    with pytest.raises(preflight.Blocked, match="unreadable journal"):
        check(state)


def test_deployment_hook_runs_preflight_twice_and_never_uses_z2_ssh() -> None:
    code = (ROOT / "scripts/plasmactl-local-control-station").read_text()
    section = code.split("deploy_profile() {", 1)[1].split("parse_options()", 1)[0]
    assert section.count("run_deployment_preflight") == 2
    assert section.index("run_deployment_preflight") < section.index("prepare_release")
    assert "plasma_cs_deploy_preflight.py" in code
    assert "ssh " not in section


START_ID = "a" * 32
OTHER_START_ID = "b" * 32


def set_starts(state: Path, starts: list[dict], runs: list[dict] | None = None) -> None:
    path = state / "bundle-programming-runs.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["starts"] = starts
    if runs is not None:
        data["runs"] = runs
    path.write_text(json.dumps(data), encoding="utf-8")


def start_record(kind: str = "batch", status: str = "ISSUED", **extra) -> dict:
    return {"start_id": START_ID, "kind": kind, "state": status, **extra}


def completed_v2_batch(start_id: str = START_ID) -> dict:
    return {"batch_id": "batch-1", "start_id": start_id,
            "state": "finished", "execution_status": "COMPLETED", "outcome": "PASS",
            "units": [{"outcome": "PASS", "attempts": [{"outcome": "PASS"}]}]}


def test_consumed_start_requires_matching_batch(state: Path) -> None:
    set_starts(state, [start_record(status="CONSUMED", batch_id="batch-1")])
    with pytest.raises(preflight.Blocked, match="admitted Batch record missing"):
        check(state)
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2",
                  "batches", [completed_v2_batch()])
    assert check(state)["journal"]["starts"] == 1


def test_consumed_batch_identity_mismatch_blocks(state: Path) -> None:
    set_starts(state, [start_record(status="CONSUMED", batch_id="batch-1")])
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2",
                  "batches", [completed_v2_batch(OTHER_START_ID)])
    with pytest.raises(preflight.Blocked, match="admitted Batch record missing"):
        check(state)


def test_consumed_start_requires_matching_run(state: Path) -> None:
    set_starts(state, [start_record(kind="run", status="CONSUMED", run_id="run-1")])
    with pytest.raises(preflight.Blocked, match="admitted Run record missing"):
        check(state)
    set_starts(state, [start_record(kind="run", status="CONSUMED", run_id="run-1")],
               [{"run_id": "run-1", "plan": {"plan_id": START_ID}, "outcome": "PASS"}])
    assert check(state)["result"] == "PASS"


def test_consumed_run_unknown_requires_explicit_acknowledgement(state: Path) -> None:
    record = start_record(kind="run", status="CONSUMED", run_id="run-1")
    run = {"run_id": "run-1", "plan": {"plan_id": START_ID},
           "outcome": "OUTCOME_UNKNOWN", "acknowledged": False}
    set_starts(state, [record], [run])
    with pytest.raises(preflight.Blocked, match="unknown/unacknowledged"):
        check(state)
    run["acknowledged"] = True
    set_starts(state, [record], [run])
    assert check(state)["result"] == "PASS"


def test_issued_start_must_be_reconciled_not_accepted(state: Path, monkeypatch) -> None:
    set_starts(state, [start_record()])
    def pending(url: str) -> dict:
        if "/api/programming/starts/" in url:
            return {"ok": True, "reconciliation": {
                "start_id": START_ID, "kind": "batch", "read_only": True,
                "state": "ACCEPTANCE_PENDING"}}
        return fake_http(url)
    monkeypatch.setattr(preflight, "http_json", pending)
    with pytest.raises(preflight.Blocked, match="admission not proved inactive"):
        check(state)

    def expired(url: str) -> dict:
        value = pending(url)
        if "/api/programming/starts/" in url:
            value["reconciliation"]["state"] = "NOT_ACCEPTED"
        return value
    monkeypatch.setattr(preflight, "http_json", expired)
    assert check(state)["journal"]["starts"] == 1


def test_issued_start_reconciliation_mismatch_fails_closed(state: Path, monkeypatch) -> None:
    set_starts(state, [start_record()])
    def wrong(url: str) -> dict:
        if "/api/programming/starts/" in url:
            return {"ok": True, "reconciliation": {
                "start_id": OTHER_START_ID, "kind": "batch", "read_only": True,
                "state": "NOT_ACCEPTED"}}
        return fake_http(url)
    monkeypatch.setattr(preflight, "http_json", wrong)
    with pytest.raises(preflight.Blocked, match="admission not proved inactive"):
        check(state)


def test_voided_start_has_no_admitted_transaction(state: Path) -> None:
    set_starts(state, [start_record(status="VOIDED")])
    assert check(state)["journal"]["starts"] == 1
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2",
                  "batches", [completed_v2_batch()])
    with pytest.raises(preflight.Blocked, match="voided Start has admitted"):
        check(state)


def test_duplicate_or_invalid_starts_block(state: Path) -> None:
    set_starts(state, [start_record(status="VOIDED"), start_record(status="VOIDED")])
    with pytest.raises(preflight.Blocked, match="duplicate/invalid"):
        check(state)
    set_starts(state, [start_record(status="SURPRISE")])
    with pytest.raises(preflight.Blocked, match="duplicate/invalid"):
        check(state)


def test_migrated_v1_v2_same_transaction_is_not_a_conflict(state: Path) -> None:
    attempt = {"attempt": 1, "plan_id": START_ID, "run_id": "run1",
               "job_id": "job1", "job_binding_sha256": "b" * 64,
               "outcome": "PASS", "safe_off": True}
    legacy = {"batch_id": "batch-1", "start_id": START_ID,
              "ppu_alias": "z2", "site_id": 2,
              "state": "finished", "outcome": "PASS",
              "attempts": [attempt]}
    current = {"batch_id": "batch-1", "start_id": START_ID,
               "state": "finished", "execution_status": "COMPLETED",
               "outcome": "PASS",
               "targets": [{"ppu_alias": "z2", "site_ids": [2]}],
               "units": [{"ppu_alias": "z2", "site_id": 2,
                          "outcome": "PASS", "status": "FINISHED",
                          "attempts": [{**attempt, "job_key": {"attempt": 1}}]}],
               "updated_at": "2026-11-15T12:00:00Z"}
    set_starts(state, [start_record(status="CONSUMED", batch_id="batch-1")])
    write_journal(state, "programming-batches.json",
                  "plasma.manager.programming-batch-journal.v1", "batches", [legacy])
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2", "batches", [current])
    assert check(state)["journal"]["batches"] == 1

    # A later v2 writer may change bookkeeping but never Job identity.
    current["units"][0]["attempts"][0]["job_id"] = "different-job"
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2", "batches", [current])
    with pytest.raises(preflight.Blocked, match="transaction identity"):
        check(state)


def test_missing_run_start_ledger_with_batches_blocks(state: Path) -> None:
    (state / "bundle-programming-runs.json").unlink()
    with pytest.raises(preflight.Blocked, match="Run/Start journal missing"):
        # Even an empty Batch ledger demonstrates this is not an all-empty system.
        check(state)


def test_bogus_terminal_batch_outcome_blocks(state: Path) -> None:
    row = completed_v2_batch()
    row["outcome"] = "UNRECOGNIZED_PASS"
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2", "batches", [row])
    with pytest.raises(preflight.Blocked, match="nonterminal or invalid outcome"):
        check(state)


def test_bogus_site_and_attempt_outcomes_block(state: Path) -> None:
    row = completed_v2_batch()
    row["units"][0]["outcome"] = "ALMOST_PASS"
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2", "batches", [row])
    with pytest.raises(preflight.Blocked, match="Site outcome"):
        check(state)
    row["units"][0]["outcome"] = "PASS"
    row["units"][0]["attempts"][0]["outcome"] = "UNDEFINED"
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2", "batches", [row])
    with pytest.raises(preflight.Blocked, match="attempt"):
        check(state)


def test_unknown_batch_execution_status_blocks(state: Path) -> None:
    row = completed_v2_batch()
    row["execution_status"] = "QUEUED"
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2", "batches", [row])
    with pytest.raises(preflight.Blocked, match="execution status"):
        check(state)


def test_duplicate_start_claim_by_distinct_batches_blocks(state: Path) -> None:
    first = completed_v2_batch()
    second = {**first, "batch_id": "batch-2"}
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2",
                  "batches", [first, second])
    with pytest.raises(preflight.Blocked, match="claimed by multiple Batches"):
        check(state)
