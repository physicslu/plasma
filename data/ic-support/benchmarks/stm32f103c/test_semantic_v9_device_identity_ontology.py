from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import canonicalize_semantic_run_v9 as pipeline
import retained_semantic_v9 as retained
import score_canonical_v9 as canonical_score
import score_semantic_extraction_v9 as semantic_score
import semantic_extraction_v9 as semantic

HERE = Path(__file__).resolve().parent


def identity_facts() -> dict:
    return {
        "profile_relationships": {},
        "targets": {
            "STM32F103C8T6": {
                "manufacturer_applicability_expression": "STM32F103x8",
                "flash_size_bytes": 65536,
                "page_size_bytes": 1024,
                "page_count": 64,
                "package_hardware": {
                    "package_family": "LQFP",
                    "pin_count": 48,
                    "debug_programming_interfaces": ["SWD", "JTAG"]
                }
            },
            "STM32F103CBT6": {
                "manufacturer_applicability_expression": "STM32F103xB",
                "flash_size_bytes": 131072,
                "page_size_bytes": 1024,
                "page_count": 128,
                "package_hardware": {
                    "package_family": "LQFP",
                    "pin_count": 48,
                    "debug_programming_interfaces": ["SWD", "JTAG"]
                }
            }
        },
        "programming_contract": {
            "program_granularity_bytes": 2,
            "unlock_keys": ["0x45670123", "0xCDEF89AB"],
            "write_erase_requires_hsi": True
        },
        "option_contract": {
            "region_start_text": "0x1FFF F800",
            "region_size_bytes": 16,
            "encoding_structure": {
                "logical_value_width_bits": 8,
                "stored_pair_width_bits": 16,
                "companion_value_present": True,
                "companion_relation": "bitwise_not"
            }
        },
        "security_contract": {
            "read_unprotect_is_destructive": True,
            "write_protection_granularity_bytes": 4096
        }
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
            "programming_manual_physical_pages": [0, 19]
        },
        "runtime": {
            "model_id": retained.EXPECTED_MODEL,
            "configured_context_tokens": retained.EXPECTED_NUM_CTX
        },
        "generation": {
            "temperature": retained.EXPECTED_TEMPERATURE,
            "seed": retained.EXPECTED_SEED
        },
        "identity_ontology": {
            "commercial_target_identity_source": "targets_map_key",
            "manufacturer_applicability_expression_is_ai_extracted": True,
            "commercial_identity_is_ai_extracted_leaf": False,
            "fuzzy_identity_equivalence": False
        },
        "trust_boundary": {
            "canonical_dataset_admission": False,
            "production_admission": False,
            "destructive_security_operation_admission": False
        },
        "response": {"semantic_facts": facts, "evidence": evidence_for(facts)}
    }


class DeviceIdentityOntologyV9Test(unittest.TestCase):
    def test_schema_separates_commercial_target_key_from_manufacturer_expression(self):
        schema = json.loads((HERE / "semantic-extraction-v7.schema.json").read_text(encoding="utf-8"))
        target = schema["$defs"]["targetFacts"]
        self.assertIn("manufacturer_applicability_expression", target["required"])
        self.assertNotIn("manufacturer_device_reference", target["properties"])
        self.assertNotIn("target_part_number", target["properties"])
        self.assertEqual(
            set(schema["properties"]["targets"]["properties"]),
            {"STM32F103C8T6", "STM32F103CBT6"}
        )

    def test_prompt_forbids_copying_commercial_icpn_as_applicability_expression(self):
        prompt = (HERE / "semantic-extraction-prompt-v7.txt").read_text(encoding="utf-8")
        self.assertIn("Do not copy the requested commercial ICPN", prompt)
        self.assertIn("manufacturer_applicability_expression", prompt)

    def test_correct_identity_ontology_scores_and_canonicalizes_exactly(self):
        run = fake_run(identity_facts())
        score = semantic_score.score_run(run)
        self.assertEqual(score["total_field_count"], 25)
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
        self.assertEqual(result["canonicalization_id"], "stm32f103c-canonicalization-v7")
        self.assertEqual(result["canonical_spec"]["targets"]["STM32F103C8T6"]["manufacturer_device_reference"], "STM32F103x8")
        self.assertEqual(result["canonical_spec"]["targets"]["STM32F103CBT6"]["manufacturer_device_reference"], "STM32F103xB")
        self.assertEqual(result["transformations"][0]["kind"], "DETERMINISTIC_IDENTITY_ONTOLOGY_PROJECTION")
        self.assertFalse(result["transformations"][0]["fuzzy_matching"])
        self.assertEqual(len(result["transformations"]), 11)
        self.assertFalse(result["trust_boundary"]["commercial_target_identity_is_ai_extracted_leaf"])
        self.assertTrue(result["trust_boundary"]["manufacturer_applicability_expression_is_ai_extracted"])
        self.assertFalse(result["trust_boundary"]["identity_fuzzy_matching"])

        scored = canonical_score.score_report(report)
        self.assertEqual(scored["exact_accuracy"], 1.0)
        self.assertEqual(scored["wrong_assertion_count"], 0)
        self.assertEqual(scored["missing_unknown_count"], 0)

    def test_commercial_icpn_echo_is_semantic_error_not_representation_equivalence(self):
        facts = identity_facts()
        facts["targets"]["STM32F103C8T6"]["manufacturer_applicability_expression"] = "STM32F103C8T6"
        facts["targets"]["STM32F103CBT6"]["manufacturer_applicability_expression"] = "STM32F103CBT6"
        score = semantic_score.score_run(fake_run(facts))
        self.assertEqual(score["semantic_accuracy"], 23 / 25)
        self.assertEqual(score["wrong_semantic_assertion_count"], 2)
        self.assertEqual(score["representation_difference_count"], 0)
        self.assertEqual(
            score["paths"]["wrong_semantic"],
            [
                "$.semantic_facts.targets.STM32F103C8T6.manufacturer_applicability_expression",
                "$.semantic_facts.targets.STM32F103CBT6.manufacturer_applicability_expression"
            ]
        )

    def test_old_ambiguous_identity_field_is_rejected(self):
        facts = identity_facts()
        target = facts["targets"]["STM32F103C8T6"]
        target["manufacturer_device_reference"] = target.pop("manufacturer_applicability_expression")
        with self.assertRaises(semantic.SemanticExtractionError):
            semantic.validate_semantic_facts(facts)

    def test_retained_proof_keeps_strict_identity_and_admission_boundaries(self):
        self.assertEqual(retained.EXPECTED_MODEL, "qwen3.8:27b-mlx")
        self.assertEqual(retained.EXPECTED_NUM_CTX, 65536)
        self.assertEqual(retained.EXPECTED_SEED, 7)
        self.assertIn("device-identity", retained.BUNDLE_ID)


if __name__ == "__main__":
    unittest.main()
