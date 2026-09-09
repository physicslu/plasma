#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from st_product_page_acquisition import AcquisitionError
from stm32f7_foundation import DEFAULT_CATALOG, deterministic_initial_targets, read_catalog
from stm32f7_phase4_6b_discovery import (
    CANONICAL_PAGE_404,
    DEFAULT_MANIFEST,
    MAX_TARGETS,
    discovery_is_clean,
    read_manifest,
    run_discovery,
    source_url_for_base,
)


class STM32F7Phase46BDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = read_catalog(DEFAULT_CATALOG)
        self.pilot_id, self.targets = read_manifest(DEFAULT_MANIFEST, self.catalog)

    @staticmethod
    def fetcher(source_url: str, timeout_seconds: float):
        del timeout_seconds
        return b"<html></html>", source_url, None, None

    @staticmethod
    def evidence_builder(**kwargs):
        base = kwargs["base_device"]
        return {
            "base_device": base,
            "parser_profile": "stm32f7_dual_surface_v1",
            "evidence_surface": "quality_and_reliability_identity_plus_sample_and_buy_lifecycle",
            "exact_icpns": [f"{base}T6"],
            "excluded_non_active_part_numbers": [],
        }

    def test_manifest_exactly_replays_phase46a_selection(self) -> None:
        observed = [(target.subfamily, target.base_device) for target in self.targets]
        self.assertEqual(observed, deterministic_initial_targets(self.catalog))
        self.assertEqual(len(observed), 16)
        self.assertEqual(len(observed), MAX_TARGETS)
        for target in self.targets:
            self.assertEqual(target.source_url, source_url_for_base(target.base_device))

    def test_clean_active_discovery_is_not_gated_by_unmapped_openocd(self) -> None:
        with patch(
            "stm32f7_phase4_6b_discovery.resolve_mapping",
            return_value={"status": "unmapped", "match_count": 0, "target_configs": []},
        ):
            summary = run_discovery(
                pilot_id=self.pilot_id,
                targets=self.targets,
                catalog_rows=self.catalog,
                fetcher=self.fetcher,
                evidence_builder=self.evidence_builder,
            )
        self.assertTrue(summary["commercial_identity_clean"])
        self.assertTrue(summary["bounded_discovery_clean"])
        self.assertEqual(summary["active_candidate_targets"], MAX_TARGETS)
        self.assertEqual(summary["openocd_routing"]["unmapped"], MAX_TARGETS)
        self.assertEqual(summary["routing_followup_required"], MAX_TARGETS)
        self.assertFalse(summary["openocd_routing"]["gates_commercial_identity"])
        self.assertTrue(discovery_is_clean(summary))

    def test_lifecycle_only_target_is_excluded_not_failed(self) -> None:
        lifecycle_base = self.targets[0].base_device

        def builder(**kwargs):
            base = kwargs["base_device"]
            if base == lifecycle_base:
                return {
                    "base_device": base,
                    "exact_icpns": [],
                    "excluded_non_active_part_numbers": [
                        {
                            "icpn": f"{base}T6",
                            "marketing_status": "NRND Not recommended for New Design.",
                        }
                    ],
                }
            return self.evidence_builder(**kwargs)

        summary = run_discovery(
            pilot_id=self.pilot_id,
            targets=self.targets,
            catalog_rows=self.catalog,
            fetcher=self.fetcher,
            evidence_builder=builder,
        )
        self.assertEqual(summary["acquisition_failure"], 0)
        self.assertEqual(summary["acquisition_success"], MAX_TARGETS)
        self.assertEqual(summary["lifecycle_excluded_targets"], 1)
        self.assertEqual(summary["active_candidate_targets"], MAX_TARGETS - 1)
        self.assertEqual(summary["excluded_non_active_part_numbers"], 1)
        self.assertTrue(summary["commercial_identity_clean"])
        self.assertTrue(summary["bounded_discovery_clean"])
        self.assertTrue(discovery_is_clean(summary))
        result = next(item for item in summary["results"] if item["base_device"] == lifecycle_base)
        self.assertEqual(result["disposition"], "lifecycle_excluded")
        self.assertEqual(result["commercial_identity_status"], "verified_non_active_only")
        self.assertEqual(result["openocd_routing"]["status"], "not_applicable")

    def test_canonical_404_is_fail_closed_exclusion_not_manual_review(self) -> None:
        unavailable_url = self.targets[0].source_url

        def fetcher(source_url: str, timeout_seconds: float):
            del timeout_seconds
            if source_url == unavailable_url:
                raise AcquisitionError(CANONICAL_PAGE_404)
            return b"<html></html>", source_url, None, None

        summary = run_discovery(
            pilot_id=self.pilot_id,
            targets=self.targets,
            catalog_rows=self.catalog,
            fetcher=fetcher,
            evidence_builder=self.evidence_builder,
        )
        self.assertEqual(summary["acquisition_failure"], 0)
        self.assertEqual(summary["acquisition_success"], MAX_TARGETS - 1)
        self.assertEqual(summary["source_unavailable_exclusions"], 1)
        self.assertEqual(summary["commercial_identity_unresolved_targets"], 1)
        self.assertFalse(summary["commercial_identity_clean"])
        self.assertTrue(summary["bounded_discovery_clean"])
        self.assertEqual(summary["identity_manual_intervention_required"], 0)
        self.assertTrue(discovery_is_clean(summary))
        result = next(item for item in summary["results"] if item["source_url"] == unavailable_url)
        self.assertEqual(result["disposition"], "source_unavailable_excluded")
        self.assertFalse(result["manual_intervention_required"])

    def test_non_404_acquisition_failure_requires_manual_review(self) -> None:
        failed_url = self.targets[0].source_url

        def fetcher(source_url: str, timeout_seconds: float):
            del timeout_seconds
            if source_url == failed_url:
                raise AcquisitionError("synthetic manufacturer evidence failure")
            return b"<html></html>", source_url, None, None

        summary = run_discovery(
            pilot_id=self.pilot_id,
            targets=self.targets,
            catalog_rows=self.catalog,
            fetcher=fetcher,
            evidence_builder=self.evidence_builder,
        )
        self.assertEqual(summary["acquisition_failure"], 1)
        self.assertEqual(summary["identity_manual_intervention_required"], 1)
        self.assertFalse(summary["bounded_discovery_clean"])
        self.assertFalse(discovery_is_clean(summary))

    def test_empty_identity_disposition_requires_manual_review(self) -> None:
        def builder(**kwargs):
            return {
                "base_device": kwargs["base_device"],
                "exact_icpns": [],
                "excluded_non_active_part_numbers": [],
            }

        summary = run_discovery(
            pilot_id=self.pilot_id,
            targets=self.targets,
            catalog_rows=self.catalog,
            fetcher=self.fetcher,
            evidence_builder=builder,
        )
        self.assertEqual(summary["acquisition_failure"], MAX_TARGETS)
        self.assertEqual(summary["identity_manual_intervention_required"], MAX_TARGETS)
        self.assertFalse(discovery_is_clean(summary))

    def test_foreign_exact_icpn_blocks_target(self) -> None:
        def builder(**kwargs):
            return {
                "base_device": kwargs["base_device"],
                "exact_icpns": ["STM32F746BET6"],
                "excluded_non_active_part_numbers": [],
            }

        summary = run_discovery(
            pilot_id=self.pilot_id,
            targets=self.targets,
            catalog_rows=self.catalog,
            fetcher=self.fetcher,
            evidence_builder=builder,
        )
        self.assertGreater(summary["identity_manual_intervention_required"], 0)
        self.assertFalse(discovery_is_clean(summary))

    def test_manifest_target_drift_fails_closed(self) -> None:
        payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        payload["targets"][0]["base_device"] = "STM32F722IE"
        payload["targets"][0]["source_url"] = source_url_for_base("STM32F722IE")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(AcquisitionError, "target selection drifted"):
                read_manifest(path, self.catalog)

    def test_manifest_url_slug_drift_fails_closed(self) -> None:
        payload = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
        payload["targets"][0]["source_url"] = source_url_for_base("STM32F723IC")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(AcquisitionError, "source URL slug mismatch"):
                read_manifest(path, self.catalog)

    def test_claims_remain_false_when_discovery_is_clean(self) -> None:
        summary = run_discovery(
            pilot_id=self.pilot_id,
            targets=self.targets,
            catalog_rows=self.catalog,
            fetcher=self.fetcher,
            evidence_builder=self.evidence_builder,
        )
        self.assertEqual(set(summary["claims"].values()), {False})
        self.assertFalse(summary["claims"]["production_write_authorized"])
        self.assertFalse(summary["claims"]["runtime_support_claimed"])


if __name__ == "__main__":
    unittest.main()
