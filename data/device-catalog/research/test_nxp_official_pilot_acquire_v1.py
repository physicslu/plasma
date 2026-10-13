#!/usr/bin/env python3
"""Bounded source parser regression; does not simulate live acquisition."""
import importlib.util
import json
import re
import unittest
from pathlib import Path

SRC = Path(__file__).with_name("nxp_official_pilot_acquire_v1.py")
spec = importlib.util.spec_from_file_location("nxp_live_pilot", SRC)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class LivePilotParserTest(unittest.TestCase):
    def test_mcx_active_ordering_code(self):
        self.assertEqual(module.exact_code("MCXC041VFK\nPackage : HUQFN24\nMCXC041VFK", "MCXC"), "MCXC041VFK")
        self.assertEqual(module.lifecycle("MCXC041VFK (935463794557) Active Yes Yes"), "Active")
    def test_nxp_qualification_not_active(self):
        self.assertEqual(module.lifecycle("MCXN236VNLT Qualification Yes"), "Qualification")
        self.assertNotEqual(module.lifecycle("MCXN236VNLT Qualification Yes"), "Active")
    def test_kl25_exact_code(self):
        self.assertEqual(module.exact_code("MKL25Z128VLK4 Package LQFP80", "MKL25Z"), "MKL25Z128VLK4")
    def test_grouped_material_declaration_variant_is_not_lost(self):
        # NXP MCX-C04x: group label MCXC041VFK, orderable variant MCXC041VFKR.
        row = ["MCXC041VFK\nPackage : HUQFN24", "MCXC041VFKR\n(935463794528)",
               "Active", "Yes", "Yes"]
        self.assertEqual(module.orderable_from_environment_cells(row, "MCXC"),
                         ("MCXC041VFKR", "Active"))

    def test_continuation_row_without_group_cell(self):
        row = ["MCXC041VFGR\n(935463841528)", "Active", "Yes", "Yes"]
        self.assertEqual(module.orderable_from_environment_cells(row, "MCXC"),
                         ("MCXC041VFGR", "Active"))

    def test_material_declaration_overrides_group_label(self):
        # NXP MCX-N23x: VDFT package label also contains VDFR ordering variant.
        row = ["MCXN236VDFT\nPackage : VFBGA184",
               "MCXN236VDFR\n(935463512518)", "Active", "Yes"]
        self.assertEqual(module.orderable_from_environment_cells(row, "MCXN"),
                         ("MCXN236VDFR", "Active"))

    def test_qualification_is_not_promoted_to_active(self):
        row = ["MCXN236VNLT\nPackage : HLQFP100",
               "MCXN236VNLT\n(935463587557)", "Qualification", "Yes"]
        self.assertEqual(module.orderable_from_environment_cells(row, "MCXN"),
                         ("MCXN236VNLT", "Qualification"))

    def test_quality_table_does_not_yield_orderable_status(self):
        row = ["MCXC041VFK\nPackage : HUQFN24",
               "MCXC041VFKR\n(935463794528)", "No", "3", "260", "40 sec."]
        self.assertIsNone(module.orderable_from_environment_cells(row, "MCXC"))

    def test_readonly_ci_product_matrix_matches_pinned_manifest(self):
        registry = json.loads(module.MANIFEST.read_text(encoding="utf-8"))
        ids = [row["id"] for row in registry["products"]]
        self.assertEqual(len(ids), len(set(ids)), "duplicate acquisition IDs")
        workflow = (module.HERE.parents[2] / ".github/workflows/"
                    "device-catalog-nxp-official-pilot-acquire-v1.yml"
                    ).read_text(encoding="utf-8")
        match = re.search(r"^\s*product:\s*\[([^]]+)\]\s*$", workflow, re.M)
        self.assertIsNotNone(match, "fixed product matrix missing")
        matrix = [item.strip() for item in match.group(1).split(",")]
        self.assertEqual(len(matrix), len(set(matrix)), "duplicate CI product IDs")
        self.assertEqual(set(matrix), set(ids), "matrix and official source pins drifted")
        self.assertFalse(registry["global_active_denominator_claimed"])
        self.assertFalse(registry["production_write_authorized"])

    def test_quality_rows_are_not_lifecycle(self):
        self.assertIsNone(module.lifecycle("MCXN236VNLT No 3 260 40 sec."))
    def test_bad_conflicting_status_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "contradictory"):
            module.lifecycle("MCXN236VNLT Active Qualification")
    def test_not_nxp_domains_are_rejected(self):
        self.assertFalse(module.official("https://www.nxp.com.evil.invalid/products"))
        self.assertFalse(module.official("http://www.nxp.com/products"))
        self.assertTrue(module.official("https://www.nxp.com/products/MCX-C04x"))
    def test_same_state_rows_keep_all_source_digests(self):
        rows = module.consolidate_lifecycle_rows({
            "MCXN236VPBT": [
                {"icpn": "MCXN236VPBT", "lifecycle": "Active",
                 "evidence_sha256": "a" * 64, "row_markup_sha256": "c" * 64},
                {"icpn": "MCXN236VPBT", "lifecycle": "Active",
                 "evidence_sha256": "b" * 64, "row_markup_sha256": "d" * 64},
            ]
        })
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["official_lifecycle_row_occurrences"], 2)
        self.assertEqual(rows[0]["row_evidence_sha256s"], ["a" * 64, "b" * 64])

    def test_same_exact_mpn_conflicting_lifecycle_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "contradictory"):
            module.consolidate_lifecycle_rows({
                "MCXN236VPBT": [
                    {"icpn": "MCXN236VPBT", "lifecycle": "Active",
                     "evidence_sha256": "a" * 64, "row_markup_sha256": "a" * 64},
                    {"icpn": "MCXN236VPBT", "lifecycle": "Qualification",
                     "evidence_sha256": "b" * 64, "row_markup_sha256": "b" * 64},
                ]
            })

    def test_ambiguous_code_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            module.exact_code("MCXC041VFK MCXC041VFGR", "MCXC")

if __name__ == "__main__":
    unittest.main()
