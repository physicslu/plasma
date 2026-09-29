"""Fail-closed tests of bounded ST commercial observation parsing."""
from __future__ import annotations
import unittest
from pathlib import Path
import validate_st_bounded_commercial_gap as audit

class OfficialRowIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid = audit.SOURCE.read_text(encoding="utf-8")

    def fails(self, source):
        with self.assertRaises(ValueError):
            audit.parse_csv_text(source)

    def test_frozen_bounded_observations(self):
        observations = audit.parse_csv_text(self.valid)
        self.assertEqual(20, len(observations))
        self.assertEqual(5, len({r["family"] for r in observations}))
        self.assertTrue(all(r["marketing_status"] == "Active" for r in observations))

    def test_duplicate(self):
        self.fails(self.valid + self.valid.splitlines()[1] + "\n")

    def test_unreviewed_pattern_cannot_be_expanded(self):
        self.fails(self.valid.replace("STM32H503CBT6,", "STM32H503CBTx,"))

    def test_wrong_lifecycle_fail_closed(self):
        self.fails(self.valid.replace("STM32N657A0H3Q,Active,", "STM32N657A0H3Q,NRND,"))

    def test_official_source_provenance(self):
        self.fails(self.valid.replace("www.st.com", "untrusted.example.com", 1))

    def test_missing_old_sentinel(self):
        self.fails(self.valid.replace(
            next(line + "\n" for line in self.valid.splitlines() if ",STM32WL33CCV6," in line),
            "",
        ))

    def test_c5_must_be_estore_same_row_not_mx1_pattern(self):
        self.fails(self.valid.replace(audit.OFFICIAL_URLS["STM32C5"],
                                      audit.OFFICIAL_URLS["STM32H5"]))

if __name__ == "__main__":
    unittest.main()
