from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import canonicalize_semantic_facts_v4 as canonicalizer
import canonicalize_semantic_run_v4 as pipeline
import score_canonical_v4 as canonical_score
import score_semantic_extraction_v4 as semantic_score
import semantic_extraction_v4 as semantic

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "canonicalization-contract-v2.json"


def relationship_facts() -> dict:
    return {
        "profile_relationships": {
            "programming": "shared",
            "memory_geometry": "different",
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
                    "package": "LQFP",
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
                    "package": "LQFP",
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


class RelationshipDerivationV4PipelineTest(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_generation_contract_removes_ai_package_relationship(self):
        schema = json.loads((HERE / "semantic-extraction-v2.schema.json").read_text(encoding="utf-8"))
        relationships = schema["properties"]["profile_relationships"]
        self.assertNotIn("package_hardware", relationships["required"])
        self.assertNotIn("package_hardware", relationships["properties"])

        generation_inputs = "\n".join(
            [
                (HERE / "semantic-extraction-v2.schema.json").read_text(encoding="utf-8"),
                (HERE / "semantic-extraction-prompt-v2.txt").read_text(encoding="utf-8"),
                (HERE / "semantic_extraction_v4.py").read_text(encoding="utf-8"),
                (HERE / "ollama_semantic_extraction_run_v4.py").read_text(encoding="utf-8"),
            ]
        )
        self.assertNotIn("semantic-extraction-ground-truth-v2.json", generation_inputs)
        self.assertNotIn("canonical-ground-truth-v2.json", generation_inputs)
        self.assertNotIn("canonicalization-contract-v2.json", generation_inputs)

    def test_semantics_score_and_package_relationship_derives_shared(self):
        facts = relationship_facts()
        run = fake_run(facts)
        score = semantic_score.score_run(run)
        self.assertEqual(score["total_field_count"], 29)
        self.assertEqual(score["semantic_accuracy"], 1.0)
        self.assertEqual(score["literal_exact_accuracy"], 1.0)
        self.assertEqual(score["wrong_semantic_assertion_count"], 0)
        self.assertEqual(score["missing_unknown_count"], 0)
        self.assertEqual(score["uncited_assertion_count"], 0)

        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            report = pipeline.canonicalize_run(run_path)

        result = report["canonicalization"]
        self.assertEqual(result["canonicalization_status"], "complete")
        self.assertEqual(result["canonicalization_id"], "stm32f103c-canonicalization-v2")
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["package_hardware"], "shared")
        self.assertEqual(result["canonical_spec"]["option_contract"]["encoding"], "byte_plus_complement")
        self.assertEqual(len(result["evidence"]), 25)
        self.assertEqual(len(result["transformations"]), 6)
        self.assertEqual(result["transformations"][0]["kind"], "DETERMINISTIC_RELATIONSHIP_DERIVATION")
        self.assertFalse(result["trust_boundary"]["ai_emits_package_hardware_relationship"])
        self.assertTrue(result["trust_boundary"]["package_hardware_relationship_is_deterministic"])

        canonical = canonical_score.score_report(report)
        self.assertEqual(canonical["total_field_count"], 25)
        self.assertEqual(canonical["exact_accuracy"], 1.0)
        self.assertEqual(canonical["wrong_assertion_count"], 0)
        self.assertEqual(canonical["missing_unknown_count"], 0)
        self.assertEqual(canonical["uncited_assertion_count"], 0)
        self.assertEqual(canonical["out_of_context_citation_count"], 0)

    def test_debug_interface_order_is_representation_only(self):
        facts = relationship_facts()
        facts["targets"]["STM32F103C8T6"]["package_hardware"]["debug_programming_interfaces"] = ["JTAG", "SWD"]
        run = fake_run(facts)
        score = semantic_score.score_run(run)
        path = "$.semantic_facts.targets.STM32F103C8T6.package_hardware.debug_programming_interfaces"
        self.assertEqual(score["semantic_accuracy"], 1.0)
        self.assertLess(score["literal_exact_accuracy"], 1.0)
        self.assertEqual(score["paths"]["representation_difference"], [path])

        payload = run["response"]
        result = canonicalizer.canonicalize_response(payload, self.contract)
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["package_hardware"], "shared")

    def test_complete_different_package_derives_different(self):
        facts = relationship_facts()
        facts["targets"]["STM32F103CBT6"]["package_hardware"]["pin_count"] = 64
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        result = canonicalizer.canonicalize_response(payload, self.contract)
        self.assertEqual(result["canonicalization_status"], "complete")
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["package_hardware"], "different")
        transformation = result["transformations"][0]
        self.assertEqual(transformation["kind"], "DETERMINISTIC_RELATIONSHIP_DERIVATION")
        self.assertEqual(transformation["output"], "different")

    def test_incomplete_package_facts_fail_closed_to_unknown(self):
        facts = relationship_facts()
        facts["targets"]["STM32F103CBT6"]["package_hardware"]["debug_programming_interfaces"] = None
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        result = canonicalizer.canonicalize_response(payload, self.contract)
        self.assertEqual(result["canonicalization_status"], "partial")
        self.assertEqual(result["canonical_spec"]["profile_relationships"]["package_hardware"], "unknown")
        self.assertIn(
            "$.canonical_spec.profile_relationships.package_hardware",
            result["unresolved_paths"],
        )
        self.assertNotIn(
            "$.canonical_spec.profile_relationships.package_hardware",
            result["evidence"],
        )

    def test_ai_cannot_add_package_relationship_to_generation_schema(self):
        facts = relationship_facts()
        facts["profile_relationships"]["package_hardware"] = "shared"
        with self.assertRaises(semantic.SemanticExtractionError):
            semantic.validate_semantic_facts(facts)


if __name__ == "__main__":
    unittest.main()
