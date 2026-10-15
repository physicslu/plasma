#!/usr/bin/env python3
"""ADR-0002 source-only governance contract tests (no device certification).

This validates the *new* vendor-agnostic research protocol and synthetic
negative transitions. It intentionally does NOT reclassify historical cohorts,
authorize Production/Catalog visibility, or execute OpenOCD/PPU.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADR = ROOT / "docs/adr/0002-openocd-software-qualified-catalog-visibility.md"
CONTRACT = ROOT / "docs/architecture/openocd-reverse-coverage-research-contract-v1.json"

BASE_P0 = {
    "manufacturer": "SYNTHETIC_VENDORA",
    "provider": "openocd-upstream",
    "provider_version": "0.12.0",
    "source_commit": "synthetic-locked-commit",
    "priority": "P0",
    "software_support": "CANDIDATE",
    "investigation_state": "P0_REVIEW_PROPOSED",
    "bounded_scope": "target/target-a.cfg + flash/driver-a.c",
    "pinned_provider": True,
    "target_config": True,
    "resolved_include_graph": True,
    "flash_driver_linkage": True,
    "operation_source_path": True,
    "credible_silicon_applicability_path": True,
    "bounded_target_or_driver_or_silicon_clue": True,
    "stop_reason": None,
    "reopen_triggers": [],
}


def audit_contract(contract: dict, adr: str) -> None:
    """Fail closed if the frozen documentary policy loses its hard boundaries."""
    expected = {
        "schema_version": 1,
        "contract_id": "ADR-0002_VENDOR_AGNOSTIC_OPENOCD_REVERSE_RESEARCH_V1",
        "authority": "RESEARCH_PRIORITY_AND_EVIDENCE_ONLY",
        "manufacturer_policy": "NO_MANUFACTURER_ALLOWLIST",
        "backend_policy": "PINNED_APPROVED_OPENOCD_PROVIDER_ONLY",
        "priority_states": ["P0", "P1", "P2"],
        "p1_bounded_outcomes": [
            "PROPOSE_P0", "CLOSE_P1_EVIDENCE_GAP", "ARCHIVE_P2"
        ],
        "p1_reopen_triggers": [
            "PINNED_PROVIDER_OR_SOURCE_CHANGED",
            "NEW_VERIFIABLE_MANUFACTURER_OR_DEVICE_EVIDENCE",
            "NEW_APPROVED_BUSINESS_NEED",
        ],
        "historical_evidence_policy": "PRESERVE_RECORDS_NO_BULK_RECLASSIFICATION",
        "runtime_or_production_changed": False,
    }
    for key, value in expected.items():
        if contract.get(key) != value:
            raise ValueError("ADR-0002 reverse policy drift: " + key)
    priorities = contract["priority_states"]
    qualify = contract["software_qualification_states"]
    assert len(priorities) == len(set(priorities)) == 3
    if qualify != ["UNKNOWN", "CANDIDATE", "SUPPORTED", "UNSUPPORTED"]:
        raise ValueError("software qualifier enum drift")
    if set(priorities) & set(qualify):
        raise ValueError("priority accidentally collapsed into software qualification")
    required_p0 = {
        "pinned_provider", "target_config", "resolved_include_graph",
        "flash_driver_linkage", "operation_source_path",
        "credible_silicon_applicability_path",
    }
    if set(contract["p0_required_source_evidence"]) != required_p0:
        raise ValueError("P0 path evidence weakened")
    if contract.get("capability_index_key") != [
        "provider", "provider_version_or_commit", "target_config",
        "flash_driver", "silicon_identity_or_probe_rule",
    ]:
        raise ValueError("manufacturer replaced the capability index key")
    required_research = {
        "bounded_scope", "source_checked_at", "missing_evidence", "stop_reason",
        "reopen_triggers", "research_priority", "investigation_state",
        "decision_source_ref",
    }
    if not required_research.issubset(contract["review_control_fields"]):
        raise ValueError("P1 traceable bounded stop/reopen fields removed")
    forbidden_inferences = {
        "exact_icpn_software_supported", "installed_ppu_runtime_binary_available",
        "hardware_hil_passed", "public_catalog_eligible", "job_execution_authorized",
    }
    if not forbidden_inferences.issubset(contract["not_proven_by_p0"]):
        raise ValueError("P0 incorrectly grants product/runtime permission")
    needs_adr = [
        "### Vendor-agnostic OpenOCD Reverse Coverage SOP",
        "NO_MANUFACTURER_ALLOWLIST",
        "Provider + Version/Commit + Target + Flash Driver + Silicon Identity/Probe Rule",
        "CLOSE_P1_EVIDENCE_GAP", "CLOSED_EVIDENCE_GAP",
        "PROPOSE_P0", "ARCHIVE_P2", "Phase 2 — CURRENT",
        "Phase 3 — DEFERRED", "SUPPORTED",
        "本修訂不重分類",
    ]
    # Scope label is encoded in the machine contract; the prose explicitly says
    # there is no manufacturer allowlist without assuming the same enum spelling.
    needs_adr.remove("NO_MANUFACTURER_ALLOWLIST")
    for heading_or_invariant in needs_adr:
        if heading_or_invariant not in adr:
            raise ValueError("ADR-0002 lacks promised evidence boundary: " +
                             heading_or_invariant)
    if "不設 Manufacturer／Brand Allowlist" not in adr:
        raise ValueError("ADR-0002 manufacturer restriction is ambiguous")


def audit_research_record(record: dict, contract: dict) -> None:
    """Source-only priority audit for new proposals; not a SUPPORT gate."""
    priority = record.get("priority")
    if priority not in contract["priority_states"]:
        raise ValueError("unknown research priority")
    if record.get("software_support") not in ("UNKNOWN", "CANDIDATE"):
        raise ValueError("research priority cannot grant software SUPPORTED/UNSUPPORTED")
    if not record.get("provider") or not record.get("source_commit") or not record.get("bounded_scope"):
        raise ValueError("provider and source-bound scope missing")
    if record.get("investigation_state") not in contract["investigation_states"]:
        raise ValueError("unknown bounded investigation state")

    full = all(record.get(field) is True
               for field in contract["p0_required_source_evidence"])
    if priority == "P0":
        if not full:
            raise ValueError("P0 has incomplete pinned programming source route")
        if record["investigation_state"] not in ("P0_REVIEW_PROPOSED", "REOPENED"):
            raise ValueError("P0 research state is not reviewed")
    elif priority == "P1":
        if not record.get("bounded_target_or_driver_or_silicon_clue"):
            raise ValueError("P1 lacks credible source clue")
        if full:
            raise ValueError("P1 full-source route must be explicitly proposed for P0 review")
        if record["investigation_state"] == "CLOSED_EVIDENCE_GAP":
            if not record.get("stop_reason") or not record.get("reopen_triggers"):
                raise ValueError("closed P1 needs stop reason and reopening criteria")
    else:
        if record["investigation_state"] != "P2_ARCHIVED" and record["investigation_state"] != "REOPENED":
            raise ValueError("P2 not archived/reopened")
        if record.get("stop_reason") not in contract["p2_stop_reasons"]:
            raise ValueError("P2 lacks a bounded research/business stop reason")

    # Manufacturer is annotation, not part of the capability index;
    # any nonblank vendor string is allowed, and UNKNOWN is valid.
    manufacturer = record.get("manufacturer")
    if manufacturer is not None and not isinstance(manufacturer, str):
        raise ValueError("manufacturer resolution must be a string or unknown")


class ADR0002ReverseCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        cls.adr = ADR.read_text(encoding="utf-8")

    def test_normative_contract_matches_adr(self):
        audit_contract(self.contract, self.adr)

    def test_p0_source_path_independent_of_manufacturer(self):
        for maker in ("SYNTHETIC_VENDORA", "SYNTHETIC_VENDORB", "UNKNOWN"):
            with self.subTest(manufacturer=maker):
                test = BASE_P0 | {"manufacturer": maker}
                audit_research_record(test, self.contract)

    def test_p0_reject_cfg_only(self):
        test = BASE_P0 | {"operation_source_path": False}
        with self.assertRaisesRegex(ValueError, "incomplete pinned programming"):
            audit_research_record(test, self.contract)

    def test_p0_reject_missing_silicon_probe(self):
        test = BASE_P0 | {"credible_silicon_applicability_path": False}
        with self.assertRaisesRegex(ValueError, "incomplete pinned programming"):
            audit_research_record(test, self.contract)

    def test_research_priority_cannot_grant_supported(self):
        test = BASE_P0 | {"software_support": "SUPPORTED"}
        with self.assertRaisesRegex(ValueError, "cannot grant software"):
            audit_research_record(test, self.contract)

    def test_closed_p1_is_still_candidate(self):
        test = BASE_P0 | {
            "priority": "P1",
            "operation_source_path": False,
            "investigation_state": "CLOSED_EVIDENCE_GAP",
            "stop_reason": "PINNED_FLASH_OPERATION_NOT_EVIDENCED",
            "reopen_triggers": ["PINNED_PROVIDER_OR_SOURCE_CHANGED"],
        }
        audit_research_record(test, self.contract)
        test["stop_reason"] = None
        with self.assertRaisesRegex(ValueError, "closed P1 needs"):
            audit_research_record(test, self.contract)

    def test_p1_reject_no_credible_clue(self):
        test = BASE_P0 | {
            "priority": "P1",
            "operation_source_path": False,
            "bounded_target_or_driver_or_silicon_clue": False,
            "investigation_state": "CLOSED_EVIDENCE_GAP",
        }
        with self.assertRaisesRegex(ValueError, "P1 lacks"):
            audit_research_record(test, self.contract)

    def test_p2_archive_not_unsupported(self):
        test = BASE_P0 | {
            "priority": "P2",
            "investigation_state": "P2_ARCHIVED",
            "software_support": "UNKNOWN",
            "stop_reason": "NO_CREDIBLE_PINNED_FLASH_PATH",
        }
        audit_research_record(test, self.contract)
        test["software_support"] = "UNSUPPORTED"
        with self.assertRaisesRegex(ValueError, "cannot grant software"):
            audit_research_record(test, self.contract)

    def test_p2_business_deprioritization_not_eol(self):
        test = BASE_P0 | {
            "priority": "P2",
            "investigation_state": "P2_ARCHIVED",
            "stop_reason": "DEFERRED_PRODUCT_DEMAND",
        }
        audit_research_record(test, self.contract)

    def test_reject_manufacturer_allowlist_in_contract(self):
        forged = copy.deepcopy(self.contract)
        forged["manufacturer_policy"] = "ONLY_ST_NXP_MICROCHIP"
        with self.assertRaisesRegex(ValueError, "manufacturer_policy"):
            audit_contract(forged, self.adr)

    def test_reject_p0_certification_in_contract(self):
        forged = copy.deepcopy(self.contract)
        forged["not_proven_by_p0"].remove("public_catalog_eligible")
        with self.assertRaisesRegex(ValueError, "incorrectly grants"):
            audit_contract(forged, self.adr)

    def test_reject_removed_p1_stop_controls(self):
        forged = copy.deepcopy(self.contract)
        forged["review_control_fields"].remove("stop_reason")
        with self.assertRaisesRegex(ValueError, "stop/reopen"):
            audit_contract(forged, self.adr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
