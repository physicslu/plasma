"""NXP LPC81x eight official material Phase1 regression and negative tests."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch
import nxp_phase1_lpc81x_exact_v1 as v1

class NxpLpc81xPhase1Tests(unittest.TestCase):
    def test_eight_materials_replay(self):
        v1.verify()
        rows = v1.build()
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(r["icpn"].startswith("LPC811") for r in rows), 2)
        self.assertEqual(sum(r["icpn"].startswith("LPC812") for r in rows), 6)
        self.assertEqual(len({r["manufacturer_12nc"] for r in rows}), 8)

    def test_packages_voltage_and_base_identity(self):
        rows = v1.build()
        self.assertEqual({r["package"] for r in rows},
                         {"TSSOP16", "TSSOP20", "SO20", "XSON16"})
        for r in rows:
            self.assertEqual((r["working_vdd_min_v"], r["working_vdd_max_v"]),
                             ("1.8", "3.6"))
            self.assertTrue(r["icpn"].startswith(r["manufacturer_base"]))
            self.assertEqual(r["analog_supply_evidence"], v1.ANA)
            self.assertEqual(r["debug_transport"], "SWD")

    def test_fail_closed_on_unreviewed_field_changes(self):
        rows = v1.read()
        old = {r["icpn_observation"]: r for r in v1.prev.build()}
        cases = {
            "flash_kb": "512", "sram_kb": "64",
            "manufacturer_12nc": "935300000000", "manufacturer_base": "LPC800",
            "package": "HVQFN33", "terminal_count": "40",
            "manufacturer_status": "No Longer Manufactured",
            "working_vdd_min_v": "1.7", "working_vdd_max_v": "4.6",
            "temperature_max_c": "125", "debug_transport": "JTAG_ONLY",
            "datasheet_revision": "Rev 1.0",
            "datasheet_power_locator": "Absolute maximum +4.6V",
            "analog_supply_evidence": "Independent VDDA and VREFP",
            "io_supply_evidence": "Independent VDDIO 5V",
            "pinned_openocd_part_id_lead": "SUPPORTED",
            "original_pdf_bytes_archived": "true",
            "original_manufacturer_html_bytes_archived": "true",
            "exact_silicon_revision_verified": "true",
            "programming_qualified": "true",
            "production_admitted": "true", "physical_hil_verified": "true",
            "evidence_scope": "SOFTWARE_SUPPORTED",
        }
        for key, value in cases.items():
            r = copy.deepcopy(rows[0])
            r[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                v1.check(r, old[r["icpn"]])

    def test_prior_openocd_wave4_promotion_rejected(self):
        r = v1.read()[0]
        previous = {x["icpn_observation"]: x for x in v1.prev.build()}
        for field in ("orderable_identity_qualified", "flash_programming_qualified",
                      "production_admitted", "manufacturer_original_bytes_archived"):
            mutated = copy.deepcopy(previous[r["icpn"]])
            mutated[field] = "true"
            with self.subTest(field=field), self.assertRaises(ValueError):
                v1.check(r, mutated)

    def test_csv_blob_source_drift_rejected(self):
        with patch.object(v1, "SOURCE_GIT_BLOB", "0"*40):
            with self.assertRaises(ValueError):
                v1.read()

    def test_unapproved_extra_material_is_rejected(self):
        orig = v1.read()
        modified = copy.deepcopy(orig)
        new = copy.deepcopy(orig[0])
        new["icpn"] = "LPC810M021FN8FP"
        modified.append(new)
        with patch.object(v1, "read", return_value=modified):
            with self.assertRaises(ValueError):
                v1.build()

if __name__ == "__main__":
    unittest.main(verbosity=2)
