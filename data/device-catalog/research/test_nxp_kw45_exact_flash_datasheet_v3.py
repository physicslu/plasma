#!/usr/bin/env python3
"""KW45 official datasheet rowspan alignment and exact-SKU source contract."""
from __future__ import annotations
import importlib.util
import unittest
from pathlib import Path

import fitz

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("kw45",HERE/"nxp_kw45_exact_flash_datasheet_v3.py")
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture(wrong_group:bool=False)->bytes:
    doc=fitz.open()
    for _ in range(5):
        doc.new_page()
    page=doc[3]
    page.insert_text((35,70),"Table 1. Ordering Information of radio parts")
    page.insert_text((275,151),"512 KB/128 KB")
    page.insert_text((275,318 if not wrong_group else 540),"1 MB/128 KB")
    ids_512=sorted(k for k,v in m.EXACT.items() if v==512)
    ids_1024=sorted(k for k,v in m.EXACT.items() if v==1024)
    for i,s in enumerate(ids_512):
        page.insert_text((35,120+28*i),s)
    for i,s in enumerate(ids_1024):
        page.insert_text((35,294+28*i),s)
    data=doc.tobytes()
    doc.close()
    return data


class Kw45ManufacturerFlashTests(unittest.TestCase):
    def test_eight_exact_flash_ambiguities_are_frozen(self):
        skus=m.from_blocked_source()
        self.assertEqual(skus,set(m.EXACT))
        self.assertEqual(len(skus),8)
        self.assertEqual(sorted(set(m.EXACT.values())),[512,1024])

    def test_real_table_layout_can_reconcile_eight_exact_skus(self):
        r=m.pdf_table(fixture())
        self.assertEqual(len(r["flash_candidates"]),8)
        self.assertEqual({x["flash_kb_from_exact_datasheet_table"]
                          for x in r["flash_candidates"]},{512,1024})
        self.assertFalse(r["production_write_authorized"])
        self.assertIsNone(r["global_nxp_active_denominator"])

    def test_missing_memory_rowspan_alignment_blocks(self):
        with self.assertRaisesRegex(ValueError,"do not align"):
            m.pdf_table(fixture(wrong_group=True))

    def test_missing_exact_sku_is_rejected(self):
        raw=fixture()
        doc=fitz.open(stream=raw,filetype="pdf")
        page=doc[3]
        # Removing a visual SKU by whitening its region is not an edit to
        # the PDF text layer. Instead build a synthetic doc with the wrong
        # MPN printed at the same position.
        d2=fitz.open()
        for _ in range(5):d2.new_page()
        p=d2[3]
        p.insert_text((35,70),"Table 1. Ordering Information of radio parts")
        p.insert_text((275,151),"512 KB/128 KB")
        p.insert_text((275,318),"1 MB/128 KB")
        for i,s in enumerate(sorted(k for k,v in m.EXACT.items() if v==512)):
            p.insert_text((35,120+28*i),"WRONGCODE" if i==0 else s)
        for i,s in enumerate(sorted(k for k,v in m.EXACT.items() if v==1024)):
            p.insert_text((35,294+28*i),s)
        bad=d2.tobytes();d2.close();doc.close()
        with self.assertRaisesRegex(ValueError,"part missing/duplicate"):
            m.pdf_table(bad)

    def test_non_pdf_is_not_manufacturer_proof(self):
        with self.assertRaisesRegex(ValueError,"PDF invalid"):
            m.pdf_table(b"fake pdf")


if __name__=="__main__":
    unittest.main()
