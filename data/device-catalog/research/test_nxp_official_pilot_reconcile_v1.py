#!/usr/bin/env python3
"""Offline negative regressions for NXP live evidence reconciliation."""
import csv
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("nxp_reconcile", HERE/"nxp_official_pilot_reconcile_v1.py")
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cfg = json.loads((HERE/"nxp-official-pilot-products-v1.json").read_text())

def hash_(value):
    return hashlib.sha256(value.encode()).hexdigest()

class NxpPilotEvidenceTests(unittest.TestCase):
    def setup_pilot(self, root):
        with (HERE/"nxp-kl25-commercial-icpn.csv").open(encoding="utf-8") as f:
            kl25 = [r["icpn"] for r in csv.DictReader(f)]
        for source in cfg["products"]:
            folder = root/("nxp-official-v1-"+source["id"])
            folder.mkdir()
            html = "<html>"+source["id"]+"</html>"
            (folder/"rendered-page.html").write_text(html)
            names = kl25 if source["id"] == "kl25" else [source["must_include"]]
            rows = [{
                "icpn": name, "lifecycle": "Active", "source_url": source["url"],
                "evidence_sha256": "a"*64, "row_markup_sha256": "b"*64,
                "row_evidence_sha256s": ["a"*64], "row_markup_sha256s": ["b"*64],
                "official_lifecycle_row_occurrences": 1,
            } for name in names]
            snapshot = {
                "acquisition_id": source["id"], "manufacturer": "NXP",
                "segment": source["segment"],
                "status": "bounded_official_product_page_observed",
                "source_url": source["url"],
                "source_population_complete": False,
                "global_active_denominator_claimed": False,
                "rendered_dom_sha256": hash_(html),
                "source_product_row_count": len(rows),
                "active_exact_count": len(rows),
                "qualification_exact_count": 0, "rows": rows,
            }
            (folder/"acquisition.json").write_text(json.dumps(snapshot))

    def test_aggregate_is_bounded_and_never_full_vendor(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.setup_pilot(root)
            result = mod.reconcile(root)
            self.assertEqual(result["observed_active_exact"], len(cfg["products"]) + 11)
            self.assertEqual(result["locked_kl25_exact_pilot"], 12)
            self.assertIsNone(result["global_active_denominator"])
            self.assertFalse(result["global_portfolio_complete"])

    def test_qualification_is_not_active(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.setup_pilot(root)
            p = root/"nxp-official-v1-mcx-n23x"/"acquisition.json"
            x = json.loads(p.read_text())
            x["rows"][0]["lifecycle"] = "Qualification"
            x["active_exact_count"] = 0
            x["qualification_exact_count"] = 1
            p.write_text(json.dumps(x))
            result = mod.reconcile(root)
            self.assertEqual(result["observed_active_exact"], len(cfg["products"]) + 10)
            self.assertEqual(result["observed_qualification_exact"], 1)

    def test_raw_html_hash_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.setup_pilot(root)
            (root/"nxp-official-v1-kl25"/"rendered-page.html").write_text("<bad>")
            with self.assertRaisesRegex(ValueError,"raw DOM evidence drift"):
                mod.reconcile(root)

    def test_missing_kl25_row_is_not_silent(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.setup_pilot(root)
            p = root/"nxp-official-v1-kl25"/"acquisition.json"
            x = json.loads(p.read_text())
            x["rows"].pop()
            x["source_product_row_count"] -= 1
            x["active_exact_count"] -= 1
            p.write_text(json.dumps(x))
            with self.assertRaisesRegex(ValueError,"KL25 exact-set drift"):
                mod.reconcile(root)

if __name__ == "__main__":
    unittest.main()
