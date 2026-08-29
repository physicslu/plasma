#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import plan_is_clean as framework_plan_is_clean  # noqa: E402
from stm32f1_admission_policy import build_canonical_row  # noqa: E402
from stm32f1_canonical_admission import (  # noqa: E402
    AdmissionError,
    build_admission_plan,
    plan_is_clean,
    read_csv,
    write_canonical_dataset,
)

EVIDENCE = HERE / "evidence" / "stm32f1-phase2.6-browser-2026-08-29"
CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
CATALOG = HERE / "openocd-parts-canonical.csv"
BASELINE = HERE / "stm32f1-acquisition-pilot-baseline.json"
HISTORICAL_PLAN = HERE / "stm32f1-phase2.7-admission-plan.json"


class CanonicalAdmissionTests(unittest.TestCase):
    def _workspace(self, root: Path) -> tuple[Path, Path, Path, Path]:
        evidence = root / EVIDENCE.name
        evidence.mkdir()
        for source in EVIDENCE.iterdir():
            (evidence / source.name).write_bytes(source.read_bytes())
        canonical = root / CANONICAL.name
        catalog = root / CATALOG.name
        baseline = root / BASELINE.name
        fields, rows = read_csv(CANONICAL)
        rows = [
            row
            for row in rows
            if "#plasma-evidence=stm32f1-phase2.6.3-" not in row["source_reference"]
            and "#plasma-evidence=stm32f1-phase2.9-scaleout-batch1-" not in row["source_reference"]
        ]
        with canonical.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        catalog.write_bytes(CATALOG.read_bytes())
        baseline.write_bytes(BASELINE.read_bytes())
        return evidence, canonical, catalog, baseline

    def _plan(self, paths: tuple[Path, Path, Path, Path]) -> dict[str, object]:
        evidence, canonical, catalog, baseline = paths
        return build_admission_plan(
            evidence_dir=evidence,
            canonical_path=canonical,
            catalog_path=catalog,
            baseline_path=baseline,
        )

    def _rehash_manifest_file(self, evidence: Path, name: str) -> None:
        manifest_path = evidence / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256((evidence / name).read_bytes()).hexdigest()
        for item in manifest["files"]:
            if item["path"] == name:
                item["sha256"] = digest
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def test_clean_plan_admits_all_26_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan = self._plan(self._workspace(Path(temp)))
            self.assertEqual(plan["decision_counts"], {"admit": 26, "already_present": 0, "manual_review_required": 0, "reject": 0})
            self.assertEqual(plan["conflicts"], 0)
            rows = {item["icpn"]: item["proposed_canonical_row"] for item in plan["candidates"]}
            self.assertEqual(rows["STM32F103ZEH6"]["package"], "LFBGA")
            self.assertEqual(rows["STM32F107VCH6"]["package"], "LFBGA")
            self.assertEqual(rows["STM32F100C8T7B"]["temperature_grade"], "-40 to 105 C")
            self.assertEqual(rows["STM32F100C8T7B"]["pin_count"], "48")
            self.assertEqual(rows["STM32F100C8T7B"]["flash_size"], "64 KiB")
            self.assertEqual(rows["STM32F103ZEH6"]["pin_count"], "144")
            self.assertEqual(rows["STM32F103ZEH6"]["flash_size"], "512 KiB")

    def test_historical_phase27_plan_semantics_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan = self._plan(self._workspace(Path(temp)))
            historical = json.loads(HISTORICAL_PLAN.read_text(encoding="utf-8"))
            self.assertEqual(plan["evidence_id"], historical["evidence_id"])
            self.assertEqual(plan["source_provenance"], historical["source_provenance"])
            self.assertEqual(plan["decision_counts"], historical["decision_counts"])
            self.assertEqual(plan["conflicts"], historical["conflicts"])
            self.assertEqual(plan["canonical_rows_before"], historical["canonical_rows_before"])
            self.assertEqual(plan["candidates"], historical["candidates"])

    def test_current_post_write_state_allows_later_canonical_admissions(self) -> None:
        plan = build_admission_plan(
            evidence_dir=EVIDENCE,
            canonical_path=CANONICAL,
            catalog_path=CATALOG,
            baseline_path=BASELINE,
        )
        _, rows = read_csv(CANONICAL)
        self.assertEqual(len(rows), 75)
        self.assertEqual(
            plan["decision_counts"],
            {"admit": 0, "already_present": 26, "manual_review_required": 0, "reject": 0},
        )

    def test_historical_26_candidate_gate_is_not_in_generic_framework(self) -> None:
        synthetic = {
            "candidate_count": 1,
            "decision_counts": {"admit": 1, "already_present": 0, "manual_review_required": 0, "reject": 0},
            "conflicts": 0,
            "issues": [],
        }
        self.assertTrue(framework_plan_is_clean(synthetic))
        self.assertFalse(plan_is_clean(synthetic))

    def test_stm32f1_policy_rejects_base_device_as_exact_icpn(self) -> None:
        fields, _ = read_csv(CANONICAL)
        candidate = {
            "manufacturer": "STMicroelectronics",
            "base_device": "STM32F100C8",
            "icpn": "STM32F100C8",
            "authoritative_evidence": {
                "evidence_id": "e1",
                "source_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html",
            },
            "base_mapping": {
                "status": "unique",
                "identifier_kind": "cmsis_device_name",
                "target_configs": ["tcl/target/stm32f1x.cfg"],
            },
        }
        with self.assertRaisesRegex(Exception, "invalid exact commercial ICPN"):
            build_canonical_row(candidate, fields)

    def test_plan_is_deterministic_for_identical_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp))
            self.assertEqual(self._plan(paths), self._plan(paths))

    def test_already_present_is_not_admitted_twice(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp))
            plan = self._plan(paths)
            fields, rows = read_csv(paths[1])
            rows.append(plan["candidates"][0]["proposed_canonical_row"])
            with paths[1].open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
                writer.writeheader(); writer.writerows(rows)
            rerun = self._plan(paths)
            self.assertEqual(rerun["decision_counts"]["already_present"], 1)
            self.assertEqual(rerun["decision_counts"]["admit"], 25)

    def test_duplicate_retained_candidate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp)); evidence = paths[0]
            summary_path = evidence / "pilot-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["results"][1]["evidence"]["exact_icpns"][0] = summary["results"][0]["evidence"]["exact_icpns"][0]
            summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._rehash_manifest_file(evidence, "pilot-summary.json")
            with self.assertRaisesRegex(Exception, "candidate|ICPN|reevaluation"):
                self._plan(paths)

    def test_conflicting_canonical_row_requires_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp)); plan = self._plan(paths)
            fields, rows = read_csv(paths[1]); conflict = dict(plan["candidates"][0]["proposed_canonical_row"])
            conflict["source_reference"] = "https://www.st.com/conflicting"
            rows.append(conflict)
            with paths[1].open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
            rerun = self._plan(paths)
            self.assertEqual(rerun["decision_counts"]["manual_review_required"], 1)
            self.assertEqual(rerun["conflicts"], 1)

    def test_ambiguous_base_mapping_requires_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp)); fields, rows = read_csv(paths[2])
            duplicate = next(dict(row) for row in rows if row["part_number"] == "STM32F100C8")
            duplicate["catalog_origin"] = "synthetic-duplicate"
            rows.append(duplicate)
            with paths[2].open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
            plan = self._plan(paths)
            self.assertEqual(plan["decision_counts"]["manual_review_required"], 4)

    def test_unmapped_base_device_requires_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp)); fields, rows = read_csv(paths[2])
            rows = [row for row in rows if row["part_number"] != "STM32F102C8"]
            with paths[2].open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
            plan = self._plan(paths)
            self.assertEqual(plan["decision_counts"]["manual_review_required"], 2)

    def test_missing_evidence_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp)); evidence = paths[0]
            provenance_path = evidence / "provenance.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8")); provenance.pop("evidence_id")
            provenance_path.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            self._rehash_manifest_file(evidence, "provenance.json")
            with self.assertRaisesRegex(Exception, "evidence_id"):
                self._plan(paths)

    def test_tampered_evidence_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp))
            with (paths[0] / "pilot-summary.json").open("a", encoding="utf-8") as handle: handle.write(" ")
            with self.assertRaisesRegex(Exception, "digest mismatch"):
                self._plan(paths)

    def test_invalid_openocd_mapping_requires_manual_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp)); fields, rows = read_csv(paths[2])
            for row in rows:
                if row["part_number"] == "STM32F107VC": row["target_config"] = ""
            with paths[2].open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
            plan = self._plan(paths)
            self.assertEqual(plan["decision_counts"]["manual_review_required"], 4)

    def test_writer_refuses_non_clean_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp)); plan = self._plan(paths)
            plan["decision_counts"]["reject"] = 1
            with self.assertRaisesRegex(AdmissionError, "non-clean"):
                write_canonical_dataset(plan=plan, canonical_path=paths[1])

    def test_writer_and_planner_are_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            paths = self._workspace(Path(temp)); plan = self._plan(paths)
            first = write_canonical_dataset(plan=plan, canonical_path=paths[1])
            second = write_canonical_dataset(plan=plan, canonical_path=paths[1])
            rerun = self._plan(paths)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], 49)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(rerun["decision_counts"], {"admit": 0, "already_present": 26, "manual_review_required": 0, "reject": 0})


if __name__ == "__main__":
    unittest.main()
