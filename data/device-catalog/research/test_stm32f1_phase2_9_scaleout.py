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

from evaluate_stm32f1_live_pilot import evaluate_live_pilot, read_baseline  # noqa: E402
from retain_stm32f1_browser_evidence import retain  # noqa: E402
from run_stm32f1_phase2_9_scaleout import command_plan  # noqa: E402
from stm32f1_acquisition_pilot import catalog_mapping, read_catalog, read_manifest  # noqa: E402
from stm32f1_admission_policy import MANUFACTURER, build_canonical_row  # noqa: E402
from stm32f1_scaleout_admission import (  # noqa: E402
    build_scaleout_plan,
    scaleout_plan_is_clean,
)

MANIFEST = HERE / "stm32f1-phase2.9-scaleout-manifest.json"
BASELINE = HERE / "stm32f1-phase2.9-scaleout-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
HISTORICAL_BASELINE = HERE / "stm32f1-acquisition-pilot-baseline.json"
HISTORICAL_EVIDENCE = HERE / "evidence" / "stm32f1-phase2.6-browser-2026-08-29"
EXPECTED_BASES = [
    "STM32F100CB",
    "STM32F100VE",
    "STM32F101RE",
    "STM32F101ZE",
    "STM32F102CB",
    "STM32F103RC",
    "STM32F105VB",
    "STM32F107RC",
]
EXPECTED_CANDIDATE_COUNT = 26
RUNTIME = {
    "engine": "chromium",
    "browser_version": "151.0.7922.34",
    "playwright_requirement": "1.62.0",
    "headless": False,
}


class Phase29ScaleoutTests(unittest.TestCase):
    def _baseline_by_base(self) -> dict[str, list[str]]:
        baseline = read_baseline(BASELINE)
        return {
            item["base_device"]: item["exact_icpns"]
            for item in baseline["targets"]
        }

    def _synthetic_pilot(self) -> dict[str, object]:
        pilot_id, targets = read_manifest(MANIFEST)
        catalog_rows = read_catalog(CATALOG)
        baseline_by_base = self._baseline_by_base()
        results = []
        for index, target in enumerate(targets):
            stamp = f"2026-08-29T15:1{index}:00Z"
            mapping = catalog_mapping(target.base_device, catalog_rows)
            results.append(
                {
                    "base_device": target.base_device,
                    "source_url": target.source_url,
                    "selection_reason": target.selection_reason,
                    "canonical_mapping": mapping,
                    "acquisition_status": "success",
                    "evidence": {
                        "schema_version": 1,
                        "parser_version": 1,
                        "acquisition_transport": "chromium_rendered_dom",
                        "base_device": target.base_device,
                        "source_url": target.source_url,
                        "final_url": target.source_url,
                        "retrieved_at_utc": stamp,
                        "http_etag": None,
                        "http_last_modified": None,
                        "evidence_surface": "quality_and_reliability_part_number",
                        "rendered_dom_sha256": f"{index + 1:064x}",
                        "evidence_section_sha256": f"{index + 101:064x}",
                        "exact_icpns": baseline_by_base[target.base_device],
                    },
                }
            )
        return {
            "schema_version": 1,
            "pilot_id": pilot_id,
            "attempted": 8,
            "acquisition_success": 8,
            "acquisition_failure": 0,
            "exact_icpn_candidates": EXPECTED_CANDIDATE_COUNT,
            "canonical_mapping": {"unique": 8, "ambiguous": 0, "unmapped": 0},
            "openocd_cfg_mapping": {"mapped": 8, "total": 8},
            "manual_intervention_required": 0,
            "results": results,
            "acquisition_transport": "chromium_rendered_dom",
            "browser_scope": "pilot",
            "browser_runtime": RUNTIME,
            "canonical_dataset_admission": False,
        }

    def _synthetic_control(self, pilot: dict[str, object]) -> dict[str, object]:
        first = pilot["results"][0]
        return {
            "schema_version": 1,
            "pilot_id": pilot["pilot_id"],
            "attempted": 1,
            "acquisition_success": 1,
            "acquisition_failure": 0,
            "exact_icpn_candidates": len(first["evidence"]["exact_icpns"]),
            "canonical_mapping": {"unique": 1, "ambiguous": 0, "unmapped": 0},
            "openocd_cfg_mapping": {"mapped": 1, "total": 1},
            "manual_intervention_required": 0,
            "results": [first],
            "acquisition_transport": "chromium_rendered_dom",
            "browser_scope": "control",
            "browser_runtime": RUNTIME,
            "canonical_dataset_admission": False,
        }

    def test_manifest_is_bounded_and_matches_expected_batch(self) -> None:
        pilot_id, targets = read_manifest(MANIFEST)
        self.assertEqual(pilot_id, "stm32f1-phase2.9-scaleout-batch1-2026-08-29")
        self.assertEqual([target.base_device for target in targets], EXPECTED_BASES)
        self.assertEqual(len(targets), 8)
        self.assertLessEqual(len(targets), 10)

    def test_research_baseline_matches_manifest_and_has_26_unique_candidates(self) -> None:
        _, targets = read_manifest(MANIFEST)
        baseline = read_baseline(BASELINE)
        self.assertFalse(baseline["canonical_dataset_admission"])
        self.assertEqual(baseline["pilot_id"], "stm32f1-phase2.9-scaleout-batch1-2026-08-29")
        baseline_by_base = self._baseline_by_base()
        self.assertEqual(set(baseline_by_base), {target.base_device for target in targets})
        candidates = [icpn for values in baseline_by_base.values() for icpn in values]
        self.assertEqual(len(candidates), EXPECTED_CANDIDATE_COUNT)
        self.assertEqual(len(set(candidates)), EXPECTED_CANDIDATE_COUNT)
        for base_device, icpns in baseline_by_base.items():
            self.assertTrue(icpns)
            self.assertTrue(all(icpn.startswith(base_device) and icpn != base_device for icpn in icpns))

    def test_batch_has_unique_openocd_mapping_for_every_base(self) -> None:
        catalog_rows = read_catalog(CATALOG)
        for base_device in EXPECTED_BASES:
            mapping = catalog_mapping(base_device, catalog_rows)
            self.assertEqual(mapping["status"], "unique", base_device)
            self.assertEqual(mapping["match_count"], 1, base_device)
            self.assertEqual(mapping["target_configs"], ["tcl/target/stm32f1x.cfg"], base_device)

    def test_scaleout_candidates_are_not_already_canonical(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            canonical_icpns = {row["icpn"] for row in csv.DictReader(handle)}
        scaleout_icpns = {
            icpn for values in self._baseline_by_base().values() for icpn in values
        }
        self.assertTrue(scaleout_icpns.isdisjoint(canonical_icpns))

    def test_existing_stm32f1_policy_can_construct_all_26_candidate_rows(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            fields = list(csv.DictReader(handle).fieldnames or [])
        catalog_rows = read_catalog(CATALOG)
        _, targets = read_manifest(MANIFEST)
        source_by_base = {target.base_device: target.source_url for target in targets}
        built: list[dict[str, str]] = []
        for base_device, icpns in self._baseline_by_base().items():
            mapping = catalog_mapping(base_device, catalog_rows)
            for icpn in icpns:
                candidate = {
                    "manufacturer": MANUFACTURER,
                    "base_device": base_device,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": "phase2.9-contract-only-not-admission",
                        "source_url": source_by_base[base_device],
                    },
                    "base_mapping": mapping,
                }
                built.append(build_canonical_row(candidate, fields))
        self.assertEqual(len(built), EXPECTED_CANDIDATE_COUNT)
        self.assertEqual(len({row["icpn"] for row in built}), EXPECTED_CANDIDATE_COUNT)
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32f1x.cfg" for row in built))
        self.assertEqual(next(row for row in built if row["icpn"] == "STM32F103RCY6TR")["package"], "WLCSP64")
        self.assertEqual(next(row for row in built if row["icpn"] == "STM32F105VBH6")["package"], "LFBGA")

    def test_baseline_is_not_misrepresented_as_retained_browser_evidence(self) -> None:
        payload = json.loads(BASELINE.read_text(encoding="utf-8"))
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn("rendered_dom_sha256", serialized)
        self.assertNotIn("evidence_section_sha256", serialized)
        self.assertNotIn("scale_ready", serialized)

    def test_dynamic_retention_accepts_eight_target_scale_ready_package(self) -> None:
        pilot = self._synthetic_pilot()
        control = self._synthetic_control(pilot)
        baseline = read_baseline(BASELINE)
        run_metadata = {
            "run_id": None,
            "run_attempt": None,
            "repository": "physicslu/plasma",
            "git_sha": "a" * 40,
        }
        evaluation = evaluate_live_pilot(
            summary=pilot,
            baseline=baseline,
            run_metadata=run_metadata,
        )
        self.assertTrue(evaluation["scale_ready"])
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
            evidence_dir = root / "retained"
            report = retain(
                control_path=control_path,
                pilot_path=pilot_path,
                evaluation_path=evaluation_path,
                baseline_path=BASELINE,
                output_dir=evidence_dir,
                evidence_id="phase2.9-eight-target-unit-evidence",
            )
            self.assertEqual(report["targets"], 8)
            self.assertEqual(report["exact_icpn_candidates"], EXPECTED_CANDIDATE_COUNT)
            self.assertTrue(report["scale_ready"])
            provenance = json.loads((evidence_dir / "provenance.json").read_text(encoding="utf-8"))
            self.assertEqual(provenance["target_count"], 8)
            self.assertEqual(provenance["baseline"]["pilot_id"], baseline["pilot_id"])

    def test_one_command_plan_is_headed_fail_closed_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            commands = command_plan(
                python=sys.executable,
                manifest=MANIFEST,
                baseline=BASELINE,
                catalog=CATALOG,
                canonical=CANONICAL,
                control_base="STM32F100CB",
                scratch=root / "scratch",
                evidence_dir=root / "evidence",
                admission_plan=root / "admission-plan.json",
                git_sha="b" * 40,
            )
        self.assertEqual(len(commands), 5)
        self.assertIn("--headed", commands[0])
        self.assertIn("--headed", commands[1])
        self.assertNotIn("--headless", commands[0])
        self.assertNotIn("--headless", commands[1])
        self.assertIn("STM32F100CB", commands[0])
        self.assertIn("b" * 40, commands[2])
        self.assertTrue(commands[3][1].endswith("retain_stm32f1_browser_evidence.py"))
        self.assertTrue(commands[4][1].endswith("stm32f1_scaleout_admission.py"))
        self.assertNotIn("write_canonical_dataset", " ".join(" ".join(command) for command in commands))
        orchestrator_source = (HERE / "run_stm32f1_phase2_9_scaleout.py").read_text(encoding="utf-8")
        planner_source = (HERE / "stm32f1_scaleout_admission.py").read_text(encoding="utf-8")
        self.assertNotIn("write_canonical_dataset", orchestrator_source)
        self.assertNotIn("write_canonical_dataset", planner_source)

    def test_scaleout_planner_reuses_historical_retained_evidence_without_hardcoded_batch(self) -> None:
        plan = build_scaleout_plan(
            evidence_dir=HISTORICAL_EVIDENCE,
            baseline_path=HISTORICAL_BASELINE,
            canonical_path=CANONICAL,
            catalog_path=CATALOG,
        )
        self.assertTrue(scaleout_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 26)
        self.assertEqual(plan["scaleout_expected_candidate_count"], 26)
        self.assertEqual(plan["decision_counts"]["already_present"], 26)
        self.assertEqual(plan["decision_counts"]["admit"], 0)
        self.assertEqual(plan["conflicts"], 0)


if __name__ == "__main__":
    unittest.main()
