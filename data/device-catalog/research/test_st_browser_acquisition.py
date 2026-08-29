#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from evaluate_stm32f1_live_pilot import evaluate_live_pilot  # noqa: E402
from run_stm32f1_browser_pilot import (  # noqa: E402
    CONTROL_BASE_DEVICE,
    parse_args,
    select_targets,
)
from st_browser_acquisition import (  # noqa: E402
    BROWSER_TRANSPORT,
    STBrowserAcquirer,
    build_browser_evidence_record,
)
from st_product_page_acquisition import AcquisitionError, MAX_RESPONSE_BYTES  # noqa: E402
from stm32f1_acquisition_pilot import PilotTarget  # noqa: E402

TARGET_URL = "https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html"
EXPECTED_ICPNS = [
    "STM32F100C8T6B",
    "STM32F100C8T6BTR",
    "STM32F100C8T7B",
    "STM32F100C8T7BTR",
]
RENDERED_HTML = """<!doctype html>
<html><body>
<h2>Quality and Reliability</h2>
<div>Part Number STM32F100C8T6B STM32F100C8T6BTR STM32F100C8T7B STM32F100C8T7BTR</div>
<h2>Documentation</h2>
</body></html>
"""


class FakeTimeoutError(Exception):
    pass


class FakePlaywrightError(Exception):
    pass


class FakeWaitable:
    def wait_for(self, *, state: str, timeout: int) -> None:
        self.state = state
        self.timeout = timeout


class FakeBodyLocator:
    def __init__(self, body_text: str) -> None:
        self.body_text = body_text

    def inner_text(self, *, timeout: int) -> str:
        del timeout
        return self.body_text


class FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status


class FakePage:
    def __init__(
        self,
        *,
        final_url: str = TARGET_URL,
        html: str = RENDERED_HTML,
        body_text: str = "Quality and Reliability Part Number STM32F100C8T6B",
        status: int = 200,
        goto_error: Exception | None = None,
    ) -> None:
        self.url = final_url
        self.html = html
        self.body_text = body_text
        self.status = status
        self.goto_error = goto_error
        self.closed = False
        self.heading = FakeWaitable()

    def goto(self, url: str, *, wait_until: str, timeout: int) -> FakeResponse:
        self.requested_url = url
        self.wait_until = wait_until
        self.timeout = timeout
        if self.goto_error is not None:
            raise self.goto_error
        return FakeResponse(self.status)

    def get_by_text(self, text: str, *, exact: bool) -> FakeWaitable:
        self.text_request = (text, exact)
        return self.heading

    def locator(self, selector: str) -> FakeBodyLocator:
        self.selector = selector
        return FakeBodyLocator(self.body_text)

    def content(self) -> str:
        return self.html

    def close(self) -> None:
        self.closed = True


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page

    def new_page(self) -> FakePage:
        return self.page


def acquirer_for(page: FakePage) -> STBrowserAcquirer:
    acquirer = STBrowserAcquirer()
    acquirer._context = FakeContext(page)
    acquirer._timeout_error = FakeTimeoutError
    acquirer._playwright_error = FakePlaywrightError
    return acquirer


def browser_summary(evidence: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "pilot_id": "browser-unit-test",
        "attempted": 1,
        "acquisition_success": 1,
        "acquisition_failure": 0,
        "exact_icpn_candidates": 4,
        "canonical_mapping": {"unique": 1, "ambiguous": 0, "unmapped": 0},
        "openocd_cfg_mapping": {"mapped": 1, "total": 1},
        "manual_intervention_required": 0,
        "acquisition_transport": BROWSER_TRANSPORT,
        "results": [
            {
                "base_device": CONTROL_BASE_DEVICE,
                "acquisition_status": "success",
                "canonical_mapping": {"status": "unique", "target_configs": ["stm32f1x.cfg"]},
                "evidence": evidence,
            }
        ],
    }


def browser_baseline() -> dict[str, object]:
    return {
        "schema_version": 1,
        "pilot_id": "browser-unit-test",
        "canonical_dataset_admission": False,
        "targets": [{"base_device": CONTROL_BASE_DEVICE, "exact_icpns": EXPECTED_ICPNS}],
    }


class BrowserAcquisitionTests(unittest.TestCase):
    def test_rendered_dom_has_explicit_non_raw_provenance(self) -> None:
        page = FakePage()
        body, final_url, etag, last_modified = acquirer_for(page).fetch(TARGET_URL, 5.0)
        self.assertTrue(page.closed)
        self.assertEqual(final_url, TARGET_URL)
        self.assertIsNone(etag)
        self.assertIsNone(last_modified)
        evidence = build_browser_evidence_record(
            body=body,
            source_url=TARGET_URL,
            final_url=final_url,
            base_device=CONTROL_BASE_DEVICE,
            retrieved_at_utc="2026-08-29T12:00:00Z",
        )
        self.assertEqual(evidence["exact_icpns"], EXPECTED_ICPNS)
        self.assertEqual(evidence["acquisition_transport"], BROWSER_TRANSPORT)
        self.assertRegex(str(evidence["rendered_dom_sha256"]), r"^[0-9a-f]{64}$")
        self.assertNotIn("raw_sha256", evidence)
        self.assertEqual(page.wait_until, "domcontentloaded")
        self.assertEqual(page.text_request, ("Quality and Reliability", True))
        self.assertEqual(page.heading.state, "attached")

    def test_live_browser_defaults_to_headed_with_explicit_headless_opt_in(self) -> None:
        default_args = parse_args(["--output", "/tmp/control.json"])
        self.assertFalse(default_args.headless)
        headless_args = parse_args(["--headless", "--output", "/tmp/control.json"])
        self.assertTrue(headless_args.headless)

    def test_browser_evidence_can_be_scale_ready_without_claiming_raw_http(self) -> None:
        evidence = build_browser_evidence_record(
            body=RENDERED_HTML.encode("utf-8"),
            source_url=TARGET_URL,
            final_url=TARGET_URL,
            base_device=CONTROL_BASE_DEVICE,
            retrieved_at_utc="2026-08-29T12:00:00Z",
        )
        report = evaluate_live_pilot(summary=browser_summary(evidence), baseline=browser_baseline())
        self.assertTrue(report["scale_ready"])
        self.assertEqual(report["transport_evidence"]["transport"], BROWSER_TRANSPORT)
        self.assertEqual(report["transport_evidence"]["valid_records"], 1)

    def test_browser_evaluator_rejects_fake_raw_sha_claim(self) -> None:
        evidence = build_browser_evidence_record(
            body=RENDERED_HTML.encode("utf-8"),
            source_url=TARGET_URL,
            final_url=TARGET_URL,
            base_device=CONTROL_BASE_DEVICE,
            retrieved_at_utc="2026-08-29T12:00:00Z",
        )
        evidence["raw_sha256"] = evidence["rendered_dom_sha256"]
        report = evaluate_live_pilot(summary=browser_summary(evidence), baseline=browser_baseline())
        self.assertFalse(report["scale_ready"])
        self.assertTrue(any("must not claim raw_sha256" in issue for issue in report["issues"]))

    def test_challenge_marker_fails_closed(self) -> None:
        page = FakePage(body_text="Access Denied - verify you are human")
        with self.assertRaisesRegex(AcquisitionError, "challenge marker"):
            acquirer_for(page).fetch(TARGET_URL, 5.0)
        self.assertTrue(page.closed)

    def test_foreign_redirect_fails_closed(self) -> None:
        page = FakePage(final_url="https://example.com/stm32f100c8.html")
        with self.assertRaisesRegex(AcquisitionError, "source host must be www.st.com"):
            acquirer_for(page).fetch(TARGET_URL, 5.0)

    def test_http_error_fails_closed(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "HTTP 503"):
            acquirer_for(FakePage(status=503)).fetch(TARGET_URL, 5.0)

    def test_playwright_timeout_is_normalized(self) -> None:
        page = FakePage(goto_error=FakeTimeoutError("navigation timeout"))
        with self.assertRaisesRegex(AcquisitionError, "browser acquisition timed out"):
            acquirer_for(page).fetch(TARGET_URL, 5.0)

    def test_rendered_dom_size_limit_is_enforced(self) -> None:
        page = FakePage(html="x" * (MAX_RESPONSE_BYTES + 1))
        with self.assertRaisesRegex(AcquisitionError, "rendered page exceeds"):
            acquirer_for(page).fetch(TARGET_URL, 5.0)

    def test_context_manager_is_required(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "context manager"):
            STBrowserAcquirer().fetch(TARGET_URL, 5.0)

    def test_control_scope_selects_only_stm32f100c8(self) -> None:
        targets = [
            PilotTarget(CONTROL_BASE_DEVICE, TARGET_URL, "control"),
            PilotTarget(
                "STM32F101C8",
                "https://www.st.com/en/microcontrollers-microprocessors/stm32f101c8.html",
                "second",
            ),
        ]
        self.assertEqual(
            [target.base_device for target in select_targets("control", targets)],
            [CONTROL_BASE_DEVICE],
        )
        self.assertEqual(select_targets("pilot", targets), targets)

    def test_control_scope_fails_if_manifest_loses_control_target(self) -> None:
        targets = [
            PilotTarget(
                "STM32F101C8",
                "https://www.st.com/en/microcontrollers-microprocessors/stm32f101c8.html",
                "second",
            )
        ]
        with self.assertRaisesRegex(AcquisitionError, CONTROL_BASE_DEVICE):
            select_targets("control", targets)

    def test_browser_dependency_is_research_only_and_pinned(self) -> None:
        requirement = (HERE / "requirements-st-browser.txt").read_text(encoding="utf-8")
        self.assertIn("playwright==1.62.0", requirement)
        web_package = (HERE.parents[2] / "software" / "web" / "package.json").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("playwright", web_package)


if __name__ == "__main__":
    unittest.main()
