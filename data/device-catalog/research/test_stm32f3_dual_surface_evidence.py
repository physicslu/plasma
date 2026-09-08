#!/usr/bin/env python3
from __future__ import annotations

import unittest

from st_product_page_acquisition import AcquisitionError
from stm32f3_dual_surface_evidence import (
    EVIDENCE_SURFACE,
    build_dual_surface_browser_evidence_record,
    dual_surface_ready,
    extract_dual_surface_part_number_records,
)

BASE = "STM32F301C6"
URL = "https://www.st.com/en/microcontrollers-microprocessors/stm32f301c6.html"


def page(*, lifecycle_rows: str, quality_extra: str = "") -> str:
    return f"""
    <html><body>
      <h2>Quality and Reliability</h2>
      <table>
        <tr><th>Part Number</th><th>RoHS Compliance Grade</th><th>Grade</th></tr>
        <tr><td>STM32F301C6T6</td><td>Ecopack2</td><td>Industrial</td></tr>
        <tr><td>STM32F301C6T6TR</td><td>Ecopack2</td><td>Industrial</td></tr>
        <tr><td>STM32F301C6T7</td><td>Ecopack2</td><td>Industrial</td></tr>
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
<tr><td>STM32F301C6T6</td><td>Active Product is in volume production.</td><td>LQFP48</td></tr>
<tr><td>STM32F301C6T6TR</td><td>Active Product is in volume production.</td><td>LQFP48</td></tr>
<tr><td>STM32F301C6T7</td><td>Active Product is in volume production.</td><td>LQFP48</td></tr>
"""


class STM32F3DualSurfaceEvidenceTests(unittest.TestCase):
    def test_exact_identity_and_lifecycle_join_cleanly(self) -> None:
        html = page(lifecycle_rows=ACTIVE_ROWS)
        records, canonical_text = extract_dual_surface_part_number_records(html, BASE)
        self.assertEqual(
            [record["icpn"] for record in records],
            ["STM32F301C6T6", "STM32F301C6T6TR", "STM32F301C6T7"],
        )
        self.assertEqual([record["active"] for record in records], [True, True, True])
        self.assertIn("Sample & Buy lifecycle projection", canonical_text)
        self.assertTrue(dual_surface_ready(html, BASE))

    def test_evidence_record_marks_distinct_dual_surface_profile(self) -> None:
        html = page(lifecycle_rows=ACTIVE_ROWS)
        evidence = build_dual_surface_browser_evidence_record(
            body=html.encode("utf-8"),
            source_url=URL,
            final_url=URL,
            base_device=BASE,
            retrieved_at_utc="2026-09-08T00:00:00Z",
        )
        self.assertEqual(evidence["evidence_surface"], EVIDENCE_SURFACE)
        self.assertEqual(evidence["parser_profile"], "stm32f3_dual_surface_v1")
        self.assertEqual(len(evidence["exact_icpns"]), 3)
        self.assertEqual(evidence["excluded_non_active_part_numbers"], [])
        self.assertRegex(str(evidence["evidence_section_sha256"]), r"^[0-9a-f]{64}$")

    def test_non_active_lifecycle_is_retained_but_not_active(self) -> None:
        rows = ACTIVE_ROWS.replace(
            "<tr><td>STM32F301C6T7</td><td>Active Product is in volume production.</td>",
            "<tr><td>STM32F301C6T7</td><td>NRND Not Recommended for New Designs.</td>",
        )
        evidence = build_dual_surface_browser_evidence_record(
            body=page(lifecycle_rows=rows).encode("utf-8"),
            source_url=URL,
            final_url=URL,
            base_device=BASE,
            retrieved_at_utc="2026-09-08T00:00:00Z",
        )
        self.assertEqual(
            evidence["exact_icpns"],
            ["STM32F301C6T6", "STM32F301C6T6TR"],
        )
        self.assertEqual(
            evidence["excluded_non_active_part_numbers"],
            [{
                "icpn": "STM32F301C6T7",
                "marketing_status": "NRND Not Recommended for New Designs.",
            }],
        )

    def test_missing_lifecycle_identity_fails_closed(self) -> None:
        rows = ACTIVE_ROWS.replace(
            "<tr><td>STM32F301C6T7</td><td>Active Product is in volume production.</td><td>LQFP48</td></tr>",
            "",
        )
        with self.assertRaisesRegex(AcquisitionError, "exact ICPN set mismatch"):
            extract_dual_surface_part_number_records(page(lifecycle_rows=rows), BASE)
        self.assertFalse(dual_surface_ready(page(lifecycle_rows=rows), BASE))

    def test_extra_lifecycle_identity_fails_closed(self) -> None:
        rows = ACTIVE_ROWS + (
            "<tr><td>STM32F301C8T6</td>"
            "<td>Active Product is in volume production.</td><td>LQFP48</td></tr>"
        )
        with self.assertRaisesRegex(AcquisitionError, "foreign STM32"):
            extract_dual_surface_part_number_records(page(lifecycle_rows=rows), BASE)

    def test_foreign_quality_identity_fails_closed(self) -> None:
        html = page(
            lifecycle_rows=ACTIVE_ROWS,
            quality_extra="<div>STM32F302C6T6</div>",
        )
        with self.assertRaisesRegex(AcquisitionError, "foreign STM32"):
            extract_dual_surface_part_number_records(html, BASE)

    def test_sample_buy_without_marketing_status_fails_closed(self) -> None:
        html = page(lifecycle_rows=ACTIVE_ROWS).replace(
            "<th>Marketing Status</th>",
            "<th>Status unavailable</th>",
        )
        with self.assertRaisesRegex(AcquisitionError, "Marketing Status"):
            extract_dual_surface_part_number_records(html, BASE)
        self.assertFalse(dual_surface_ready(html, BASE))


if __name__ == "__main__":
    unittest.main()
