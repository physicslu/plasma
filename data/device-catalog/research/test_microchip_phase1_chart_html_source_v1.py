"""Synthetic original HTML capture tests. No manufacturer evidence is invented."""
import json
from pathlib import Path
import tempfile
import unittest

import microchip_phase1_chart_html_source_v1 as probe


FIXTURE = (b"<!doctype html><html><body><table><tr><td>ATSAMD21G15</td>"
           b"<td>32 KB</td></tr><tr><td>ATSAMC21G18A</td>"
           b"<td>256 KB</td></tr></table></body></html>")


class ChartSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source-original"

    def test_source_byte_replay_not_semantic_spec(self):
        report = probe.capture(self.path, getter=lambda: FIXTURE)
        self.assertEqual(report, probe.replay(self.path))
        self.assertEqual(report["capture_outcome"], "CAPTURED_NOT_SEMANTICALLY_VERIFIED")
        self.assertEqual(report["phase1_specifications_verified"], 0)
        self.assertEqual(report["exact_icpn_verified"], 0)
        self.assertTrue(report["no_exact_icpn_admission"])
        manifest = json.loads((self.path / "manifest.json").read_text())
        self.assertTrue(manifest["original_response_retained"])

    def test_tampered_original_byte_fails(self):
        probe.capture(self.path, getter=lambda: FIXTURE)
        f = self.path / "original-chart.html"
        f.write_bytes(f.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            probe.replay(self.path)

    def test_missing_chart_markers_are_source_unavailable(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_NOT_AVAILABLE"):
            probe.capture(self.path, getter=lambda: b"<html>No chart here</html>")
        result = json.loads((self.path / "manifest.json").read_text())
        self.assertEqual(result["capture_outcome"], "SOURCE_NOT_AVAILABLE")
        self.assertFalse(result["original_response_retained"])
        with self.assertRaisesRegex(ValueError, "source not captured"):
            probe.replay(self.path)

    def test_offsite_redirect_not_allowed(self):
        self.assertTrue(probe.authorized(probe.URL))
        self.assertFalse(probe.authorized("https://www.microchipdirect.com/404"))
        self.assertFalse(probe.authorized("http://www.microchipdirect.com/chart.aspx?branchID=21&mid=3"))
        self.assertFalse(probe.authorized("https://not-microchip.example.com/chart.aspx?branchID=21&mid=3"))

    def test_recorded_manifest_cannot_claim_software_support(self):
        probe.capture(self.path, getter=lambda: FIXTURE)
        manifest_path = self.path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["software_supported_claimed"] = True
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "manifest inconsistent"):
            probe.replay(self.path)


if __name__ == "__main__":
    unittest.main()
