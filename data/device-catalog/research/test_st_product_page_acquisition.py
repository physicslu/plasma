#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from st_product_page_acquisition import (  # noqa: E402
    AcquisitionError,
    build_evidence_record,
    extract_exact_icpns,
    extract_part_number_records,
    validate_source_url,
)


SYNTHETIC_HTML = """
<!doctype html>
<html>
  <body>
    <h1>Example device</h1>
    <h2>All resources</h2>
    <p>Unrelated text.</p>
    <h2>Quality and Reliability</h2>
    <table>
      <thead><tr><th>Part Number</th><th>Marketing Status</th><th>Grade</th></tr></thead>
      <tbody>
        <tr><td>STM32F103C8T6</td><td>Active Product is in volume production.</td><td>Industrial</td></tr>
        <tr><td>STM32F103C8T6TR</td><td>Active Product is in volume production.</td><td>Industrial</td></tr>
        <tr><td>STM32F103C8T7</td><td>Active Product is in volume production.</td><td>Industrial</td></tr>
        <tr><td>STM32F103C8T7TR</td><td>Active Product is in volume production.</td><td>Industrial</td></tr>
      </tbody>
    </table>
    <div>STM32F103C8T6</div>
    <h2>Sample &amp; Buy</h2>
    <div>STM32F103CBT6 must not be scanned outside the evidence section.</div>
  </body>
</html>
""".strip()


class ProductPageAcquisitionTests(unittest.TestCase):
    def test_extracts_unique_active_exact_icpns_from_quality_section(self) -> None:
        icpns, section_text = extract_exact_icpns(SYNTHETIC_HTML, "STM32F103C8")
        self.assertEqual(
            icpns,
            [
                "STM32F103C8T6",
                "STM32F103C8T6TR",
                "STM32F103C8T7",
                "STM32F103C8T7TR",
            ],
        )
        self.assertIn("Part Number", section_text)
        self.assertIn("Marketing Status", section_text)
        self.assertNotIn("STM32F103CBT6", section_text)

    def test_non_active_part_number_is_audited_but_not_admitted(self) -> None:
        html = """
        <h2>Quality and Reliability</h2>
        <table>
          <tr><th>Part Number</th><th>Marketing Status</th><th>Package</th></tr>
          <tr><td>STM32F446ZCT6</td><td>Active Product is in volume production.</td><td>LQFP 144</td></tr>
          <tr><td>STM32F446ZCT6TR</td><td>Active Product is in volume production.</td><td>LQFP 144</td></tr>
          <tr><td>STM32F446ZCT7</td><td>Proposal Customer feedback requested.</td><td>-</td></tr>
        </table>
        <h2>Sample &amp; Buy</h2>
        """
        records, _section = extract_part_number_records(html, "STM32F446ZC")
        self.assertEqual([record["icpn"] for record in records], [
            "STM32F446ZCT6",
            "STM32F446ZCT6TR",
            "STM32F446ZCT7",
        ])
        self.assertEqual([record["active"] for record in records], [True, True, False])
        icpns, _section = extract_exact_icpns(html, "STM32F446ZC")
        self.assertEqual(icpns, ["STM32F446ZCT6", "STM32F446ZCT6TR"])

        record = build_evidence_record(
            body=html.encode("utf-8"),
            source_url="https://www.st.com/en/microcontrollers-microprocessors/stm32f446zc.html",
            final_url="https://www.st.com/en/microcontrollers-microprocessors/stm32f446zc.html",
            base_device="STM32F446ZC",
            retrieved_at_utc="2026-08-30T00:00:00Z",
        )
        self.assertEqual(record["exact_icpns"], ["STM32F446ZCT6", "STM32F446ZCT6TR"])
        self.assertEqual(record["excluded_non_active_part_numbers"], [
            {"icpn": "STM32F446ZCT7", "marketing_status": "Proposal Customer feedback requested."}
        ])

    def test_evidence_record_hashes_raw_and_normalized_evidence(self) -> None:
        body = SYNTHETIC_HTML.encode("utf-8")
        record = build_evidence_record(
            body=body,
            source_url="https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html",
            final_url="https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html",
            base_device="STM32F103C8",
            retrieved_at_utc="2026-08-29T00:00:00Z",
        )
        self.assertEqual(record["schema_version"], 1)
        self.assertEqual(record["parser_version"], 2)
        self.assertEqual(
            record["evidence_surface"],
            "quality_and_reliability_part_number_marketing_status",
        )
        self.assertEqual(len(record["raw_sha256"]), 64)
        self.assertEqual(len(record["evidence_section_sha256"]), 64)
        self.assertEqual(len(record["exact_icpns"]), 4)
        self.assertEqual(len(record["part_number_records"]), 4)
        self.assertEqual(record["excluded_non_active_part_numbers"], [])

    def test_missing_quality_section_fails_closed(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "Quality and Reliability"):
            extract_exact_icpns("<h2>Other</h2><p>Part Number STM32F103C8T6</p>", "STM32F103C8")

    def test_missing_part_number_marker_fails_closed(self) -> None:
        html = "<h2>Quality and Reliability</h2><p>Marketing Status Active STM32F103C8T6</p><h2>Next</h2>"
        with self.assertRaisesRegex(AcquisitionError, "Part Number"):
            extract_exact_icpns(html, "STM32F103C8")

    def test_missing_marketing_status_marker_fails_closed(self) -> None:
        html = "<h2>Quality and Reliability</h2><p>Part Number STM32F103C8T6</p><h2>Next</h2>"
        with self.assertRaisesRegex(AcquisitionError, "Marketing Status"):
            extract_exact_icpns(html, "STM32F103C8")

    def test_foreign_stm32_token_in_evidence_section_fails_closed(self) -> None:
        html = """
        <h2>Quality and Reliability</h2>
        <table>
          <tr><th>Part Number</th><th>Marketing Status</th></tr>
          <tr><td>STM32F103C8T6</td><td>Active</td></tr>
          <tr><td>STM32F103CBT6</td><td>Active</td></tr>
        </table>
        <h2>Next</h2>
        """
        with self.assertRaisesRegex(AcquisitionError, "foreign STM32"):
            extract_exact_icpns(html, "STM32F103C8")

    def test_non_st_or_non_https_source_fails(self) -> None:
        bad_urls = [
            "http://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html",
            "https://example.com/en/microcontrollers-microprocessors/stm32f103c8.html",
            "https://estore.st.com/en/products/stm32f103c8.html",
        ]
        for url in bad_urls:
            with self.subTest(url=url):
                with self.assertRaises(AcquisitionError):
                    validate_source_url(url)


if __name__ == "__main__":
    unittest.main()
