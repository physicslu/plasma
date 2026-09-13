#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

from st_product_page_acquisition import AcquisitionError
import stm32l1_phase_l1_2_discovery as core
from stm32l1_phase_l1_2_sharded import (
    aggregate_summaries,
    run_discovery_slice,
    select_shard,
    slice_is_clean,
)


class STM32L1PhaseL12ShardedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = core.read_catalog(core.DEFAULT_CATALOG)
        cls.full_targets = core.deterministic_targets(cls.rows)

    @staticmethod
    def fake_fetcher(url: str, timeout_seconds: float):
        assert timeout_seconds > 0
        return b"synthetic", url, None, None

    @staticmethod
    def fake_evidence_builder(**kwargs):
        base = kwargs["base_device"]
        icpn = f"{base}SYNTH"
        record = {"icpn": icpn, "marketing_status": "Active"}
        return {
            "evidence_surface": core.AUTHORITY_SURFACE,
            "exact_icpns": [icpn],
            "excluded_non_active_part_numbers": [],
            "part_number_records": [record],
        }

    def build_summaries(self, shard_count: int = 4):
        summaries = []
        for shard_index in range(shard_count):
            targets = select_shard(
                self.full_targets,
                shard_index=shard_index,
                shard_count=shard_count,
            )
            summary = run_discovery_slice(
                full_targets=self.full_targets,
                targets=targets,
                shard_index=shard_index,
                shard_count=shard_count,
                catalog_rows=self.rows,
                fetcher=self.fake_fetcher,
                evidence_builder=self.fake_evidence_builder,
                timeout_seconds=1.0,
            )
            self.assertTrue(slice_is_clean(summary))
            summaries.append(summary)
        return summaries

    def test_four_shards_partition_full_target_set_exactly_once(self) -> None:
        shards = [
            select_shard(self.full_targets, shard_index=index, shard_count=4)
            for index in range(4)
        ]
        observed = [target.base_device for shard in shards for target in shard]
        expected = [target.base_device for target in self.full_targets]
        self.assertEqual(len(observed), len(set(observed)))
        self.assertEqual(set(observed), set(expected))
        self.assertEqual(len(expected), 59)
        self.assertEqual(sum(len(target.surfaces) for target in self.full_targets), 78)

    def test_synthetic_shards_reconstruct_canonical_clean_summary(self) -> None:
        summary = aggregate_summaries(
            full_targets=self.full_targets,
            summaries=self.build_summaries(),
        )
        self.assertTrue(core.discovery_is_clean(summary))
        self.assertEqual(summary["base_device_count"], 59)
        self.assertEqual(summary["evidence_surface_count"], 78)
        self.assertEqual(summary["parallel_shards"]["count"], 4)
        self.assertTrue(summary["parallel_shards"]["base_device_surfaces_are_atomic"])
        self.assertTrue(summary["representative_continuity_clean"])
        self.assertTrue(all(value is False for value in summary["claims"].values()))

    def test_missing_shard_fails_closed(self) -> None:
        summaries = self.build_summaries()
        with self.assertRaises(AcquisitionError):
            aggregate_summaries(full_targets=self.full_targets, summaries=summaries[:-1])

    def test_duplicate_shard_index_fails_closed(self) -> None:
        summaries = self.build_summaries()
        summaries[-1] = copy.deepcopy(summaries[0])
        with self.assertRaises(AcquisitionError):
            aggregate_summaries(full_targets=self.full_targets, summaries=summaries)

    def test_duplicate_base_across_shards_fails_closed(self) -> None:
        summaries = self.build_summaries()
        summaries[1]["results"].append(copy.deepcopy(summaries[0]["results"][0]))
        summaries[1]["base_device_count"] += 1
        summaries[1]["attempted"] += 1
        summaries[1]["commercial_identity_verified_targets"] += 1
        summaries[1]["active_candidate_targets"] += 1
        summaries[1]["evidence_surface_count"] += summaries[0]["results"][0]["required_surface_count"]
        summaries[1]["surface_attempted"] += summaries[0]["results"][0]["required_surface_count"]
        summaries[1]["surface_success"] += summaries[0]["results"][0]["required_surface_count"]
        with self.assertRaises(AcquisitionError):
            aggregate_summaries(full_targets=self.full_targets, summaries=summaries)


if __name__ == "__main__":
    unittest.main()
