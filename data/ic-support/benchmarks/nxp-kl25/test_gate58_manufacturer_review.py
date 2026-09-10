#!/usr/bin/env python3
"""Gate 5.8 manufacturer semantic/citation review regressions; model/network free."""
from __future__ import annotations

import copy
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_evidence_pack as builder
import gate58_review as gate58

HERE = Path(__file__).resolve().parent


class Gate58ManufacturerReviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = gate58.load_contract()
        cls.live_contract = gate58.load_live_contract()
        cls.definitions = gate58.load_unit_definitions()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.run_dir = root / "bounded-primary-runs" / gate58.EXPECTED_REQUIRED_RUN["run_id"]
        self.run_dir.mkdir(parents=True)
        for name in ("socket", "create_connection"):
            guard = patch.object(socket, name, side_effect=AssertionError("network forbidden in Gate 5.8 CI"))
            guard.start()
            self.addCleanup(guard.stop)

    def build_artifacts(self, *, supplemental_debug_citation: bool = False):
        required = self.contract["required_retained_run"]
        units = gate58._unit_index(self.definitions)
        unit_results = []
        for index, unit_id in enumerate(sorted(units), start=1):
            source, page = sorted(units[unit_id]["primary_refs"])[0]
            evidence = [{"source_id": source, "pdf_page_number": page}]
            if supplemental_debug_citation and unit_id == "nxp-kl25-debug-security-interaction-v0":
                evidence.append({"source_id": source, "pdf_page_number": 151})
            unit_results.append({
                "primary_unit_id": unit_id,
                "state": "FACTS",
                "facts": [{
                    "fact_id": f"gate58-fixture-{index:02d}",
                    "kind": "CONSTRAINT",
                    "statement": f"Synthetic manufacturer-review fixture for {unit_id}.",
                    "evidence": evidence,
                }],
            })

        aggregate = {
            "schema_version": "0.1.0",
            "artifact_type": "kl25_bounded_aggregate",
            "bounded_contract_id": "nxp-kl25-bounded-extraction-v1",
            "execution_contract_id": required["live_bounded_contract_id"],
            "execution_mode": required["execution_mode"],
            "target": required["model_id"] and self.contract["target"],
            "bundle_digest": required["bundle_digest"],
            "pre_ai_manifest_digest": required["pre_ai_manifest_digest"],
            "status": required["aggregate_status"],
            "errors": [],
            "admission": {},
            "qualification_status": "NOT_QUALIFIED",
            "acceptance_blockers": [],
            "review_required": True,
            "children": [],
            "semantic_scope": copy.deepcopy(self.live_contract["live_runtime"]["semantic_scope"]),
            "semantic_scope_digest": builder.canonical_sha256(self.live_contract["live_runtime"]["semantic_scope"]),
            "response": {
                "schema_version": "0.1.0",
                "target": self.contract["target"],
                "unit_results": unit_results,
            },
        }
        aggregate["aggregate_digest"] = builder.canonical_sha256(aggregate)

        provenance = {
            "schema_version": "0.1.0",
            "artifact_type": "kl25_live_bounded_run_provenance",
            "target": self.contract["target"],
            "bundle_digest": required["bundle_digest"],
            "pre_ai_manifest_digest": required["pre_ai_manifest_digest"],
            "live_bounded_contract_id": required["live_bounded_contract_id"],
            "live_bounded_contract_digest": builder.canonical_sha256(self.live_contract),
            "aggregate_digest": aggregate["aggregate_digest"],
            "ollama_runtime_identity": {
                "ollama_url_policy": "loopback_only",
                "ollama_version": "0.33.3",
                "model_id": required["model_id"],
                "model_digest": "sha256:" + required["model_digest"],
            },
            "execution": {
                "execution_mode": required["execution_mode"],
                "model_id": required["model_id"],
                "semantic_scope": copy.deepcopy(self.live_contract["live_runtime"]["semantic_scope"]),
                "automatic_retries": 0,
            },
        }
        provenance["provenance_digest"] = builder.canonical_sha256(provenance)

        report = {
            "schema_version": "0.1.1",
            "artifact_type": "kl25_live_bounded_qualification_report",
            "qualification_contract_id": required["live_bounded_contract_id"],
            "target": self.contract["target"],
            "bundle_digest": required["bundle_digest"],
            "pre_ai_manifest_digest": required["pre_ai_manifest_digest"],
            "aggregate_digest": aggregate["aggregate_digest"],
            "model_id": required["model_id"],
            "model_digest": required["model_digest"],
            "status": required["pre_review_qualification_status"],
            "integrity": {"status": "PASS", "errors": []},
            "semantic_screening": {"status": "PASS", "errors": []},
            "review": {
                "required": True,
                "status": "PENDING",
                "basis_required": "manufacturer_evidence",
                "gate57_can_issue_qualified": False,
            },
        }
        report["report_digest"] = builder.canonical_sha256(report)
        return aggregate, provenance, report

    def write_artifacts(self, aggregate, provenance, report):
        (self.run_dir / "aggregate-report.json").write_text(json.dumps(aggregate), encoding="utf-8")
        (self.run_dir / "live-bounded-provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
        (self.run_dir / "qualification-report.json").write_text(json.dumps(report), encoding="utf-8")

    def build_view(self, *, supplemental_debug_citation: bool = False):
        aggregate, provenance, report = self.build_artifacts(
            supplemental_debug_citation=supplemental_debug_citation
        )
        gate58.validate_retained_artifacts(
            run_dir=self.run_dir,
            aggregate=aggregate,
            provenance=provenance,
            qualification_report=report,
            contract=self.contract,
            live_contract=self.live_contract,
            definitions=self.definitions,
        )
        view = gate58.build_review_view_from_artifacts(
            run_id=self.run_dir.name,
            aggregate=aggregate,
            provenance=provenance,
            qualification_report=report,
            contract=self.contract,
            definitions=self.definitions,
        )
        return view, aggregate, provenance, report

    def completed_verdict(self, view):
        verdict = gate58.build_review_template(view, self.contract)
        for item in verdict["fact_verdicts"]:
            item.update({
                "semantic_support": "SUPPORTED",
                "citation_entailment": "COMPLETE",
                "atomicity": "PASS",
                "scope": "PASS",
                "terminology": "PASS",
                "rationale": "Reviewed against the locked manufacturer evidence and supported at the stated specificity.",
            })
        verdict["overall_verdict"] = "PASS"
        return verdict

    def test_contract_is_frozen_and_model_free(self):
        gate58.validate_contract(
            self.contract,
            live_contract=self.live_contract,
            definitions=self.definitions,
        )
        self.assertFalse(self.contract["review_policy"]["local_ai_rerun_required"])
        self.assertTrue(self.contract["review_policy"]["local_ai_rerun_forbidden_for_gate58"])

    def test_exact_retained_identity_is_required(self):
        aggregate, provenance, report = self.build_artifacts()
        wrong_dir = self.run_dir.parent / "20260909T999999Z"
        wrong_dir.mkdir()
        with self.assertRaisesRegex(gate58.Gate58ReviewError, "bound to retained run"):
            gate58.validate_retained_artifacts(
                run_dir=wrong_dir,
                aggregate=aggregate,
                provenance=provenance,
                qualification_report=report,
                contract=self.contract,
                live_contract=self.live_contract,
                definitions=self.definitions,
            )

    def test_model_digest_drift_fails_closed(self):
        aggregate, provenance, report = self.build_artifacts()
        provenance["ollama_runtime_identity"]["model_digest"] = "b" * 64
        provenance["provenance_digest"] = builder.canonical_sha256(
            {k: v for k, v in provenance.items() if k != "provenance_digest"}
        )
        with self.assertRaisesRegex(gate58.Gate58ReviewError, "model digest mismatch"):
            gate58.validate_retained_artifacts(
                run_dir=self.run_dir,
                aggregate=aggregate,
                provenance=provenance,
                qualification_report=report,
                contract=self.contract,
                live_contract=self.live_contract,
                definitions=self.definitions,
            )

    def test_every_fact_requires_primary_citation(self):
        aggregate, provenance, report = self.build_artifacts()
        debug = next(
            item for item in aggregate["response"]["unit_results"]
            if item["primary_unit_id"] == "nxp-kl25-debug-security-interaction-v0"
        )
        debug["facts"][0]["evidence"] = [
            {"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 151}
        ]
        aggregate["aggregate_digest"] = builder.canonical_sha256(
            {k: v for k, v in aggregate.items() if k != "aggregate_digest"}
        )
        provenance["aggregate_digest"] = aggregate["aggregate_digest"]
        provenance["provenance_digest"] = builder.canonical_sha256(
            {k: v for k, v in provenance.items() if k != "provenance_digest"}
        )
        report["aggregate_digest"] = aggregate["aggregate_digest"]
        report["report_digest"] = builder.canonical_sha256(
            {k: v for k, v in report.items() if k != "report_digest"}
        )
        with self.assertRaisesRegex(gate58.Gate58ReviewError, "missing PRIMARY citation"):
            gate58.validate_retained_artifacts(
                run_dir=self.run_dir,
                aggregate=aggregate,
                provenance=provenance,
                qualification_report=report,
                contract=self.contract,
                live_contract=self.live_contract,
                definitions=self.definitions,
            )

    def test_review_view_separates_primary_and_supplemental_citations(self):
        view, _, _, _ = self.build_view(supplemental_debug_citation=True)
        debug = next(
            item for item in view["units"]
            if item["primary_unit_id"] == "nxp-kl25-debug-security-interaction-v0"
        )
        fact = debug["facts"][0]
        self.assertEqual(fact["primary_citations"], [
            {"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 149}
        ])
        self.assertEqual(fact["supplemental_citations"], [
            {"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 151}
        ])
        self.assertEqual(view["fact_count"], 8)

    def test_unreviewed_template_is_review_incomplete(self):
        view, _, _, _ = self.build_view()
        verdict = gate58.build_review_template(view, self.contract)
        report = gate58.validate_verdict(verdict, view=view, contract=self.contract)
        self.assertEqual(report["status"], "REVIEW_INCOMPLETE")
        self.assertEqual(report["fully_reviewed_fact_count"], 0)
        self.assertFalse(report["trust_boundary"]["exact_retained_semantic_run_qualified"])

    def test_all_pass_qualifies_only_the_exact_retained_semantic_run(self):
        view, _, _, _ = self.build_view()
        verdict = self.completed_verdict(view)
        report = gate58.validate_verdict(verdict, view=view, contract=self.contract)
        self.assertEqual(report["status"], "QUALIFIED")
        self.assertEqual(report["fully_reviewed_fact_count"], report["fact_count"])
        self.assertTrue(report["trust_boundary"]["exact_retained_semantic_run_qualified"])
        self.assertFalse(report["trust_boundary"]["model_quality_admission"])
        self.assertFalse(report["trust_boundary"]["canonical_dataset_admission"])
        self.assertFalse(report["trust_boundary"]["hil_admission"])
        self.assertFalse(report["trust_boundary"]["production_admission"])
        self.assertFalse(report["trust_boundary"]["destructive_security_operation_admission"])

    def test_any_review_defect_rejects_qualification(self):
        view, _, _, _ = self.build_view()
        verdict = self.completed_verdict(view)
        verdict["fact_verdicts"][0]["citation_entailment"] = "PARTIAL"
        verdict["fact_verdicts"][0]["rationale"] = "The cited page supports only part of the material statement."
        verdict["overall_verdict"] = "FAIL"
        report = gate58.validate_verdict(verdict, view=view, contract=self.contract)
        self.assertEqual(report["status"], "REJECTED_REVIEW")
        self.assertFalse(report["trust_boundary"]["exact_retained_semantic_run_qualified"])

    def test_cross_vendor_contamination_is_a_review_failure(self):
        view, _, _, _ = self.build_view()
        verdict = self.completed_verdict(view)
        verdict["fact_verdicts"][0]["terminology"] = "CROSS_VENDOR_CONTAMINATION"
        verdict["fact_verdicts"][0]["rationale"] = "The fact introduces non-NXP terminology not established by the locked evidence."
        verdict["overall_verdict"] = "FAIL"
        report = gate58.validate_verdict(verdict, view=view, contract=self.contract)
        self.assertEqual(report["status"], "REJECTED_REVIEW")

    def test_missing_fact_verdict_fails_closed(self):
        view, _, _, _ = self.build_view()
        verdict = self.completed_verdict(view)
        verdict["fact_verdicts"].pop()
        with self.assertRaisesRegex(gate58.Gate58ReviewError, "exact retained fact set"):
            gate58.validate_verdict(verdict, view=view, contract=self.contract)

    def test_fact_digest_prevents_stale_verdict_reuse(self):
        view, _, _, _ = self.build_view()
        verdict = self.completed_verdict(view)
        verdict["fact_verdicts"][0]["fact_digest"] = "0" * 64
        with self.assertRaisesRegex(gate58.Gate58ReviewError, "fact digest mismatch"):
            gate58.validate_verdict(verdict, view=view, contract=self.contract)

    def test_filesystem_loader_revalidates_self_digests(self):
        view, aggregate, provenance, report = self.build_view()
        self.write_artifacts(aggregate, provenance, report)
        loaded = gate58.build_review_view(self.run_dir)
        self.assertEqual(loaded, view)
        aggregate["status"] = "REJECTED_INTEGRITY"
        self.write_artifacts_to_existing(aggregate, provenance, report)
        with self.assertRaisesRegex(gate58.Gate58ReviewError, "aggregate_digest mismatch"):
            gate58.build_review_view(self.run_dir)

    def write_artifacts_to_existing(self, aggregate, provenance, report):
        (self.run_dir / "aggregate-report.json").write_text(json.dumps(aggregate), encoding="utf-8")
        (self.run_dir / "live-bounded-provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
        (self.run_dir / "qualification-report.json").write_text(json.dumps(report), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
