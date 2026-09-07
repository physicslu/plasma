from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import canonicalize_semantic_run_v8 as canonical_pipeline
import retained_semantic_v8 as retained
import score_canonical_v8 as canonical_score
import score_semantic_extraction_v8 as semantic_score
import semantic_extraction_v8 as semantic


def relationship_facts() -> dict:
    return {
        "profile_relationships": {},
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


def fake_run() -> dict:
    facts = relationship_facts()
    return {
        "schema_version": semantic.SEMANTIC_RUN_SCHEMA_VERSION,
        "experiment_id": semantic.SEMANTIC_EXPERIMENT_ID,
        "status": "success",
        "source_lock_id": "stm32f103c-source-lock-v0",
        "source_digests": {},
        "arm": retained.EXPECTED_ARM,
        "context": {
            "datasheet_physical_pages": [0],
            "programming_manual_physical_pages": [0, 19],
        },
        "runtime": {
            "model_id": retained.EXPECTED_MODEL,
            "configured_context_tokens": retained.EXPECTED_NUM_CTX,
        },
        "generation": {
            "temperature": retained.EXPECTED_TEMPERATURE,
            "seed": retained.EXPECTED_SEED,
        },
        "usage": {},
        "timing": {},
        "trust_boundary": {
            "canonical_dataset_admission": False,
            "production_admission": False,
            "destructive_security_operation_admission": False,
        },
        "response": {"semantic_facts": facts, "evidence": evidence_for(facts)},
    }


class RetainedSemanticV8ProofTest(unittest.TestCase):
    def _build_bundle(self, root: Path) -> None:
        run = fake_run()
        raw_path = root / retained.FILES["raw"]
        raw_path.write_text(json.dumps(run["response"]), encoding="utf-8")
        run_path = root / retained.FILES["run"]
        run_path.write_text(json.dumps(run), encoding="utf-8")

        semantic_report = retained._score_semantic(run, run_path)
        (root / retained.FILES["semantic_score"]).write_text(json.dumps(semantic_report), encoding="utf-8")

        canonical_report = canonical_pipeline.canonicalize_run(run_path)
        canonical_path = root / retained.FILES["canonical"]
        canonical_path.write_text(json.dumps(canonical_report), encoding="utf-8")

        canonical_report["trust_boundary"]["destructive_security_operation_admission"] = False
        canonical_report["canonicalization"]["trust_boundary"]["destructive_security_operation_admission"] = False
        canonical_path.write_text(json.dumps(canonical_report), encoding="utf-8")
        cscore = canonical_score.score_report(canonical_report)
        score_report = {
            "schema_version": canonical_score.SCORE_SCHEMA_VERSION,
            "pipeline_id": canonical_pipeline.PIPELINE_ID,
            "canonical_file": canonical_path.name,
            "canonical_sha256": "fixture",
            "score": cscore,
        }
        (root / retained.FILES["canonical_score"]).write_text(json.dumps(score_report), encoding="utf-8")

    def test_complete_bundle_verifies_and_has_no_ai_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_bundle(root)
            manifest = retained.verify_bundle(root)
        self.assertEqual(manifest["status"], "verified_retained_model_proof")
        self.assertEqual(manifest["semantic"]["accuracy"], 1.0)
        self.assertEqual(manifest["canonical"]["exact_accuracy"], 1.0)
        self.assertFalse(manifest["trust_boundary"]["ai_emits_profile_relationships"])
        self.assertFalse(manifest["trust_boundary"]["production_admission"])
        self.assertFalse(manifest["trust_boundary"]["hil_admission"])

    def test_wrong_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_bundle(root)
            run_path = root / retained.FILES["run"]
            run = json.loads(run_path.read_text(encoding="utf-8"))
            run["runtime"]["model_id"] = "other-model"
            run_path.write_text(json.dumps(run), encoding="utf-8")
            with self.assertRaises(retained.RetainedProofError):
                retained.verify_bundle(root)

    def test_nonzero_semantic_error_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._build_bundle(root)
            score_path = root / retained.FILES["semantic_score"]
            report = json.loads(score_path.read_text(encoding="utf-8"))
            report["score"]["wrong_semantic_assertion_count"] = 1
            score_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(retained.RetainedProofError):
                retained.verify_bundle(root)


if __name__ == "__main__":
    unittest.main()
