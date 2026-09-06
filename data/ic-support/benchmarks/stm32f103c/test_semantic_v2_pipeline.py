from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import canonicalize_semantic_run as canonical_pipeline
import score_canonical_v2 as canonical_score
import score_semantic_extraction_v2 as semantic_score
import semantic_extraction_v2 as semantic

HERE = Path(__file__).resolve().parent


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
        pm = any(marker in path for marker in ("programming_contract", "option_contract", "security_contract"))
        out[path] = [{
            "source_id": "st_pm0075_rev2" if pm else "st_ds5319_rev20",
            "physical_page_index": 19 if pm else 0,
        }]

    walk(facts, "$.semantic_facts")
    return out


def successful_run(payload: dict) -> dict:
    return {
        "schema_version": semantic.SEMANTIC_RUN_SCHEMA_VERSION,
        "experiment_id": semantic.SEMANTIC_EXPERIMENT_ID,
        "arm": "reduced_context",
        "source_lock_id": "stm32f103c-source-lock-v0",
        "source_digests": {
            "st_ds5319_rev20": "sha256:test-ds",
            "st_pm0075_rev2": "sha256:test-pm",
        },
        "context": {
            "datasheet_physical_pages": [0],
            "programming_manual_physical_pages": [19],
        },
        "runtime": {"model_id": "test-model"},
        "generation": {"num_ctx": 65536},
        "usage": {"input_tokens": 55732, "generation_tokens": 1510},
        "timing": {"total_time_ms": 1.0},
        "status": "success",
        "response": payload,
    }


class SemanticV2PipelineTest(unittest.TestCase):
    def test_semantic_schema_local_ref_is_enforced(self):
        facts = semantic_facts()
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        parsed = semantic.parse_model_result(json.dumps(payload))
        self.assertEqual(parsed, payload)

        invalid = json.loads(json.dumps(payload))
        invalid["semantic_facts"]["targets"]["STM32F103C8T6"]["unexpected"] = 1
        with self.assertRaises(semantic.SemanticExtractionError):
            semantic.parse_model_result(json.dumps(invalid))

    def test_asserted_semantic_leaf_requires_exact_evidence_path(self):
        facts = semantic_facts()
        evidence = evidence_for(facts)
        evidence.pop("$.semantic_facts.option_contract.region_start_text")
        with self.assertRaises(semantic.SemanticExtractionError):
            semantic.parse_model_result(json.dumps({"semantic_facts": facts, "evidence": evidence}))

    def test_manufacturer_near_qwen_values_score_as_semantically_correct(self):
        facts = semantic_facts()
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        score = semantic_score.score_run(successful_run(payload))
        self.assertEqual(score["status"], "scored")
        self.assertEqual(score["semantic_accuracy"], 1.0)
        self.assertEqual(score["wrong_semantic_assertion_count"], 0)
        self.assertEqual(score["missing_unknown_count"], 0)
        self.assertEqual(score["uncited_assertion_count"], 0)
        self.assertEqual(score["out_of_context_citation_count"], 0)
        self.assertEqual(score["asserted_leaf_count"], 21)

    def test_representation_variants_do_not_become_semantic_errors(self):
        facts = semantic_facts()
        facts["option_contract"]["region_start_text"] = "0X1ffff800"
        facts["option_contract"]["encoding_semantics"] = "byte + complement"
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        score = semantic_score.score_run(successful_run(payload))
        self.assertEqual(score["semantic_accuracy"], 1.0)
        self.assertEqual(score["wrong_semantic_assertion_count"], 0)
        self.assertEqual(score["representation_difference_count"], 2)
        self.assertLess(score["literal_exact_accuracy"], 1.0)

    def test_semantic_run_canonicalizes_to_exact_25_field_spec(self):
        facts = semantic_facts()
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        run = successful_run(payload)
        with tempfile.TemporaryDirectory() as temp_dir:
            run_path = Path(temp_dir) / "reduced_context.semantic.run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            report = canonical_pipeline.canonicalize_run(run_path)
        score = canonical_score.score_report(report)
        self.assertEqual(score["exact_accuracy"], 1.0)
        self.assertEqual(score["exact_field_count"], 25)
        self.assertEqual(score["wrong_assertion_count"], 0)
        self.assertEqual(score["missing_unknown_count"], 0)
        self.assertEqual(score["uncited_assertion_count"], 0)
        self.assertEqual(score["out_of_context_citation_count"], 0)
        self.assertEqual(score["transformation_count"], 4)

    def test_generation_surface_does_not_reference_hidden_answer_or_canonical_contract(self):
        runner = (HERE / "ollama_semantic_extraction_run.py").read_text(encoding="utf-8")
        prompt = (HERE / "semantic-extraction-prompt-v0.txt").read_text(encoding="utf-8")
        forbidden = (
            "semantic-extraction-ground-truth-v0.json",
            "canonical-ground-truth-v0.json",
            "canonicalization-contract-v0.json",
            "extraction-ground-truth.json",
        )
        for token in forbidden:
            self.assertNotIn(token, runner)
            self.assertNotIn(token, prompt)
        self.assertNotIn("commercial_part_base", prompt)
        self.assertNotIn("byte_plus_complement", prompt)


if __name__ == "__main__":
    unittest.main()
