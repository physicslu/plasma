from __future__ import annotations

import json
import unittest
from pathlib import Path

import canonicalize_semantic_facts as canonicalizer

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "canonicalization-contract-v0.json"
GROUND_TRUTH = HERE / "extraction-ground-truth.json"
SEMANTIC_SCHEMA = HERE / "semantic-extraction.schema.json"
CANONICAL_SCHEMA = HERE / "canonical-spec.schema.json"


def semantic_facts() -> dict:
    return {
        "profile_relationships": {
            "programming": "shared",
            "memory_geometry": "different",
            "package_hardware": "shared",
            "option": "shared",
            "security": "shared",
        },
        "targets": {
            "STM32F103C8T6": {
                "manufacturer_device_reference": "STM32F103x8",
                "flash_size_bytes": 65536,
                "page_size_bytes": 1024,
                "page_count": 64,
            },
            "STM32F103CBT6": {
                "manufacturer_device_reference": "STM32F103xB",
                "flash_size_bytes": 131072,
                "page_size_bytes": 1024,
                "page_count": 128,
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
            "encoding_semantics": "complemented",
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


class CanonicalizationFoundationTest(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_schema_artifacts_are_distinct_and_parseable(self):
        semantic_schema = json.loads(SEMANTIC_SCHEMA.read_text(encoding="utf-8"))
        canonical_schema = json.loads(CANONICAL_SCHEMA.read_text(encoding="utf-8"))
        self.assertEqual(semantic_schema["$id"], self.contract["semantic_schema_id"])
        self.assertEqual(canonical_schema["$id"], self.contract["canonical_schema_id"])
        self.assertNotEqual(semantic_schema["$id"], canonical_schema["$id"])
        self.assertIn("manufacturer_device_reference", semantic_schema["$defs"]["targetFacts"]["properties"])
        self.assertNotIn("commercial_part_base", semantic_schema["$defs"]["targetFacts"]["properties"])
        self.assertIn("commercial_part_base", canonical_schema["$defs"]["targetSpec"]["properties"])

    def test_qwen_like_manufacturer_near_facts_canonicalize_to_v0_ground_truth(self):
        facts = semantic_facts()
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        report = canonicalizer.canonicalize_response(payload, self.contract)

        self.assertEqual(report["canonicalization_status"], "complete")
        self.assertEqual(report["canonical_spec"]["targets"]["STM32F103C8T6"]["manufacturer_device_reference"], "STM32F103x8")
        self.assertEqual(report["canonical_spec"]["targets"]["STM32F103C8T6"]["commercial_part_base"], "STM32F103C8")
        self.assertEqual(report["canonical_spec"]["targets"]["STM32F103CBT6"]["manufacturer_device_reference"], "STM32F103xB")
        self.assertEqual(report["canonical_spec"]["targets"]["STM32F103CBT6"]["commercial_part_base"], "STM32F103CB")
        self.assertEqual(report["canonical_spec"]["option_contract"]["region_start"], "0x1FFFF800")
        self.assertEqual(report["canonical_spec"]["option_contract"]["encoding"], "byte_plus_complement")

        expected = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))["expected"]
        projection = canonicalizer.legacy_benchmark_projection(report["canonical_spec"])
        self.assertEqual(projection, expected)

        # 21 asserted semantic leaves plus deterministic ICPN + commercial-part identity for two targets.
        self.assertEqual(len(payload["evidence"]), 21)
        self.assertEqual(len(report["evidence"]), 25)
        self.assertEqual(len(report["transformations"]), 4)
        self.assertEqual(report["unresolved_paths"], [])
        self.assertFalse(report["trust_boundary"]["canonical_dataset_admission"])
        self.assertFalse(report["trust_boundary"]["production_admission"])

    def test_commercial_part_base_is_not_inferred_from_ai_reference(self):
        facts = semantic_facts()
        facts["targets"]["STM32F103C8T6"]["manufacturer_device_reference"] = "MANUFACTURER-GROUP-X"
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        report = canonicalizer.canonicalize_response(payload, self.contract)
        target = report["canonical_spec"]["targets"]["STM32F103C8T6"]
        self.assertEqual(target["manufacturer_device_reference"], "MANUFACTURER-GROUP-X")
        self.assertEqual(target["commercial_part_base"], "STM32F103C8")
        authority = report["evidence"]["$.canonical_spec.targets.STM32F103C8T6.commercial_part_base"]
        self.assertEqual(authority[0]["source_id"], "st_ds5319_rev20")
        self.assertEqual(authority[0]["physical_page_index"], 0)

    def test_address_normalization_is_representation_only(self):
        self.assertEqual(canonicalizer.normalize_hex_address("0x1FFF F800"), "0x1FFFF800")
        self.assertEqual(canonicalizer.normalize_hex_address("  0X0000ab cd  "), "0xABCD")
        with self.assertRaises(canonicalizer.CanonicalizationError):
            canonicalizer.normalize_hex_address("1FFF-F800")

    def test_unrecognized_controlled_vocabulary_fails_closed(self):
        facts = semantic_facts()
        facts["option_contract"]["encoding_semantics"] = "paired-inverse-maybe"
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        with self.assertRaises(canonicalizer.CanonicalizationError):
            canonicalizer.canonicalize_response(payload, self.contract)

    def test_asserted_semantic_fact_without_evidence_fails_closed(self):
        facts = semantic_facts()
        evidence = evidence_for(facts)
        evidence.pop("$.semantic_facts.option_contract.region_start_text")
        with self.assertRaises(canonicalizer.CanonicalizationError):
            canonicalizer.canonicalize_response({"semantic_facts": facts, "evidence": evidence}, self.contract)

    def test_null_semantic_fact_can_remain_unresolved_without_fabrication(self):
        facts = semantic_facts()
        facts["option_contract"]["encoding_semantics"] = None
        evidence = evidence_for(facts)
        report = canonicalizer.canonicalize_response({"semantic_facts": facts, "evidence": evidence}, self.contract)
        self.assertEqual(report["canonicalization_status"], "partial")
        self.assertIsNone(report["canonical_spec"]["option_contract"]["encoding"])
        self.assertIn("$.canonical_spec.option_contract.encoding", report["unresolved_paths"])
        self.assertNotIn("$.canonical_spec.option_contract.encoding", report["evidence"])


if __name__ == "__main__":
    unittest.main()
