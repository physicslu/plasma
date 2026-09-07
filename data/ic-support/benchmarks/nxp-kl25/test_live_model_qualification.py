#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import build_evidence_pack as builder
import qualify_semantic_run as qualification

HERE = Path(__file__).resolve().parent


UNIT_FIXTURES = {
    "nxp-kl25-ftfa-register-model-v0": (422, 431, "FTFA register model exposes FSTAT status and FCCOB command object registers."),
    "nxp-kl25-ftfa-command-sequencing-v0": (435, 439, "FCCOB command sequencing launches through CCIF and checks ACCERR or FPVIOL status."),
    "nxp-kl25-program-longword-v0": (444, 445, "Program Longword uses the FCCOB command object for the programming operation."),
    "nxp-kl25-erase-sector-v0": (446, 448, "Erase Flash Sector defines the sector erase command behavior."),
    "nxp-kl25-erase-all-blocks-v0": (451, 452, "Erase All Blocks is constrained when flash protection applies."),
    "nxp-kl25-flash-security-v0": (454, 455, "FSEC defines flash security controls including SEC, MEEN, and KEYEN fields."),
    "nxp-kl25-debug-security-interaction-v0": (149, 150, "SWD access changes in the secure security state and mass erase remains a constrained recovery path."),
    "nxp-kl25-swd-mdm-ap-v0": (151, 157, "SWD exposes the MDM-AP status and mass erase control path."),
}


class KL25LiveModelQualificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((HERE / "live-model-qualification-contract.json").read_text(encoding="utf-8"))

    def build_packs(self):
        result = {}
        for unit_id, (start, end, _) in UNIT_FIXTURES.items():
            pack_id = f"{unit_id}-pack-v0"
            result[pack_id] = {
                "pack_id": pack_id,
                "primary_unit_id": unit_id,
                "included_units": [
                    {
                        "unit_id": unit_id,
                        "origin": "PRIMARY",
                        "source_id": "nxp_kl25_rm_rev3",
                        "pdf_page_range": [start, end],
                    }
                ],
            }
        return result

    def build_semantic_run(self, packs):
        results = []
        for unit_id, (start, _, statement) in UNIT_FIXTURES.items():
            results.append(
                {
                    "primary_unit_id": unit_id,
                    "state": "FACTS",
                    "facts": [
                        {
                            "fact_id": f"live-{unit_id}",
                            "kind": "CONSTRAINT",
                            "statement": statement,
                            "evidence": [
                                {"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": start}
                            ],
                        }
                    ],
                }
            )
        raw = json.dumps(
            {"schema_version": "0.1.0", "target": "MKL25Z128VLK4", "unit_results": results},
            sort_keys=True,
        )
        run = {
            "schema_version": "0.1.0",
            "artifact_type": "kl25_semantic_extraction_run",
            "target": "MKL25Z128VLK4",
            "bundle_digest": self.contract["required_input"]["bundle_digest"],
            "pre_ai_manifest_digest": self.contract["required_input"]["pre_ai_manifest_digest"],
            "semantic_contract_id": self.contract["required_input"]["semantic_contract_id"],
            "runtime": {
                "transport": "ollama_native_chat",
                "runtime_label": "kl25-live-model-qualification",
                "model_id": "qwen3.8:27b-mlx",
            },
            "prompt": {"sha256": "b" * 64, "byte_length": 1000},
            "trust_boundary": {
                "semantic_extraction_admission": False,
                "model_quality_admission": False,
            },
            "status": "success",
            "response": json.loads(raw),
            "transport_metadata": {
                "response_model": "qwen3.8:27b-mlx",
                "done": True,
                "done_reason": "stop",
                "usage": {"input_tokens": 12000, "generation_tokens": 900},
                "timing": {"wall_time_ms": 1000.0},
            },
            "transport_invoked": True,
            "raw_response_sha256": builder.sha256_text(raw),
        }
        return run, raw

    def build_provenance(self, run, raw):
        provenance = {
            "schema_version": "0.1.0",
            "artifact_type": "kl25_live_model_run_provenance",
            "target": "MKL25Z128VLK4",
            "bundle_digest": run["bundle_digest"],
            "pre_ai_manifest_digest": run["pre_ai_manifest_digest"],
            "semantic_run_digest": builder.canonical_sha256(run),
            "raw_response_sha256": builder.sha256_text(raw),
            "ollama_runtime_identity": {
                "ollama_url_policy": "loopback_only",
                "ollama_version": "0.12.0",
                "model_id": "qwen3.8:27b-mlx",
                "model_digest": "sha256:" + "a" * 64,
            },
            "execution": {
                "transport": "ollama_native_chat",
                "model_id": "qwen3.8:27b-mlx",
                "runtime_label": "kl25-live-model-qualification",
                "ollama_endpoint_policy": "loopback_only",
                "generation": copy.deepcopy(self.contract["live_runtime"]["generation"]),
            },
            "code_fingerprints": {"qualify_semantic_run.py": "f" * 64},
            "manufacturer_text_retained_in_provenance": False,
        }
        provenance["provenance_digest"] = builder.canonical_sha256(provenance)
        return provenance

    def assess(self, *, mutate_run=None, mutate_provenance=None, reviewed_verdict=None):
        packs = self.build_packs()
        run, raw = self.build_semantic_run(packs)
        if mutate_run:
            mutate_run(run)
            run["raw_response_sha256"] = builder.sha256_text(raw)
        provenance = self.build_provenance(run, raw)
        if mutate_provenance:
            mutate_provenance(provenance)
            provenance["provenance_digest"] = builder.canonical_sha256(
                {key: value for key, value in provenance.items() if key != "provenance_digest"}
            )
        return qualification.assess_live_run(
            contract=copy.deepcopy(self.contract),
            semantic_run=run,
            raw_response=raw,
            provenance=provenance,
            packs=packs,
            reviewed_verdict=reviewed_verdict,
        ), run

    def test_valid_live_run_is_ready_for_manufacturer_evidence_review(self):
        report, _ = self.assess()
        self.assertEqual(report["status"], "READY_FOR_REVIEW")
        self.assertEqual(report["integrity"]["status"], "PASS")
        self.assertEqual(report["semantic_screening"]["status"], "PASS")
        self.assertEqual(report["review"]["status"], "PENDING")
        self.assertFalse(report["trust_boundary"]["semantic_extraction_admission"])
        self.assertFalse(report["trust_boundary"]["model_quality_admission"])

    def test_wrong_model_or_unlocked_model_digest_fails_integrity(self):
        report, _ = self.assess(
            mutate_run=lambda run: run["runtime"].__setitem__("model_id", "other-model")
        )
        self.assertEqual(report["status"], "REJECTED_INTEGRITY")
        report, _ = self.assess(
            mutate_provenance=lambda provenance: provenance["ollama_runtime_identity"].__setitem__("model_digest", "bad")
        )
        self.assertEqual(report["status"], "REJECTED_INTEGRITY")

    def test_unknown_or_stm32_projection_fails_screening(self):
        def unknown(run):
            run["response"]["unit_results"][0]["state"] = "UNKNOWN"
            run["response"]["unit_results"][0]["facts"] = []

        report, _ = self.assess(mutate_run=unknown)
        self.assertEqual(report["status"], "REJECTED_SCREENING")

        def project_stm32(run):
            run["response"]["unit_results"][0]["facts"][0]["statement"] += " STM32 FLASH_CR KEYR"

        report, _ = self.assess(mutate_run=project_stm32)
        self.assertEqual(report["status"], "REJECTED_SCREENING")

    def test_dependency_only_citation_does_not_satisfy_primary_unit_grounding(self):
        def mutate(run):
            for item in run["response"]["unit_results"]:
                if item["primary_unit_id"] == "nxp-kl25-program-longword-v0":
                    item["facts"][0]["evidence"] = [
                        {"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 422}
                    ]

        report, _ = self.assess(mutate_run=mutate)
        self.assertEqual(report["status"], "REJECTED_SCREENING")
        self.assertTrue(any("primary Evidence Unit" in item for item in report["semantic_screening"]["errors"]))

    def test_raw_response_and_parsed_response_must_be_identical(self):
        def mutate(run):
            run["response"]["unit_results"][0]["facts"][0]["statement"] += " Additional FTFA context."

        report, _ = self.assess(mutate_run=mutate)
        self.assertEqual(report["status"], "REJECTED_INTEGRITY")
        self.assertTrue(any("raw response and parsed" in item for item in report["integrity"]["errors"]))

    def test_reviewed_verdict_is_required_before_qualified(self):
        report, run = self.assess()
        self.assertEqual(report["status"], "READY_FOR_REVIEW")
        verdict = {
            "schema_version": "0.1.0",
            "artifact_type": "kl25_reviewed_semantic_verdict",
            "target": "MKL25Z128VLK4",
            "semantic_run_digest": builder.canonical_sha256(run),
            "review_basis": "manufacturer_evidence",
            "unit_verdicts": [
                {
                    "primary_unit_id": unit_id,
                    "verdict": "PASS",
                    "rationale": "Reviewed against the bounded manufacturer Evidence Pack.",
                }
                for unit_id in sorted(UNIT_FIXTURES)
            ],
            "overall_verdict": "PASS",
        }
        report, _ = self.assess(reviewed_verdict=verdict)
        self.assertEqual(report["status"], "QUALIFIED")
        self.assertEqual(report["review"]["status"], "PASS")
        self.assertFalse(report["trust_boundary"]["semantic_extraction_admission"])

    def test_review_digest_mismatch_is_rejected(self):
        verdict = {
            "artifact_type": "kl25_reviewed_semantic_verdict",
            "target": "MKL25Z128VLK4",
            "semantic_run_digest": "0" * 64,
            "review_basis": "manufacturer_evidence",
            "unit_verdicts": [
                {
                    "primary_unit_id": unit_id,
                    "verdict": "PASS",
                    "rationale": "Reviewed against manufacturer evidence.",
                }
                for unit_id in sorted(UNIT_FIXTURES)
            ],
            "overall_verdict": "PASS",
        }
        report, _ = self.assess(reviewed_verdict=verdict)
        self.assertEqual(report["status"], "REJECTED_REVIEW")

    def test_contract_admits_only_the_model_free_harness(self):
        admission = self.contract["admission"]
        self.assertTrue(admission["live_model_qualification_harness"])
        self.assertFalse(admission["live_model_run_retained"])
        self.assertFalse(admission["semantic_extraction"])
        self.assertFalse(admission["model_quality"])
        self.assertFalse(admission["canonical_dataset"])
        self.assertFalse(admission["hil"])
        self.assertFalse(admission["production"])
        self.assertFalse(admission["destructive_security_operation"])


if __name__ == "__main__":
    unittest.main()
