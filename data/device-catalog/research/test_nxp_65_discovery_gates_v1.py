"""NXP ADR-0002: fail closed on research-only OpenOCD wave consolidation."""
from __future__ import annotations

import copy
import unittest
from collections import Counter
from unittest.mock import patch

import nxp_65_discovery_gates_v1 as v1


class Nxp65DiscoveryGatesTests(unittest.TestCase):
    def test_65_exact_observations_are_disjoint_and_replay(self):
        v1.verify()
        rows = v1.build()
        self.assertEqual(len(rows), 65)
        self.assertEqual(Counter(r["priority_lead"] for r in rows),
                         {"P0": 60, "P1": 5})
        self.assertEqual(Counter(r["wave"] for r in rows),
                         {"2": 27, "3": 18, "4": 20})
        self.assertTrue(all(r["openocd_source_commit"] == v1.UPSTREAM for r in rows))
        self.assertTrue(all(r["orderable_identity_qualified"] == "false"
                            and r["production_admitted"] == "false"
                            and r["flash_programming_qualified"] == "false"
                            and r["manufacturer_original_bytes_archived"] == "false"
                            for r in rows))

    def test_all_three_jtag_leads_preserve_transport_boundary(self):
        rows = v1.build()
        self.assertEqual(
            {r["icpn_observation"] for r in rows if
             r["transport_gate"] == "JTAG_ROUTE_NOT_SWD_VERIFIED"},
            {"LPC2148FBD64", "LPC2378FBD144", "LPC2378FBD144K"})
        self.assertTrue(all(r["hardware_validation_qualified"] == "false"
                            for r in rows))

    def test_product_lifecycle_and_display_code_not_promoted(self):
        rows = {r["icpn_observation"]: r for r in v1.build()}
        self.assertEqual(rows["LPC1769FBD100"]["next_research_gate"],
                         "PRODUCT_ACTIVE_ONLY_MATERIAL_UNVERIFIED")
        self.assertEqual(rows["LPC2148FBD64"]["next_research_gate"],
                         "MIXED_MATERIAL_LIFECYCLE_AND_JTAG")
        self.assertEqual(rows["LPC1114FBD48/333J"]["next_research_gate"],
                         "RAW_DISPLAY_CODE_ORDERING_NORMALIZATION")
        self.assertEqual(rows["LPC11U24FHI33/301Y"]["next_research_gate"],
                         "RAW_DISPLAY_CODE_ORDERING_NORMALIZATION")

    def test_block_false_source_promotion(self):
        for wave, filename, sha, _ in v1.WAVES:
            source = v1.read_json(filename, sha)
            original = source["records"][0]
            changed = copy.deepcopy(original)
            col = {2: "openocd_software_supported",
                   3: "software_supported",
                   4: "flash_programming_qualified"}[wave]
            changed[col] = True
            with self.subTest(wave=wave):
                with self.assertRaises(ValueError):
                    v1.classify(wave, changed, filename)

    def test_block_lifecycle_and_material_scope_upgrade(self):
        _, f3, h3, _ = v1.WAVES[1]
        _, f4, h4, _ = v1.WAVES[2]
        w3 = v1.read_json(f3, h3)["records"]
        w4 = v1.read_json(f4, h4)["records"]
        mixed = copy.deepcopy(next(x for x in w3
                                   if x["icpn"] == "LPC2148FBD64"))
        mixed["qualifying_gap"] = "every part Active"
        with self.assertRaises(ValueError):
            v1.classify(3, mixed, f3)
        product = copy.deepcopy(next(x for x in w4
                                     if x["icpn"] == "LPC1769FBD100"))
        product["manufacturer_evidence_scope"] = "MATERIAL_ACTIVE"
        with self.assertRaises(ValueError):
            v1.classify(4, product, f4)

    def test_source_custody_git_lock_is_real(self):
        with self.assertRaises(ValueError):
            v1.locked_bytes(v1.WAVES[0][1], "0" * 40)

    def test_detects_stale_csv(self):
        class Fake:
            def read_bytes(self):
                return b"not a valid replay"
        with patch.object(v1, "LEDGER", Fake()):
            with self.assertRaises(ValueError):
                v1.verify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
