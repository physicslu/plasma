"""Host-only: the start journal survives a Control Station ROLLBACK.

PR-C made a Batch start Manager-owned, so its record carries no PPU. The
journal still writes ``ppu_alias`` as a string, because a Manager rolled back
to a release that predates PR-C validates that field's type and refuses to
start when it fails. These tests exercise that claim as behaviour, not as a
type assertion: an older Manager must START, must still see both an
unconsumed and a consumed start, must keep the history it did not write, and
must not destroy this release's transaction evidence when it persists.

The empty ``ppu_alias`` is a placeholder and never an identity: the record
says what it is in ``start_scope``, and no PPU is ever addressed by "".

No PPU, FPGA or DUT: this is a journal contract only.
"""
from __future__ import annotations

import json

import pytest

from plasma_manager.programming import (
    MANAGER_SCOPE, BundleProgrammingWorkflow, CONFIRM_TOKEN, ProgrammingError, VOID_TOKEN,
)

from .test_bundle_programming_workflow import (
    ALIAS, FakeCoordinator, FakeGateway, OPS_RESOURCE_SHA, READ_BODY, image, make,
)


# --------------------------------------------------------------- the old reader
# Verbatim behaviour of `_load_journal`'s start validation as it stood before
# PR-C (main 9e5fbcfc1). A rolled-back Manager runs exactly this: any record it
# rejects here is a Control Station that will not start.

def legacy_load(path) -> dict[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    starts: dict[str, dict] = {}
    for item in data.get("starts") or []:
        if (type(item["start_id"]) is not str or type(item["ppu_alias"]) is not str
                or item["kind"] not in ("run", "batch")
                or item["state"] not in ("ISSUED", "CONSUMED", "VOIDED")):
            raise ValueError("start record")
        starts[item["start_id"]] = dict(item)
    return starts


def legacy_persist(path, starts: dict[str, dict]) -> None:
    """The old writer: it writes the records it loaded, verbatim."""
    data = json.loads(path.read_text(encoding="utf-8"))
    ordered = sorted(starts.values(), key=lambda record: record["issued_at"])
    path.write_text(json.dumps({**data, "starts": ordered}, sort_keys=True), encoding="utf-8")


def rig(tmp_path):
    coord = FakeCoordinator(active_sha="e" * 64)
    gateway = FakeGateway(image=image(), coordinator=coord,
                          resource_for=lambda _a: OPS_RESOURCE_SHA)
    workflow, _c, _g = make(tmp_path, coordinator=coord, gateway=gateway)
    return workflow, coord, gateway


def journal(tmp_path):
    return tmp_path / "runs.json"


def written(tmp_path) -> dict[str, dict]:
    return {record["start_id"]: record
            for record in json.loads(journal(tmp_path).read_text(encoding="utf-8"))["starts"]}


def seeded(tmp_path):
    """One run start, one unconsumed Batch start, one consumed Batch start."""
    workflow, coord, gateway = rig(tmp_path)
    planned = workflow.plan(ALIAS, READ_BODY)["plan"]
    workflow.start(ALIAS, {"plan_id": planned["plan_id"], "confirm": CONFIRM_TOKEN})
    pending = workflow.issue_batch_start({"kind": "batch"})["start"]["start_id"]
    consumed = workflow.issue_batch_start({"kind": "batch"})["start"]["start_id"]
    targets = [{"ppu_alias": ALIAS, "site_ids": [2, 3]}]
    workflow.consume_batch_start(consumed, "b" * 32, targets)
    return workflow, coord, gateway, planned["plan_id"], pending, consumed


# ------------------------------------------------------------ what is written

def test_a_canonical_start_says_so_and_carries_no_ppu_identity(tmp_path):
    _w, _c, _g, plan_id, pending, consumed = seeded(tmp_path)
    records = written(tmp_path)
    for start_id in (pending, consumed):
        record = records[start_id]
        # The record states its own scope; the empty alias is only a
        # placeholder for the older reader's type check.
        assert record["start_scope"] == MANAGER_SCOPE
        assert record["ppu_alias"] == ""
        assert record["kind"] == "batch"
    # A run start is PPU-owned and is untouched by PR-C.
    assert records[plan_id]["ppu_alias"] == ALIAS
    assert "start_scope" not in records[plan_id]


# --------------------------------------------------------- the rollback itself

def test_an_older_manager_starts_on_a_journal_this_release_wrote(tmp_path):
    _w, _c, _g, plan_id, pending, consumed = seeded(tmp_path)
    # Startup: the old validation accepts every record. A raise here is a
    # Control Station that will not come up after a rollback.
    old = legacy_load(journal(tmp_path))
    assert set(old) == {plan_id, pending, consumed}
    # History it did not write is kept, with its state and evidence.
    assert old[pending]["state"] == "ISSUED"
    assert old[consumed]["state"] == "CONSUMED"
    assert old[consumed]["batch_id"] == "b" * 32
    assert old[consumed]["targets"] == [{"ppu_alias": ALIAS, "site_ids": [2, 3]}]
    assert old[plan_id]["kind"] == "run" and old[plan_id]["state"] == "CONSUMED"


def test_the_placeholder_alias_matches_no_ppu_for_an_older_manager(tmp_path):
    _w, _c, _g, _plan, pending, consumed = seeded(tmp_path)
    old = legacy_load(journal(tmp_path))
    # The pre-PR-C reconcile and void compared `record["ppu_alias"] != alias`.
    # "" is not an alias any registry can hold, so an older Manager answers
    # "not this PPU's" for a canonical start instead of granting it to one.
    for start_id in (pending, consumed):
        assert old[start_id]["ppu_alias"] == ""
        assert old[start_id]["ppu_alias"] != ALIAS


def test_an_older_manager_persisting_keeps_this_release_s_evidence(tmp_path):
    workflow, coord, gateway, plan_id, pending, consumed = seeded(tmp_path)
    # The rolled-back Manager runs for a while and writes the journal itself.
    legacy_persist(journal(tmp_path), legacy_load(journal(tmp_path)))
    # Rolling forward again: the canonical starts are still canonical, the
    # Batch transaction evidence is intact, and nothing became a PPU.
    workflow2 = BundleProgrammingWorkflow(
        coordinator=coord, registry=workflow.registry,
        gateway_client_factory=lambda endpoint, timeout: gateway,
        gate=workflow.gate, request_timeout_s=5.0, routes_root=workflow.routes_root,
        journal_path=journal(tmp_path), sleep=lambda _s: None,
        spawn=lambda target: target(), poll_interval_s=0.0)
    for start_id in (pending, consumed):
        record = workflow2._starts[start_id]
        assert record["ppu_alias"] is None
        assert record["start_scope"] == MANAGER_SCOPE
    assert workflow2._starts[consumed]["batch_id"] == "b" * 32
    assert workflow2._starts[consumed]["targets"] == [{"ppu_alias": ALIAS, "site_ids": [2, 3]}]
    assert workflow2._starts[consumed]["state"] == "CONSUMED"
    assert workflow2._starts[plan_id]["ppu_alias"] == ALIAS
    # The consumed start still reconciles as admitted, so a replay is still a
    # 409 rather than a second Batch.
    view = workflow2.reconcile_start(consumed)["reconciliation"]
    assert view["ppu_alias"] is None
    assert view["state"] == "OUTCOME_UNKNOWN"  # the Batch record itself is gone here
    assert view["reason"] == "ADMITTED_RECORD_MISSING"
    with pytest.raises(ProgrammingError) as caught:
        workflow2.require_batch_start(consumed)
    assert caught.value.code == "programming_start_not_startable"


def test_an_unconsumed_start_does_not_survive_a_restart_as_startable(tmp_path):
    workflow, coord, gateway, _plan, pending, _consumed = seeded(tmp_path)
    legacy_persist(journal(tmp_path), legacy_load(journal(tmp_path)))
    workflow2 = BundleProgrammingWorkflow(
        coordinator=coord, registry=workflow.registry,
        gateway_client_factory=lambda endpoint, timeout: gateway,
        gate=workflow.gate, request_timeout_s=5.0, routes_root=workflow.routes_root,
        journal_path=journal(tmp_path), sleep=lambda _s: None,
        spawn=lambda target: target(), poll_interval_s=0.0)
    # Admissibility is memory only, as it always was: after any restart the
    # ISSUED record is still there to be reconciled, but nothing can start it.
    assert workflow2._starts[pending]["state"] == "ISSUED"
    with pytest.raises(ProgrammingError):
        workflow2.require_batch_start(pending)
    view = workflow2.reconcile_start(pending)["reconciliation"]
    assert view["state"] == "NOT_ACCEPTED"
    assert view["ppu_alias"] is None
    # It can still be voided, and voiding names no PPU.
    voided = workflow2.void_start(pending, {"void": VOID_TOKEN})["reconciliation"]
    assert voided["state"] == "NOT_ACCEPTED"
    assert voided["ppu_alias"] is None


# -------------------------------------------------------- broken records fail

@pytest.mark.parametrize("patch", [
    # Manager scope with a PPU on it: the two statements contradict.
    {"start_scope": MANAGER_SCOPE, "ppu_alias": ALIAS},
    # A run start is PPU-owned; the placeholder can never stand in for one.
    {"kind": "run", "ppu_alias": "", "start_scope": MANAGER_SCOPE},
    {"kind": "run", "ppu_alias": ""},
])
def test_a_record_that_contradicts_itself_refuses_to_load(tmp_path, patch):
    workflow, coord, gateway, _plan, _pending, consumed = seeded(tmp_path)
    data = json.loads(journal(tmp_path).read_text(encoding="utf-8"))
    for record in data["starts"]:
        if record["start_id"] == consumed:
            record.update(patch)
    journal(tmp_path).write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RuntimeError):
        BundleProgrammingWorkflow(
            coordinator=coord, registry=workflow.registry,
            gateway_client_factory=lambda endpoint, timeout: gateway,
            gate=workflow.gate, request_timeout_s=5.0, routes_root=workflow.routes_root,
            journal_path=journal(tmp_path), sleep=lambda _s: None,
            spawn=lambda target: target(), poll_interval_s=0.0)
