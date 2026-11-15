from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
START_ID = "a" * 32
OTHER_START_ID = "b" * 32

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
    (tmp_path / "manager.yaml").write_text("manager:\n  registry_state_path: " + json.dumps(str(tmp_path / "registry.json")) + "\n")
    def live_http(url):
        if "/api/programming/starts/" not in url:
            return fake_http(url)
        sid = url.rsplit("/", 1)[1]
        data = json.loads((tmp_path / "bundle-programming-runs.json").read_text())
        start = next(x for x in data["starts"] if x["start_id"] == sid)
        view = {"start_id": sid, "kind": start["kind"], "read_only": True, "state": "NOT_ACCEPTED"}
        if start["state"] == "CONSUMED":
            kind = start["kind"]
            if kind == "run":
                row = next(r for r in data["runs"] if r["run_id"] == start["run_id"])
            else:
                rows = []
                for name in ["programming-batches.json", "programming-batches.json.v2"]:
                    if (tmp_path / name).exists():
                        rows += json.loads((tmp_path / name).read_text())["batches"]
                row = next(r for r in rows if r["batch_id"] == start["batch_id"])
            view.update(state="OUTCOME_UNKNOWN" if row["outcome"] == "OUTCOME_UNKNOWN" else "TERMINAL_CONFIRMED", outcome=row["outcome"], acknowledged=row.get("acknowledged"))
            view[kind] = row
        return {"ok": True, "reconciliation": view}
    monkeypatch.setattr(preflight, "http_json", live_http)
    write_journal(tmp_path, "programming-batches.json",
                  "plasma.manager.programming-batch-journal.v1", "batches", [])
    write_journal(tmp_path, "bundle-programming-runs.json",
                  "plasma.manager.bundle-programming-journal.v1", "runs", [])
    data = json.loads((tmp_path / "bundle-programming-runs.json").read_text())
    data["starts"] = []
    (tmp_path / "bundle-programming-runs.json").write_text(json.dumps(data))
    return tmp_path


def check(state: Path) -> dict:
    return preflight.check(state, "http://127.0.0.1:18280", "http://ppu:18080", state / "manager.yaml")


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
                      "attempts": [{"state": "finished", "outcome": "PASS"}],
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
    {"run_id": "x", "plan": {"plan_id": START_ID}, "state": "finished", "acknowledged": False, "outcome": None},
    {"run_id": "x", "plan": {"plan_id": START_ID}, "state": "finished", "outcome": "OUTCOME_UNKNOWN", "acknowledged": False},
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
            "targets": [{"ppu_alias": "z2", "site_ids": [2]}],
            "units": [{"ppu_alias": "z2", "site_id": 2, "outcome": "PASS", "attempts": [{"state": "finished", "outcome": "PASS"}]}]}


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
               [{"run_id": "run-1", "plan": {"plan_id": START_ID}, "state": "finished", "acknowledged": False, "outcome": "PASS"}])
    assert check(state)["result"] == "PASS"


def test_consumed_run_unknown_requires_explicit_acknowledgement(state: Path) -> None:
    record = start_record(kind="run", status="CONSUMED", run_id="run-1")
    run = {"run_id": "run-1", "plan": {"plan_id": START_ID}, "state": "finished",
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
               "state": "finished", "outcome": "PASS", "safe_off": True}
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


def test_batch_aggregate_disagrees_with_site_blocks(state: Path) -> None:
    row = completed_v2_batch()
    row["units"][0]["outcome"] = "BLOCKED"
    row["units"][0]["attempts"] = []
    write_journal(state, "programming-batches.json.v2",
                  "plasma.manager.programming-batch-journal.v2",
                  "batches", [row])
    with pytest.raises(preflight.Blocked, match="aggregate/Site outcomes disagree"):
        check(state)


def test_run_invalid_terminal_state_or_outcome_blocks(state: Path) -> None:
    run = {"run_id": "x", "plan": {"plan_id": START_ID}, "state": "accepted", "acknowledged": False, "outcome": "PASS"}
    set_starts(state, [], [run])
    with pytest.raises(preflight.Blocked, match="outcome not terminal"):
        check(state)
    run.update(state="finished", outcome="UNRECOGNIZED")
    set_starts(state, [], [run])
    with pytest.raises(preflight.Blocked, match="invalid terminal outcome"):
        check(state)


@pytest.mark.parametrize('names', [
    ['programming-batches.json'], ['bundle-programming-runs.json'],
    ['programming-batches.json', 'bundle-programming-runs.json'],
])
def test_missing_evidence_is_not_new_install_idle(state, names):
    for name in names:
        (state / name).unlink()
    with pytest.raises(preflight.Blocked):
        check(state)


@pytest.mark.parametrize('config', [None, '{}', 'manager: {}',
    'manager:\n  registry_state_path: /other/registry.json',
    'manager:\n  registry_state_path: registry.json', 'manager: [bad]'])
def test_config_must_prove_actual_journal_directory(state, config):
    path = state / 'manager.yaml'
    if config is None:
        path.unlink()
    else:
        path.write_text(config)
    with pytest.raises(preflight.Blocked, match='journal location'):
        check(state)


@pytest.mark.parametrize('payload', [b'\xff', b'{"schema":1,"schema":2}', b'[]', b'{}'])
def test_malformed_journal_fails_closed_without_mutation(state, payload):
    (state / 'programming-batches.json').write_bytes(payload)
    before = {p.name: p.read_bytes() for p in state.iterdir()}
    with pytest.raises(preflight.Blocked):
        check(state)
    assert before == {p.name: p.read_bytes() for p in state.iterdir()}


@pytest.mark.parametrize('outcome', ['PASS', 'FAIL', 'BLOCKED'])
def test_known_terminal_runs_pass(state, outcome):
    set_starts(state, [start_record(kind='run', status='CONSUMED', run_id='r')],
               [{'run_id': 'r', 'plan': {'plan_id': START_ID}, 'state': 'finished',
                 'outcome': outcome, 'acknowledged': False}])
    assert check(state)['result'] == 'PASS'


@pytest.mark.parametrize('changes', [
    {'outcome': 'UNKNOWN'}, {'outcome': 'PARTIAL'}, {'state': 'running'},
    {'state': None}, {'acknowledged': 'true'}, {'run_id': None}, {'plan': []},
])
def test_malformed_terminal_run_blocks(state, changes):
    run = {'run_id': 'r', 'plan': {'plan_id': START_ID}, 'state': 'finished',
           'outcome': 'PASS', 'acknowledged': False, **changes}
    set_starts(state, [], [run])
    with pytest.raises(preflight.Blocked):
        check(state)


def test_duplicate_run_and_batch_ids_block(state):
    run = {'run_id': 'r', 'plan': {'plan_id': START_ID}, 'state': 'finished',
           'outcome': 'PASS', 'acknowledged': False}
    set_starts(state, [], [run, run])
    with pytest.raises(preflight.Blocked, match='duplicate'):
        check(state)
    set_starts(state, [], [])
    row = completed_v2_batch()
    write_journal(state, 'programming-batches.json.v2',
                  'plasma.manager.programming-batch-journal.v2', 'batches', [row, row])
    with pytest.raises(preflight.Blocked, match='duplicate Batch'):
        check(state)


@pytest.mark.parametrize('status', ['CONSUMED', 'VOIDED', 'ISSUED'])
def test_live_unknown_start_blocks_even_when_local_history_looks_terminal(state, monkeypatch, status):
    if status == 'CONSUMED':
        write_journal(state, 'programming-batches.json.v2',
                      'plasma.manager.programming-batch-journal.v2', 'batches', [completed_v2_batch()])
    set_starts(state, [start_record(status=status, batch_id='batch-1')])
    def unknown(url):
        if '/api/programming/starts/' in url:
            return {'ok': True, 'reconciliation': {'start_id': START_ID,
                    'kind': 'batch', 'read_only': True, 'state': 'OUTCOME_UNKNOWN',
                    'reason': 'JOURNAL_INCONSISTENT'}}
        return fake_http(url)
    monkeypatch.setattr(preflight, 'http_json', unknown)
    before = {p.name: p.read_bytes() for p in state.iterdir()}
    with pytest.raises(preflight.Blocked, match='admission not proved inactive'):
        check(state)
    assert before == {p.name: p.read_bytes() for p in state.iterdir()}


@pytest.mark.parametrize('field', ['busy', 'active_job_count', 'owner_kind', 'owner_id'])
def test_missing_ppu_owner_evidence_blocks(state, monkeypatch, field):
    def missing(url):
        value = fake_http(url)
        if url.endswith('/api/status'):
            del value['ppu']['execution'][field]
        return value
    monkeypatch.setattr(preflight, 'http_json', missing)
    with pytest.raises(preflight.Blocked, match='active/unknown execution owner'):
        check(state)


def test_unavailable_manager_blocks(state, monkeypatch):
    def unavailable(url):
        raise preflight.Blocked('endpoint unavailable')
    monkeypatch.setattr(preflight, 'http_json', unavailable)
    with pytest.raises(preflight.Blocked, match='endpoint unavailable'):
        check(state)


@pytest.mark.parametrize('outcome', ['PASS', 'FAIL', 'PARTIAL', 'BLOCKED'])
def test_v2_terminal_outcomes_and_stopped_skips(state, outcome):
    row = completed_v2_batch()
    row['outcome'] = outcome
    row['units'][0]['outcome'] = 'PASS' if outcome == 'PARTIAL' else outcome
    if outcome == 'PARTIAL':
        row['execution_status'] = 'STOPPED'
        row['targets'][0]['site_ids'].append(3)
        row['units'].append({'ppu_alias': 'z2', 'site_id': 3, 'outcome': None,
                             'status': 'SKIPPED', 'attempts': []})
    write_journal(state, 'programming-batches.json.v2',
                  'plasma.manager.programming-batch-journal.v2', 'batches', [row])
    assert check(state)['result'] == 'PASS'


@pytest.mark.parametrize('checkpoint', [1, 2])
def test_actual_deploy_flow_stops_at_either_checkpoint(tmp_path, checkpoint):
    import subprocess
    code = (ROOT / 'scripts/plasmactl-local-control-station').read_text()
    deploy = 'deploy_profile() {' + code.split('deploy_profile() {', 1)[1].split('parse_options()', 1)[0]
    trace = tmp_path / 'trace'
    # Execute the real deploy function with host-only stubs. Any activation
    # call is forbidden; second-check failure may only follow release build.
    stubs = '''
set -Eeuo pipefail
# Extracted deploy_profile() needs the CLI mode flag initialized explicitly.
dev_fresh_state=0
require_linux_user_runtime() { :; }
require_command() { :; }
resolve_base_python() { :; }
validate_settings() { :; }
require_clean_source() { :; }
require_owned_installation() { :; }
current_sha() { echo abc; }
prepare_release() { echo build >> "$trace"; prepared_release=/unused; }
count=0
run_deployment_preflight() {
  count=$((count+1))
  echo "check$count" >> "$trace"
  if (( count == checkpoint )); then return 2; fi
}
readlink() { echo ACTIVATION_FORBIDDEN >> "$trace"; return 99; }
'''
    result = subprocess.run(['bash', '-c', stubs + deploy + '\ndeploy_profile'],
                            env={'PATH': '/usr/bin:/bin', 'trace': str(trace),
                                 'checkpoint': str(checkpoint)}, capture_output=True, text=True)
    assert result.returncode == 2, result.stderr
    assert trace.read_text().splitlines() == (['check1'] if checkpoint == 1
                                             else ['check1', 'build', 'check2'])


@pytest.mark.parametrize('changes', [
    {'execution_status': None}, {'targets': []},
    {'targets': [{'ppu_alias': 'z2', 'site_ids': [True]}]},
    {'targets': [{'ppu_alias': 'other', 'site_ids': [2]}]},
    {'units': None}, {'units': [{'outcome': 'PASS'}]},
])
def test_malformed_v2_terminal_routing_blocks(state, changes):
    row = {**completed_v2_batch(), **changes}
    write_journal(state, 'programming-batches.json.v2',
                  'plasma.manager.programming-batch-journal.v2', 'batches', [row])
    with pytest.raises(preflight.Blocked):
        check(state)


@pytest.mark.parametrize('value', [None, [], {}, 1])
def test_malformed_schema_type_is_blocked(state, value):
    (state / 'programming-batches.json').write_text(json.dumps({'schema': value, 'batches': []}))
    with pytest.raises(preflight.Blocked):
        check(state)
