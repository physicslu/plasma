#!/usr/bin/env python3
"""Fast offline replay of the per-SKU NXP 353 metadata status map."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("nxp_status_v2",HERE/"nxp_metadata_status_index_v2.py")
assert spec and spec.loader
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class NxpMetadataIndexTests(unittest.TestCase):
    def test_materialized_exact_353_records(self):
        records,summary=mod.materialize()
        self.assertEqual(len(records),353)
        self.assertEqual(len(set(r["icpn"] for r in records)),353)
        self.assertEqual(summary["status_counts"],{"B":93,"C":201,"K":12,"P":47})
        self.assertEqual(summary["blocked_reason_counts"],{"-":260,"F":8,"H":85})
        self.assertFalse(summary["production_write_authorized"])
        self.assertIsNone(summary["global_nxp_active_denominator"])
        self.assertTrue(all(row["programming_backend_qualified"]=="false" for row in records))

    def test_broken_per_sku_state_hash_fails_closed(self):
        x=json.loads(mod.STATUS_MAP.read_text())
        x["status_map"]="C"+x["status_map"][1:]
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bad.json"
            path.write_text(json.dumps(x))
            with patch.object(mod,"STATUS_MAP",path):
                with self.assertRaisesRegex(ValueError,"SHA256 status map drift"):
                    mod.materialize()

    def test_block_reason_on_unblocked_sku_rejected(self):
        x=json.loads(mod.STATUS_MAP.read_text())
        x["status_map_sha256"]=mod.sha(x["status_map"]+"\n")
        # Change reason on first successful SKU: maps must fail, whether
        # because hash evidence changed or because status/cause disagree.
        x["blocked_reason_map"]="H"+x["blocked_reason_map"][1:]
        x["blocked_reason_map_sha256"]=mod.sha(x["blocked_reason_map"]+"\n")
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bad.json"
            path.write_text(json.dumps(x))
            with patch.object(mod,"STATUS_MAP",path):
                with self.assertRaisesRegex(ValueError,"blocked source flag"):
                    mod.materialize()

    def test_forged_vendor_denominator_rejected(self):
        x=json.loads(mod.STATUS_MAP.read_text())
        x["claims"]["global_nxp_active_denominator"]=353
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"bad.json"
            path.write_text(json.dumps(x))
            with patch.object(mod,"STATUS_MAP",path):
                with self.assertRaisesRegex(ValueError,"changed authority"):
                    mod.materialize()


if __name__=="__main__":
    unittest.main()
