"""Fail closed on source drift, wrong MCXE247 PLL rail or false SRAM certainty."""
from __future__ import annotations

import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import nxp_phase1_mcxe_rails_v27 as v27


class NxpPhase1EVoltageV27Tests(unittest.TestCase):
    def test_full_501_row_replay_15_electric_and_two_ram_conflicts(self):
        v27.verify()
        rows = v27.build()
        self.assertEqual(len(rows), 501)
        self.assertEqual(sum(x["identity_state"] == "ADMITTED" for x in rows), 224)
        after = v27.stats(rows)["after_admitted"]["fields"]
        self.assertEqual(after["working_vdd"],
                         {"VERIFIED":181, "PARTIAL":39,"UNKNOWN":4,"CONFLICT":0})
        self.assertEqual(after["io_supply"],
                         {"VERIFIED":157, "PARTIAL":24,"UNKNOWN":43,"CONFLICT":0})
        self.assertEqual(after["vdda"],
                         {"VERIFIED":181, "PARTIAL":0,"UNKNOWN":43,"CONFLICT":0})
        self.assertEqual(after["ram"],
                         {"VERIFIED":197, "PARTIAL":25,"UNKNOWN":0,"CONFLICT":2})

    def test_not_mixing_e24_e31_and_preserve_exact_other_fields(self):
        old, new = v27.baseline_rows(), v27.build()
        self.assertEqual(len(old), len(new))
        changes = 0
        for a, b in zip(old,new):
            self.assertEqual(a["icpn"],b["icpn"])
            for key,val in a.items():
                if key in v27.CHANGED and a["icpn"] in v27.EXACT:
                    continue
                self.assertEqual(val,b[key],(a["icpn"],key))
            if a["icpn"] in v27.EXACT:
                changes+=1
                if a["icpn"].startswith("MCXE24"):
                    self.assertEqual(b["working_vdd"],"2.7 to 5.5")
                    self.assertEqual(b["io_supply_state"],"PARTIAL")
                    self.assertIn("independent VDDIO NOT established",b["io_supply"])
                    if a["icpn"].startswith("MCXE247"):
                        self.assertIn("PLL engaged ≥2.97V",
                                      b["mcxe_electrical_mode_constraint_v27"])
                else:
                    self.assertEqual(b["working_vdd"],"2.97 to 5.5")
                    self.assertEqual(b["io_supply_state"],"VERIFIED")
                    self.assertIn("VDD_HV_A",b["vdda"])
                    self.assertIn("no separate independent VDDA pin",
                                  b["mcxe_analog_rail_inference_limit_v27"])
                if a["icpn"] in v27.RAM_CONFLICTS:
                    self.assertEqual(a["ram_state"],"VERIFIED")
                    self.assertEqual(b["ram_state"],"CONFLICT")
                    self.assertEqual(b["ram"],a["ram"])
                    self.assertEqual(b["mcxe_new_ram_value_v27"],"112")
                    self.assertEqual(b["mcxe_prior_ram_source_v27"],
                                     "MCXE31FS Rev1 2025-10-23 p2 RAM64KB")
                else:
                    self.assertEqual(a["ram_state"],b["ram_state"])
                self.assertEqual(b["mcxe_original_pdf_sha256_v27"],"NOT_ARCHIVED")
            else:
                for key in v27.CHANGED:
                    self.assertEqual(a[key],b[key])
        self.assertEqual(changes,15)

    def test_source_mutation_negative_matrix(self):
        source=v27.read(v27.SOURCE)
        ix24=next(i for i,x in enumerate(source) if x["source_family"]=="MCXE24")
        ix31=next(i for i,x in enumerate(source) if x["source_family"]=="MCXE31")
        ix315=next(i for i,x in enumerate(source) if x["icpn"]=="MCXE315MLF")
        cases=[
            ("invented exact ordering",ix24,"icpn","MCXE245FAKE"),
            ("duplicated SKU",ix24,"icpn",source[ix31]["icpn"]),
            ("wrong commercial flash",ix24,"previous_flash_kb","12345"),
            ("wrong E24 voltage",ix24,"working_vdd_range","1.8 to 5.5"),
            ("PLL restriction discarded",ix24,"operating_mode_constraints","2.7V all modes even 247 PLL"),
            ("independent VDDIO fabricated",ix24,"io_supply_evidence","GPIO independent VDDIO 2.7–5.5"),
            ("VDDA as independent",ix24,"analog_supply_evidence","VDDA independent 5.5"),
            ("rating substituted for operating",ix24,"source_normal_electrical_locator","Table 2 absolute max"),
            ("fake original manufacturer SHA",ix24,"source_original_pdf_sha256","a"*64),
            ("PDF archive invented",ix31,"source_original_pdf_archived","true"),
            ("E31 wrong rail",ix31,"working_vdd_range","2.7 to 5.5"),
            ("E31 VREFH as analog rail",ix31,"analog_supply_evidence","VREFH is VDDA"),
            ("RAM conflict silently cleared",ix315,"ram_disposition","UNCHANGED"),
            ("RAM source contradictory value erased",ix315,"ram_new_datasheet_table2_kb","64"),
            ("production claimed",ix24,"nonclaim","SUPPORTED and HIL PASSED"),
        ]
        original_read=v27.read
        for label,index,col,value in cases:
            with self.subTest(label=label):
                modified=copy.deepcopy(source)
                modified[index][col]=value
                def fake_read(path):
                    if path==v27.SOURCE:
                        return modified
                    return original_read(path)
                with patch.object(v27,"read",side_effect=fake_read):
                    with self.assertRaises(ValueError):
                        v27.build()

    def test_lock_reject_false_certification_or_source_drift(self):
        original=v27.load()
        cases=[
            ("vendor_original_pdf_bytes_archived",True),
            ("vendor_original_pdf_sha256","a"*64),
            ("source_byte_replay_verified",True),
            ("production_catalog_changed",True),
            ("software_programming_qualified",True),
            ("physical_hil_verified",True),
            ("source_15_git_blob","0"*40),
            ("baseline_501_v26_git_blob","0"*40),
            ("prior_54_exact_v21_git_blob","0"*40),
        ]
        for key,value in cases:
            with self.subTest(key=key):
                altered=copy.deepcopy(original)
                altered[key]=value
                fake=SimpleNamespace(read_text=lambda encoding="utf-8":json.dumps(altered))
                with patch.object(v27,"LOCK",fake):
                    with self.assertRaises(ValueError):
                        v27.load()

    def test_e24_vdda_and_e31_analog_scope_not_collapsed(self):
        source=v27.read(v27.SOURCE)
        self.assertEqual(len(source),15)
        self.assertEqual({x["source_family"] for x in source},{"MCXE24","MCXE31"})
        self.assertTrue(all(x["analog_supply_evidence"]==v27.E24_ANALOG
                            for x in source if x["source_family"]=="MCXE24"))
        self.assertTrue(all(x["analog_supply_evidence"]==v27.E31_ANALOG
                            for x in source if x["source_family"]=="MCXE31"))
        self.assertEqual({x["icpn"] for x in source
                          if x["ram_disposition"].startswith("OPEN_CONFLICT")},
                         v27.RAM_CONFLICTS)


if __name__=="__main__":
    unittest.main(verbosity=2)
