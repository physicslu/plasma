#!/usr/bin/env python3
from __future__ import annotations

import unittest

from st_product_page_acquisition import AcquisitionError
from stm32f7_dual_surface_evidence import (
    EVIDENCE_SURFACE,
    PARSER_PROFILE,
    build_dual_surface_browser_evidence_record,
    dual_surface_ready,
    extract_dual_surface_part_number_records,
)

BASE = "STM32F722IC"
URL = "https://www.st.com/en/microcontrollers-microprocessors/stm32f722ic.html"


def page(*, lifecycle_rows: str, quality_extra: str = "") -> str:
    return f"""
    <html><body>
      <h2>Quality and Reliability</h2>
      <table>
        <tr><th>Part Number</th><th>RoHS Compliance Grade</th><th>Grade</th></tr>
        <tr><td>STM32F722ICK6</td><td>Ecopack2</td><td>Industrial</td></tr>
        <tr><td>STM32F722ICT6</td><td>Ecopack2</td><td>Industrial</td></tr>
      </table>
      {quality_extra}
      <h2>Sample &amp; Buy</h2>
      <table>
        <tr><th>Part Number</th><th>Marketing Status</th><th>Package</th></tr>
        {lifecycle_rows}
      </table>
      <h2>Documentation</h2>
    </body></html>
    """


ACTIVE_ROWS = """
<tr><td>STM32F722ICK6</td><td>Active Product is in volume production.</td><td>UFBGA176</td></tr>
<tr><td>STM32F722ICT6</td><td>Active Product is in volume production.</td><td>LQFP176</td></tr>
"""


class STM32F7DualSurfaceEvidenceTests(unittest.TestCase):
    def test_exact_identity_and_lifecycle_join_cleanly(self) -> None:
        html = page(lifecycle_rows=ACTIVE_ROWS)
        records, canonical_text = extract_dual_surface_part_number_records(html, BASE)
        self.assertEqual(
            [record["icpn"] for record in records],
            ["STM32F722ICK6", "STM32F722ICT6"],
        )
        self.assertEqual([record["active"] for record in records], [True, True])
        self.assertIn("Sample & Buy lifecycle projection", canonical_text)
        self.assertTrue(dual_surface_ready(html, BASE))

    def test_evidence_record_uses_stm32f7_owned_profile(self) -> None:
        evidence = build_dual_surface_browser_evidence_record(
            body=page(lifecycle_rows=ACTIVE_ROWS).encode("utf-8"),
            source_url=URL,
            final_url=URL,
            base_device=BASE,
            retrieved_at_utc="2026-09-09T00:00:00Z",
        )
        self.assertEqual(evidence["evidence_surface"], EVIDENCE_SURFACE)
        self.assertEqual(evidence["parser_profile"], PARSER_PROFILE)
        self.assertEqual(PARSER_PROFILE, "stm32f7_dual_surface_v1")
        self.assertEqual(evidence["exact_icpns"], ["STM32F722ICK6", "STM32F722ICT6"])
        self.assertEqual(evidence["excluded_non_active_part_numbers"], [])
        self.assertRegex(str(evidence["evidence_section_sha256"]), r"^[0-9a-f]{64}$")

    def test_non_active_identity_is_retained_but_excluded_from_active_set(self) -> None:
        rows = ACTIVE_ROWS.replace(
            "<tr><td>STM32F722ICT6</td><td>Active Product is in volume production.</td>",
            "<tr><td>STM32F722ICT6</td><td>NRND Not Recommended for New Designs.</td>",
        )
        evidence = build_dual_surface_browser_evidence_record(
            body=page(lifecycle_rows=rows).encode("utf-8"),
            source_url=URL,
            final_url=URL,
            base_device=BASE,
            retrieved_at_utc="2026-09-09T00:00:00Z",
        )
        self.assertEqual(evidence["exact_icpns"], ["STM32F722ICK6"])
        self.assertEqual(
            evidence["excluded_non_active_part_numbers"],
            [{
                "icpn": "STM32F722ICT6",
                "marketing_status": "NRND Not Recommended for New Designs.",
            }],
        )

    def test_missing_lifecycle_identity_fails_closed(self) -> None:
        rows = ACTIVE_ROWS.replace(
            "<tr><td>STM32F722ICT6</td><td>Active Product is in volume production.</td><td>LQFP176</td></tr>",
            "",
        )
        with self.assertRaisesRegex(AcquisitionError, "exact ICPN set mismatch"):
            extract_dual_surface_part_number_records(page(lifecycle_rows=rows), BASE)

    def test_foreign_identity_fails_closed(self) -> None:
        rows = ACTIVE_ROWS + (
            "<tr><td>STM32F723ICK6</td>"
            "<td>Active Product is in volume production.</td><td>UFBGA176</td></tr>"
        )
        with self.assertRaisesRegex(AcquisitionError, "foreign STM32"):
            extract_dual_surface_part_number_records(page(lifecycle_rows=rows), BASE)

    def test_missing_marketing_status_column_fails_closed(self) -> None:
        html = page(lifecycle_rows=ACTIVE_ROWS).replace(
            "<th>Marketing Status</th>", "<th>Status unavailable</th>"
        )
        with self.assertRaisesRegex(AcquisitionError, "Marketing Status"):
            extract_dual_surface_part_number_records(html, BASE)
        self.assertFalse(dual_surface_ready(html, BASE))


if __name__ == "__main__":
    unittest.main()
