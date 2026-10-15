#!/usr/bin/env python3
"""Negative tests for Microchip ST-style Phase 1 2,563 field evidence."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import microchip_phase1_cfg2563_st_field_ledger_v1 as ledger

SHA="a"*64


def field(state="VERIFIED", value=10, scope="exact_mcp_response_row"):
    return {
        "status":state,
        "value":value,
        "unit":"KB",
        "source_locator":"Microchip official product/source table #3",
        "evidence_scope":scope,
        "original_response_sha256_refs":[SHA],
        "notes":"Original manufacturer evidence only",
    }


class MicrochipFiveCfgSTFields(unittest.TestCase):
    def test_identified_identity_only_is_verified(self):
        item=ledger.normalize_field(field())
        self.assertEqual(item["state"],"VERIFIED")
        self.assertEqual(item["source_authority"],"Microchip Technology official")
        self.assertEqual(item["source_sha256_refs"],[SHA])

    def test_chart_partial_stays_partial(self):
        item=ledger.normalize_field(field("PARTIAL",123,
                             "official_base_device_chart_not_exact_icpn"))
        self.assertEqual(item["state"],"PARTIAL")
        self.assertNotEqual(item["state"],"VERIFIED")

    def test_family_cannot_be_promoted_to_verified(self):
        with self.assertRaisesRegex(ValueError,"cannot be promoted"):
            ledger.normalize_field(field("VERIFIED",123,
                             "official_base_device_chart_not_exact_icpn"))

    def test_unsourced_or_forged_field_rejected(self):
        for key,bad in (("source_locator",None),
                        ("original_response_sha256_refs",["INVALID"]),
                        ("evidence_scope",None)):
            item=field()
            item[key]=bad
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError,"lacks"):
                    ledger.normalize_field(item)

    def test_unknown_must_be_absent_not_numeric_zero(self):
        unknown=dict(field("UNKNOWN",None,"none"),
                     source_locator=None,evidence_scope=None,
                     original_response_sha256_refs=None,unit=None)
        self.assertEqual(ledger.normalize_field(unknown)["state"],"UNKNOWN")
        unknown["value"]=0
        with self.assertRaisesRegex(ValueError,"UNKNOWN"):
            ledger.normalize_field(unknown)

    def test_not_applicable_requires_explicit_source_and_cannot_be_zero(self):
        raw=field("NOT_APPLICABLE",None,"official_exact_applicability_table")
        raw["unit"]=None
        raw["notes"]="Manufacturer table says NOT_APPLICABLE for this exact item"
        result=ledger.normalize_field(raw)
        self.assertEqual(result["state"],"NOT_APPLICABLE")
        self.assertIsNone(result["value"])
        self.assertEqual(result["source_sha256_refs"],[SHA])
        invented=dict(raw, value=0)
        with self.assertRaisesRegex(ValueError,"NOT_APPLICABLE"):
            ledger.normalize_field(invented)
        uncited=dict(raw, original_response_sha256_refs=None)
        with self.assertRaisesRegex(ValueError,"NOT_APPLICABLE"):
            ledger.normalize_field(uncited)

    def test_conflict_must_not_select_winner(self):
        conflict=dict(field("CONFLICT",None,"unresolved_conflict"))
        self.assertEqual(ledger.normalize_field(conflict)["state"],"CONFLICT")
        conflict["value"]=123
        with self.assertRaisesRegex(ValueError,"CONFLICT"):
            ledger.normalize_field(conflict)

    def test_freeze_digest_is_deterministic_order_independent(self):
        sample=[
            {"icpn":"IC-AA","base_device":"IC","openocd_target_cfg_research_only":
                "tcl/target/pic32mx.cfg"},
            {"icpn":"IC-BB","base_device":"ICB","openocd_target_cfg_research_only":
                "tcl/target/atsaml1x.cfg"},
        ]
        self.assertEqual(ledger.freeze_digest(sample),
                         ledger.freeze_digest(list(reversed(sample))))
        altered=copy.deepcopy(sample)
        altered[0]["base_device"]="DIFFERENT"
        self.assertNotEqual(ledger.freeze_digest(altered),
                            ledger.freeze_digest(sample))

    def test_st_field_contract_and_cfg_cohort_frozen(self):
        self.assertEqual(sum(ledger.EXPECTED_BY_CFG.values()),2563)
        self.assertEqual(ledger.FROZEN_IDENTITY_SHA256,
                         "0c37ad68c1db0a4fb50ff5a1d229faaca0ee6eac44cfb9d9b7de4e8a931daf2a")
        self.assertEqual(len(ledger.EXPECTED_BY_CFG),5)
        self.assertEqual(len(ledger.ST_FIELDS),13)
        self.assertIn("working_vdd",ledger.ST_FIELDS)
        self.assertEqual(ledger.FROM_MICROCHIP["working_vdd"],"vdd")
        self.assertNotIn("software_supported",ledger.ST_FIELDS)


if __name__=="__main__":
    unittest.main()
