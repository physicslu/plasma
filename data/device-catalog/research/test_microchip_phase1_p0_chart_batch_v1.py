"""Synthetic-only tests for source-bound Microchip Phase 1 P0 chart batch."""
import json
from pathlib import Path
import tempfile
import unittest

import microchip_phase1_chart_html_source_v1 as source
from microchip_phase1_chart_semantics_v1 import HEADERS
import microchip_phase1_p0_chart_batch_v1 as batch

KEYS = list(HEADERS)
HEADINGS = list(HEADERS.values())
NAMES = ["ATSAMD21G18", "ATSAME54P20A", "PIC32MX170F256B",
         "ATSAML11E16A", "AVR32DA28"]
VALUES = {"base_device": "", "core_model": "Cortex-M0+", "flash": "256",
          "ram": "32", "vdd": "1.62V - 3.63V", "temperature": "-40 to 125",
          "pin_count": "48", "package": "48/VQFN"}


def fake_html(names=None, invalid_vdd=False, invalid_header=False):
    names = list(NAMES if names is None else names)
    headings = list(HEADINGS)
    if invalid_header:
        headings[headings.index("Flash (KB)")] = "Unverified Memory"
    header = "<tr>" + "".join("<th>" + name + "</th>" for name in headings) + "</tr>"
    lines = []
    for dev in names:
        cells = dict(VALUES, base_device=dev + " [More Info]")
        if invalid_vdd and dev == "ATSAMD21G18":
            cells["vdd"] = "untrusted-voltage"
        lines.append("<tr>" + "".join("<td>" + cells[k] + "</td>" for k in KEYS)
                     + "</tr>")
    # Source-capture smoke-check markers outside chart rows, not evidence claims.
    return ("<html><body>ATSAMD21G15 ATSAMC21G18A<table>" + header
            + "".join(lines) + "</table></body></html>").encode("utf-8")


class P0ChartBatchTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "original"
        self.tmp = Path(directory.name)

    def capture(self, html=None):
        source.capture(self.root, getter=lambda: fake_html() if html is None else html)

    def test_p0_priority_p1_deferred_p2_archive_and_evidence_counts(self):
        self.capture()
        report = batch.build_report(self.root)
        counts = report["chart_records"]
        self.assertEqual([counts[k] for k in
                          ("observed_chart_base_devices", "P0_source_leads",
                           "P1_deferred", "P2_archive_only")], [5, 3, 1, 1])
        self.assertEqual(report["p0_by_source_lead"],
                         {"pic32mx": 1, "sam-d-c-r-l0": 1, "sam-e5-d5": 1})
        base = {r["base_device_chart_observation"]: r
                for r in report["p0_family_records"]}
        samd = base["ATSAMD21G18"]
        fields = samd["fields_family_scope_only"]
        self.assertEqual(fields["flash"]["value"], 256)
        self.assertEqual(fields["flash"]["original_header"], "Flash (KB)")
        self.assertEqual(fields["ram"]["value"], 32)
        self.assertEqual(fields["vdd"]["value"], {"min": 1.62, "max": 3.63})
        self.assertEqual(fields["temperature"]["value"], {"min": -40, "max": 125})
        self.assertEqual(fields["io_supply"]["status"], "UNKNOWN")
        self.assertEqual(fields["vdda"]["status"], "UNKNOWN")
        self.assertEqual(samd["existing_reviewed_mcp_pilot_icpns_not_replayed_here"],
                         ["ATSAMD21G18A-MF", "ATSAMD21G18A-MU"])
        self.assertEqual(report["p0_field_coverage"]["flash"]["PARTIAL"], 3)
        self.assertEqual(report["p0_field_coverage"]["flash"]["VERIFIED"], 0)
        self.assertFalse(report["manufacturer_population_complete"])
        self.assertIsNone(report["software_supported_icpn_count"])
        self.assertEqual(report["exact_icpn_fields_verified_from_chart"], 0)
        self.assertFalse(report["production_write_authorized"])
        self.assertEqual(len(report["p1_deferred_base_names"]), 1)
        self.assertTrue(report["p1_deferred_base_names"][0]["deep_enrichment_deferred"])
        self.assertEqual(report["p2_archive_only_base_names"][0]["base_device_chart_observation"],
                         "AVR32DA28")
        self.assertNotIn("fields_family_scope_only",
                         report["p2_archive_only_base_names"][0])
        self.assertTrue(all(r["openocd_software_supported_claimed"] is False
                            for r in report["p0_family_records"]))

    def test_unparseable_vdd_keeps_gap_not_fake_zero_or_verification(self):
        self.capture(fake_html(invalid_vdd=True))
        report = batch.build_report(self.root)
        samd = next(r for r in report["p0_family_records"]
                    if r["base_device_chart_observation"] == "ATSAMD21G18")
        field = samd["fields_family_scope_only"]["vdd"]
        self.assertEqual(field["status"], "UNKNOWN")
        self.assertIsNone(field["value"])
        self.assertEqual(field["gap"], "UNPARSEABLE_CHART_VALUE")
        self.assertEqual(field["original_raw_value"], "untrusted-voltage")
        self.assertEqual(report["p0_field_coverage"]["vdd"]["UNKNOWN"], 1)

    def test_duplicates_fail_closed(self):
        self.capture(fake_html(names=NAMES + ["ATSAMD21G18"]))
        with self.assertRaisesRegex(ValueError, "duplicate chart Base Device"):
            batch.build_report(self.root)

    def test_missing_header_contract_fails_closed(self):
        self.capture(fake_html(invalid_header=True))
        with self.assertRaisesRegex(ValueError, "header row missing"):
            batch.build_report(self.root)

    def test_chart_with_no_p0_canary_fails_closed(self):
        self.capture(fake_html(names=["ATSAML11E16A", "AVR32DA28"]))
        with self.assertRaisesRegex(ValueError, "canary Base Device missing"):
            batch.build_report(self.root)

    def test_tampered_original_html_fails_before_field_mapping(self):
        self.capture()
        sourcefile = self.root / "original-chart.html"
        sourcefile.write_bytes(sourcefile.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "source integrity mismatch"):
            batch.build_report(self.root)

    def test_source_lock_version_is_required(self):
        self.capture()
        lock = json.loads(batch.LOCK.read_text(encoding="utf-8"))
        lock["provider"]["version"] = "unapproved-master"
        alternative = self.tmp / "unsafe-research-lock.json"
        alternative.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, "untrusted research lead lock"):
            batch.build_report(self.root, lock_path=alternative)

    def test_replay_deterministic_under_same_raw_source(self):
        self.capture()
        first = batch.build_report(self.root)
        second = batch.build_report(self.root)
        self.assertEqual(first, second)
        self.assertEqual(first["source_original_sha256"],
                         source.replay(self.root)["original_byte_sha256"])


if __name__ == "__main__":
    unittest.main()
