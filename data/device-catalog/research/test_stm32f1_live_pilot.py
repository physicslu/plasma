#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from evaluate_stm32f1_live_pilot import evaluate_live_pilot, read_baseline  # noqa: E402
from run_stm32f1_live_pilot import RateLimitedFetcher  # noqa: E402
from st_product_page_acquisition import AcquisitionError  # noqa: E402
from stm32f1_acquisition_pilot import read_manifest  # noqa: E402


class LivePilotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.baseline = read_baseline(HERE / "stm32f1-acquisition-pilot-baseline.json")

    def clean_summary(self) -> dict[str, object]:
        results: list[dict[str, object]] = []
        candidate_count = 0
        for target in self.baseline["targets"]:
            base_device = target["base_device"]
            exact_icpns = list(target["exact_icpns"])
            candidate_count += len(exact_icpns)
            source_url = (
                "https://www.st.com/en/microcontrollers-microprocessors/"
                f"{base_device.lower()}.html"
            )
            results.append(
                {
                    "base_device": base_device,
                    "source_url": source_url,
                    "selection_reason": "synthetic live-evidence test",
                    "canonical_mapping": {
                        "status": "unique",
                        "match_count": 1,
                        "identifier_kind": "cmsis_device_name",
                        "target_configs": ["tcl/target/stm32f1x.cfg"],
                    },
                    "acquisition_status": "success",
                    "evidence": {
                        "schema_version": 1,
                        "parser_version": 1,
                        "source_url": source_url,
                        "final_url": source_url,
                        "base_device": base_device,
                        "retrieved_at_utc": "2026-08-29T12:00:00Z",
                        "http_etag": None,
                        "http_last_modified": None,
                        "raw_sha256": "a" * 64,
                        "evidence_section_sha256": "b" * 64,
                        "evidence_surface": "quality_and_reliability_part_number",
                        "exact_icpns": exact_icpns,
                    },
                }
            )
        target_count = len(results)
        return {
            "schema_version": 1,
            "pilot_id": self.baseline["pilot_id"],
            "attempted": target_count,
            "acquisition_success": target_count,
            "acquisition_failure": 0,
            "exact_icpn_candidates": candidate_count,
            "canonical_mapping": {"unique": target_count, "ambiguous": 0, "unmapped": 0},
            "openocd_cfg_mapping": {"mapped": target_count, "total": target_count},
            "manual_intervention_required": 0,
            "results": results,
        }

    def test_checked_in_baseline_is_research_only_and_totals_26_candidates(self) -> None:
        self.assertFalse(self.baseline["canonical_dataset_admission"])
        self.assertEqual(len(self.baseline["targets"]), 6)
        self.assertEqual(
            sum(len(target["exact_icpns"]) for target in self.baseline["targets"]),
            26,
        )

    def test_baseline_target_set_matches_checked_in_pilot_manifest(self) -> None:
        pilot_id, manifest_targets = read_manifest(HERE / "stm32f1-acquisition-pilot-manifest.json")
        self.assertEqual(self.baseline["pilot_id"], pilot_id)
        self.assertEqual(
            {target["base_device"] for target in self.baseline["targets"]},
            {target.base_device for target in manifest_targets},
        )

    def test_clean_live_summary_is_scale_ready_without_optional_cache_headers(self) -> None:
        report = evaluate_live_pilot(summary=self.clean_summary(), baseline=self.baseline)
        self.assertTrue(report["scale_ready"])
        self.assertEqual(report["decision"], "scale_ready")
        self.assertEqual(report["observed_exact_icpn_candidates"], 26)
        self.assertTrue(report["candidate_baseline_match"])
        self.assertEqual(report["transport_evidence"]["valid_records"], 6)
        self.assertEqual(report["transport_evidence"]["etag_present"], 0)
        self.assertEqual(report["transport_evidence"]["last_modified_present"], 0)
        self.assertTrue(report["transport_evidence"]["headers_are_optional"])
        self.assertFalse(report["canonical_dataset_admission"])

    def test_candidate_replacement_with_same_total_count_requires_review(self) -> None:
        summary = self.clean_summary()
        evidence = summary["results"][0]["evidence"]
        evidence["exact_icpns"][-1] = "STM32F100C8X6"
        report = evaluate_live_pilot(summary=summary, baseline=self.baseline)
        self.assertFalse(report["scale_ready"])
        self.assertEqual(report["observed_exact_icpn_candidates"], 26)
        self.assertFalse(report["candidate_baseline_match"])
        self.assertEqual(len(report["candidate_drift"]), 1)
        self.assertIn("live exact ICPN candidate set differs", report["issues"][-1])

    def test_invalid_transport_digest_requires_review(self) -> None:
        summary = self.clean_summary()
        summary["results"][2]["evidence"]["raw_sha256"] = "not-a-digest"
        report = evaluate_live_pilot(summary=summary, baseline=self.baseline)
        self.assertFalse(report["scale_ready"])
        self.assertEqual(report["transport_evidence"]["valid_records"], 5)
        self.assertTrue(any("invalid raw_sha256" in issue for issue in report["issues"]))

    def test_runner_manual_intervention_cannot_be_promoted_to_scale_ready(self) -> None:
        summary = self.clean_summary()
        summary["manual_intervention_required"] = 1
        report = evaluate_live_pilot(summary=summary, baseline=self.baseline)
        self.assertFalse(report["scale_ready"])
        self.assertTrue(any("manual intervention" in issue for issue in report["issues"]))

    def test_rate_limited_fetcher_delays_between_requests_only(self) -> None:
        sleeps: list[float] = []
        calls: list[str] = []

        def fake_fetcher(url: str, timeout_seconds: float):
            self.assertEqual(timeout_seconds, 9.0)
            calls.append(url)
            return b"html", url, None, None

        fetcher = RateLimitedFetcher(
            delay_seconds=2.0,
            fetcher=fake_fetcher,
            sleeper=sleeps.append,
        )
        for suffix in ("a", "b", "c"):
            fetcher(f"https://www.st.com/en/{suffix}.html", 9.0)
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [2.0, 2.0])

    def test_rate_limited_fetcher_rejects_aggressive_delay(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "at least 1.0 seconds"):
            RateLimitedFetcher(delay_seconds=0.5)

    def test_manual_workflow_has_no_push_or_pull_request_trigger(self) -> None:
        workflow = (
            HERE.parents[2] / ".github" / "workflows" / "stm32f1-live-acquisition-pilot.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("--delay 2.0", workflow)
        self.assertIn("if: always()", workflow)


if __name__ == "__main__":
    unittest.main()
