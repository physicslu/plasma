"""NXP LPC822/824 eight exact source crosswalk: negative and invariance checks."""
from __future__ import annotations
import copy
import unittest
from unittest.mock import patch
import nxp_phase1_lpc82x_exact_v1 as v1


class Lpc82xPhase1EvidenceTest(unittest.TestCase):
    def test_exact_eight_source_replay(self):
        v1.verify()
        rows = v1.build()
        self.assertEqual(len(rows), 8)
        self.assertEqual(sum(x["icpn"].startswith("LPC822") for x in rows), 4)
        self.assertEqual(sum(x["icpn"].startswith("LPC824") for x in rows), 4)

    def test_12nc_and_package_specific_identity(self):
        rows = v1.build()
        self.assertEqual(len({r["manufacturer_12nc"] for r in rows}), 8)
        self.assertEqual({r["datasheet_package"] for r in rows},
                         {"TSSOP20", "HVQFN33"})
        for r in rows:
            if r["datasheet_package"] == "HVQFN33":
                self.assertEqual(r["nxp_product_package_alias"], "HVQFN32")
                self.assertEqual(r["datasheet_electrical_terminals"], "33")
            else:
                self.assertEqual(r["datasheet_electrical_terminals"], "20")

    def test_supply_and_reference_are_not_conflated(self):
        rows = v1.build()
        self.assertEqual({(r["normal_vdd_min_v"], r["normal_vdd_max_v"])
                          for r in rows}, {("1.8", "3.6")})
        self.assertTrue(all("not an analog supply" in r["vrefp_scope"]
                            for r in rows))
        self.assertTrue(all("separate VDDA not evidenced" in
                            r["analog_supply_domain"] for r in rows))

    def test_fail_closed_on_field_mutations(self):
        originals = v1.read()
        base = {r["icpn_observation"]: r for r in v1.baseline.build()}
        mutations = [
            ("flash_kb", "512"), ("sram_kb", "64"),
            ("manufacturer_12nc", "935300000000"),
            ("normal_vdd_min_v", "1.7"),
            ("normal_vdd_max_v", "5.5"),
            ("temperature_max_c", "125"),
            ("datasheet_package", "HVQFN32"),
            ("datasheet_revision", "Rev 1.0"),
            ("manufacturer_material_status", "No Longer Manufactured"),
            ("io_supply_domain", "independent VDDIO 5.5V"),
            ("analog_supply_domain", "separate VDDA"),
            ("vrefp_scope", "VREFP is VDDA"),
            ("original_datasheet_pdf_binary_archived", "true"),
            ("original_material_html_binary_archived", "true"),
            ("ordering_to_silicon_part_id_verified", "true"),
            ("openocd_programming_qualified", "true"),
            ("production_admitted", "true"),
            ("physical_hil_verified", "true"),
        ]
        for field, value in mutations:
            modified = copy.deepcopy(originals[1])
            modified[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                v1.check_one(modified, base[modified["icpn"]])

    def test_source_hash_drift_rejected(self):
        with patch.object(v1, "SOURCE_GIT_BLOB", "0" * 40):
            with self.assertRaises(ValueError):
                v1.read()

    def test_original_wave3_source_promotion_rejected(self):
        rows = v1.read()
        base = {r["icpn_observation"]: r for r in v1.baseline.build()}
        row = rows[0]
        original = copy.deepcopy(base[row["icpn"]])
        for field in ("orderable_identity_qualified",
                      "flash_programming_qualified", "production_admitted"):
            altered = copy.deepcopy(original)
            altered[field] = "true"
            with self.subTest(field=field), self.assertRaises(ValueError):
                v1.check_one(row, altered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
