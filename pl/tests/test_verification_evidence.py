"""Host-only adversarial tests for Verification Platform v1 evidence honesty."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pl.tools import verification_evidence as ev


@pytest.fixture
def valid_receipt():
    paths, digest = ev.source_fingerprint([
        "pl/rtl/bus/fixed_ppu_unified_axi_site1.sv",
        "pl/rtl/bus/fixed_fpga_swd_site_axi_lite.sv",
    ])
    return {
        "schema_version": "plasma-verification-v1",
        "commit_sha": "a" * 40,
        "stage": "SIM-2", "status": "PASS",
        "runner_class": "github-hosted", "runner_identity": "host / ubuntu24 / 1",
        "tools": {"python": "3.12.1", "pytest": "8.4.2", "cocotb": "1.9.2",
                  "cocotb_test": "0.2.6", "simulator": "Icarus Verilog 11.0"},
        "rtl_top": "fixed_ppu_unified_axi_site1",
        "rtl_source_digest": digest, "rtl_sources": paths,
        "driver_module": "plasma_interfaces.fixed_abi_swd.FixedABISWDController",
        "suite": "pl/verification/test_fixed_ppu_unified_axi_rtl.py",
        "test_counts": {"passed": 1, "failed": 0, "errors": 0, "skipped": 0},
        "seed": None, "ci_run_url": None, "artifacts": ["sim.log"],
        "claims": ["One actual pytest runner successfully completed"],
        "not_tested": list(ev.SIM_NOT_TESTED),
        "exit_code": 0, "reason": None,
    }


def test_valid_receipt_and_measured_source_digest(valid_receipt):
    ev.validate_receipt(valid_receipt, verify_source=True)


@pytest.mark.parametrize(("field", "replacement"), [
    ("schema_version", "plasma-verification-v2"),
    ("commit_sha", "unknown"),
    ("stage", "HIL"),
    ("status", "SUCCESS"),
    ("rtl_source_digest", "0" * 64),
    ("runner_class", "trusted-robot"),
])
def test_schema_refuses_invalid_identity_or_enums(valid_receipt, field, replacement):
    doc = copy.deepcopy(valid_receipt)
    doc[field] = replacement
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc, verify_source=True)


def test_schema_refuses_unrecognised_claim_fields(valid_receipt):
    doc = dict(valid_receipt, physically_programmed=True)
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc)


@pytest.mark.parametrize(("key", "value"), [
    ("exit_code", 1),
    ("reason", "not actually executed"),
    ("claims", []),
    ("rtl_top", None),
    ("driver_module", None),
    ("rtl_sources", []),
])
def test_pass_cannot_be_invented_from_missing_evidence(valid_receipt, key, value):
    doc = copy.deepcopy(valid_receipt)
    doc[key] = value
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc)


def test_pass_rejects_missing_tool_version(valid_receipt):
    doc = copy.deepcopy(valid_receipt)
    doc["tools"]["simulator"] = None
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc)


def test_pass_rejects_skipped_only_or_hidden_failure(valid_receipt):
    doc = copy.deepcopy(valid_receipt)
    doc["test_counts"] = {"passed": 0, "failed": 0, "skipped": 1, "errors": 0}
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc)
    doc["test_counts"] = {"passed": 1, "failed": 1, "skipped": 0, "errors": 0}
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc)


def test_host_only_receipt_must_include_physical_nonclaims(valid_receipt):
    doc = copy.deepcopy(valid_receipt)
    doc["not_tested"].remove(ev.SIM_NOT_TESTED[3])
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc)


def test_mutated_rtl_fingerprint_is_rejected(valid_receipt):
    doc = copy.deepcopy(valid_receipt)
    doc["rtl_sources"][0]["sha256"] = "b" * 64
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc, verify_source=True)


def test_unsafe_source_escape_rejected():
    with pytest.raises(ev.EvidenceError):
        ev.source_fingerprint(["../tmp/unsafe.sv"])
    with pytest.raises(ev.EvidenceError):
        ev.source_fingerprint(["pl/rtl/bus/fixed_ppu_unified_axi_site1.sv"] * 2)


def test_not_run_cannot_be_misreported_as_pass(valid_receipt):
    doc = copy.deepcopy(valid_receipt)
    doc.update(status="NOT_RUN", exit_code=None, reason="No declared hardware authority",
               claims=[], test_counts={"passed": 0, "failed": 0, "skipped": 0, "errors": 0})
    ev.validate_receipt(doc)
    doc["claims"] = ["Hardware PASS"]
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc)


def test_blocked_receipt_can_have_empty_rtl_sources(valid_receipt):
    doc = copy.deepcopy(valid_receipt)
    doc.update(status="BLOCKED", exit_code=None, reason="Tool not installed",
               rtl_sources=[], rtl_source_digest=None, claims=[],
               test_counts={"passed": 0, "failed": 0, "skipped": 0, "errors": 0})
    ev.validate_receipt(doc)


def test_fail_requires_nonzero_exit_code_and_no_success_claims(valid_receipt):
    doc = copy.deepcopy(valid_receipt)
    doc.update(status="FAIL", exit_code=1, reason="pytest reported a failure", claims=[],
               test_counts={"passed": 0, "failed": 1, "skipped": 0, "errors": 0})
    ev.validate_receipt(doc)
    doc["exit_code"] = 0
    with pytest.raises(ev.EvidenceError):
        ev.validate_receipt(doc)


def test_junit_count_is_from_actual_testcases_not_text(tmp_path: Path):
    result = tmp_path / "result.xml"
    result.write_text(
        '<testsuites><testsuite tests="4">'
        '<testcase name="ok"/><testcase name="bad"><failure/></testcase>'
        '<testcase name="error"><error/></testcase>'
        '<testcase name="skip"><skipped/></testcase>'
        '</testsuite></testsuites>', encoding="utf-8",
    )
    assert ev.junit_counts(result) == {"passed": 1, "failed": 1, "errors": 1,
                                       "skipped": 1}
    result.write_text("<testsuite tests='5'/>", encoding="utf-8")
    with pytest.raises(ev.EvidenceError):
        ev.junit_counts(result)


def test_validate_cli_rejects_tampered_receipt(valid_receipt, tmp_path):
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(valid_receipt), encoding="utf-8")
    assert ev.main(["validate", "--receipt", str(path), "--verify-source"]) == 0
    doc = copy.deepcopy(valid_receipt)
    doc["status"] = "PASS"
    doc["test_counts"]["passed"] = 0
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert ev.main(["validate", "--receipt", str(path)]) != 0


def test_receipt_sources_are_exactly_the_compiled_cocotb_sources(valid_receipt):
    suite, _ = ev._under_root(valid_receipt["suite"])
    ev.assert_pilot_source_contract(
        suite, valid_receipt["rtl_sources"] + [
            {"path": "pl/rtl/site/swd_waveform_engine.sv", "sha256": "0" * 64},
            {"path": "pl/rtl/site/swd_transaction_master.sv", "sha256": "0" * 64},
            {"path": "pl/rtl/bus/fixed_fpga_ppu_global_identity_axi_lite.sv",
             "sha256": "0" * 64},
        ], "fixed_ppu_unified_axi_site1",
    )


def test_receipt_must_reject_unmeasured_compiled_rtl(valid_receipt):
    suite, _ = ev._under_root(valid_receipt["suite"])
    with pytest.raises(ev.EvidenceError, match="Receipt RTL list differs"):
        ev.assert_pilot_source_contract(suite, valid_receipt["rtl_sources"],
                                        "fixed_ppu_unified_axi_site1")


def test_receipt_must_reject_wrong_simulator_top(valid_receipt):
    suite, _ = ev._under_root(valid_receipt["suite"])
    with pytest.raises(ev.EvidenceError, match="RTL simulator/top mismatch"):
        ev.assert_pilot_source_contract(suite, valid_receipt["rtl_sources"],
                                        "not_the_simulated_top")
