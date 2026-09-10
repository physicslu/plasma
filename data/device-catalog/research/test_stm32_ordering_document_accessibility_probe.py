#!/usr/bin/env python3
from __future__ import annotations

import unittest

from stm32_ordering_document_accessibility_probe import (
    EXPECTED_TARGET_COUNT,
    REQUIRED_ORDERING_LABELS,
    Target,
    choose_datasheet_url,
    datasheet_urls_from_html,
    inspect_pdf_text,
    probe_is_clean,
    read_manifest,
    run_probe,
)

GOOD_TEXT = " ".join([
    "STM32U031 STM32U073 STM32U083 STM32C011 STM32C031 STM32C051 STM32C071 STM32C091 STM32C092",
    "8 Ordering information",
    *REQUIRED_ORDERING_LABELS,
    "Packing TR tape and reel",
    "DS14463 - Rev 2",
])


def html_for(base: str) -> bytes:
    return f'<html><body><a href="https://www.st.com/resource/en/datasheet/{base.lower()}.pdf">Download datasheet</a></body></html>'.encode()


class Tests(unittest.TestCase):
    def test_manifest_is_exact_retained_u0_c0_subset(self) -> None:
        pilot, targets = read_manifest()
        self.assertTrue(pilot)
        self.assertEqual(len(targets), EXPECTED_TARGET_COUNT)
        self.assertEqual([t.series for t in targets], ["STM32U0"] * 3 + ["STM32C0"] * 6)

    def test_datasheet_link_extraction_is_official_only(self) -> None:
        html = '<a href="/resource/en/datasheet/stm32u031c6.pdf">good</a><a href="https://evil.example/a.pdf">bad</a>'
        self.assertEqual(datasheet_urls_from_html(html, "https://www.st.com/en/microcontrollers-microprocessors/stm32u031c6.html"), ["https://www.st.com/resource/en/datasheet/stm32u031c6.pdf"])

    def test_choose_prefers_exact_base_slug(self) -> None:
        urls = ["https://www.st.com/resource/en/datasheet/shared.pdf", "https://www.st.com/resource/en/datasheet/stm32c031c4.pdf"]
        self.assertEqual(choose_datasheet_url(urls, "STM32C031C4"), (urls[1], False))

    def test_single_shared_datasheet_is_explicit(self) -> None:
        url = "https://www.st.com/resource/en/datasheet/stm32c091xc-stm32c092xc.pdf"
        self.assertEqual(choose_datasheet_url([url], "STM32C091CB"), (url, True))

    def test_ordering_text_contract(self) -> None:
        result = inspect_pdf_text(GOOD_TEXT, "STM32U031")
        self.assertTrue(result["ordering_schema_complete"])
        self.assertEqual(result["document_id"], "DS14463")
        self.assertEqual(result["revision"], 2)

    def test_all_accessible_probe_stays_nonselecting(self) -> None:
        _, targets = read_manifest()
        def product_fetch(url: str, timeout: float):
            del timeout
            base = next(t.base_device for t in targets if t.product_url == url)
            return html_for(base), url, None, None
        def pdf_fetch(url: str, timeout: float):
            del timeout
            return b"%PDF-FAKE", url, "application/pdf"
        summary = run_probe(pilot_id="test", targets=targets, product_fetcher=product_fetch, pdf_fetcher=pdf_fetch, text_extractor=lambda _: GOOD_TEXT)
        self.assertTrue(probe_is_clean(summary))
        self.assertIsNone(summary["selected_next_research_family"])
        self.assertEqual(summary["by_series"]["STM32U0"]["accessible_targets"], 3)
        self.assertEqual(summary["by_series"]["STM32C0"]["accessible_targets"], 6)

    def test_missing_datasheet_is_dispositioned_not_selected(self) -> None:
        targets = [Target("STM32U0", "STM32U031", "STM32U031C6", "https://www.st.com/en/microcontrollers-microprocessors/stm32u031c6.html")]
        summary = run_probe(
            pilot_id="test",
            targets=targets,
            product_fetcher=lambda url, timeout: (b"<html></html>", url, None, None),
            pdf_fetcher=lambda url, timeout: (b"%PDF", url, "application/pdf"),
            text_extractor=lambda _: GOOD_TEXT,
        )
        self.assertEqual(summary["results"][0]["disposition"], "document_unavailable")
        self.assertIsNone(summary["selected_next_research_family"])

    def test_incomplete_ordering_contract_fails_closed_to_manual_review(self) -> None:
        target = Target("STM32U0", "STM32U031", "STM32U031C6", "https://www.st.com/en/microcontrollers-microprocessors/stm32u031c6.html")
        summary = run_probe(
            pilot_id="test",
            targets=[target],
            product_fetcher=lambda url, timeout: (html_for(target.base_device), url, None, None),
            pdf_fetcher=lambda url, timeout: (b"%PDF-FAKE", url, "application/pdf"),
            text_extractor=lambda _: "STM32U031 Ordering information",
        )
        self.assertEqual(summary["results"][0]["disposition"], "manual_review")


if __name__ == "__main__":
    unittest.main()
