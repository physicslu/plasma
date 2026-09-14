#!/usr/bin/env python3

import json
import unittest
from pathlib import Path

from stm32_trustzone_cohort_qualification import build_qualification

ROOT = Path(__file__).resolve().parent
FROZEN = ROOT / "stm32-trustzone-cohort-gate1-qualification.json"


class TrustZoneCohortQualificationTests(unittest.TestCase):
    def test_frozen_qualification_matches_generator(self):
        expected = json.loads(FROZEN.read_text(encoding="utf-8"))
        self.assertEqual(build_qualification(), expected)

    def test_scope_is_bounded_and_deterministic(self):
        result = build_qualification()
        self.assertEqual(result["authority"], "research_only")
        self.assertEqual(
            [item["plasma_series"] for item in result["candidates"]],
            ["STM32L5", "STM32U3", "STM32U5"],
        )
        self.assertEqual([item["rank"] for item in result["candidates"]], [1, 2, 3])
        self.assertEqual(result["selected_for_next_research"], "STM32L5")
        self.assertTrue(all(not item["legacy_standard_shortlist_eligible"] for item in result["candidates"]))

    def test_no_support_or_production_claims(self):
        claims = build_qualification()["claims"]
        self.assertTrue(claims)
        self.assertTrue(all(value is False for value in claims.values()))


if __name__ == "__main__":
    unittest.main()
