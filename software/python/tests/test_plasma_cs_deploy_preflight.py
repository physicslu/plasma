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
        return {"ok": True}
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
        return {"ok": True} if url.endswith("/api/health/live") else {"ppu": {}}
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
