#!/usr/bin/env python3
"""Boundary checks for Microchip SAM L10/11 original ordering PDF field enrichment."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import microchip_phase1_p1_exact_pdf_field_enrichment_v1 as enh
import microchip_phase1_p1_ordering_crosswalk_v1 as pdf

MCP="a"*64
ICPN="ATSAML11D16A-MUT"
BASE="ATSAML11D16A"


def ordinary():
    return {
        "flash_kib":64,
        "ram_kib":16,
        "pin_count":24,
        "package":"VQFN",
        "package_code":"M",
        "temperature_min_c":-40,
        "temperature_max_c":85,
        "core_model":"Arm Cortex-M23",
    }


class SAML1xExactFieldEvidence(unittest.TestCase):
    def test_ordering_field_table_contract(self):
        data=ordinary()
        for field,value,unit in (
            ("package","VQFN",None),
            ("pin_count",24,"pins"),
            ("flash",64,"KB"),
            ("ram",16,"KB"),
            ("core_model","Arm Cortex-M23",None),
            ("temperature",{"min":-40,"max":85},"°C"),
        ):
            ev=enh.verified_from_original_sources(field,data,[MCP],BASE,ICPN)
            self.assertEqual(ev["state"],"VERIFIED")
            self.assertEqual(ev["value"],value)
            self.assertEqual(ev["unit"],unit)
            self.assertIn(pdf.PDF_SHA,ev["source_sha256_refs"])
            self.assertIn(MCP,ev["source_sha256_refs"])
            self.assertIn("p.14",ev["source_locator"])
            self.assertIn("p.16",ev["source_locator"])
            self.assertEqual(ev["source_revision"],"DS60001513G")

    def test_vendor_exact_ordercode_identity_is_required(self):
        with self.assertRaisesRegex(ValueError,"manufacturer exact SKU"):
            enh.verified_from_original_sources("flash",ordinary(),[MCP],
                                                BASE,"ATSAML10D16A-MUT")
        with self.assertRaisesRegex(ValueError,"manufacturer exact SKU"):
            enh.verified_from_original_sources("flash",ordinary(),[MCP],
                                                BASE,"ATSAML11D16A")

    def test_invalid_or_absent_original_sha_rejected(self):
        for hashes in ([],["bad"],[MCP,MCP]):
            with self.subTest(hashes=hashes):
                with self.assertRaisesRegex(ValueError,"hashes absent"):
                    enh.verified_from_original_sources("ram",ordinary(),hashes,
                                                        BASE,ICPN)

    def test_missing_and_fabricated_main_flash_rejected(self):
        for value in (0,None,-4,"64",64.0):
            item=ordinary()
            item["flash_kib"]=value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError,"memory"):
                    enh.verified_from_original_sources("flash",item,[MCP],
                                                        BASE,ICPN)

    def test_unsafe_supply_and_architecture_inference_rejected(self):
        for name in ("working_vdd","io_supply","vdda","core_architecture",
                     "erase","program","software_supported"):
            with self.subTest(field=name):
                with self.assertRaisesRegex(ValueError,"unrelated"):
                    enh.verified_from_original_sources(name,ordinary(),[MCP],
                                                        BASE,ICPN)

    def test_suffix_inconsistent_temperature_rejected(self):
        item=ordinary()
        item["temperature_max_c"]=190
        with self.assertRaisesRegex(ValueError,"temperature"):
            enh.verified_from_original_sources("temperature",item,[MCP],
                                                BASE,ICPN)

    def test_unknown_pin_count_rejected(self):
        item=ordinary()
        item["pin_count"]=28
        with self.assertRaisesRegex(ValueError,"pin count"):
            enh.verified_from_original_sources("pin_count",item,[MCP],
                                                BASE,ICPN)

    def test_variant_package_unrecognized_rejected(self):
        item=ordinary()
        item["package"]="BGA"
        with self.assertRaisesRegex(ValueError,"package"):
            enh.verified_from_original_sources("package",item,[MCP],
                                                BASE,ICPN)

    def test_vao_is_not_ordinary_source_qualified(self):
        candidate="ATSAML10E16A-MZTVAO"
        self.assertIsNone(pdf.ORDER.fullmatch(candidate))
        self.assertIsNotNone(pdf.SPECIAL_VAO.fullmatch(candidate))
        self.assertEqual(enh.EXCEPTIONS,4)
        self.assertEqual(enh.EXACT,122)

    def test_frozen_cohort_invariant(self):
        self.assertEqual(enh.FROZEN_SHA,
                         "0c37ad68c1db0a4fb50ff5a1d229faaca0ee6eac44cfb9d9b7de4e8a931daf2a")
        self.assertEqual(enh.EXPECTED,2563)
        self.assertEqual(len(enh.PROMOTE),6)


if __name__=="__main__":
    unittest.main()
