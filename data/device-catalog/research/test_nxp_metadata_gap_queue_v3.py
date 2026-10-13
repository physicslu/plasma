#!/usr/bin/env python3
"""NXP durable 129-row post-bump exception queue, research-only."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("nxp_q",HERE/"nxp_metadata_gap_queue_v3.py")
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class Nxp353BulkExceptionQueueTests(unittest.TestCase):
    def test_all_129_exact_after_independent_eleven_bump_replay(self):
        rows,report=m.queue()
        self.assertEqual(len(rows),129)
        self.assertEqual(len({x["icpn"] for x in rows}),129)
        self.assertEqual(report["four_source_fields_total_REVIEW_REQUIRED"],212)
        self.assertEqual(report["outstanding_metadata_exact_total"],129)
        self.assertEqual(report["exception_counts"],{
            "flash_multi_value":8,
            "http_non200":85,
            "imx_rt_flash_temperature":23,
            "mcx_flash_ambient":5,
            "wireless_ambient":8,
        })
        self.assertEqual(m.FROZEN.read_text(),m.render(rows))
        self.assertTrue(all(x["production_write_authorized"]=="false" for x in rows))
        self.assertIsNone(report["global_nxp_active_denominator"])

    def test_source_blocked_eighty_five_remains_never_inferred(self):
        rows,_=m.queue()
        blocked=[x for x in rows if x["exception_class"]=="http_non200"]
        self.assertEqual(len(blocked),85)
        self.assertTrue(all(x["manufacturer_evidence_route"]==
            "official_datasheet_exact_ordering_table_required" for x in blocked))

    def test_sku_research_queue_does_not_claim_flash_backend(self):
        rows,s=m.queue()
        self.assertTrue(all(x["catalog_admission_authorized"]=="false" for x in rows))
        self.assertFalse(s["programming_backend_qualified"])

    def test_forged_evidence_authority_fails_closed(self):
        x=json.loads(m.GATE.read_text())
        x["production_write_authorized"]=True
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"unsafe.json"
            path.write_text(json.dumps(x))
            with patch.object(m,"GATE",path):
                with self.assertRaisesRegex(ValueError,"lock drift"):
                    m.queue()

if __name__=="__main__":
    unittest.main()
