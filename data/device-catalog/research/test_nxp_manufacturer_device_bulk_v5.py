#!/usr/bin/env python3
"""Fail-closed NXP manufacturer device acquisition, not programming."""
import importlib.util
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("nxp_mfg_v5",HERE/"nxp_manufacturer_device_bulk_v5.py")
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ManufacturerDeviceV5Tests(unittest.TestCase):
    def test_unambiguous_exact_nxp_parametric(self):
        from bs4 import BeautifulSoup
        html=('<table><tr><td>SRAM (kB)</td><td>64</td></tr>'
              '<tr><td>Supply Voltage [Min to Max] (V)</td>'
              '<td>1.71 to 3.6</td></tr></table>')
        cells=m.source_cells(BeautifulSoup(html,"html.parser"))
        self.assertEqual(m.field(cells,m.EVIDENCE_LABELS["ram_kb"]),
                         ("64","independently_replayed_exact_manufacturer_html"))
        self.assertEqual(m.field(cells,m.EVIDENCE_LABELS["vdd_range"]),
                         ("1.71 to 3.6","independently_replayed_exact_manufacturer_html"))

    def test_conflicting_exact_vendor_cell_stays_unknown(self):
        from bs4 import BeautifulSoup
        x=BeautifulSoup('<table><tr><td>SRAM (kB)</td><td>32</td></tr>'
                        '<tr><td>SRAM (kB)</td><td>64</td></tr></table>',"html.parser")
        self.assertEqual(m.field(m.source_cells(x),m.EVIDENCE_LABELS["ram_kb"]),
                         ("","conflicting_manufacturer_parametric_cells"))

    def test_missing_io_and_analog_supply_are_not_inferred_from_vdd(self):
        self.assertNotIn("io_supply",m.EVIDENCE_LABELS)
        self.assertNotIn("vdda",m.EVIDENCE_LABELS)
        self.assertIn("io_supply_evidence_state",m.DEVICE_FIELDS)
        self.assertIn("vdda_evidence_state",m.DEVICE_FIELDS)

    def test_canonical_schema_and_no_backend(self):
        self.assertEqual(len(m.CANONICAL_FIELDS),19)
        self.assertEqual(m.CANONICAL_FIELDS[0:5],
                         ["manufacturer","icpn","family","series","base_device"])
        self.assertIn("mapping_status",m.CANONICAL_FIELDS)
        self.assertIn("openocd_target_config",m.CANONICAL_FIELDS)

    def test_only_known_official_product_family_segments(self):
        self.assertEqual(m.family_series("MCXA145VMP","mcx"),("MCX","MCX A"))
        self.assertEqual(m.family_series("K32L2B31VMP0A","k32"),("K32L2","K32 L2"))
        self.assertEqual(m.family_series("LPC55S69JEV98E","lpc"),("LPC55","LPC55"))
        with self.assertRaisesRegex(ValueError,"non-K32L2"):
            m.family_series("MCXA145VMP","k32")

    def test_unsupported_family_rejected(self):
        with self.assertRaisesRegex(ValueError,"unknown NXP product group"):
            m.family_series("FOO123","future")

if __name__=="__main__":
    unittest.main()
