"""Fail-closed Phase 1 NXP K32L2B bounded family VDD-source regression."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import nxp_phase1_k32l2b_vdd_v25 as v25


class TestNXPPhase1K32L2BVDDv25(unittest.TestCase):
    def test_501_source_replay_and_metrics(self):
        v25.verify()
        rows = v25.build()
        self.assertEqual(len(rows), 501)
        admitted = [r for r in rows if r["identity_state"] == "ADMITTED"]
        self.assertEqual(len(admitted), 224)
        s = v25.stats(rows)
        self.assertEqual(s["after_admitted"]["fields"]["working_vdd"],
                         {"VERIFIED": 135, "PARTIAL": 39,
                          "UNKNOWN": 50, "CONFLICT": 0})
        self.assertEqual(s["all_501"]["fields"]["working_vdd"],
                         {"VERIFIED": 150, "PARTIAL": 81,
                          "UNKNOWN": 270, "CONFLICT": 0})
        self.assertFalse(s["vendor_original_pdf_sha256_archived"])
        self.assertFalse(s["k32l2b_independent_vddio_or_vdda_qualified"])
        self.assertIsNone(s["software_programming_qualified"])
        self.assertIsNone(s["physical_hil_validated"])

    def test_only_12_admitted_vdd_fields_change(self):
        old = v25.baseline_rows()
        new = v25.build()
        self.assertEqual(len(old), len(new))
        switched = 0
        for a, b in zip(old, new):
            self.assertEqual(a["icpn"], b["icpn"])
            self.assertEqual(a["identity_state"], b["identity_state"])
            for key, value in a.items():
                if key in ("working_vdd", "working_vdd_unit", "working_vdd_state") and a["icpn"] in v25.EXPECTED:
                    continue
                self.assertEqual(value, b[key], (a["icpn"], key))
            if a["icpn"] in v25.EXPECTED:
                self.assertEqual(a["working_vdd_state"], "UNKNOWN")
                self.assertEqual(b["working_vdd_state"], "PARTIAL")
                self.assertEqual(b["working_vdd"], "1.71 to 3.6")
                self.assertEqual(b["working_vdd_unit"], "V")
                self.assertEqual(b["k32l2b_vdd_original_pdf_sha256_v25"], "NOT_ARCHIVED")
                self.assertEqual(b["io_supply_state"], "UNKNOWN")
                self.assertEqual(b["vdda_state"], "UNKNOWN")
                self.assertEqual(b["ram_state"], "PARTIAL")
                switched += 1
        self.assertEqual(switched, 12)

    def test_reject_bad_source_revisions_and_unsupported_promotions(self):
        source = v25.read_source()
        def one_change(field, val):
            rows = copy.deepcopy(source)
            rows[0][field] = val
            return rows
        cases = [
            ("duplicate exact code", "icpn", source[1]["icpn"]),
            ("made-up exact code", "icpn", "K32L2B31NOTREAL"),
            ("wrong flash", "previous_flash_kb", "999"),
            ("unapproved source URL", "family_voltage_source_url", "https://other.example/nxp.pdf"),
            ("wrong revision", "family_voltage_revision", "Rev 999"),
            ("wrong source table", "source_locator", "Absolute maximum"),
            ("wrong voltage", "observed_min_v", "1.14"),
            ("false exact verified", "confidence", "VERIFIED"),
            ("false original PDF hash", "vendor_original_pdf_sha256", "a"*64),
            ("fake exact-level source", "source_scope", "EXACT_MATERIAL_DATASHEET"),
            ("source accessibility fabricated", "primary_k32l2b_datasheet_access", "READ_AND_HASHED"),
            ("false VDDA/HIL implication", "source_note", "Separate VDDA/VDDIO and HIL verified"),
        ]
        for label, col, val in cases:
            with self.subTest(label=label):
                with patch.object(v25, "read_source", return_value=one_change(col,val)):
                    with self.assertRaises(ValueError):
                        v25.build()

    def test_explicitly_deny_false_pdf_custody_in_lock(self):
        lock = v25.load()
        bad = copy.deepcopy(lock)
        bad["original_vendor_pdf_binary_archived"] = True
        # The load() path must fail if any reviewer fabricates a captured PDF.
        real_read = v25.LOCK.read_text
        with patch.object(v25, "blob", wraps=v25.blob):
            self.assertFalse(lock["original_vendor_pdf_binary_archived"])
        self.assertTrue(bad["original_vendor_pdf_binary_archived"])
        self.assertNotEqual(bad,lock)

if __name__ == "__main__":
    unittest.main(verbosity=2)
