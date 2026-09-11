from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

import vendor_neutral_admission_adapter as adapter


HERE = Path(__file__).resolve().parent
EVIDENCE = {
    "source_id": "nxp_kl25_rm_rev3",
    "pdf_page_number": 439,
    "source_sha256": "7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241",
    "locator": "synthetic projection fixture",
}


def synthetic_legacy() -> dict:
    units = [{"primary_unit_id": "synthetic-unit", "facts": []}]
    verdicts = []
    dispositions = []
    transformed_reviews = []
    for index in range(140):
        fact_id = f"synthetic-fact-{index:03d}"
        fact_digest = f"{index:064x}"
        units[0]["facts"].append(
            {
                "fact_id": fact_id,
                "fact_digest": fact_digest,
                "kind": "SYNTHETIC",
                "statement": f"Synthetic statement {index}",
                "all_citations": [{"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 439}],
            }
        )
        verdict = {
            "fact_id": fact_id,
            "fact_digest": fact_digest,
            "primary_unit_id": "synthetic-unit",
            "rationale": "Synthetic manufacturer review rationale.",
            **adapter.PASS,
        }
        action = "ACCEPT"
        candidate_total = 1
        if index >= 130:
            action = "SPLIT" if index < 133 else "NARROW"
            candidate_total = 2 if index < 133 else 1
            verdict["scope"] = "FAIL"
        verdicts.append(verdict)
        candidates = []
        for part in range(candidate_total):
            candidate_id = f"{fact_id}-candidate-{part}"
            candidate = {
                "candidate_id": candidate_id,
                "candidate_digest": f"{1000 + index * 2 + part:064x}",
                "statement": f"Candidate {index}/{part}",
                "evidence": [EVIDENCE],
            }
            candidates.append(candidate)
            if action != "ACCEPT":
                transformed_reviews.append({"candidate_id": candidate_id, **adapter.PASS})
        dispositions.append(
            {
                "primary_unit_id": "synthetic-unit",
                "fact_id": fact_id,
                "fact_digest": fact_digest,
                "action": action,
                "projection_state": "KNOWLEDGE_ONLY" if action != "ACCEPT" else "EXECUTION_PROFILE_REQUIRED",
                "candidates": candidates,
            }
        )

    fields = [
        ("memory.main_flash_start", "0x00000000"),
        ("memory.main_flash_size_bytes", 131072),
        ("memory.sector_size_bytes", 1024),
        ("silicon.program_granularity_bytes", 4),
        ("safety.flash_configuration_field_start", "0x00000400"),
    ]
    canonical_fields = [
        {"path": path, "value": value, "candidate_ids": [], "manufacturer_evidence": [], "review_record_id": None}
        for path, value in fields
    ]
    operation_requirements = {
        "READ": ["memory.main_flash_start", "memory.main_flash_size_bytes"],
        "VERIFY": ["memory.main_flash_start", "memory.main_flash_size_bytes"],
        "PROGRAM": ["memory.main_flash_start", "memory.main_flash_size_bytes", "silicon.program_granularity_bytes", "safety.flash_configuration_field_start"],
        "ERASE_SECTOR": ["memory.main_flash_start", "memory.main_flash_size_bytes", "memory.sector_size_bytes", "safety.flash_configuration_field_start"],
    }
    operations = {
        name: {
            "state": "ADMITTED",
            "required_fields": paths,
            "canonical_spec_digest": "1" * 64,
            "backend_lock_digest": adapter.CONTRACT["legacy_release"]["backend_lock_digest"],
            "hardware_runtime_ready": False,
        }
        for name, paths in operation_requirements.items()
    }
    for name in list(adapter.CONTRACT["operation_mapping"])[4:]:
        operations[name] = {
            "state": "BLOCKED",
            "reason": "outside frozen non-destructive Software Executor scope",
            "hardware_runtime_ready": False,
        }
    return {
        "view": {"units": units},
        "verdict": {"fact_verdicts": verdicts},
        "disposition": {"dispositions": dispositions},
        "candidate_review": {"candidate_reviews": transformed_reviews},
        "canonical_spec": {
            "target": "MKL25Z128VLK4",
            "spec_digest": "1" * 64,
            "canonical_fields": canonical_fields,
            "blocked_fields": [],
            "silicon": {"controller": "FTFA"},
        },
        "operations": {"operations": operations},
        "backend_lock": {
            "lock_digest": adapter.CONTRACT["legacy_release"]["backend_lock_digest"],
            "commit": adapter.CONTRACT["legacy_release"]["openocd_commit"],
            "files": {"src/flash/nor/kinetis.c": "2" * 64},
            "admitted_constraints": {"erase_requires_exact_sector_range": True},
            "trust_boundary": {"hardware_behavior_validated": False},
        },
    }


class VendorNeutralAdmissionAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.package = adapter.build_package(synthetic_legacy())

    def test_projection_passes_generic_validator_with_exact_coverage(self) -> None:
        result = adapter.validate_projection(self.package)
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["candidate_count"], 143)
        review = self.package["artifacts"]["nxp-kl25-review-binding-v1"]
        candidate_review = self.package["artifacts"]["nxp-kl25-candidate-review-v1"]
        self.assertEqual(len(review["review_subjects"]), 140)
        review_report = self.package["artifacts"]["nxp-kl25-gate58-review-verdict-v1"]
        self.assertEqual(len(review_report["findings"]), 10)
        self.assertEqual(len(candidate_review["candidate_reviews"]), 143)
        statuses = [row["review_status"] for row in candidate_review["candidate_reviews"]]
        self.assertEqual(statuses.count("INHERITED_GATE58_FULL_PASS"), 130)
        self.assertEqual(statuses.count("EXPLICIT_POST_REVIEW_PASS"), 13)

    def test_erase_is_target_owned_exact_sector_contract(self) -> None:
        operation_admission = self.package["artifacts"][self.package["operation_admission_id"]]
        erase = next(row for row in operation_admission["operations"] if row["request_operation"] == "ERASE")
        contract = self.package["artifacts"][erase["operation_contract_id"]]
        self.assertEqual(contract["target_operation"], "ERASE_SECTOR")
        self.assertEqual(contract["erase_scope"], "exact_sector_range")
        self.assertFalse(contract["implicit_range_padding"])

    def test_security_operations_stay_blocked_and_hardware_false(self) -> None:
        rows = self.package["artifacts"][self.package["operation_admission_id"]]["operations"]
        self.assertEqual(sum(row["state"] == "BLOCKED" for row in rows), 8)
        self.assertTrue(all(row["hardware_runtime_ready"] is False for row in rows))

    def test_fact_wrapper_preserves_legacy_digest_and_tamper_fails(self) -> None:
        fact = self.package["artifacts"]["synthetic-fact-000"]
        self.assertEqual(fact["legacy_fact_digest"], "0" * 64)
        tampered = copy.deepcopy(self.package)
        tampered["artifacts"]["synthetic-fact-000"]["statement"] = "changed"
        with self.assertRaisesRegex(Exception, "stale digest"):
            adapter.validate_projection(tampered)

    def test_local_schemas_and_contract_are_closed_and_versioned(self) -> None:
        for name in ("vendor-neutral-admission-payload.schema.json", "vendor-neutral-admission-wrapper.schema.json"):
            schema = json.loads((HERE / name).read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertFalse(schema["additionalProperties"])
        self.assertEqual(adapter.CONTRACT["expected_counts"]["facts"], 140)

    def test_full_locked_release_when_paths_are_available(self) -> None:
        names = ("NXP_KL25_RETAINED_RUN_DIR", "NXP_KL25_GATE58_DIR", "NXP_KL25_LEGACY_RELEASE_DIR")
        if not all(os.environ.get(name) for name in names):
            self.skipTest("locked external release paths are not configured")
        with tempfile.TemporaryDirectory() as directory:
            result = adapter.build_sidecar(
                Path(os.environ[names[0]]),
                Path(os.environ[names[1]]),
                Path(os.environ[names[2]]),
                Path(directory) / "sidecar",
            )
            self.assertEqual(result["generic_validation"]["status"], "VALID")
            self.assertEqual(result["legacy_validation"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
