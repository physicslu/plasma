from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import canonicalize_semantic_facts as legacy_canonicalizer
import canonicalize_semantic_facts_v3 as canonicalizer
import canonicalize_semantic_run_v3 as pipeline
import score_canonical_v3 as canonical_score
import score_semantic_extraction_v3 as semantic_score
import semantic_extraction_v3 as semantic

HERE = Path(__file__).resolve().parent
CONTRACT = HERE / "canonicalization-contract-v1.json"
LEGACY_CONTRACT = HERE / "canonicalization-contract-v0.json"


def structured_facts() -> dict:
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


class StructuredSemanticV3PipelineTest(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_generation_inputs_do_not_leak_hidden_canonical_mapping(self):
        generation_inputs = "\n".join(
            [
                (HERE / "semantic-extraction-v1.schema.json").read_text(encoding="utf-8"),
                (HERE / "semantic-extraction-prompt-v1.txt").read_text(encoding="utf-8"),
                (HERE / "semantic_extraction_v3.py").read_text(encoding="utf-8"),
                (HERE / "ollama_semantic_extraction_run_v3.py").read_text(encoding="utf-8"),
            ]
        )
        self.assertNotIn("byte_plus_complement", generation_inputs)
        self.assertNotIn("semantic-extraction-ground-truth-v1.json", generation_inputs)
        self.assertNotIn("canonical-ground-truth-v1.json", generation_inputs)
        self.assertNotIn("canonicalization-contract-v1.json", generation_inputs)

    def test_structured_semantics_score_and_canonicalize_exactly(self):
        facts = structured_facts()
        run = fake_run(facts)
        score = semantic_score.score_run(run)
        self.assertEqual(score["total_field_count"], 24)
        self.assertEqual(score["semantic_accuracy"], 1.0)
        self.assertEqual(score["literal_exact_accuracy"], 1.0)
        self.assertEqual(score["wrong_semantic_assertion_count"], 0)
        self.assertEqual(score["uncited_assertion_count"], 0)

        with tempfile.TemporaryDirectory() as tmp:
            run_path = Path(tmp) / "run.json"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            report = pipeline.canonicalize_run(run_path)

        result = report["canonicalization"]
        self.assertEqual(result["canonicalization_status"], "complete")
        self.assertEqual(result["canonicalization_id"], "stm32f103c-canonicalization-v1")
        self.assertEqual(result["canonical_spec"]["option_contract"]["encoding"], "byte_plus_complement")
        self.assertEqual(len(result["evidence"]), 25)
        self.assertEqual(len(result["transformations"]), 5)
        self.assertEqual(result["transformations"][0]["kind"], "STRUCTURED_OPTION_ENCODING_MAPPING")
        self.assertFalse(result["trust_boundary"]["free_form_semantic_matching"])

        canonical = canonical_score.score_report(report)
        self.assertEqual(canonical["total_field_count"], 25)
        self.assertEqual(canonical["exact_accuracy"], 1.0)
        self.assertEqual(canonical["wrong_assertion_count"], 0)
        self.assertEqual(canonical["uncited_assertion_count"], 0)
        self.assertEqual(canonical["out_of_context_citation_count"], 0)

    def test_free_form_encoding_sentence_is_schema_invalid(self):
        facts = structured_facts()
        facts["option_contract"]["encoding_structure"] = (
            "Option bytes are stored as a byte and its complement and the controller computes the companion."
        )
        with self.assertRaises(semantic.SemanticExtractionError):
            semantic.validate_semantic_facts(facts)

    def test_unadmitted_complete_structure_fails_closed(self):
        facts = structured_facts()
        facts["option_contract"]["encoding_structure"]["logical_value_width_bits"] = 16
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        with self.assertRaises(canonicalizer.CanonicalizationError):
            canonicalizer.canonicalize_response(payload, self.contract)

    def test_partial_structure_stays_unresolved(self):
        facts = structured_facts()
        facts["option_contract"]["encoding_structure"]["companion_relation"] = "unknown"
        payload = {"semantic_facts": facts, "evidence": evidence_for(facts)}
        report = canonicalizer.canonicalize_response(payload, self.contract)
        self.assertEqual(report["canonicalization_status"], "partial")
        self.assertIsNone(report["canonical_spec"]["option_contract"]["encoding"])
        self.assertIn("$.canonical_spec.option_contract.encoding", report["unresolved_paths"])
        self.assertFalse(report["trust_boundary"]["free_form_semantic_matching"])

    def test_legacy_free_form_sentence_is_not_added_as_alias(self):
        facts = structured_facts()
        sentence = (
            "Option bytes are stored as a byte and its complement (nOption). The FPEC takes the LSB and "
            "automatically computes the MSB (complement) to guarantee correctness."
        )
        legacy_facts = {
            "profile_relationships": facts["profile_relationships"],
            "targets": facts["targets"],
            "programming_contract": facts["programming_contract"],
            "option_contract": {
                "region_start_text": facts["option_contract"]["region_start_text"],
                "region_size_bytes": facts["option_contract"]["region_size_bytes"],
                "encoding_semantics": sentence,
            },
            "security_contract": facts["security_contract"],
        }
        legacy_evidence = {
            path: citations
            for path, citations in evidence_for(facts).items()
            if not path.startswith("$.semantic_facts.option_contract.encoding_structure.")
        }
        legacy_evidence["$.semantic_facts.option_contract.encoding_semantics"] = [
            {"source_id": "st_pm0075_rev2", "physical_page_index": 19}
        ]
        legacy_contract = json.loads(LEGACY_CONTRACT.read_text(encoding="utf-8"))
        with self.assertRaises(legacy_canonicalizer.CanonicalizationError):
            legacy_canonicalizer.canonicalize_response(
                {"semantic_facts": legacy_facts, "evidence": legacy_evidence},
                legacy_contract,
            )


if __name__ == "__main__":
    unittest.main()
