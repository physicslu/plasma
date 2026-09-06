from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import canonicalize_semantic_facts_v7 as canonicalizer
import canonicalize_semantic_run_v7 as pipeline
import score_canonical_v7 as canonical_score
import score_semantic_extraction_v7 as semantic_score
import semantic_extraction_v7 as semantic

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "canonicalization-contract-v5.json"
APPLICABILITY = HERE / "option-applicability-v0.json"


def relationship_facts() -> dict:
    return {
        "profile_relationships": {"security": "shared"},
        "targets": {
            "STM32F103C8T6": {
                "manufacturer_device_reference": "STM32F103x8",
                "flash_size_bytes": 65536,
                "page_size_bytes": 1024,
                "page_count": 64,
                "package_hardware": {
                    "package_family": "LQFP",
                    "pin_count": 48,
                    "debug_programming_interfaces": ["SWD", "JTAG"],
                },
            },
            "STM32F103CBT6": {
                "manufacturer_device_reference": "STM32F103xB",
                "flash_size_bytes": 131072,
                "page_size_bytes": 1024,
                "page_count": 128,
                "package_hardware": {
                    "package_family": "LQFP",
                    "pin_count": 48,
                    "debug_programming_interfaces": ["SWD", "JTAG"],
                },
            },
        },
        "programming_contract": {
            "program_granularity_bytes": 2,
            "unlock_keys": ["0x45670123", "0xCDEF89AB"],
            "write_erase_requires_hsi": True,
        },
        "option_contract": {
            "region_start_text": "0x1FFF F800",
            "region_size_bytes": 16,
            "encoding_structure": {
                "logical_value_width_bits": 8,
                "stored_pair_width_bits": 16,
                "companion_value_present": True,
                "companion_relation": "bitwise_not",
            },
        },
        "security_contract": {
            "read_unprotect_is_destructive": True,
            "write_protection_granularity_bytes": 4096,
        },
    }


def evidence_for(facts: dict) -> dict:
    out: dict[str, list[dict]] = {}

    def walk(value, path: str):
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, f"{path}.{key}")
            return
        if value is None or value == "unknown":
            return
        source_id = "st_pm0075_rev2" if any(
            marker in path for marker in ("programming_contract", "option_contract", "security_contract")
        ) else "st_ds5319_rev20"
        page_index = 19 if source_id == "st_pm0075_rev2" else 0
        out[path] = [{"source_id": source_id, "physical_page_index": page_index}]

    walk(facts, "$.semantic_facts")
    return out


def fake_run(facts: dict) -> dict:
    return {
        "schema_version": semantic.SEMANTIC_RUN_SCHEMA_VERSION,
        "experiment_id": semantic.SEMANTIC_EXPERIMENT_ID,
        "status": "success",
        "source_lock_id": "stm32f103c-source-lock-v0",
        "source_digests": {},
        "arm": "reduced_context",
        "context": {
            "datasheet_physical_pages": [0],
            "programming_manual_physical_pages": [0, 19],
        },
        "runtime": {},
        "generation": {},
        "usage": {},
        "timing": {},
        "response": {"semantic_facts": facts, "evidence": evidence_for(facts)},
    }


class OptionRelationshipDerivationV7PipelineTest(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.applicability = json.loads(APPLICABILITY.read_text(encoding="utf-8"))

    def test_generation_contract_removes_ai_programming_option_memory_and_package_relationships(self):
        schema = json.loads((HERE / "semantic-extraction-v5.schema.json").read_text(encoding="utf-8"))
        relationships = schema["properties"]["profile_relationships"]
        for relationship in ("programming", "option", "memory_geometry", "package_hardware"):
            self.assertNotIn(relationship, relationships["required"])
            self.assertNotIn(relationship, relationships["properties"])

        generation_inputs = "\n".join(
            [
                (HERE / "semantic-extraction-v5.schema.json").read_text(encoding="utf-8"),
                (HERE / "semantic-extraction-prompt-v5.txt").read_text(encoding="utf-8"),
                (HERE / "semantic_extraction_v7.py").read_text(encoding="utf-8"),
                (HERE / "ollama_semantic_extraction_run_v7.py").read_text(encoding="utf-8"),
            ]
        )
        self.assertNotIn("option-applicability-v0.json", generation_inputs)
        self.assertNotIn("semantic-extraction-ground-truth-v5.json", generation_inputs)
        self.assertNotIn("canonicalization-contract-v5.json", generation_inputs)

    def test_option_applicability_projection_is_bound_to_evidence_foundation(self):
        canonicalizer.validate_option_applicability_projection(self.applicability)
        tampered = copy.deepcopy(self.applicability)
        tampered["targets"]["STM32F103CBT6"]["evidence"][0]["physical_page_index"] = 1
        with self.assertRaises(canonicalizer.CanonicalizationError):
            canonicalizer.validate_option_applicability_projection(tampered)

    def test_semantics_and_all_four_relationships_derive_expected_result(self):
        facts = relationship_facts()
        run = fake_run(facts)
        score = semantic_score.score_run(run)
        self.assertEqual(score["total_field_count"], 26)
        self.assertEqual(score["semantic_accuracy"], 1.0)
        self.assertEqual(score["wrong_semantic_assertion_count"], 0)
        self.assertEqual(score["missing_unknown_count"], 0)
        self.assertEqual(score["uncited_assertion_count"], 0)

        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            report = pipeline.canonicalize_run(run_path)

        result = report["canonicalization"]
        relationships = result["canonical_spec"]["profile_relationships"]
        self.assertEqual(result["canonicalization_status"], "complete")
        self.assertEqual(result["canonicalization_id"], "stm32f103c-canonicalization-v5")
        self.assertEqual(relationships["programming"], "shared")
        self.assertEqual(relationships["option"], "shared")
        self.assertEqual(relationships["memory_geometry"], "different")
        self.assertEqual(relationships["package_hardware"], "shared")
        self.assertEqual(relationships["security"], "shared")
        self.assertEqual(len(result["transformations"]), 9)
        self.assertEqual(result["transformations"][0]["relationship"], "option")
        self.assertEqual(result["transformations"][1]["relationship"], "programming")
        self.assertEqual(result["transformations"][2]["relationship"], "memory_geometry")
        self.assertEqual(result["transformations"][3]["relationship"], "package_hardware")
        self.assertEqual(
            result["transformations"][0]["comparison"]["semantics"],
            "applicable_option_contract_identity",
        )
        self.assertEqual(
            result["evidence"]["$.canonical_spec.profile_relationships.option"],
            [{"source_id": "st_pm0075_rev2", "physical_page_index": 0}],
        )
        self.assertFalse(result["trust_boundary"]["ai_emits_option_relationship"])
        self.assertTrue(result["trust_boundary"]["option_relationship_is_applicability_derived"])
        self.assertFalse(result["trust_boundary"]["option_relationship_from_raw_generated_field_equality"])

        canonical = canonical_score.score_report(report)
        self.assertEqual(canonical["total_field_count"], 25)
        self.assertEqual(canonical["exact_accuracy"], 1.0)
        self.assertEqual(canonical["wrong_assertion_count"], 0)
        self.assertEqual(canonical["missing_unknown_count"], 0)
        self.assertEqual(canonical["uncited_assertion_count"], 0)
        self.assertEqual(canonical["out_of_context_citation_count"], 0)

    def test_same_applicable_option_contract_derives_shared(self):
        relationship, _, transform = canonicalizer.derive_option_relationship(
            self.applicability, self.contract, verify_authority=False
        )
        self.assertEqual(relationship, "shared")
        self.assertEqual(transform["output"], "shared")

    def test_different_applicable_option_contracts_derive_different(self):
        applicability = copy.deepcopy(self.applicability)
        applicability["targets"]["STM32F103CBT6"]["contract_id"] = "other-option-contract-v0"
        relationship, _, _ = canonicalizer.derive_option_relationship(
            applicability, self.contract, verify_authority=False
        )
        self.assertEqual(relationship, "different")

    def test_insufficient_option_applicability_fails_closed_to_unknown(self):
        applicability = copy.deepcopy(self.applicability)
        applicability["targets"]["STM32F103CBT6"]["contract_id"] = None
        relationship, citations, transform = canonicalizer.derive_option_relationship(
            applicability, self.contract, verify_authority=False
        )
        self.assertEqual(relationship, "unknown")
        self.assertEqual(citations, [])
        self.assertEqual(transform["output"], "unknown")

    def test_option_relationship_is_not_derived_from_generated_option_fields(self):
        facts = relationship_facts()
        facts["option_contract"]["region_size_bytes"] = 32
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        result = canonicalizer.canonicalize_response(payload, self.contract)
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["option"], "shared")
        self.assertFalse(result["trust_boundary"]["option_relationship_from_raw_generated_field_equality"])

    def test_ai_cannot_add_derived_relationships(self):
        for relationship in ("programming", "option", "memory_geometry", "package_hardware"):
            facts = relationship_facts()
            facts["profile_relationships"][relationship] = "shared"
            with self.assertRaises(semantic.SemanticExtractionError):
                semantic.validate_semantic_facts(facts)


if __name__ == "__main__":
    unittest.main()
