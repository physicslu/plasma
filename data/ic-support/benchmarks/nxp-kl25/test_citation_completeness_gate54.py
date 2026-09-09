#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import semantic_extraction as semantic

HERE = Path(__file__).resolve().parent


class Gate54CitationCompletenessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.semantic_contract = json.loads(
            (HERE / "semantic-extraction-contract.json").read_text(encoding="utf-8")
        )
        cls.qualification_contract = json.loads(
            (HERE / "live-model-qualification-contract.json").read_text(encoding="utf-8")
        )
        cls.packs = {
            "synthetic-pack-v0": {
                "pack_id": "synthetic-pack-v0",
                "primary_unit_id": "synthetic-unit-v0",
                "page_refs": [
                    {
                        "source_id": "nxp_kl25_rm_rev3",
                        "pdf_page_number": 10,
                    },
                    {
                        "source_id": "nxp_kl25_rm_rev3",
                        "pdf_page_number": 11,
                    },
                ],
            }
        }

    def test_gate54_contracts_are_versioned_and_fail_closed(self):
        self.assertEqual(
            self.semantic_contract["contract_id"],
            "nxp-kl25-semantic-extraction-v1",
        )
        policy = self.semantic_contract["output"]["citation_completeness"]
        self.assertTrue(policy["facts_should_be_atomic"])
        self.assertTrue(policy["every_material_clause_requires_complete_evidence"])
        self.assertTrue(policy["multi_page_claim_requires_all_supporting_pages"])
        self.assertTrue(policy["split_disjoint_evidence_claims"])
        self.assertTrue(policy["irrelevant_padding_citations_forbidden"])

        self.assertEqual(
            self.qualification_contract["contract_id"],
            "nxp-kl25-live-model-qualification-v4",
        )
        self.assertEqual(
            self.qualification_contract["required_input"]["semantic_contract_id"],
            "nxp-kl25-semantic-extraction-v1",
        )
        review = self.qualification_contract["review"]
        self.assertTrue(review["semantic_truth_and_citation_quality_are_independent"])
        self.assertTrue(review["require_complete_fact_citations_for_review_pass"])
        self.assertTrue(review["qualification_requires_semantic_and_citation_review_pass"])

    def test_prompt_explicitly_requires_atomic_complete_citations(self):
        prompt, meta = semantic.render_prompt(
            "Synthetic manufacturer evidence pages 10 and 11.",
            contract=copy.deepcopy(self.semantic_contract),
            packs=copy.deepcopy(self.packs),
        )
        normalized = " ".join(prompt.lower().split())
        self.assertIn("prefer atomic facts", normalized)
        self.assertIn("every material clause", normalized)
        self.assertIn("cite every necessary page", normalized)
        self.assertIn("split them into separate atomic facts", normalized)
        self.assertIn("do not pad a fact with irrelevant pages", normalized)
        self.assertIn("register address", normalized)
        self.assertIn("field meaning", normalized)
        self.assertIn("must cite both pages or be split", normalized)
        self.assertEqual(
            meta["citation_completeness_policy"],
            self.semantic_contract["output"]["citation_completeness"],
        )

    def test_provider_schema_supports_multi_page_complete_citation(self):
        schema = semantic.build_output_json_schema(
            copy.deepcopy(self.semantic_contract),
            packs=copy.deepcopy(self.packs),
        )
        evidence_schema = (
            schema["properties"]["unit_results"]["items"]["properties"]["facts"]
            ["items"]["properties"]["evidence"]
        )
        self.assertEqual(evidence_schema["minItems"], 1)
        self.assertNotIn("maxItems", evidence_schema)

        value = {
            "schema_version": "0.1.0",
            "target": "MKL25Z128VLK4",
            "unit_results": [
                {
                    "primary_unit_id": "synthetic-unit-v0",
                    "state": "FACTS",
                    "facts": [
                        {
                            "fact_id": "synthetic-unit-v0-1",
                            "kind": "REGISTER_FIELD",
                            "statement": "Synthetic address and field meaning are jointly stated.",
                            "evidence": [
                                {
                                    "source_id": "nxp_kl25_rm_rev3",
                                    "pdf_page_number": 10,
                                },
                                {
                                    "source_id": "nxp_kl25_rm_rev3",
                                    "pdf_page_number": 11,
                                },
                            ],
                        }
                    ],
                }
            ],
        }
        parsed = semantic.parse_model_result(
            json.dumps(value),
            contract=copy.deepcopy(self.semantic_contract),
            packs=copy.deepcopy(self.packs),
        )
        self.assertEqual(parsed, value)

    def test_provider_schema_supports_split_atomic_facts_with_local_citations(self):
        value = {
            "schema_version": "0.1.0",
            "target": "MKL25Z128VLK4",
            "unit_results": [
                {
                    "primary_unit_id": "synthetic-unit-v0",
                    "state": "FACTS",
                    "facts": [
                        {
                            "fact_id": "synthetic-unit-v0-address",
                            "kind": "REGISTER",
                            "statement": "Synthetic register address is established.",
                            "evidence": [
                                {
                                    "source_id": "nxp_kl25_rm_rev3",
                                    "pdf_page_number": 10,
                                }
                            ],
                        },
                        {
                            "fact_id": "synthetic-unit-v0-field",
                            "kind": "REGISTER_FIELD",
                            "statement": "Synthetic field meaning is established.",
                            "evidence": [
                                {
                                    "source_id": "nxp_kl25_rm_rev3",
                                    "pdf_page_number": 11,
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        parsed = semantic.parse_model_result(
            json.dumps(value),
            contract=copy.deepcopy(self.semantic_contract),
            packs=copy.deepcopy(self.packs),
        )
        self.assertEqual(parsed, value)

    def test_parser_does_not_pretend_to_prove_natural_language_completeness(self):
        value = {
            "schema_version": "0.1.0",
            "target": "MKL25Z128VLK4",
            "unit_results": [
                {
                    "primary_unit_id": "synthetic-unit-v0",
                    "state": "FACTS",
                    "facts": [
                        {
                            "fact_id": "synthetic-unit-v0-ambiguous",
                            "kind": "CONSTRAINT",
                            "statement": "Synthetic compound statement whose semantic support cannot be proven by syntax alone.",
                            "evidence": [
                                {
                                    "source_id": "nxp_kl25_rm_rev3",
                                    "pdf_page_number": 10,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        parsed = semantic.parse_model_result(
            json.dumps(value),
            contract=copy.deepcopy(self.semantic_contract),
            packs=copy.deepcopy(self.packs),
        )
        self.assertEqual(parsed, value)
        # Gate 5.4 deliberately does not add fuzzy or inferred citation repair.
        # Natural-language completeness remains a manufacturer-evidence review duty.

    def test_missing_gate54_policy_is_rejected_before_transport_schema_use(self):
        contract = copy.deepcopy(self.semantic_contract)
        del contract["output"]["citation_completeness"]
        with self.assertRaisesRegex(semantic.ModelOutputSchemaError, "citation completeness policy missing"):
            semantic.build_output_json_schema(contract, packs=copy.deepcopy(self.packs))


if __name__ == "__main__":
    unittest.main()
