#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

from st_product_page_acquisition import AcquisitionError
from stm32c0_phase_c0_2_discovery import (
    AUTHORITY_SURFACE,
    EXPECTED_C0_1_REPRESENTATIVES,
    EXPECTED_SUBFAMILIES,
    RateLimitedFetcher,
    deterministic_targets,
    discovery_is_clean,
    read_catalog,
    run_discovery,
    target_manifest,
)


class STM32C0C02DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_catalog()
        cls.targets = deterministic_targets(cls.rows)

    def test_deterministic_targets_are_complete_bounded_unique_surface(self) -> None:
        bases = [target.base_device for target in self.targets]
        self.assertGreater(len(bases), 6)
        self.assertLessEqual(len(bases), 73)
        self.assertEqual(len(bases), len(set(bases)))
        self.assertEqual({target.subfamily for target in self.targets}, set(EXPECTED_SUBFAMILIES))
        self.assertTrue(EXPECTED_C0_1_REPRESENTATIVES.issubset(set(bases)))
        self.assertTrue(all(target.source_url.endswith(f"/{target.base_device.lower()}.html") for target in self.targets))

    def test_target_manifest_is_research_only_and_deterministic(self) -> None:
        first = target_manifest(self.targets)
        second = target_manifest(deterministic_targets(read_catalog()))
        self.assertEqual(first, second)
        self.assertEqual(first["phase"], "C0.2")
        self.assertEqual(first["family"], "STM32C0")
        self.assertEqual(first["base_device_count"], len(self.targets))
        self.assertTrue(first["claims"])
        self.assertTrue(all(value is False for value in first["claims"].values()))

    def test_rate_limit_cannot_be_weakened_below_one_second(self) -> None:
        with self.assertRaises(AcquisitionError):
            RateLimitedFetcher(delay_seconds=0.99, fetcher=lambda _url, _timeout: (b"", "", None, None))

    def _active_evidence(self, *, base_device: str, **_kwargs: object) -> dict[str, object]:
        return {
            "schema_version": 1,
            "base_device": base_device,
            "evidence_surface": AUTHORITY_SURFACE,
            "exact_icpns": [base_device + "T6"],
            "excluded_non_active_part_numbers": [],
        }

    @staticmethod
    def _fetch(url: str, _timeout: float) -> tuple[bytes, str, None, None]:
        return b"synthetic", url, None, None

    def test_synthetic_all_active_discovery_closes_without_route_gate(self) -> None:
        summary = run_discovery(
            targets=self.targets,
            catalog_rows=self.rows,
            fetcher=self._fetch,
            evidence_builder=self._active_evidence,
        )
        self.assertTrue(discovery_is_clean(summary))
        self.assertEqual(summary["attempted"], len(self.targets))
        self.assertEqual(summary["active_candidate_targets"], len(self.targets))
        self.assertEqual(summary["active_exact_icpn_candidates"], len(self.targets))
        self.assertTrue(summary["representative_continuity_clean"])
        self.assertFalse(summary["openocd_routing"]["gates_commercial_identity"])
        self.assertTrue(all(value is False for value in summary["claims"].values()))

    def test_manual_review_blocks_discovery(self) -> None:
        bad_base = self.targets[-1].base_device

        def builder(*, base_device: str, **kwargs: object) -> dict[str, object]:
            if base_device == bad_base:
                raise AcquisitionError("synthetic schema mismatch")
            return self._active_evidence(base_device=base_device, **kwargs)

        summary = run_discovery(
            targets=self.targets,
            catalog_rows=self.rows,
            fetcher=self._fetch,
            evidence_builder=builder,
        )
        self.assertFalse(discovery_is_clean(summary))
        self.assertEqual(summary["identity_manual_intervention_required"], 1)
        self.assertEqual(summary["acquisition_failure"], 1)

    def test_source_unavailable_is_dispositioned_but_not_clean(self) -> None:
        bad_base = self.targets[-1].base_device

        def fetch(url: str, timeout: float) -> tuple[bytes, str, None, None]:
            if bad_base.lower() in url:
                raise AcquisitionError("browser navigation returned HTTP 404")
            return self._fetch(url, timeout)

        summary = run_discovery(
            targets=self.targets,
            catalog_rows=self.rows,
            fetcher=fetch,
            evidence_builder=self._active_evidence,
        )
        self.assertFalse(discovery_is_clean(summary))
        self.assertEqual(summary["source_unavailable_exclusions"], 1)
        self.assertEqual(summary["identity_manual_intervention_required"], 0)

    def test_lifecycle_only_nonrepresentative_target_can_be_cleanly_dispositioned(self) -> None:
        lifecycle_base = next(
            target.base_device for target in reversed(self.targets)
            if target.base_device not in EXPECTED_C0_1_REPRESENTATIVES
        )

        def builder(*, base_device: str, **kwargs: object) -> dict[str, object]:
            if base_device == lifecycle_base:
                return {
                    "schema_version": 1,
                    "base_device": base_device,
                    "evidence_surface": AUTHORITY_SURFACE,
                    "exact_icpns": [],
                    "excluded_non_active_part_numbers": [
                        {"icpn": base_device + "T6", "marketing_status": "Obsolete Product"}
                    ],
                }
            return self._active_evidence(base_device=base_device, **kwargs)

        summary = run_discovery(
            targets=self.targets,
            catalog_rows=self.rows,
            fetcher=self._fetch,
            evidence_builder=builder,
        )
        self.assertTrue(discovery_is_clean(summary))
        self.assertEqual(summary["lifecycle_excluded_targets"], 1)
        self.assertEqual(summary["active_candidate_targets"], len(self.targets) - 1)

    def test_representative_lifecycle_regression_blocks_continuity(self) -> None:
        lifecycle_base = sorted(EXPECTED_C0_1_REPRESENTATIVES)[0]

        def builder(*, base_device: str, **kwargs: object) -> dict[str, object]:
            if base_device == lifecycle_base:
                return {
                    "schema_version": 1,
                    "base_device": base_device,
                    "evidence_surface": AUTHORITY_SURFACE,
                    "exact_icpns": [],
                    "excluded_non_active_part_numbers": [
                        {"icpn": base_device + "T6", "marketing_status": "Obsolete Product"}
                    ],
                }
            return self._active_evidence(base_device=base_device, **kwargs)

        summary = run_discovery(
            targets=self.targets,
            catalog_rows=self.rows,
            fetcher=self._fetch,
            evidence_builder=builder,
        )
        self.assertFalse(discovery_is_clean(summary))
        self.assertFalse(summary["representative_continuity_clean"])

    def test_duplicate_target_is_rejected(self) -> None:
        targets = list(self.targets) + [copy.copy(self.targets[0])]
        with self.assertRaises(AcquisitionError):
            target_manifest(targets)


if __name__ == "__main__":
    unittest.main()
