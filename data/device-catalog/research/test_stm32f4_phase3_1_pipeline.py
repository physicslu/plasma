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
from device_catalog_pipeline_framework import pipeline_plan_is_clean  # noqa: E402
from evaluate_stm32f4_pilot import evaluate_live_pilot, read_baseline  # noqa: E402
from retain_stm32f4_browser_evidence import retain  # noqa: E402
from stm32f4_acquisition_pilot import read_catalog, read_manifest, run_pilot  # noqa: E402
from stm32f4_admission import build_admission_plan  # noqa: E402
from stm32f4_admission_policy import TARGET_CONFIG  # noqa: E402

MANIFEST = HERE / "stm32f4-phase3.1-pilot-manifest.json"
BASELINE = HERE / "stm32f4-phase3.1-pilot-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
F1_CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
EXPECTED_COUNT = 18
RUNTIME = {
    "engine": "chromium",
    "browser_version": "151.0.7922.34",
    "playwright_requirement": "1.62.0",
    "headless": False,
}


class STM32F4Phase31PipelineTests(unittest.TestCase):
    def _baseline_by_base(self) -> dict[str, list[str]]:
        baseline = read_baseline(BASELINE)
        return {target["base_device"]: target["exact_icpns"] for target in baseline["targets"]}

    def _evidence_builder(self, **kwargs: object) -> dict[str, object]:
        base = str(kwargs["base_device"])
        index = list(self._baseline_by_base()).index(base) + 1
        return {
            "schema_version": 1,
            "parser_version": 1,
            "acquisition_transport": "chromium_rendered_dom",
            "base_device": base,
            "source_url": str(kwargs["source_url"]),
            "final_url": str(kwargs["final_url"]),
            "retrieved_at_utc": str(kwargs["retrieved_at_utc"]),
            "http_etag": kwargs.get("http_etag"),
            "http_last_modified": kwargs.get("http_last_modified"),
            "evidence_surface": "quality_and_reliability_part_number",
            "rendered_dom_sha256": f"{index:064x}",
            "evidence_section_sha256": f"{index + 100:064x}",
            "exact_icpns": self._baseline_by_base()[base],
        }

    @staticmethod
    def _fetcher(source_url: str, timeout_seconds: float) -> tuple[bytes, str, str | None, str | None]:
        del timeout_seconds
        return b"synthetic rendered DOM", source_url, None, None

    def _pilot(self) -> tuple[dict[str, object], dict[str, object]]:
        pilot_id, targets = read_manifest(MANIFEST)
        catalog = read_catalog(CATALOG)
        timestamps = iter(
            [
                "2026-08-30T02:10:00Z",
                "2026-08-30T02:11:00Z",
                "2026-08-30T02:12:00Z",
                "2026-08-30T02:13:00Z",
            ]
        )
        pilot = run_pilot(
            pilot_id=pilot_id,
            targets=targets,
            catalog_rows=catalog,
            fetcher=self._fetcher,
            evidence_builder=self._evidence_builder,
            retrieved_at_factory=lambda: next(timestamps),
        )
        pilot["acquisition_transport"] = "chromium_rendered_dom"
        pilot["browser_scope"] = "pilot"
        pilot["browser_runtime"] = RUNTIME
        pilot["canonical_dataset_admission"] = False

        control = run_pilot(
            pilot_id=pilot_id,
            targets=[targets[0]],
            catalog_rows=catalog,
            fetcher=self._fetcher,
            evidence_builder=self._evidence_builder,
            retrieved_at_factory=lambda: "2026-08-30T02:09:00Z",
        )
        control["acquisition_transport"] = "chromium_rendered_dom"
        control["browser_scope"] = "control"
        control["browser_runtime"] = RUNTIME
        control["canonical_dataset_admission"] = False
        return control, pilot

    def test_synthetic_browser_pilot_maps_all_18_exact_icpns(self) -> None:
        _, pilot = self._pilot()
        self.assertEqual(pilot["attempted"], 4)
        self.assertEqual(pilot["acquisition_success"], 4)
        self.assertEqual(pilot["exact_icpn_candidates"], EXPECTED_COUNT)
        self.assertEqual(pilot["canonical_mapping"], {"unique": 4, "ambiguous": 0, "unmapped": 0})
        self.assertEqual(pilot["openocd_cfg_mapping"], {"mapped": 4, "total": 4})
        self.assertEqual(pilot["manual_intervention_required"], 0)
        mappings = [item for result in pilot["results"] for item in result["candidate_mappings"]]
        self.assertEqual(len(mappings), EXPECTED_COUNT)
        self.assertTrue(all(item["status"] == "unique" for item in mappings))
        self.assertTrue(all(item["target_configs"] == [TARGET_CONFIG] for item in mappings))

    def test_evidence_retention_and_generic_admission_are_end_to_end_idempotent(self) -> None:
        control, pilot = self._pilot()
        baseline = read_baseline(BASELINE)
        evaluation = evaluate_live_pilot(
            summary=pilot,
            baseline=baseline,
            run_metadata={"repository": "physicslu/plasma", "git_sha": "a" * 40},
        )
        self.assertTrue(evaluation["scale_ready"])
        self.assertTrue(evaluation["candidate_baseline_match"])
        self.assertEqual(evaluation["candidate_drift"], [])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            control_path = root / "control.json"
            pilot_path = root / "pilot.json"
            evaluation_path = root / "evaluation.json"
            for path, value in (
                (control_path, control),
                (pilot_path, pilot),
                (evaluation_path, evaluation),
            ):
                path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            evidence_dir = root / "evidence"
            report = retain(
                control_path=control_path,
                pilot_path=pilot_path,
                evaluation_path=evaluation_path,
                baseline_path=BASELINE,
                output_dir=evidence_dir,
                evidence_id="stm32f4-phase3.1-synthetic-regression",
            )
            self.assertEqual(report["targets"], 4)
            self.assertEqual(report["exact_icpn_candidates"], EXPECTED_COUNT)
            self.assertTrue(report["scale_ready"])

            with F1_CANONICAL.open(newline="", encoding="utf-8") as handle:
                fields = list(csv.DictReader(handle).fieldnames or [])
            canonical = root / "stm32f4-commercial-icpn.csv"
            with canonical.open("w", newline="", encoding="utf-8") as handle:
                csv.writer(handle, lineterminator="\n").writerow(fields)

            plan = build_admission_plan(
                evidence_dir=evidence_dir,
                baseline_path=BASELINE,
                catalog_path=CATALOG,
                canonical_path=canonical,
            )
            self.assertTrue(pipeline_plan_is_clean(plan))
            self.assertEqual(plan["candidate_count"], EXPECTED_COUNT)
            self.assertEqual(plan["decision_counts"]["admit"], EXPECTED_COUNT)
            self.assertEqual(plan["conflicts"], 0)

            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 0)
            self.assertEqual(first["rows_after"], EXPECTED_COUNT)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(second["status"], "no_op")


if __name__ == "__main__":
    unittest.main()
