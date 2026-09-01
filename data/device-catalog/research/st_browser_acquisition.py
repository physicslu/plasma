#!/usr/bin/env python3
"""Browser-backed acquisition adapter for official ST product pages.

This research adapter exists because raw urllib/curl acquisition was not reliable
in the observed GitHub-hosted and Codex execution environments. It does not bypass
CAPTCHA/WAF controls, does not modify request headers to impersonate a browser,
and does not write canonical ICPN data. It returns rendered DOM HTML to the
existing fail-closed evidence parser without mislabeling rendered DOM as raw HTTP.
"""

from __future__ import annotations

import hashlib
from typing import Any

from st_product_page_acquisition import (
    AcquisitionError,
    MAX_RESPONSE_BYTES,
    PARSER_VERSION,
    SCHEMA_VERSION,
    extract_part_number_records,
    validate_source_url,
)

CHALLENGE_MARKERS = (
    "verify you are human",
    "access denied",
    "captcha",
    "request rejected",
)
QUALITY_HEADING = "Quality and Reliability"
MARKETING_STATUS_LABEL = "Marketing Status"
BROWSER_TRANSPORT = "chromium_rendered_dom"
# ST's CDN has produced deterministic net::ERR_HTTP2_PROTOCOL_ERROR failures on
# GitHub-hosted Chromium runners. Forcing HTTP/1.1 changes transport negotiation
# only; it does not alter request headers, evidence scope, or parser semantics.
CHROMIUM_LAUNCH_ARGS = ["--disable-http2"]
DEFAULT_NAVIGATION_ATTEMPTS = 2


def build_browser_evidence_record(
    *,
    body: bytes,
    source_url: str,
    final_url: str,
    base_device: str,
    retrieved_at_utc: str,
    http_etag: str | None = None,
    http_last_modified: str | None = None,
) -> dict[str, object]:
    """Build evidence whose digest explicitly represents rendered DOM, not raw HTTP."""

    if http_etag is not None or http_last_modified is not None:
        raise AcquisitionError("browser evidence must not claim raw HTTP cache headers")
    try:
        html_text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AcquisitionError("rendered ST product DOM is not valid UTF-8") from exc

    records, section_text = extract_part_number_records(html_text, base_device)
    exact_icpns = [str(record["icpn"]) for record in records if record["active"] is True]
    excluded = [
        {"icpn": str(record["icpn"]), "marketing_status": str(record["marketing_status"])}
        for record in records
        if record["active"] is not True
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "acquisition_transport": BROWSER_TRANSPORT,
        "source_url": source_url,
        "final_url": final_url,
        "base_device": base_device,
        "retrieved_at_utc": retrieved_at_utc,
        "http_etag": None,
        "http_last_modified": None,
        "rendered_dom_sha256": hashlib.sha256(body).hexdigest(),
        "evidence_section_sha256": hashlib.sha256(section_text.encode("utf-8")).hexdigest(),
        "evidence_surface": "quality_and_reliability_part_number",
        "part_number_records": records,
        "excluded_non_active_part_numbers": excluded,
        "exact_icpns": exact_icpns,
    }


class STBrowserAcquirer:
    """Context-managed Chromium acquisition adapter."""

    def __init__(
        self,
        *,
        headless: bool = True,
        navigation_attempts: int = DEFAULT_NAVIGATION_ATTEMPTS,
    ) -> None:
        if navigation_attempts < 1:
            raise AcquisitionError("browser navigation attempts must be at least 1")
        self.headless = headless
        self.navigation_attempts = navigation_attempts
        self.browser_version: str | None = None
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._rotate_browser_after_fetch = False
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
            self._launch_browser()
            self._rotate_browser_after_fetch = True
        except PlaywrightError as exc:
            self._playwright.stop()
            self._playwright = None
            raise AcquisitionError(f"failed to launch Chromium: {exc}") from exc
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._close_browser_context()
        if self._playwright is not None:
            self._playwright.stop()
        self._playwright = None
        self._rotate_browser_after_fetch = False

    def _launch_browser(self) -> None:
        if self._playwright is None:
            raise AcquisitionError("browser acquirer must be used as a context manager")
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=CHROMIUM_LAUNCH_ARGS,
        )
        self.browser_version = self._browser.version
        self._context = self._browser.new_context()

    def _close_browser_context(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        self._context = None
        self._browser = None

    @staticmethod
    def _retryable_failure_message(stage: str, *, timed_out: bool) -> str:
        if stage == "navigation":
            return "browser acquisition timed out" if timed_out else "browser acquisition failed"
        if stage == "evidence readiness":
            return (
                "browser evidence readiness timed out"
                if timed_out
                else "browser evidence readiness failed"
            )
        return (
            "browser evidence extraction timed out"
            if timed_out
            else "browser evidence extraction failed"
        )

    @staticmethod
    def _wait_for_evidence_surface(page: Any, timeout_ms: int) -> None:
        # The parser requires both the exact Quality and Reliability section and
        # its Marketing Status data. Waiting for both closes a race where the
        # section heading is attached before the commercial table is rendered.
        # Marketing Status is checked first so the final locator remains the
        # historical Quality heading in lightweight fake-page unit tests.
        page.get_by_text(MARKETING_STATUS_LABEL, exact=True).wait_for(
            state="attached", timeout=timeout_ms
        )
        page.get_by_text(QUALITY_HEADING, exact=True).wait_for(
            state="attached", timeout=timeout_ms
        )

    def fetch(self, source_url: str, timeout_seconds: float) -> tuple[bytes, str, None, None]:
        validate_source_url(source_url)
        if timeout_seconds <= 0:
            raise AcquisitionError("browser acquisition timeout must be positive")
        if self._context is None:
            self._launch_browser()

        timeout_ms = int(timeout_seconds * 1000)
        attempts = self.navigation_attempts if self._rotate_browser_after_fetch else 1

        for attempt in range(1, attempts + 1):
            if self._context is None:
                self._launch_browser()
            page: Any = self._context.new_page()
            stage = "navigation"
            try:
                response = page.goto(source_url, wait_until="domcontentloaded", timeout=timeout_ms)
                final_url = page.url
                validate_source_url(final_url)
                if response is not None and response.status >= 400:
                    raise AcquisitionError(f"browser navigation returned HTTP {response.status}")

                stage = "evidence readiness"
                self._wait_for_evidence_surface(page, timeout_ms)

                stage = "evidence extraction"
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
                if attempt >= attempts:
                    message = self._retryable_failure_message(stage, timed_out=True)
                    raise AcquisitionError(f"{message}: {exc}") from exc
            except self._playwright_error as exc:
                if attempt >= attempts:
                    message = self._retryable_failure_message(stage, timed_out=False)
                    raise AcquisitionError(f"{message}: {exc}") from exc
            finally:
                page.close()
                # Real browser-backed acquisition uses a fresh Chromium process
                # for every bounded target and every retry. This avoids carrying
                # a half-rendered ST page or transport connection into the next
                # evidence attempt without changing headers or parser semantics.
                if self._rotate_browser_after_fetch:
                    self._close_browser_context()

        raise AcquisitionError("browser acquisition exhausted retryable attempts")
