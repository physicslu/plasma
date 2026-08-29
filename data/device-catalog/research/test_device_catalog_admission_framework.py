#!/usr/bin/env python3
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import (
    AdmissionError,
    CandidateManualReview,
    CandidateReject,
    build_admission_plan,
    canonical_csv_sha256,
    plan_is_clean,
    read_csv,
    write_canonical_dataset,
)

FIELDS = ["manufacturer", "icpn", "base_device", "source_reference"]


def candidate(icpn: str, *, base_device: str = "DEV1", manufacturer: str = "Vendor") -> dict[str, object]:
    return {
        "manufacturer": manufacturer,
        "base_device": base_device,
        "icpn": icpn,
        "authoritative_evidence": {"evidence_id": "e1", "source_url": "https://vendor.example/device"},
        "base_mapping": {"status": "unique", "target_configs": ["target.cfg"]},
    }


def row_builder(item: dict[str, object], fields: list[str]) -> dict[str, str]:
    icpn = item["icpn"]
    if icpn == "REJECT":
        raise CandidateReject("policy rejected candidate")
    if icpn == "REVIEW":
        raise CandidateManualReview("policy requires review")
    values = {
        "manufacturer": str(item["manufacturer"]),
        "icpn": str(icpn),
        "base_device": str(item["base_device"]),
        "source_reference": f"evidence:{item['authoritative_evidence']['evidence_id']}",
    }
    return {field: values[field] for field in fields}


def build_plan(items: list[dict[str, object]], rows: list[dict[str, str]] | None = None) -> dict[str, object]:
    return build_admission_plan(
        candidate_inputs=items,
        canonical_fields=FIELDS,
        canonical_rows=[] if rows is None else rows,
        source_provenance={"evidence_id": "e1", "repository": "example/repo", "executed_git_sha": "abc"},
        input_bindings={"canonical_dataset": "canonical.csv", "evidence_manifest_sha256": "f" * 64},
        row_builder=row_builder,
    )


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


class DeviceCatalogAdmissionFrameworkTests(unittest.TestCase):
    def test_generic_clean_gate_has_no_batch_size_assumption(self) -> None:
        for count in (0, 1, 3, 17):
            plan = build_plan([candidate(f"PN{index}") for index in range(count)])
            self.assertEqual(plan["candidate_count"], count)
            self.assertTrue(plan_is_clean(plan))

    def test_deterministic_ordering(self) -> None:
        plan = build_plan(
            [
                candidate("PN3", base_device="DEV2"),
                candidate("PN2", base_device="DEV1"),
                candidate("PN1", base_device="DEV1"),
            ]
        )
        self.assertEqual([item["icpn"] for item in plan["candidates"]], ["PN1", "PN2", "PN3"])

    def test_already_present_is_distinct_from_conflict(self) -> None:
        existing = row_builder(candidate("PN1"), FIELDS)
        same = build_plan([candidate("PN1")], [existing])
        self.assertEqual(same["decision_counts"]["already_present"], 1)
        conflict = dict(existing)
        conflict["source_reference"] = "evidence:other"
        changed = build_plan([candidate("PN1")], [conflict])
        self.assertEqual(changed["decision_counts"]["manual_review_required"], 1)
        self.assertEqual(changed["conflicts"], 1)

    def test_duplicate_candidate_is_rejected(self) -> None:
        plan = build_plan([candidate("PN1"), candidate("PN1")])
        self.assertEqual(plan["decision_counts"]["admit"], 1)
        self.assertEqual(plan["decision_counts"]["reject"], 1)
        self.assertFalse(plan_is_clean(plan))

    def test_policy_reject_and_manual_review_are_preserved(self) -> None:
        plan = build_plan([candidate("REJECT"), candidate("REVIEW")])
        self.assertEqual(plan["decision_counts"]["reject"], 1)
        self.assertEqual(plan["decision_counts"]["manual_review_required"], 1)
        self.assertFalse(plan_is_clean(plan))

    def test_writer_refuses_non_clean_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "canonical.csv"
            write_rows(path, [])
            plan = build_plan([candidate("REJECT")])
            with self.assertRaisesRegex(AdmissionError, "non-clean"):
                write_canonical_dataset(plan=plan, canonical_path=path)

    def test_writer_binds_to_planned_canonical_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "canonical.csv"
            write_rows(path, [])
            plan = build_plan([candidate("PN1")])
            write_rows(path, [row_builder(candidate("OTHER"), FIELDS)])
            with self.assertRaisesRegex(AdmissionError, "changed after admission planning"):
                write_canonical_dataset(plan=plan, canonical_path=path)

    def test_writer_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "canonical.csv"
            write_rows(path, [])
            plan = build_plan([candidate("PN1"), candidate("PN2")])
            first = write_canonical_dataset(plan=plan, canonical_path=path)
            second = write_canonical_dataset(plan=plan, canonical_path=path)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], 2)
            self.assertEqual(second["status"], "no_op")
            fields, rows = read_csv(path)
            self.assertEqual(fields, FIELDS)
            self.assertEqual(len(rows), 2)

    def test_canonical_hash_is_bound_by_framework(self) -> None:
        rows = [row_builder(candidate("PN0"), FIELDS)]
        plan = build_plan([candidate("PN1")], rows)
        self.assertEqual(plan["inputs"]["canonical_input_sha256"], canonical_csv_sha256(FIELDS, rows))

    def test_authoritative_evidence_is_transport_agnostic_and_retained(self) -> None:
        item = candidate("PN1")
        item["authoritative_evidence"] = {
            "evidence_id": "csv-evidence",
            "transport": "official_csv",
            "sha256": "a" * 64,
        }
        plan = build_admission_plan(
            candidate_inputs=[item],
            canonical_fields=FIELDS,
            canonical_rows=[],
            source_provenance={"evidence_id": "csv-evidence"},
            input_bindings={"canonical_dataset": "canonical.csv"},
            row_builder=row_builder,
        )
        self.assertEqual(plan["candidates"][0]["authoritative_evidence"]["transport"], "official_csv")


if __name__ == "__main__":
    unittest.main()
