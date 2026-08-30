#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import write_canonical_dataset  # noqa: E402
from device_catalog_pipeline_framework import (  # noqa: E402
    AdmissionInputs,
    build_pipeline_plan,
    pipeline_plan_is_clean,
)
from stm32f4_admission_policy import (  # noqa: E402
    FAMILY,
    TARGET_CONFIG,
    build_candidate_inputs,
    build_canonical_row,
    resolve_ordering_pattern_mapping,
)

BASELINE = HERE / "stm32f4-phase3.1-pilot-baseline.json"
MANIFEST = HERE / "stm32f4-phase3.1-pilot-manifest.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
F1_CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
EXPECTED_COUNT = 18


class STM32F4Phase31PolicyTests(unittest.TestCase):
    def _baseline(self) -> dict[str, object]:
        return json.loads(BASELINE.read_text(encoding="utf-8"))

    def _manifest(self) -> dict[str, object]:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def _catalog_rows(self) -> list[dict[str, str]]:
        with CATALOG.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def _canonical_fields(self) -> list[str]:
        with F1_CANONICAL.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle).fieldnames or [])

    def _synthetic_summary(self) -> dict[str, object]:
        baseline = self._baseline()
        manifest = self._manifest()
        source_by_base = {
            item["base_device"]: item["source_url"]
            for item in manifest["targets"]
        }
        results = []
        for index, target in enumerate(baseline["targets"]):
            base = target["base_device"]
            results.append(
                {
                    "base_device": base,
                    "evidence": {
                        "source_url": source_by_base[base],
                        "rendered_dom_sha256": f"{index + 1:064x}",
                        "evidence_section_sha256": f"{index + 101:064x}",
                        "exact_icpns": target["exact_icpns"],
                    },
                }
            )
        return {"results": results}

    def test_baseline_is_bounded_and_contains_18_unique_exact_icpns(self) -> None:
        baseline = self._baseline()
        self.assertEqual(baseline["pilot_id"], "stm32f4-phase3.1-bounded-pilot-2026-08-30")
        self.assertFalse(baseline["canonical_dataset_admission"])
        self.assertEqual(len(baseline["targets"]), 4)
        values = [icpn for target in baseline["targets"] for icpn in target["exact_icpns"]]
        self.assertEqual(len(values), EXPECTED_COUNT)
        self.assertEqual(len(set(values)), EXPECTED_COUNT)

    def test_every_exact_icpn_has_one_ordering_pattern_mapping(self) -> None:
        catalog_rows = self._catalog_rows()
        values = [icpn for target in self._baseline()["targets"] for icpn in target["exact_icpns"]]
        for icpn in values:
            mapping = resolve_ordering_pattern_mapping(icpn, catalog_rows)
            self.assertEqual(mapping["status"], "unique", icpn)
            self.assertEqual(mapping["match_count"], 1, icpn)
            self.assertEqual(mapping["identifier_kind"], "ordering_pattern", icpn)
            self.assertEqual(mapping["target_configs"], [TARGET_CONFIG], icpn)

        expected = {
            "STM32F401CCF6TR": "STM32F401CCFx",
            "STM32F407VGT6TR": "STM32F407VGTx",
            "STM32F411CEY3TR": "STM32F411CEYx",
            "STM32F429ZIY6TR": "STM32F429ZIYx",
        }
        for icpn, pattern in expected.items():
            self.assertEqual(
                resolve_ordering_pattern_mapping(icpn, catalog_rows)["existing_identifier"],
                pattern,
            )

    def test_f4_policy_builds_expected_package_pin_flash_and_temperature_semantics(self) -> None:
        fields = self._canonical_fields()
        candidates = build_candidate_inputs(
            summary=self._synthetic_summary(),
            evidence_id="phase3.1-synthetic-policy-contract",
            catalog_rows=self._catalog_rows(),
        )
        rows = {candidate["icpn"]: build_canonical_row(candidate, fields) for candidate in candidates}
        self.assertEqual(len(rows), EXPECTED_COUNT)
        self.assertTrue(all(row["family"] == FAMILY for row in rows.values()))
        self.assertTrue(all(row["openocd_target_config"] == TARGET_CONFIG for row in rows.values()))
        self.assertTrue(all(row["existing_identifier_kind"] == "ordering_pattern" for row in rows.values()))
        self.assertTrue(all(row["cmsis_device_name"] == "" for row in rows.values()))

        self.assertEqual(rows["STM32F401CCU6"]["package"], "UFQFPN")
        self.assertEqual(rows["STM32F401CCU6"]["pin_count"], "48")
        self.assertEqual(rows["STM32F401CCY6TT"]["package"], "WLCSP")
        self.assertEqual(rows["STM32F401CCY6TT"]["pin_count"], "49")
        self.assertEqual(rows["STM32F407VGT6"]["flash_size"], "1024 KiB")
        self.assertEqual(rows["STM32F411CEY3TR"]["temperature_grade"], "-40 to 125 C")
        self.assertEqual(rows["STM32F429ZIT6"]["pin_count"], "144")
        self.assertEqual(rows["STM32F429ZIY6TR"]["pin_count"], "143")
        self.assertEqual(rows["STM32F429ZIY6TR"]["flash_size"], "2048 KiB")

    def test_generic_phase30_pipeline_accepts_f4_without_core_changes(self) -> None:
        fields = self._canonical_fields()
        candidates = build_candidate_inputs(
            summary=self._synthetic_summary(),
            evidence_id="phase3.1-synthetic-pipeline-contract",
            catalog_rows=self._catalog_rows(),
        )
        with tempfile.TemporaryDirectory() as temp:
            canonical = Path(temp) / "stm32f4-commercial-icpn.csv"
            with canonical.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle, lineterminator="\n").writerow(fields)
            plan = build_pipeline_plan(
                canonical_path=canonical,
                row_builder=build_canonical_row,
                admission_inputs=AdmissionInputs(
                    evidence_id="phase3.1-synthetic-pipeline-contract",
                    candidate_inputs=candidates,
                    source_provenance={
                        "repository": "physicslu/plasma",
                        "executed_git_sha": "a" * 40,
                    },
                    input_bindings={"family_adapter": "stm32f4-phase3.1"},
                    expected_candidate_count=EXPECTED_COUNT,
                ),
            )
            self.assertTrue(pipeline_plan_is_clean(plan))
            self.assertEqual(plan["decision_counts"]["admit"], EXPECTED_COUNT)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 0)
            self.assertEqual(first["rows_after"], EXPECTED_COUNT)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")


if __name__ == "__main__":
    unittest.main()
