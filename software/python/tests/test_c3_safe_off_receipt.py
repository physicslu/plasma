"""C-3: the safe release an Adapter reports is observed, never asserted.

Host-only. Mock subprocesses throughout; no Z2, MMIO, FPGA, OpenOCD or DUT.

``_session`` is the only place that proves a Site was left safe, and it is the
only place that may say so. These tests hold two things:

* every public entry point -- ``probe``, ``programming``, ``read`` and the
  legacy ``flash_cycle`` -- fails closed when the native ps_owner marker is
  absent, so no receipt can carry a safe release the session did not observe;
* the receipt and the root-private evidence record report the same
  observation, because both read one ``SafeOff``.

Before this, each entry point returned the literal ``"safe_off": True``. That
was true only because ``_session`` happens to raise first -- an invariant
nothing tested and nothing enforced. Only ``probe`` had a missing-marker test.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from .test_ppu_stage_c3_site_worker import (F103, GOOD, SAFE_OFF_RECEIPT, abi5,
                                            flash_image, flash_log, make_abi5,
                                            worker)

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux") or os.geteuid() == 0,
                                reason="Linux SO_PEERCRED, non-root")

ADDRESS = 0x08000400
PAYLOAD = b"X" * 20
# A session that connected and read the DP but never reported the ps_owner
# SAFE_OFF line: the Site's state at release is not known.
NO_MARKER = b"Info : SWD DPIDR 0x1ba01477\nPLASMA_DPREG0=0x1ba01477\n"


def read_range() -> object:
    profile = worker.parse_flash_profile(dict(F103))
    return worker.FlashRange(profile, "read", ADDRESS, 1024)


def call(adapter, operation: str):
    kwargs: dict[str, object] = {"deadline": time.monotonic() + 30,
                                 "cancel": threading.Event()}
    if operation == "programming":
        kwargs["image"] = flash_image(PAYLOAD, load_address=ADDRESS)
        kwargs["operations"] = ("erase", "program", "verify")
    elif operation == "read":
        kwargs["flash_range"] = read_range()
    elif operation == "flash_cycle":
        kwargs["image"] = flash_image(PAYLOAD, load_address=ADDRESS)
    return adapter.run(2, operation, **kwargs)


OPERATIONS = ["probe", "programming", "read", "flash_cycle"]


# ------------------------------------------------- the observation itself


@pytest.mark.parametrize("marker,revoked,reason,verified", [
    (True, True, None, True),
    # The marker alone is not a safe release: the root admission must be gone.
    (True, False, None, False),
    # A killed or cancelled child may have died mid-transaction.
    (True, True, "OPERATION_TIMEOUT", False),
    (True, True, "CANCELLED_DURING_OPERATION", False),
    (False, True, None, False),
    (False, False, "OPERATION_TIMEOUT", False),
])
def test_a_safe_release_needs_every_condition(marker, revoked, reason, verified):
    observed = abi5.SafeOff(marker_present=marker, admission_revoked=revoked,
                            termination_reason=reason)
    assert observed.verified is verified
    assert observed.receipt()["safe_off"] is verified
    assert observed.receipt()["safe_off_evidence"] == {
        "marker_present": marker, "admission_revoked": revoked,
        "termination_reason": reason}


# -------------------------------------------------- every entry point fails closed


@pytest.mark.parametrize("operation", OPERATIONS)
def test_no_entry_point_reports_a_safe_release_it_did_not_observe(tmp_path, operation):
    """The regression this PR exists for: the marker is the only source."""
    adapter, calls, _ = make_abi5(tmp_path, log=NO_MARKER, flash_readback=PAYLOAD)
    with pytest.raises(worker.TransportUnknown, match="SAFE_OFF_NOT_VERIFIED"):
        call(adapter, operation)
    # Fail closed, but never leave the Site admitted.
    assert calls["run"] == [["admit", "2"], ["revoke", "2"]]


@pytest.mark.parametrize("operation", OPERATIONS)
def test_a_missing_marker_is_never_rescued_by_a_successful_operation(tmp_path, operation):
    """A perfect Flash log without the marker is still not a safe release."""
    log = flash_log(ADDRESS, 1024, len(PAYLOAD)).replace(
        b"SAFE_OFF_MODE_OFF_VERIFIED\n", b"")
    adapter, _calls, _ = make_abi5(tmp_path, log=log, flash_readback=PAYLOAD)
    with pytest.raises(worker.TransportUnknown, match="SAFE_OFF_NOT_VERIFIED"):
        call(adapter, operation)


# ------------------------------------------------------- receipt and evidence agree


@pytest.mark.parametrize("operation", ["probe", "programming", "read", "flash_cycle"])
def test_the_receipt_reports_the_observation(tmp_path, operation):
    readback = PAYLOAD if operation != "read" else b"\x00" * 1024
    log = (GOOD if operation == "probe"
           else flash_log(ADDRESS, 1024, len(PAYLOAD)))
    adapter, _calls, _ = make_abi5(tmp_path, log=log, flash_readback=readback)
    result = call(adapter, operation)
    assert result["result"] == "PASS"
    assert {k: result[k] for k in SAFE_OFF_RECEIPT} == SAFE_OFF_RECEIPT


def test_the_receipt_and_the_root_private_record_cannot_disagree(tmp_path):
    adapter, _calls, _ = make_abi5(tmp_path, log=GOOD)
    result = call(adapter, "probe")
    [metadata] = sorted((tmp_path / "openocd-evidence").glob("*.json"))
    record = json.loads(metadata.read_text())
    # Both sides read one SafeOff, so the private record is the receipt's proof.
    assert record["safe_off_verified"] is result["safe_off"]
    assert record["safe_off_marker_present"] is result["safe_off_evidence"]["marker_present"]
    assert record["admission_revoked"] is result["safe_off_evidence"]["admission_revoked"]
    assert record["termination_reason"] == result["safe_off_evidence"]["termination_reason"]


def test_the_operator_recovery_probe_reports_it_too(tmp_path):
    """verify_safe_off is recovery evidence; it carries the same observation."""
    adapter, _calls, _ = make_abi5(tmp_path, log=GOOD)
    out = adapter.verify_safe_off(2, deadline=time.monotonic() + 5)
    assert out["result"] == "SAFE_OFF_VERIFIED"
    assert {k: out[k] for k in SAFE_OFF_RECEIPT} == SAFE_OFF_RECEIPT
    assert out["log_sha256"] == hashlib.sha256(GOOD.decode().encode()).hexdigest()


def test_no_literal_safe_off_remains_in_the_adapter():
    """The value is derived; a literal would silently outlive its check."""
    source = Path(abi5.__file__).read_text()
    assert '"safe_off": True' not in source
    assert '"safe_off": False' not in source
    assert source.count("def receipt(") == 1
