"""Negative evidence, identity and rail-safety tests for NXP Phase 1 v26."""
from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import nxp_phase1_mcxn_rails_v26 as v26


class TestNxpPhase1MCXNRailsV26(unittest.TestCase):
    def test_exact_31_and_deterministic_501(self):
        v26.verify()
        rows = v26.build()
        s = v26.stats(rows)
        self.assertEqual(len(rows), 501)
        self.assertEqual(s["exact_official_ordering_rail_joins"], 31)
        self.assertEqual(s["document_exact_counts"],
                         {"MCXN23x": 6, "MCXNP184M150F70": 25})
        self.assertFalse(s["source_pdf_original_bytes_archived"])
        self.assertEqual(s["software_supported_promotions"], 0)
        self.assertEqual(s["production_or_hil_promotions"], 0)
        self.assertEqual(s["after_admitted"]["fields"]["working_vdd"],
                         {"VERIFIED": 166, "PARTIAL": 39,
                          "UNKNOWN": 19, "CONFLICT": 0})
        self.assertEqual(s["after_admitted"]["fields"]["vdda"],
                         {"VERIFIED": 166, "PARTIAL": 0,
                          "UNKNOWN": 58, "CONFLICT": 0})
        self.assertEqual(s["after_admitted"]["fields"]["io_supply"],
                         {"VERIFIED": 150, "PARTIAL": 16,
                          "UNKNOWN": 58, "CONFLICT": 0})

    def test_only_three_normal_rails_per_existing_mcxn(self):
        old = v26.baseline_rows()
        new = v26.build()
        selected = 0
        for a, b in zip(old, new):
            self.assertEqual(a["icpn"], b["icpn"])
            for key, value in a.items():
                if key in v26.CHANGED and a["icpn"].startswith("MCXN"):
                    continue
                self.assertEqual(value, b[key], (a["icpn"], key))
            if a["icpn"].startswith("MCXN") and a["identity_state"] == "ADMITTED":
                selected += 1
                self.assertEqual(b["working_vdd_state"], "VERIFIED")
                self.assertEqual(b["io_supply_state"], "VERIFIED")
                self.assertEqual(b["vdda_state"], "VERIFIED")
                self.assertEqual(b["working_vdd"], "1.71 to 3.6")
                self.assertIn("restricted", b["io_supply"])
                self.assertIn("VDD_P4", b["vdda"])
                self.assertEqual(b["mcxn_source_pdf_sha256_v26"], "NOT_ARCHIVED")
            else:
                for field in v26.CHANGED:
                    self.assertEqual(a[field], b[field], (a["icpn"], field))
        self.assertEqual(selected, 31)

    def test_reject_unauthorized_source_mutations(self):
        src = v26.read(v26.SOURCE)
        def mutate(key, value):
            cp = copy.deepcopy(src)
            cp[0][key] = value
            return cp
        cases = [
            ("duplicate SKU", "icpn", src[1]["icpn"]),
            ("new invented identity", "icpn", "MCXN235FAKE"),
            ("bad Flash", "existing_flash_kb", "9999"),
            ("wrong source family", "source_document", "MCXE31FS"),
            ("wrong datasheet revision", "source_revision", "Rev 999"),
            ("rating instead of operating", "rail_operating_table_locator",
             "Table 8 absolute max"),
            ("IO 1.2V unconditional", "io_rail_description",
             "P0/P1/P2/P3/P4 all normal 1.2V"),
            ("VDDA independent", "analog_rail_description",
             "VDD_ANA independent 1.14V"),
            ("fuse high voltage generalized", "vdd_sys_mode_description",
             "VDD_SYS always 2.75V"),
            ("fake manufacturer PDF SHA", "original_vendor_pdf_sha256",
             "a" * 64),
            ("unearned source scope", "source_scope",
             "PER_MATERIAL_OPERATING_RAIL_MEASURED"),
            ("false software authorization", "document_limit",
             "SUPPORTED and HIL PASSED"),
        ]
        for label, field, value in cases:
            with self.subTest(label=label):
                prior = v26.read
                def fake(path):
                    return mutate(field, value) if path == v26.SOURCE else prior(path)
                with patch.object(v26, "read", side_effect=fake):
                    with self.assertRaises(ValueError):
                        v26.build()

    def test_reject_lock_false_original_pdf_and_software_authorization(self):
        lock = v26.load()
        for key, val in (
            ("original_official_pdf_archive", True),
            ("original_official_pdf_sha256", "b" * 64),
            ("software_supported_promoted", True),
            ("production_or_hardware_changed", True),
            ("expected_field_state", "PARTIAL"),
        ):
            with self.subTest(key=key):
                forged = copy.deepcopy(lock)
                forged[key] = val
                fake_file = SimpleNamespace(
                    read_text=lambda encoding="utf-8": json.dumps(forged))
                with patch.object(v26, "LOCK", fake_file):
                    with self.assertRaises(ValueError):
                        v26.load()

    def test_reject_wrong_scope_or_changed_exact_54_source_sha(self):
        lock = v26.load()
        for field in ("official_31_source_git_blob",
                      "frozen_v21_exact_54_git_blob",
                      "frozen_prior_501_v25_git_blob"):
            with self.subTest(field=field):
                forged = copy.deepcopy(lock)
                forged[field] = "0" * 40
                fake_file = SimpleNamespace(
                    read_text=lambda encoding="utf-8": json.dumps(forged))
                with patch.object(v26, "LOCK", fake_file):
                    with self.assertRaises(ValueError):
                        v26.load()


if __name__ == "__main__":
    unittest.main(verbosity=2)
