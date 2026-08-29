#!/usr/bin/env python3
"""Browser-backed acquisition adapter for official ST product pages.

This research adapter exists because raw urllib/curl acquisition was not reliable
in the observed GitHub-hosted and Codex execution environments. It does not bypass
CAPTCHA/WAF controls, does not modify request headers to impersonate a browser,
and does not write canonical ICPN data. It returns rendered DOM HTML to the
existing fail-closed evidence parser.
"""

from __future__ import annotations

from typing import Any

from st_product_page_acquisition import (
    AcquisitionError,
    MAX_RESPONSE_BYTES,
    validate_source_url,
)

CHALLENGE_MARKERS = (
    "verify you are human",
    "access denied",
    "captcha",
    "request rejected",
)
QUALITY_HEADING = "Quality and Reliability"
PART_NUMBER_MARKER = "Part Number"


class STBrowserAcquirer:
    """Context-managed Chromium acquisition adapter."""

    def __init__(self, *, headless: bool = True) -> None:
        self.headless = headless
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._timeout_error: type[BaseException] | tuple[type[BaseException], ...] = Exception
        self._playwright_error: type[BaseException] | tuple[type[BaseException], ...] = Exception

    def __enter__(self) -> "STBrowserAcquirer":
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AcquisitionError(
                "Playwright is required for browser acquisition; "
                "install data/device-catalog/research/requirements-st-browser.txt "
                "and run `python -m playwright install chromium`"
            ) from exc

        self._timeout_error = PlaywrightTimeoutError
        self._playwright_error = PlaywrightError
        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=self.headless)
            self._context = self._browser.new_context()
        except Exception:
            self._playwright.stop()
            self._playwright = None
            raise
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None

    def fetch(self, source_url: str, timeout_seconds: float) -> tuple[bytes, str, None, None]:
        validate_source_url(source_url)
        if timeout_seconds <= 0:
            raise AcquisitionError("browser acquisition timeout must be positive")
        if self._context is None:
            raise AcquisitionError("browser acquirer must be used as a context manager")

        timeout_ms = int(timeout_seconds * 1000)
        page = self._context.new_page()
        try:
            response = page.goto(source_url, wait_until="domcontentloaded", timeout=timeout_ms)
            final_url = page.url
            validate_source_url(final_url)
            if response is not None and response.status >= 400:
                raise AcquisitionError(f"browser navigation returned HTTP {response.status}")

            page.get_by_role("heading", name=QUALITY_HEADING, exact=True).wait_for(
                state="visible", timeout=timeout_ms
            )
            page.get_by_text(PART_NUMBER_MARKER, exact=True).first.wait_for(
                state="visible", timeout=timeout_ms
            )
            body_text = page.locator("body").inner_text(timeout=timeout_ms)
            folded = body_text.casefold()
            for marker in CHALLENGE_MARKERS:
                if marker in folded:
                    raise AcquisitionError(
                        f"browser acquisition encountered challenge marker: {marker}"
                    )

            html_text = page.content()
            body = html_text.encode("utf-8")
            if len(body) > MAX_RESPONSE_BYTES:
                raise AcquisitionError(f"rendered page exceeds {MAX_RESPONSE_BYTES} bytes")
            return body, final_url, None, None
        except self._timeout_error as exc:
            raise AcquisitionError(f"browser acquisition timed out: {exc}") from exc
        except self._playwright_error as exc:
            raise AcquisitionError(f"browser acquisition failed: {exc}") from exc
        finally:
            page.close()
