#!/usr/bin/env python3
"""Generic Playwright transport for ST dual-surface product-page evidence."""

from __future__ import annotations

import time
from typing import Any

from st_browser_acquisition import (
    CHALLENGE_MARKERS,
    CHROMIUM_LAUNCH_ARGS,
    EVIDENCE_READINESS_POLL_SECONDS,
)
from st_dual_surface_evidence import dual_surface_ready
from st_product_page_acquisition import AcquisitionError, MAX_RESPONSE_BYTES, validate_source_url

DEFAULT_NAVIGATION_ATTEMPTS = 2


class STDualSurfaceBrowserAcquirer:
    def __init__(
        self,
        *,
        base_by_url: dict[str, str],
        family_label: str,
        headless: bool = True,
        navigation_attempts: int = DEFAULT_NAVIGATION_ATTEMPTS,
        reuse_browser: bool = False,
        global_deadline: bool = False,
    ) -> None:
        if navigation_attempts < 1:
            raise AcquisitionError("browser navigation attempts must be at least 1")
        if not base_by_url:
            raise AcquisitionError("ST dual-surface browser acquisition requires URL/Base bindings")
        if not family_label.strip():
            raise AcquisitionError("ST dual-surface browser acquisition requires family_label")
        self.base_by_url = dict(base_by_url)
        self.family_label = family_label.strip()
        self.headless = headless
        self.navigation_attempts = navigation_attempts
        self.reuse_browser = reuse_browser
        self.global_deadline = global_deadline
        self.browser_version: str | None = None
        self._playwright: Any = None
        self._browser: Any = None
        self._timeout_error: type[BaseException] | tuple[type[BaseException], ...] = Exception
        self._playwright_error: type[BaseException] | tuple[type[BaseException], ...] = Exception

    def __enter__(self) -> "STDualSurfaceBrowserAcquirer":
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AcquisitionError("Playwright is required for ST dual-surface browser acquisition") from exc
        self._timeout_error = PlaywrightTimeoutError
        self._playwright_error = PlaywrightError
        self._playwright = sync_playwright().start()
        if self.reuse_browser:
            self._launch_browser()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._close_browser()
        if self._playwright is not None:
            self._playwright.stop()
        self._playwright = None

    def _launch_browser(self) -> None:
        if self._playwright is None:
            raise AcquisitionError("browser acquirer must be used as a context manager")
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=CHROMIUM_LAUNCH_ARGS,
        )
        self.browser_version = self._browser.version

    def _close_browser(self) -> None:
        if self._browser is not None:
            self._browser.close()
        self._browser = None

    def _operation_timeout_ms(self, *, deadline: float | None, timeout_seconds: float) -> int:
        if deadline is None:
            return max(1, int(timeout_seconds * 1000))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AcquisitionError(
                f"{self.family_label} per-device global acquisition deadline exceeded"
            )
        return max(1, int(remaining * 1000))

    def _safe_close(self, resource: Any) -> None:
        if resource is None:
            return
        try:
            resource.close()
        except Exception:
            # Cleanup must not mask the authoritative acquisition result.
            pass

    def fetch(self, source_url: str, timeout_seconds: float) -> tuple[bytes, str, None, None]:
        validate_source_url(source_url)
        base_device = self.base_by_url.get(source_url)
        if base_device is None:
            raise AcquisitionError(f"unregistered {self.family_label} acquisition URL")
        if timeout_seconds <= 0:
            raise AcquisitionError("browser acquisition timeout must be positive")
        deadline = time.monotonic() + timeout_seconds if self.global_deadline else None
        last_error: AcquisitionError | None = None

        for attempt in range(1, self.navigation_attempts + 1):
            if not self.reuse_browser:
                self._close_browser()
            if self._browser is None:
                self._launch_browser()
            context = None
            page = None
            try:
                context = self._browser.new_context()
                page = context.new_page()
                response = page.goto(
                    source_url,
                    wait_until="domcontentloaded",
                    timeout=self._operation_timeout_ms(
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    ),
                )
                final_url = page.url
                validate_source_url(final_url)
                if response is not None and response.status >= 400:
                    raise AcquisitionError(f"browser navigation returned HTTP {response.status}")

                body_text = page.locator("body").inner_text(
                    timeout=self._operation_timeout_ms(
                        deadline=deadline,
                        timeout_seconds=timeout_seconds,
                    )
                )
                folded = body_text.casefold()
                for marker in CHALLENGE_MARKERS:
                    if marker in folded:
                        raise AcquisitionError(
                            f"browser acquisition encountered challenge marker: {marker}"
                        )

                readiness_deadline = deadline or (time.monotonic() + timeout_seconds)
                while True:
                    html_text = page.content()
                    if dual_surface_ready(html_text, base_device):
                        body = html_text.encode("utf-8")
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise AcquisitionError(
                                f"rendered page exceeds {MAX_RESPONSE_BYTES} bytes"
                            )
                        return body, final_url, None, None
                    remaining = readiness_deadline - time.monotonic()
                    if remaining <= 0:
                        if self.global_deadline:
                            raise AcquisitionError(
                                f"{self.family_label} per-device global acquisition deadline exceeded"
                            )
                        raise AcquisitionError(
                            f"{self.family_label} dual-surface evidence readiness timed out: "
                            "Q&R exact identity / Sample & Buy Marketing Status join incomplete"
                        )
                    time.sleep(min(EVIDENCE_READINESS_POLL_SECONDS, remaining))
            except self._timeout_error as exc:
                if deadline is not None and time.monotonic() >= deadline:
                    last_error = AcquisitionError(
                        f"{self.family_label} per-device global acquisition deadline exceeded"
                    )
                else:
                    last_error = AcquisitionError("browser acquisition timed out")
                if attempt >= self.navigation_attempts or (
                    deadline is not None and time.monotonic() >= deadline
                ):
                    raise last_error from exc
            except self._playwright_error as exc:
                last_error = AcquisitionError("browser acquisition failed")
                # A Playwright transport error can mean Chromium is no longer usable.
                self._close_browser()
                if attempt >= self.navigation_attempts:
                    raise last_error from exc
            except AcquisitionError as exc:
                last_error = exc
                if attempt >= self.navigation_attempts or (
                    deadline is not None and time.monotonic() >= deadline
                ):
                    raise
            finally:
                self._safe_close(page)
                self._safe_close(context)
                if not self.reuse_browser:
                    self._close_browser()

        assert last_error is not None
        raise last_error
