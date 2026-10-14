"""Synthetic raw row extraction tests; no real manufacturer field verification."""
import tempfile
from pathlib import Path
import unittest

import microchip_phase1_chart_html_source_v1 as source
import microchip_phase1_chart_html_row_probe_v1 as rows


DOC = (b'<html><body><table>'
       b'<tr><th>Device</th><th>Flash (KB)</th><th>RAM (KB)</th></tr>'
       b'<tr><td><a>ATSAMD21G18A</a></td><td>256</td><td>32</td></tr>'
       b'<tr><td>ATSAMD21G15</td><td>32</td><td>4</td></tr>'
       b'<tr><td>ATSAMC21G18A</td><td>256</td><td>32</td></tr>'
       b'</table></body></html>')


class ChartRowDiscoveryTest(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "source"

    def test_chart_source_and_unpromoted_row(self):
        source.capture(self.root, getter=lambda: DOC)
        report = rows.inspect(self.root)
        self.assertEqual(report["source_tr_nodes_seen"], 4)
        self.assertEqual(report["header_samples"][0]["headers_observed"],
                         ["Device", "Flash (KB)", "RAM (KB)"])
        self.assertEqual(len(report["target_raw_row_candidates"]), 1)
        self.assertEqual(
            [x["text"] for x in report["target_raw_row_candidates"][0]["raw_cells_not_mapped"]],
            ["ATSAMD21G18A", "256", "32"])
        self.assertFalse(report["semantic_field_alignment_verified"])
        self.assertEqual(report["phase1_specifications_verified"], 0)

    def test_source_tamper_disallows_any_row_findings(self):
        source.capture(self.root, getter=lambda: DOC)
        (self.root / "original-chart.html").write_bytes(DOC + b"\n")
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            rows.inspect(self.root)

    def test_absent_target_does_not_mean_no_manufacturer_sku(self):
        content = DOC.replace(b"ATSAMD21G18A", b"ATSAMD21E18A")
        source.capture(self.root, getter=lambda: content)
        report = rows.inspect(self.root)
        self.assertEqual(report["target_raw_row_candidates"], [])
        self.assertFalse(report["chart_row_commercial_icpn_verified"])


if __name__ == "__main__":
    unittest.main()
