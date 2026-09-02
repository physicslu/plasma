#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from st_browser_acquisition import (  # noqa: E402
    QUALITY_HEADING,
    STBrowserAcquirer,
)

TARGET_URL = "https://www.st.com/en/microcontrollers-microprocessors/stm32f411rc.html"
READY_HTML = """<!doctype html><html><body>
<h2>Quality and Reliability</h2>
<table><tr><th>Part Number</th><th>Marketing Status</th></tr>
<tr><td>STM32F411RCT6</td><td>Active Product is in volume production.</td></tr></table>
</body></html>"""
INCOMPLETE_QR_HTML = """<!doctype html><html><body>
<section class="quick-view"><p>Marketing Status</p><p>Active</p></section>
<h2>Quality and Reliability</h2>
<table><tr><th>Part Number</th></tr>
<tr><td>STM32F411RCT6</td></tr></table>
<h2>Sample and Buy</h2>
<table><tr><th>Marketing Status</th></tr></table>
</body></html>"""


class FakeTimeoutError(Exception):
    pass


class FakePlaywrightError(Exception):
    pass


class FakeWaitable:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def wait_for(self, *, state: str, timeout: int) -> None:
        self.calls.append((state, timeout))
        if self.error is not None:
            raise self.error


class FakeBody:
    def inner_text(self, *, timeout: int) -> str:
        del timeout
        return "Quality and Reliability Part Number Marketing Status STM32F411RCT6 Active"


class FakeResponse:
    status = 200


class FakePage:
    def __init__(
        self,
        *,
        html: str = READY_HTML,
        heading_error: Exception | None = None,
    ) -> None:
        self.url = TARGET_URL
        self.html = html
        self.closed = False
        self.requests: list[tuple[str, bool]] = []
        self.heading = FakeWaitable(heading_error)

    def goto(self, url: str, *, wait_until: str, timeout: int) -> FakeResponse:
        self.goto_call = (url, wait_until, timeout)
        return FakeResponse()

    def get_by_text(self, text: str, *, exact: bool) -> FakeWaitable:
        self.requests.append((text, exact))
        if text != QUALITY_HEADING:
            raise AssertionError(f"unexpected global readiness locator: {text}")
        return self.heading

    def locator(self, selector: str) -> FakeBody:
        self.selector = selector
        return FakeBody()

    def content(self) -> str:
        return self.html

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False

    def new_page(self) -> FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True


class RetryAcquirer(STBrowserAcquirer):
    def __init__(self, pages: list[FakePage]) -> None:
        super().__init__(navigation_attempts=len(pages))
        self.pages = pages
        self.page_index = 0
        self._playwright = object()
        self._timeout_error = FakeTimeoutError
        self._playwright_error = FakePlaywrightError
        self._rotate_browser_after_fetch = True
        self._context = FakeContext(self.pages[0])

    def _launch_browser(self) -> None:
        self.page_index += 1
        self._context = FakeContext(self.pages[self.page_index])
        self._browser = None


class BrowserReadinessRetryTests(unittest.TestCase):
    def test_qr_parser_surface_is_the_readiness_contract(self) -> None:
        self.assertTrue(STBrowserAcquirer._quality_surface_ready(READY_HTML))
        self.assertFalse(STBrowserAcquirer._quality_surface_ready(INCOMPLETE_QR_HTML))

    def test_evidence_surface_waits_for_quality_heading_and_parser_markers(self) -> None:
        page = FakePage()
        acquirer = STBrowserAcquirer()
        acquirer._context = FakeContext(page)
        acquirer._timeout_error = FakeTimeoutError
        acquirer._playwright_error = FakePlaywrightError

        body, final_url, etag, last_modified = acquirer.fetch(TARGET_URL, 5.0)

        self.assertEqual(body.decode("utf-8"), READY_HTML)
        self.assertEqual(final_url, TARGET_URL)
        self.assertIsNone(etag)
        self.assertIsNone(last_modified)
        self.assertEqual(page.requests, [(QUALITY_HEADING, True)])
        self.assertTrue(page.closed)

    def test_unrelated_marketing_status_does_not_satisfy_qr_readiness(self) -> None:
        first = FakePage(html=INCOMPLETE_QR_HTML)
        second = FakePage()
        acquirer = RetryAcquirer([first, second])

        body, final_url, _, _ = acquirer.fetch(TARGET_URL, 0.001)

        self.assertEqual(body.decode("utf-8"), READY_HTML)
        self.assertEqual(final_url, TARGET_URL)
        self.assertTrue(first.closed)
        self.assertTrue(second.closed)
        self.assertEqual(first.requests, [(QUALITY_HEADING, True)])
        self.assertEqual(second.requests, [(QUALITY_HEADING, True)])


if __name__ == "__main__":
    unittest.main()
