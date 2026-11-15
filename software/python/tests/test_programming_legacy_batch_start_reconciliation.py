"""Read-only legacy Start recovery; never edits durable Start/Batch journals."""
from __future__ import annotations

from copy import deepcopy
import threading

import pytest

from plasma_manager.programming import BundleProgrammingWorkflow, PROGRAMMING


START_ID = "a" * 32
BATCH_ID = "b" * 32
LEGACY_START = {
    "start_id": START_ID, "kind": "batch", "state": "CONSUMED",
    "ppu_alias": "z2", "site_id": 2, "operation": PROGRAMMING,
    "batch_id": BATCH_ID, "targets": None,
}
TERMINAL_BATCH = {
    "batch_id": BATCH_ID, "start_id": START_ID,
    "targets": [{"ppu_alias": "z2", "site_ids": [2]}],
    "units": [{"ppu_alias": "z2", "site_id": 2, "outcome": "PASS",
               "attempts": [{"job_binding_sha256": "c" * 64,
                             "outcome": "PASS", "safe_off": True}]}],
    "operations": ["erase", "program", "verify"],
    "state": "finished", "outcome": "PASS", "reason": None,
}


def reconcile(start=None, batch=None) -> dict:
    """Build a real workflow reconciliation view with no device/coordinator."""
    workflow = object.__new__(BundleProgrammingWorkflow)
    workflow._lock = threading.RLock()
    workflow._runs = {}
    workflow._starts = {START_ID: deepcopy(LEGACY_START if start is None else start)}
    target = deepcopy(TERMINAL_BATCH if batch is None else batch)
    # Explicit local-only Batch lookup; no PPU, scheduler or journal writes.
    return workflow.reconcile_start(
        START_ID, find_batch=lambda sid: target if sid == START_ID else None,
    )["reconciliation"]


def test_proven_pre_scope_single_site_terminal_start_confirms_readonly() -> None:
    start_before = deepcopy(LEGACY_START)
    batch_before = deepcopy(TERMINAL_BATCH)
    result = reconcile(start_before, batch_before)
    assert result["state"] == "TERMINAL_CONFIRMED"
    assert result["kind"] == "batch"
    assert result["outcome"] == "PASS"
    assert result["batch"]["batch_id"] == BATCH_ID
    assert result["identity"]["ppu_alias"] == "z2"
    assert result["identity"]["site_id"] == 2
    assert start_before == LEGACY_START
    assert batch_before == TERMINAL_BATCH


@pytest.mark.parametrize("field,value", [
    ("ppu_alias", "other"),
    ("ppu_alias", None),
    ("site_id", 1),
    ("site_id", None),
    ("kind", "run"),
    ("state", "ISSUED"),
    ("batch_id", "f" * 32),
    ("operation", "read"),
    ("start_scope", "MANAGER_SCOPE"),
    ("targets", [{"ppu_alias": "z2", "site_ids": [3]}]),
])
def test_legacy_start_identity_disagreement_stays_unknown(field, value) -> None:
    start = deepcopy(LEGACY_START)
    start[field] = value
    view = reconcile(start)
    assert view["state"] == "OUTCOME_UNKNOWN"
    assert view["reason"] == "JOURNAL_INCONSISTENT"


def test_wrong_start_id_does_not_match_even_when_batch_id_matches() -> None:
    batch = deepcopy(TERMINAL_BATCH)
    batch["start_id"] = "f" * 32
    view = reconcile(batch=batch)
    assert view["state"] == "OUTCOME_UNKNOWN"
    assert view["reason"] == "START_IDENTITY_MISMATCH"


def test_multi_target_never_infers_a_historical_missing_target_set() -> None:
    batch = deepcopy(TERMINAL_BATCH)
    batch["targets"][0]["site_ids"] = [2, 3]
    view = reconcile(batch=batch)
    assert view["state"] == "OUTCOME_UNKNOWN"
    assert view["reason"] == "JOURNAL_INCONSISTENT"


def test_manager_scoped_missing_targets_is_not_legacy() -> None:
    modern = deepcopy(LEGACY_START)
    modern.update(start_scope="MANAGER_SCOPE", ppu_alias=None)
    view = reconcile(modern)
    assert view["state"] == "OUTCOME_UNKNOWN"
    assert view["reason"] == "JOURNAL_INCONSISTENT"


def test_real_outcome_unknown_is_never_upgraded_to_pass() -> None:
    batch = deepcopy(TERMINAL_BATCH)
    batch.update(state="finished", outcome="OUTCOME_UNKNOWN",
                 reason="MANAGER_RESTARTED_DURING_BATCH")
    view = reconcile(batch=batch)
    assert view["state"] == "OUTCOME_UNKNOWN"
    assert view["outcome"] == "OUTCOME_UNKNOWN"
    assert view["reason"] == "MANAGER_RESTARTED_DURING_BATCH"


@pytest.mark.parametrize("invalid_site", [0, 65, True, -1])
def test_historical_site_must_be_a_real_one_based_hardware_site(invalid_site) -> None:
    record = deepcopy(LEGACY_START)
    batch = deepcopy(TERMINAL_BATCH)
    record["site_id"] = invalid_site
    batch["targets"][0]["site_ids"] = [invalid_site]
    view = reconcile(record, batch)
    assert view["state"] == "OUTCOME_UNKNOWN"
    assert view["reason"] == "JOURNAL_INCONSISTENT"
