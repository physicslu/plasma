#!/usr/bin/env python3
"""Model-free fixtures for official ST selector-export preflight.

Synthetic sources MUST NEVER be used as live manufacturer evidence.
"""
from __future__ import annotations

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import preflight_st_selector_export as preflight


def make_xlsx() -> bytes:
    strings = ["Commercial Part Number", "Marketing Status", "Series",
               "STM32H503CBT6", "Active", "STM32H5"]
    lookup = {s: i for i, s in enumerate(strings)}
    def shared_cell(ref: str, value: str) -> str:
        return f'<c r="{ref}" t="s"><v>{lookup[value]}</v></c>'
    def inline_cell(ref: str, value: str) -> str:
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        '<row r="1">' + inline_cell("A1", "MCU selector export") + '</row>'
        '<row r="2">' +
        shared_cell("A2", "Commercial Part Number") +
        shared_cell("B2", "Marketing Status") +
        shared_cell("C2", "Series") + '</row>'
        '<row r="3">' +
        shared_cell("A3", "STM32H503CBT6") +
        shared_cell("B3", "Active") +
        shared_cell("C3", "STM32H5") + '</row>'
        '</sheetData></worksheet>'
    )
    noncandidate = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetData><row r="1">' + inline_cell("A1", "Filters") +
        '</row></sheetData></worksheet>'
    )
    shared = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(strings)}" uniqueCount="{len(strings)}">' +
        ''.join(f'<si><t>{escape(value)}</t></si>' for value in strings) +
        '</sst>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="MCU Selector" sheetId="1" r:id="rId1"/>'
        '<sheet name="Filters" sheetId="2" r:id="rId2"/></sheets></workbook>'
    )
    relationships = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet2.xml"/></Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in {
            "xl/workbook.xml": workbook,
            "xl/_rels/workbook.xml.rels": relationships,
            "xl/sharedStrings.xml": shared,
            "xl/worksheets/sheet1.xml": xml,
            "xl/worksheets/sheet2.xml": noncandidate,
        }.items():
            archive.writestr(name, content)
    return buffer.getvalue()


class STPreflightTest(unittest.TestCase):
    def test_csv_mixed_active_nonactive_and_wildcard_fail_closed(self) -> None:
        raw = (
            "Commercial Part Number,Marketing Status,Series\n"
            "STM32H503CBT6,Active,STM32H5\n"
            "STM32H503CBT6,Active,STM32H5\n"
            "STM32H503CBT6TR,Active,STM32H5\n"
            "STM32F030C6T6,Active,STM32F0\n"
            "STM32F030C6Tx,Active,STM32F0\n"
            "STM32C531CBT6,Proposal,STM32C5\n"
            "STM32WL33CCV6,NRND,STM32WL3\n"
            "NUCLEO-F030R8,Active,Board\n"
        ).encode()
        _, _, rows, available = preflight.table_from_export("selection.csv", raw)
        self.assertTrue(available)
        data = preflight.analyze_rows(rows, {"STM32F030C6T6"})
        self.assertEqual(data["total_nonblank_data_rows"], 8)
        self.assertEqual(data["observed_active_exact_count"], 3)
        self.assertEqual(data["observed_active_in_production_count"], 1)
        self.assertEqual(data["observed_active_not_in_production"],
                         ["STM32H503CBT6", "STM32H503CBT6TR"])
        self.assertEqual([x["icpn"] for x in data["observed_nonactive"]],
                         ["STM32C531CBT6", "STM32WL33CCV6"])
        self.assertEqual(len(data["pattern_or_nonexact_rows"]), 1)
        self.assertEqual(data["non_stm32_rows"][0]["raw_identifier"], "NUCLEO-F030R8")
        self.assertNotIn("STM32F030C6TX", data["observed_active_exact_icpns"])
        self.assertFalse(data["input_quality_ready_for_review"])
        self.assertIsNone(data["actual_active_st_coverage_percent"])

    def test_conflicting_lifecycle_is_not_admitted(self) -> None:
        rows = [
            {"source_row": "2", "mpn": "STM32H503CBT6", "marketing_status": "Active"},
            {"source_row": "3", "mpn": "STM32H503CBT6", "marketing_status": "Obsolete"},
            {"source_row": "4", "mpn": "STM32C531CBT6", "marketing_status": "?", "family": "C5"},
            {"source_row": "5", "mpn": "STM32WL33CCV6", "marketing_status": "not recommended for new designs"},
        ]
        data = preflight.analyze_rows(rows, set())
        self.assertEqual(data["observed_active_exact_count"], 0)
        self.assertEqual(data["conflicting_lifecycle"],
                         [{"icpn": "STM32H503CBT6", "observed_statuses": ["Active", "Obsolete"]}])
        self.assertEqual(data["unknown_lifecycle_identities"], ["STM32C531CBT6"])
        self.assertEqual(data["observed_nonactive"],
                         [{"icpn": "STM32WL33CCV6", "status": "NRND"}])
        self.assertFalse(data["input_quality_ready_for_review"])

    def test_missing_marketing_status_never_infers_active(self) -> None:
        _, _, rows, has_status = preflight.table_from_export(
            "mcu_selector.csv", b"Part Number,Series\nSTM32H503CBT6,H5\n")
        self.assertFalse(has_status)
        data = preflight.analyze_rows(rows, set())
        self.assertEqual(data["observed_active_exact_count"], 0)
        self.assertEqual(data["unknown_lifecycle_identities"], ["STM32H503CBT6"])

    def test_export_provenance_exact_sha256_and_full_scope_rejected(self) -> None:
        data = b"Part Number,Marketing Status\nSTM32H503CBT6,Active\n"
        provenance = {
            "schema_version": 1,
            "source_kind": "STM32CubeMX_MCU_Selector",
            "official_source_url": "https://www.st.com/en/development-tools/stm32cubemx.html",
            "tool_version": "6.18.1",
            "acquired_at_utc": "2026-09-29T06:00:00Z",
            "raw_export_sha256": hashlib.sha256(data).hexdigest(),
            "filter_disclosure": {
                "device_scope": "STM32 MCU only",
                "marketing_status": "all",
                "other_filters": "none",
            },
            "full_portfolio_completeness_reviewed": False,
        }
        preflight.validate_provenance(provenance, data)
        changed = provenance | {"raw_export_sha256": "0" * 64}
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            preflight.validate_provenance(changed, data)
        changed = provenance | {"full_portfolio_completeness_reviewed": True}
        with self.assertRaisesRegex(ValueError, "preflight is not"):
            preflight.validate_provenance(changed, data)
        changed = provenance | {"official_source_url": "https://example.net/mcu.xlsx"}
        with self.assertRaisesRegex(ValueError, "official ST domain"):
            preflight.validate_provenance(changed, data)

    def test_xlsx_shared_strings_and_two_worksheets(self) -> None:
        raw = make_xlsx()
        sheet, headers, rows, status_available = preflight.table_from_export(
            "mcu_export.xlsx", raw)
        self.assertEqual(sheet, "MCU Selector")
        self.assertTrue(status_available)
        self.assertEqual(headers,
                         ["Commercial Part Number", "Marketing Status", "Series"])
        self.assertEqual(rows[0]["mpn"], "STM32H503CBT6")
        self.assertEqual(rows[0]["marketing_status"], "Active")
        self.assertEqual(rows[0]["source_row"], "3")
        data = preflight.analyze_rows(rows, set())
        self.assertEqual(data["observed_active_not_in_production"],
                         ["STM32H503CBT6"])
        with self.assertRaisesRegex(ValueError, "exactly one selector table"):
            preflight.table_from_export("mcu_export.xlsx", raw, "Bad Sheet")

    def test_frozen_production_baseline_all_23_sources(self) -> None:
        identities, baseline = preflight.production_set()
        self.assertEqual(len(identities), 2683)
        self.assertEqual(baseline["production_baseline"]["integrity_bound_source_count"], 23)
        for sku in preflight.SENTINELS:
            self.assertNotIn(sku, identities)


if __name__ == "__main__":
    unittest.main()
