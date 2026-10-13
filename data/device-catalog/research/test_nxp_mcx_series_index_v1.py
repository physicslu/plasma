#!/usr/bin/env python3
import importlib.util
import unittest
from pathlib import Path
H=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("nxp_index",H/"nxp_mcx_series_index_v1.py")
assert spec and spec.loader
x=importlib.util.module_from_spec(spec)
spec.loader.exec_module(x)
class MCXIndexTests(unittest.TestCase):
    def test_unique_path_candidates(self):
        pages=["https://www.nxp.com/products/MCX-A17","https://www.nxp.com/products/MCX-A17?tab=Package_Quality_Tab"]
        self.assertEqual(x.normalize_leads(pages,"A"),["https://www.nxp.com/products/MCX-A17"])
    def test_other_series_excluded(self):
        self.assertEqual(x.normalize_leads(["https://www.nxp.com/products/MCX-W23"],"A"),[])
    def test_offdomain_navigation_is_not_product_evidence(self):
        self.assertEqual(x.normalize_leads([
            "https://community.nxp.com", "https://www.nxp.com.evil.invalid/products/MCX-A17",
            "https://www.nxp.com/products/MCX-A17"
        ],"A"), ["https://www.nxp.com/products/MCX-A17"])
    def test_no_sku_claim_from_link(self):
        self.assertEqual(x.normalize_leads(["https://www.nxp.com/products/MCX-A17"],"A"),
                         ["https://www.nxp.com/products/MCX-A17"])
if __name__=="__main__":
    unittest.main()
