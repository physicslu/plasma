"""Safety regression for NXP KL25/K32L2A VDD-relative GPIO evidence, Phase 1 only."""
import copy
import unittest
from unittest.mock import patch

import nxp_phase1_kl25_k32l2a_io_v24 as v24
import nxp_phase1_mcxa_rails_v23 as v23

class TestNxpPhase1KinetisIoV24(unittest.TestCase):
    def test_deterministic_ledger_and_coverage(self):
        v24.verify()

    def test_exact_16_partial_and_no_research_identity_changes(self):
        old = v23.build()
        new = v24.build()
        self.assertEqual(len(old), len(new), 501)
        changes = 0
        for a, b in zip(old, new):
            self.assertEqual(a["icpn"], b["icpn"])
            for name, value in a.items():
                if name in ("io_supply", "io_supply_state") and a["icpn"].startswith(("MKL25Z", "K32L2A")):
                    continue
                self.assertEqual(value, b[name], (a["icpn"], name))
            if a["icpn"].startswith(("MKL25Z", "K32L2A")) and a["identity_state"] == "ADMITTED":
                self.assertEqual(a["io_supply_state"], "UNKNOWN")
                self.assertEqual(b["io_supply_state"], "PARTIAL")
                self.assertIn("VDDIO supply NOT established", b["io_supply"])
                self.assertEqual(b["io_reference_pdf_sha256_v24"], "NOT_ARCHIVED")
                changes += 1
            else:
                self.assertEqual(a["io_supply"], b["io_supply"])
                self.assertEqual(a["io_supply_state"], b["io_supply_state"])
        self.assertEqual(changes, 16)
        s = v24.stats(new)
        self.assertEqual(s["after_admitted"]["fields"]["io_supply"],
                         {"VERIFIED": 119, "PARTIAL": 16, "UNKNOWN": 89, "CONFLICT": 0})
        self.assertIsNone(s["software_programming_supported"])
        self.assertIsNone(s["physical_site_hil_validated"])

    def test_fail_closed_wrong_sku_flash_revision_scope_and_voltage_claim(self):
        original = v24.source_records()
        bad_cases = [
            ("duplicate identity", lambda r: r[1].__setitem__("icpn", r[0]["icpn"])),
            ("wrong flash", lambda r: r[0].__setitem__("original_flash_kb", "9999")),
            ("wrong document", lambda r: r[0].__setitem__("datasheet_id", "EXTERNAL")),
            ("wrong revision", lambda r: r[0].__setitem__("datasheet_revision", "Rev 999")),
            ("wrong operating table", lambda r: r[0].__setitem__("operating_table_locator", "Absolute Maximum")),
            ("unsafe verified", lambda r: r[0].__setitem__("io_supply_evidence_state", "VERIFIED")),
            ("unsupported independent rail", lambda r: r[0].__setitem__("independent_io_rail_established", "YES")),
            ("fabricated pdf hash", lambda r: r[0].__setitem__("original_vendor_pdf_sha256", "abc")),
            ("ratings misread", lambda r: r[0].__setitem__("scope_note", "VIO rating is VDDIO supply")),
            ("unmatched exact ordering code", lambda r: r[0].__setitem__("icpn", "K32L2A41NOTAREALPART")),
        ]
        for label, mutate in bad_cases:
            with self.subTest(label=label):
                altered = copy.deepcopy(original)
                mutate(altered)
                with patch.object(v24, "source_records", return_value=altered):
                    with self.assertRaises(ValueError):
                        v24.build()

if __name__ == "__main__":
    unittest.main()
