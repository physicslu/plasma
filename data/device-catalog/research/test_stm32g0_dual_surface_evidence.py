#!/usr/bin/env python3
from __future__ import annotations
import unittest
from st_product_page_acquisition import AcquisitionError
from stm32g0_dual_surface_evidence import (
    EVIDENCE_SURFACE, PARSER_PROFILE, build_dual_surface_browser_evidence_record,
    dual_surface_ready, extract_dual_surface_part_number_records,
)
BASE="STM32G030C6"
URL="https://www.st.com/en/microcontrollers-microprocessors/stm32g030c6.html"

def page(*, lifecycle_rows: str) -> str:
    return f'''<html><body><h2>Quality and Reliability</h2><table>
<tr><th>Part Number</th><th>RoHS Compliance Grade</th><th>Grade</th></tr>
<tr><td>STM32G030C6T6</td><td>Ecopack2</td><td>Industrial</td></tr></table>
<h2>Sample &amp; Buy</h2><table><tr><th>Part Number</th><th>Marketing Status</th><th>Package</th></tr>
{lifecycle_rows}</table><h2>Documentation</h2></body></html>'''
ACTIVE='<tr><td>STM32G030C6T6</td><td>Active Product is in volume production.</td><td>LQFP48</td></tr>'

class Tests(unittest.TestCase):
    def test_active_join(self):
        records,text=extract_dual_surface_part_number_records(page(lifecycle_rows=ACTIVE),BASE)
        self.assertEqual([r['icpn'] for r in records],["STM32G030C6T6"])
        self.assertTrue(records[0]['active']); self.assertTrue(dual_surface_ready(page(lifecycle_rows=ACTIVE),BASE))
        self.assertIn('Sample & Buy lifecycle projection',text)
    def test_profile(self):
        e=build_dual_surface_browser_evidence_record(body=page(lifecycle_rows=ACTIVE).encode(),source_url=URL,final_url=URL,base_device=BASE,retrieved_at_utc='2026-09-09T00:00:00Z')
        self.assertEqual(e['evidence_surface'],EVIDENCE_SURFACE); self.assertEqual(PARSER_PROFILE,'stm32g0_dual_surface_v1')
        self.assertEqual(e['exact_icpns'],['STM32G030C6T6'])
    def test_nonactive_excluded(self):
        rows=ACTIVE.replace('Active Product is in volume production.','NRND Not Recommended for New Designs.')
        e=build_dual_surface_browser_evidence_record(body=page(lifecycle_rows=rows).encode(),source_url=URL,final_url=URL,base_device=BASE,retrieved_at_utc='2026-09-09T00:00:00Z')
        self.assertEqual(e['exact_icpns'],[]); self.assertEqual(e['excluded_non_active_part_numbers'][0]['icpn'],'STM32G030C6T6')
    def test_foreign_fails(self):
        rows=ACTIVE+'<tr><td>STM32G031C6T6</td><td>Active Product is in volume production.</td><td>LQFP48</td></tr>'
        with self.assertRaisesRegex(AcquisitionError,'foreign STM32'): extract_dual_surface_part_number_records(page(lifecycle_rows=rows),BASE)
    def test_missing_status_fails(self):
        html=page(lifecycle_rows=ACTIVE).replace('<th>Marketing Status</th>','<th>Status unavailable</th>')
        with self.assertRaisesRegex(AcquisitionError,'Marketing Status'): extract_dual_surface_part_number_records(html,BASE)

if __name__=='__main__': unittest.main()
