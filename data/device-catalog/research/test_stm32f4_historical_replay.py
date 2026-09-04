#!/usr/bin/env python3
from __future__ import annotations

import unittest

from stm32f4_historical_replay import admitted_after_phase42


def row(phase: str) -> dict[str, str]:
    return {
        "source_reference": (
            "https://www.st.com/example#plasma-evidence="
            f"stm32f4-phase4.2{phase}-bounded-retained"
        )
    }


class STM32F4HistoricalReplayTests(unittest.TestCase):
    def test_single_letter_phase_order_is_preserved(self) -> None:
        self.assertFalse(admitted_after_phase42(row("f"), "f"))
        self.assertTrue(admitted_after_phase42(row("g"), "f"))
        self.assertFalse(admitted_after_phase42(row("e"), "f"))

    def test_phase_order_continues_from_z_to_aa(self) -> None:
        self.assertFalse(admitted_after_phase42(row("z"), "z"))
        self.assertTrue(admitted_after_phase42(row("aa"), "z"))
        self.assertFalse(admitted_after_phase42(row("z"), "aa"))
        self.assertFalse(admitted_after_phase42(row("aa"), "aa"))
        self.assertTrue(admitted_after_phase42(row("ab"), "aa"))

    def test_unrelated_evidence_is_not_treated_as_a_phase_admission(self) -> None:
        self.assertFalse(admitted_after_phase42({"source_reference": "https://example.invalid"}, "f"))

    def test_invalid_cutoff_fails_closed(self) -> None:
        for cutoff in ("", "a1", "a-a"):
            with self.subTest(cutoff=cutoff):
                with self.assertRaises(ValueError):
                    admitted_after_phase42(row("aa"), cutoff)


if __name__ == "__main__":
    unittest.main()
