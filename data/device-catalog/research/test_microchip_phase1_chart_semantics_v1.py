"""Synthetic chart family-field mapping regression; no synthetic values are evidence."""
import tempfile
from pathlib import Path
import unittest

import microchip_phase1_chart_html_source_v1 as source
import microchip_phase1_chart_semantics_v1 as semantic

NAMES = ["Device Name", "CPU", "Flash (KB)", "RAM (KB)",
         "Operation Voltage Range", "Temperature Range", "Pin count", "Packages"]
VALS = ["ATSAMD21G18 [More Info]", "Cortex-M0+", "256", "32",
        "1.62V - 3.63V", "-40 to 125", "48", "45/WLCSP 48/TQFP 48/VQFN"]


def official_looking_synthetic(headers=None, values=None, repeat=False):
    headers = NAMES if headers is None else headers
    values = VALS if values is None else values
    head = "<tr>" + "".join(f"<th>{x}</th>" for x in headers) + "</tr>"
    row = "<tr>" + "".join(f"<td>{x}</td>" for x in values) + "</tr>"
    return ("<html><body><table>" + head + row + (row if repeat else "")
            + "<tr><td>ATSAMD21G15</td></tr>"
            + "<tr><td>ATSAMC21G18A</td></tr></table></body></html>").encode()


class ChartSemanticPhase1Test(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name) / "original"

    def test_family_fields_partial_and_pilot_link_without_promotion(self):
        source.capture(self.root, getter=lambda: official_looking_synthetic())
        result = semantic.extract_family(self.root)
        fields = result["fields_family_scope_only"]
        self.assertEqual(fields["flash"]["value"], 256)
        self.assertEqual(fields["flash"]["unit"], "KB")
        self.assertEqual(fields["ram"]["value"], 32)
        self.assertEqual(fields["vdd"]["value"], {"min": 1.62, "max": 3.63})
        self.assertEqual(fields["temperature"]["value"], {"min": -40, "max": 125})
        self.assertEqual(fields["core_model"]["value"], "Cortex-M0+")
        self.assertEqual(fields["package"]["value"], "45/WLCSP 48/TQFP 48/VQFN")
        self.assertEqual(fields["io_supply"]["status"], "UNKNOWN")
        self.assertTrue(all(x["status"] == "PARTIAL" for k, x in fields.items()
                            if k not in ("io_supply", "vdda")))
        self.assertEqual(result["research_priority"], "P0")
        self.assertEqual(result["openocd_research_lead"], "sam-d-c-r-l0")
        linked = result["linked_existing_exact_icpns_not_admitted"]
        self.assertEqual({x["icpn"] for x in linked},
                         {"ATSAMD21G18A-MU", "ATSAMD21G18A-MF"})
        self.assertFalse(result["software_support_qualified"])
        self.assertFalse(result["production_write_authorized"])
        self.assertEqual(result["exact_icpn_verified_from_chart"], 0)

    def test_duplicate_family_target_rejected(self):
        source.capture(self.root, getter=lambda: official_looking_synthetic(repeat=True))
        with self.assertRaisesRegex(ValueError, "single exact manufacturer Base Device"):
            semantic.extract_family(self.root)

    def test_missing_flash_header_rejected(self):
        headers = list(NAMES)
        headers[2] = "Unreviewed generic memory field"
        source.capture(self.root, getter=lambda: official_looking_synthetic(headers=headers))
        with self.assertRaisesRegex(ValueError, "chart header contract"):
            semantic.extract_family(self.root)

    def test_wrong_electrical_range_rejected(self):
        vals = list(VALS)
        vals[4] = "TBD"
        source.capture(self.root, getter=lambda: official_looking_synthetic(values=vals))
        with self.assertRaisesRegex(ValueError, "invalid original manufacturer VDD range"):
            semantic.extract_family(self.root)

    def test_original_source_tamper_rejected_before_mapping(self):
        source.capture(self.root, getter=lambda: official_looking_synthetic())
        html = self.root / "original-chart.html"
        html.write_bytes(html.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "integrity mismatch"):
            semantic.extract_family(self.root)


if __name__ == "__main__":
    unittest.main()
