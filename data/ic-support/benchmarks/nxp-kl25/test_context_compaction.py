#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import unittest

import build_evidence_pack as builder
import semantic_context
import semantic_runner


class CapturingTransport:
    def __init__(self, raw_text: str):
        self.raw_text = raw_text
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return {
            "raw_text": self.raw_text,
            "response_model": "qwen3.8:27b-mlx",
            "done": True,
            "done_reason": "stop",
            "usage": {"input_tokens": 1000, "generation_tokens": 200},
            "timing": {"wall_time_ms": 10.0},
        }


class KL25ContextCompactionTest(unittest.TestCase):
    def evidence_block(self, page: int, body: str) -> tuple[dict, str]:
        digest = builder.sha256_text(body)
        ref = {
            "source_id": "nxp_kl25_rm_rev3",
            "pdf_page_number": page,
            "page_text_sha256": digest,
            "required_by_unit_ids": [],
        }
        block = (
            f"=== BEGIN nxp_kl25_rm_rev3 PDF_PAGE {page} SHA256 {digest} ===\n"
            f"{body}\n"
            f"=== END nxp_kl25_rm_rev3 PDF_PAGE {page} ==="
        )
        return ref, block

    def workspace(self, *, conflicting_duplicate: bool = False):
        ref1a, block1a = self.evidence_block(1, "shared manufacturer page")
        ref2, block2 = self.evidence_block(2, "unit A manufacturer page")
        duplicate_body = "conflicting manufacturer page" if conflicting_duplicate else "shared manufacturer page"
        ref1b, block1b = self.evidence_block(1, duplicate_body)
        ref3, block3 = self.evidence_block(3, "unit B manufacturer page")

        evidence_text = {
            "pack-a": "\n\n".join([block1a, block2]) + "\n",
            "pack-b": "\n\n".join([block1b, block3]) + "\n",
        }
        packs = {
            "pack-a": {
                "pack_id": "pack-a",
                "pack_digest": "a" * 64,
                "primary_unit_id": "unit-a",
                "page_refs": [ref1a, ref2],
            },
            "pack-b": {
                "pack_id": "pack-b",
                "pack_digest": "b" * 64,
                "primary_unit_id": "unit-b",
                "page_refs": [ref1b, ref3],
            },
        }
        manifest = {
            "schema_version": "0.1.0",
            "artifact_type": "pre_ai_input_manifest",
            "target": "MKL25Z128VLK4",
            "source_lock_id": "source-lock",
            "bundle_id": "bundle",
            "bundle_digest": "c" * 64,
            "packs": [
                {
                    "pack_id": pack_id,
                    "pack_digest": packs[pack_id]["pack_digest"],
                    "evidence_sha256": builder.sha256_text(evidence_text[pack_id]),
                }
                for pack_id in ("pack-a", "pack-b")
            ],
            "authority_boundary": {
                "input_is_manufacturer_evidence_only": True,
                "canonical_ground_truth_allowed": False,
                "production_profile_allowed": False,
                "ai_may_change_applicability_binding": False,
                "ai_may_remove_deterministic_evidence": False,
            },
            "execution": {
                "repository_ci_validates_through_context_assembly": True,
                "model_inference_required_in_repository_ci": False,
                "semantic_extraction_admission": False,
            },
        }
        manifest["manifest_digest"] = builder.canonical_sha256(manifest)
        return manifest, packs, evidence_text

    def semantic_contract(self):
        return {
            "schema_version": "0.1.0",
            "contract_id": "synthetic-semantic-contract",
            "target": "MKL25Z128VLK4",
            "output": {
                "allowed_states": ["FACTS", "UNKNOWN"],
                "allowed_fact_kinds": ["CONSTRAINT"],
                "citation_completeness": {
                    "facts_should_be_atomic": True,
                    "every_material_clause_requires_complete_evidence": True,
                    "multi_page_claim_requires_all_supporting_pages": True,
                    "split_disjoint_evidence_claims": True,
                    "irrelevant_padding_citations_forbidden": True,
                },
            },
            "admission": {
                "semantic_extraction": False,
                "model_quality": False,
            },
        }

    def test_compaction_removes_only_cross_pack_duplicate_physical_pages(self):
        manifest, packs, evidence_text = self.workspace()
        before = copy.deepcopy((manifest, packs, evidence_text))
        compact, audit = semantic_context.assemble_compact_model_context(
            manifest,
            packs=packs,
            evidence_text=evidence_text,
        )

        self.assertEqual(audit["strategy"], semantic_context.COMPACT_CONTEXT_STRATEGY)
        self.assertEqual(audit["page_occurrences"], 4)
        self.assertEqual(audit["unique_physical_pages"], 3)
        self.assertEqual(audit["duplicate_occurrences_removed"], 1)
        self.assertLess(audit["context_bytes"], audit["legacy_context_bytes"])
        self.assertEqual(compact.count("PDF_PAGE 1 SHA256"), 1)
        self.assertEqual(compact.count("PDF_PAGE 2 SHA256"), 1)
        self.assertEqual(compact.count("PDF_PAGE 3 SHA256"), 1)
        self.assertEqual((manifest, packs, evidence_text), before)
        self.assertFalse(audit["gate3_artifacts_mutated"])

    def test_same_physical_page_with_different_content_fails_closed(self):
        manifest, packs, evidence_text = self.workspace(conflicting_duplicate=True)
        with self.assertRaises(semantic_context.SemanticContextError):
            semantic_context.assemble_compact_model_context(
                manifest,
                packs=packs,
                evidence_text=evidence_text,
            )

    def test_runner_uses_compact_context_and_preserves_per_unit_citation_rules(self):
        manifest, packs, evidence_text = self.workspace()
        raw = json.dumps(
            {
                "schema_version": "0.1.0",
                "target": "MKL25Z128VLK4",
                "unit_results": [
                    {
                        "primary_unit_id": "unit-a",
                        "state": "FACTS",
                        "facts": [
                            {
                                "fact_id": "a-1",
                                "kind": "CONSTRAINT",
                                "statement": "Unit A fact.",
                                "evidence": [{"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 2}],
                            }
                        ],
                    },
                    {
                        "primary_unit_id": "unit-b",
                        "state": "FACTS",
                        "facts": [
                            {
                                "fact_id": "b-1",
                                "kind": "CONSTRAINT",
                                "statement": "Unit B fact.",
                                "evidence": [{"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 3}],
                            }
                        ],
                    },
                ],
            }
        )
        transport = CapturingTransport(raw)
        record = semantic_runner.execute_semantic_run(
            contract=self.semantic_contract(),
            pre_ai_manifest=manifest,
            packs=packs,
            evidence_text=evidence_text,
            transport=transport,
            transport_label="ollama_native_chat",
            model_id="qwen3.8:27b-mlx",
            runtime_label="repository-ci",
            request_options={"num_ctx": 65536, "max_tokens": 8192},
            context_strategy=semantic_context.COMPACT_CONTEXT_STRATEGY,
        )

        self.assertEqual(record["status"], "success")
        self.assertEqual(record["context"]["page_occurrences"], 4)
        self.assertEqual(record["context"]["unique_physical_pages"], 3)
        prompt = transport.kwargs["prompt"]
        self.assertEqual(prompt.count("PDF_PAGE 1 SHA256"), 1)
        self.assertIn("unit-a", prompt)
        self.assertIn("unit-b", prompt)


if __name__ == "__main__":
    unittest.main()
