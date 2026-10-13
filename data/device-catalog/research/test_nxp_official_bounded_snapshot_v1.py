#!/usr/bin/env python3
"""Frozen research-only NXP bounded manufacturer source snapshot contract."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "nxp-official-bounded-snapshot-2026-10-13-v1.json"
REGISTRY = HERE / "nxp-official-pilot-products-v1.json"
KL25_CSV = HERE / "nxp-kl25-commercial-icpn.csv"


def exact_set_hash(names: set[str]) -> str:
    return hashlib.sha256("".join(x + "\n" for x in sorted(names)).encode("utf-8")).hexdigest()


class BoundedSnapshotContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        cls.r = json.loads(REGISTRY.read_text(encoding="utf-8"))
        cls.report = cls.s["reconciliation"]

    def test_source_population_remains_bounded_and_not_authorized(self):
        self.assertEqual(self.s["authority"], "read_only_manufacturer_evidence_observation")
        self.assertFalse(self.s["scope_limits"]["source_population_complete"])
        self.assertFalse(self.s["scope_limits"]["production_publication_authorized"])
        self.assertFalse(self.s["scope_limits"]["production_admission_ready"])
        self.assertFalse(self.s["scope_limits"]["runtime_programming_qualified"])
        self.assertIsNone(self.s["scope_limits"]["global_nxp_active_denominator"])
        self.assertIsNone(self.s["scope_limits"]["global_nxp_active_coverage"])
        self.assertIsNone(self.report["global_active_denominator"])
        self.assertIsNone(self.report["global_active_coverage"])
        self.assertFalse(self.report["global_portfolio_complete"])
        self.assertFalse(self.report["claims"]["production_write_authorized"])
        self.assertFalse(self.report["claims"]["runtime_programming_support_claimed"])
        self.assertFalse(self.report["claims"]["physical_validation_claimed"])

    def test_frozen_exact_active_and_other_lifecycle_sets(self):
        p = self.report
        active = p["observed_active_icpns"]
        qualification = p["observed_qualification_icpns"]
        self.assertEqual(len(active), 353)
        self.assertEqual(len(active), len(set(active)))
        self.assertEqual(active, sorted(active))
        self.assertEqual(len(qualification), 2)
        self.assertEqual(len(qualification), len(set(qualification)))
        self.assertTrue(set(active).isdisjoint(qualification))
        self.assertEqual(p["observed_unique_exact"], 368)
        self.assertEqual(p["observed_active_exact"], 353)
        self.assertEqual(p["observed_qualification_exact"], 2)
        self.assertEqual(p["observed_other_lifecycle_exact"], 13)
        other = p["observed_other_lifecycle_icpns"]
        self.assertEqual(len(other), 13)
        self.assertEqual([r["icpn"] for r in other],
                         sorted(r["icpn"] for r in other))
        self.assertEqual(len({r["icpn"] for r in other}), 13)
        self.assertEqual(
            {r["lifecycle"] for r in other},
            {"NRND", "No Longer Manufactured"},
        )
        self.assertEqual(
            sum(r["lifecycle"] == "NRND" for r in other), 12,
        )
        self.assertEqual(
            sum(r["lifecycle"] == "No Longer Manufactured" for r in other), 1,
        )
        self.assertTrue(set(active).isdisjoint(r["icpn"] for r in other))
        self.assertTrue(set(qualification).isdisjoint(r["icpn"] for r in other))
        self.assertEqual(
            len(set(active) | set(qualification) |
                {r["icpn"] for r in other}), 368,
        )

        self.assertEqual(p["observed_active_missing_from_production"], 353)
        self.assertTrue(all(re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]{3,63}", x) for x in active))
        self.assertEqual(
            exact_set_hash(set(active)),
            "8d25ee58d833b69d9d6b6bc68bd20d11090c33c543e606507b95ce667267eb24",
        )
        self.assertEqual(p["observed_active_exact_set_sha256"], exact_set_hash(set(active)))

    def test_snapshot_source_pages_match_current_pinned_source_list(self):
        pages = self.report["source_pages"]
        ids = {p["id"] for p in self.r["products"]}
        self.assertEqual(self.report["official_product_page_count"], 23)
        self.assertEqual(len(ids), 23)
        self.assertEqual({p["product"] for p in pages}, ids)
        self.assertEqual(len(pages), len(ids))
        self.assertEqual(sum(p["page_exact_count"] for p in pages), 368)
        self.assertEqual(sum(p["page_active_count"] for p in pages), 353)
        self.assertEqual(sum(p["page_qualification_count"] for p in pages), 2)
        by_id = {p["id"]: p for p in self.r["products"]}
        for page in pages:
            self.assertEqual(page["segment"], by_id[page["product"]]["segment"])
            self.assertFalse(page["complete_manufacturer_denominator"])
            self.assertRegex(page["raw_dom_sha256"], r"^[a-f0-9]{64}$")
            self.assertGreaterEqual(
                page["page_exact_count"],
                page["page_active_count"] + page["page_qualification_count"],
            )
        self.assertFalse(self.r["global_active_denominator_claimed"])
        self.assertFalse(self.r["production_write_authorized"])

    def test_kl25_frozen_exact_twelve_are_observed_active(self):
        with KL25_CSV.open(encoding="utf-8", newline="") as stream:
            names = [r["icpn"] for r in csv.DictReader(stream)]
        self.assertEqual(len(names), 12)
        self.assertEqual(len(set(names)), 12)
        self.assertTrue(set(names).issubset(set(self.report["observed_active_icpns"])))
        self.assertEqual(self.report["locked_kl25_exact_pilot"], 12)

    def test_two_independent_runs_agree_on_exact_active_set(self):
        first = self.s["captured_from"]
        second = self.s["independent_replay"]
        self.assertNotEqual(first["workflow_run_id"], second["workflow_run_id"])
        self.assertNotEqual(first["producing_commit_sha"], second["producing_commit_sha"])
        self.assertRegex(first["producing_commit_sha"], r"^[a-f0-9]{40}$")
        self.assertRegex(second["producing_commit_sha"], r"^[a-f0-9]{40}$")
        self.assertEqual(second["observed_active_exact"], 353)
        self.assertEqual(second["observed_unique_exact"], 368)
        self.assertEqual(second["observed_active_exact_set_sha256"],
                         self.report["observed_active_exact_set_sha256"])
        self.assertTrue(second["all_product_acquisition_jobs_passed"])
        self.assertTrue(second["bounded_reconciliation_passed"])
        first_prior = self.s["prior_replay"]
        self.assertNotEqual(first_prior["workflow_run_id"], first["workflow_run_id"])
        self.assertNotEqual(first_prior["workflow_run_id"], second["workflow_run_id"])
        self.assertEqual(first_prior["workflow_run_id"], 38333219588)
        self.assertEqual(first["workflow_run_id"], 38334514193)



if __name__ == "__main__":
    unittest.main()
