#!/usr/bin/env python3
"""Offline synthetic XLSX tests; synthetic data is never manufacturer evidence."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape

import microchip_phase1_chart_xlsx_v1 as chart

NS = chart.MAIN_NS
REL = chart.OFFICE_REL_NS
RNS = chart.PACKAGE_REL_NS


def fixture_xlsx(path, *, duplicates=False, formula=False, extra_link=False,
                 use_shared=True):
    rows = [
        ("Device", "Flash (KB)", "VDD (V)"),
        ("ATSAMD21G18A", "256", "1.62–3.63"),
        ("ATSAML11E16A", "64", "1.62–3.63"),
        ("AVR32DA28", "32", "1.8–5.5"),
    ]
    if duplicates:
        rows.append(rows[1])
    shared = ["Device", "Flash (KB)", "VDD (V)"]
    def cell(label, value, row):
        if use_shared and row == 1:
            return f'<c r="{label}{row}" t="s"><v>{shared.index(value)}</v></c>'
        if formula and row == 2 and label == "B":
            return f'<c r="{label}{row}"><f>1+1</f><v>2</v></c>'
        return (f'<c r="{label}{row}" t="inlineStr"><is><t>'
                f'{escape(value)}</t></is></c>')
    contents = "".join(
        f'<row r="{i}">' + "".join(
            cell(chr(65+j), value, i) for j, value in enumerate(values)
        ) + '</row>' for i, values in enumerate(rows, 1)
    )
    with ZipFile(path, "w", ZIP_DEFLATED) as out:
        out.writestr("xl/workbook.xml", (
            f'<workbook xmlns="{NS}" xmlns:r="{REL}"><sheets>'
            '<sheet name="MCUs" sheetId="1" r:id="rId1"/>'
            '</sheets></workbook>'))
        out.writestr("xl/_rels/workbook.xml.rels", (
            f'<Relationships xmlns="{RNS}"><Relationship Id="rId1" '
            f'Type="{REL}/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>'))
        out.writestr("xl/worksheets/sheet1.xml",
                     f'<worksheet xmlns="{NS}"><sheetData>{contents}'
                     '</sheetData></worksheet>')
        if use_shared:
            out.writestr("xl/sharedStrings.xml", (
                f'<sst xmlns="{NS}">' + "".join(
                    f'<si><t>{escape(value)}</t></si>' for value in shared
                ) + '</sst>'))
        if extra_link:
            out.writestr("xl/externalLinks/externalLink1.xml", "<x/>")


def config():
    return {
        "chart_url": "https://www.microchip.com/en-us/products/microcontrollers",
        "chart_scope": "Synthetic test chart only; not an official manufacturer capture",
        "worksheet": "MCUs",
        "captured_at_utc": "2026-10-14T03:30:00Z",
        "columns": {
            "base_device": {"header": "Device", "unit": None},
            "flash": {"header": "Flash (KB)", "unit": "KB"},
            "vdd": {"header": "VDD (V)", "unit": "V"}
        }
    }


class Phase1ChartTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "synthetic.xlsx"
        fixture_xlsx(self.file)

    def test_priority_cohort_and_no_exact_admission(self):
        report = chart.generate(self.file, config())
        self.assertEqual(report["counts"],
                         {"chart_base_device_rows": 3, "P0": 1, "P1": 1, "P2": 1,
                          "exact_icpn_rows_verified": 0, "production_admitted": 0})
        self.assertEqual([r["priority"] for r in report["records"]],
                         ["P0", "P1", "P2"])
        self.assertEqual([r["base_device_observed"] for r in report["records"]],
                         ["ATSAMD21G18A", "ATSAML11E16A", "AVR32DA28"])
        self.assertEqual(report["classification"]["pinned_openocd_version"], "0.12.0")
        self.assertTrue(report["classification"]["p0_p1_are_not_supported"])
        self.assertEqual(report["records"][0]["pinned_source_lead_id"],
                         "sam-d-c-r-l0")
        self.assertEqual(report["records"][1]["pinned_source_lead_id"],
                         "sam-l1x-target-only")
        self.assertEqual(report["records"][0]["fields"]["flash"]["status"], "PARTIAL")
        self.assertEqual(report["records"][0]["fields"]["flash"]["raw_value"], "256")
        self.assertEqual(report["records"][0]["fields"]["ram"]["status"], "UNKNOWN")
        self.assertEqual(report["records"][0]["fields"]["flash"]["unit"], "KB")
        self.assertTrue(report["records"][2]["archive_only"])
        self.assertNotIn("fields", report["records"][2])
        self.assertFalse(report["production_write_authorized"])
        self.assertFalse(report["manufacturer_population_complete"])
        self.assertIsNone(report["exact_icpn_software_supported_count"])

    def test_capture_hash_and_repeatable_output(self):
        a = chart.generate(self.file, config())
        b = chart.generate(self.file, config())
        self.assertEqual(a, b)
        self.assertEqual(a["chart"]["original_byte_sha256"],
                         hashlib.sha256(self.file.read_bytes()).hexdigest())
        self.assertFalse(a["chart"]["original_bytes_embedded"])
        fixture_xlsx(self.file, use_shared=False)
        changed = chart.generate(self.file, config())
        self.assertNotEqual(a["chart"]["original_byte_sha256"],
                            changed["chart"]["original_byte_sha256"])

    def test_no_sku_or_openocd_support_claim_from_chart(self):
        report = chart.generate(self.file, config())
        for row in report["records"]:
            self.assertEqual(row["internal_admission_state"], "NOT_ADMITTED")
            self.assertFalse(row["exact_icpn_verified"])
            self.assertFalse(row["software_supported_claimed"])
        self.assertEqual(report["counts"]["exact_icpn_rows_verified"], 0)

    def test_duplicate_base_device_rejected(self):
        fixture_xlsx(self.file, duplicates=True)
        with self.assertRaisesRegex(ValueError, "duplicate chart base device"):
            chart.generate(self.file, config())

    def test_formula_rejected(self):
        fixture_xlsx(self.file, formula=True)
        with self.assertRaisesRegex(ValueError, "formula cell prohibited"):
            chart.generate(self.file, config())

    def test_external_link_rejected(self):
        fixture_xlsx(self.file, extra_link=True)
        with self.assertRaisesRegex(ValueError, "external links/macros"):
            chart.generate(self.file, config())

    def test_chart_scope_url_and_header_required(self):
        cfg = config()
        cfg["chart_url"] = "https://evil.example.com/chart"
        with self.assertRaisesRegex(ValueError, "official Microchip chart URL"):
            chart.generate(self.file, cfg)
        cfg = config()
        cfg["columns"]["flash"]["header"] = "Invented Header"
        with self.assertRaisesRegex(ValueError, "required chart column"):
            chart.generate(self.file, cfg)

    def test_numeric_source_unit_cannot_be_guessed(self):
        cfg = config()
        cfg["columns"]["flash"]["unit"] = None
        with self.assertRaisesRegex(ValueError, "numeric/range chart fields require"):
            chart.generate(self.file, cfg)

    def test_source_lock_pin_required(self):
        lock = json.loads(chart.LOCK.read_text(encoding="utf-8"))
        lock["provider"]["version"] = "unreviewed-latest"
        fake = Path(self.temp.name) / "altered-lock.json"
        fake.write_text(json.dumps(lock), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "untrusted/mismatched"):
            chart.generate(self.file, config(), lock_path=fake)

    def test_missing_sheet_fails_closed(self):
        cfg = config()
        cfg["worksheet"] = "Other"
        with self.assertRaisesRegex(ValueError, "required worksheet"):
            chart.generate(self.file, cfg)


if __name__ == "__main__":
    unittest.main()
