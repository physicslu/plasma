from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import canonicalize_semantic_facts_v5 as canonicalizer
import canonicalize_semantic_run_v5 as pipeline
import score_canonical_v5 as canonical_score
import score_semantic_extraction_v5 as semantic_score
import semantic_extraction_v5 as semantic

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "canonicalization-contract-v3.json"


def relationship_facts() -> dict:
    return {
        "profile_relationships": {
            "programming": "shared",
            "option": "shared",
            "security": "shared",
        },
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
            "programming_manual_physical_pages": [19],
        },
        "runtime": {},
        "generation": {},
        "usage": {},
        "timing": {},
        "response": {"semantic_facts": facts, "evidence": evidence_for(facts)},
    }


class MemoryRelationshipDerivationV5PipelineTest(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_generation_contract_removes_ai_memory_and_package_relationships(self):
        schema = json.loads((HERE / "semantic-extraction-v3.schema.json").read_text(encoding="utf-8"))
        relationships = schema["properties"]["profile_relationships"]
        for relationship in ("memory_geometry", "package_hardware"):
            self.assertNotIn(relationship, relationships["required"])
            self.assertNotIn(relationship, relationships["properties"])

        generation_inputs = "\n".join(
            [
                (HERE / "semantic-extraction-v3.schema.json").read_text(encoding="utf-8"),
                (HERE / "semantic-extraction-prompt-v3.txt").read_text(encoding="utf-8"),
                (HERE / "semantic_extraction_v5.py").read_text(encoding="utf-8"),
                (HERE / "ollama_semantic_extraction_run_v5.py").read_text(encoding="utf-8"),
            ]
        )
        self.assertNotIn("semantic-extraction-ground-truth-v3.json", generation_inputs)
        self.assertNotIn("canonical-ground-truth-v3.json", generation_inputs)
        self.assertNotIn("canonicalization-contract-v3.json", generation_inputs)

    def test_semantics_and_memory_relationship_derive_expected_result(self):
        facts = relationship_facts()
        run = fake_run(facts)
        score = semantic_score.score_run(run)
        self.assertEqual(score["total_field_count"], 28)
        self.assertEqual(score["semantic_accuracy"], 1.0)
        self.assertEqual(score["wrong_semantic_assertion_count"], 0)
        self.assertEqual(score["missing_unknown_count"], 0)
        self.assertEqual(score["uncited_assertion_count"], 0)

        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            report = pipeline.canonicalize_run(run_path)

        result = report["canonicalization"]
        self.assertEqual(result["canonicalization_status"], "complete")
        self.assertEqual(result["canonicalization_id"], "stm32f103c-canonicalization-v3")
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["memory_geometry"], "different")
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["package_hardware"], "shared")
        self.assertEqual(len(result["transformations"]), 7)
        self.assertEqual(result["transformations"][0]["relationship"], "memory_geometry")
        self.assertEqual(result["transformations"][1]["relationship"], "package_hardware")
        self.assertFalse(result["trust_boundary"]["ai_emits_memory_geometry_relationship"])
        self.assertTrue(result["trust_boundary"]["memory_geometry_relationship_is_deterministic"])

        canonical = canonical_score.score_report(report)
        self.assertEqual(canonical["total_field_count"], 25)
        self.assertEqual(canonical["exact_accuracy"], 1.0)
        self.assertEqual(canonical["wrong_assertion_count"], 0)
        self.assertEqual(canonical["missing_unknown_count"], 0)
        self.assertEqual(canonical["uncited_assertion_count"], 0)
        self.assertEqual(canonical["out_of_context_citation_count"], 0)

    def test_complete_equal_memory_facts_derive_shared(self):
        facts = relationship_facts()
        cb = facts["targets"]["STM32F103CBT6"]
        cb["flash_size_bytes"] = 65536
        cb["page_count"] = 64
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        result = canonicalizer.canonicalize_response(payload, self.contract)
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["memory_geometry"], "shared")
        self.assertEqual(result["transformations"][0]["output"], "shared")

    def test_complete_unequal_memory_facts_derive_different(self):
        facts = relationship_facts()
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        result = canonicalizer.canonicalize_response(payload, self.contract)
        transformation = result["transformations"][0]
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["memory_geometry"], "different")
        self.assertEqual(transformation["comparison"]["semantics"], "exact_field_equality")
        self.assertEqual(len(transformation["source_paths"]), 6)
        self.assertEqual(transformation["output"], "different")

    def test_incomplete_memory_facts_fail_closed_to_unknown(self):
        facts = relationship_facts()
        facts["targets"]["STM32F103CBT6"]["page_count"] = None
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        result = canonicalizer.canonicalize_response(payload, self.contract)
        self.assertEqual(result["canonicalization_status"], "partial")
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["memory_geometry"], "unknown")
        self.assertIn("$.canonical_spec.profile_relationships.memory_geometry", result["unresolved_paths"])
        self.assertNotIn("$.canonical_spec.profile_relationships.memory_geometry", result["evidence"])
        self.assertEqual(result["transformations"][0]["source_paths"], [])

    def test_ai_cannot_add_memory_or_package_relationship(self):
        for relationship in ("memory_geometry", "package_hardware"):
            facts = relationship_facts()
            facts["profile_relationships"][relationship] = "shared"
            with self.assertRaises(semantic.SemanticExtractionError):
                semantic.validate_semantic_facts(facts)


if __name__ == "__main__":
    unittest.main()
