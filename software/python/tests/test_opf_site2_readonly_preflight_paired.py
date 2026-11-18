"""Host-only regression for the one-shot paired Site 2 Path 2 preflight."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import opf_site2_readonly_preflight_paired as paired

SOURCE = "a" * 40


def _observer(host, source_sha, helper=None):
    assert host == "192.168.2.99"
    assert source_sha == SOURCE
    assert helper is PAIR
    return {
        "schema": paired.preflight.SCHEMA, "source_sha": SOURCE,
        "readiness": "NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS",
        "blockers": [], "rest": {
            "health_ready": True, "site2_idle": True, "site2_enabled": True,
        }, "z2": {
            "engine": {"status": "VERIFIED", "driver": "plasma_swd", "abi": 5},
            "fpga": {"status": "IMAGE", "boot_match": True,
                     "manager_state": "operating"},
            "site2_seal": {"present": False},
            "site2_admission": {"present": False},
            "openocd_pids": [],
        },
    }


PAIR = SimpleNamespace(z2_login_credentials=lambda home:
                       ({"ssh_host": "192.168.2.99"}, Path("/tmp/test-known")))


def test_only_enrolled_host_source_pinned_and_no_dut_or_fpga():
    result = paired.run(SOURCE, pair=PAIR,
                        probe=SimpleNamespace(SCHEMA=paired.preflight.SCHEMA,
                                              run=_observer))
    assert result["result"] == "OBSERVED"
    assert result["engine_selection"] == "VERIFIED"
    assert result["fpga_same_boot"] is True
    assert result["dut_flash"] == result["fpga_reload"] == "NOT_RUN"
    assert result["hardware_site_lock"] == "NOT_VERIFIED"
    assert result["provider_runtime_resolution"] == "NOT_RUN"


@pytest.mark.parametrize("host", [
    "example.com", "8.8.8.8", "127.0.0.1notanip", "",
])
def test_invalid_paired_target_fails_before_observation(host):
    fake = SimpleNamespace(z2_login_credentials=lambda home:
                           ({"ssh_host": host}, Path("/tmp/test-known")))
    observer = SimpleNamespace(
        SCHEMA=paired.preflight.SCHEMA,
        run=lambda *a, **kw: pytest.fail("probe must never execute"),
    )
    with pytest.raises(ValueError, match="ENROLLED_TARGET_INVALID"):
        paired.run(SOURCE, pair=fake, probe=observer)


def test_wrong_source_sha_fails_before_private_pairing():
    fake = SimpleNamespace(
        z2_login_credentials=lambda home: pytest.fail("pair must not be opened"))
    with pytest.raises(ValueError, match="PINNED_SOURCE_INVALID"):
        paired.run("not-a-sha", pair=fake)


def test_mismatched_preflight_receipt_not_qualified():
    observed = _observer("192.168.2.99", SOURCE, PAIR)
    observed["source_sha"] = "b" * 40
    probe = SimpleNamespace(SCHEMA=paired.preflight.SCHEMA,
                            run=lambda *a, **kw: observed)
    with pytest.raises(ValueError, match="PREFLIGHT_RECEIPT_INVALID"):
        paired.run(SOURCE, pair=PAIR, probe=probe)


def test_read_only_blockers_are_reported_not_falsified():
    observed = _observer("192.168.2.99", SOURCE, PAIR)
    observed["blockers"] = ["SITE2_SEALED"]
    observed["readiness"] = "BLOCKED_OR_UNVERIFIED"
    observed["z2"]["site2_seal"]["present"] = True
    probe = SimpleNamespace(SCHEMA=paired.preflight.SCHEMA,
                            run=lambda *a, **kw: observed)
    report = paired.run(SOURCE, pair=PAIR, probe=probe)
    assert report["readiness"] == "BLOCKED_OR_UNVERIFIED"
    assert report["blockers"] == ["SITE2_SEALED"]
    assert report["site2_sealed"] is True
