#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import diagnose_st_transport as diagnostic  # noqa: E402
from st_product_page_acquisition import AcquisitionError  # noqa: E402


SUCCESS = {"status": "success"}
FAILURE = {"status": "failure"}


class TransportDiagnosticTests(unittest.TestCase):
    def test_classification_prefers_real_urllib_success(self) -> None:
        self.assertEqual(
            diagnostic.classify_transport(
                {
                    "dns": FAILURE,
                    "tcp": FAILURE,
                    "tls": FAILURE,
                    "urllib": SUCCESS,
                }
            ),
            "transport_ok",
        )

    def test_classification_identifies_urllib_specific_failure(self) -> None:
        self.assertEqual(
            diagnostic.classify_transport(
                {
                    "dns": SUCCESS,
                    "tcp": SUCCESS,
                    "tls": SUCCESS,
                    "urllib": FAILURE,
                    "curl_plasma_headers": SUCCESS,
                }
            ),
            "urllib_specific_failure",
        )

    def test_classification_identifies_header_policy_suspicion(self) -> None:
        self.assertEqual(
            diagnostic.classify_transport(
                {
                    "dns": SUCCESS,
                    "tcp": SUCCESS,
                    "tls": SUCCESS,
                    "urllib": FAILURE,
                    "curl_plasma_headers": FAILURE,
                    "curl_default": SUCCESS,
                }
            ),
            "request_header_policy_suspected",
        )

    def test_classification_identifies_broad_http_path_failure(self) -> None:
        self.assertEqual(
            diagnostic.classify_transport(
                {
                    "dns": SUCCESS,
                    "tcp": SUCCESS,
                    "tls": SUCCESS,
                    "urllib": FAILURE,
                    "curl_plasma_headers": FAILURE,
                    "curl_default": FAILURE,
                }
            ),
            "upstream_http_response_failure_or_filter",
        )

    def test_classification_preserves_lower_layer_failures(self) -> None:
        cases = [
            ("dns", "dns_failure"),
            ("tcp", "tcp_path_failure_or_address_selection"),
            ("tls", "tls_path_failure_or_address_selection"),
        ]
        for failed_probe, expected in cases:
            with self.subTest(failed_probe=failed_probe):
                probes = {
                    "dns": SUCCESS,
                    "tcp": SUCCESS,
                    "tls": SUCCESS,
                    "urllib": FAILURE,
                    "curl_plasma_headers": FAILURE,
                    "curl_default": FAILURE,
                }
                probes[failed_probe] = FAILURE
                self.assertEqual(diagnostic.classify_transport(probes), expected)

    def test_successful_urllib_short_circuits_curl_comparisons(self) -> None:
        with (
            patch.object(diagnostic, "probe_dns", return_value=SUCCESS),
            patch.object(diagnostic, "probe_tcp", return_value=SUCCESS),
            patch.object(diagnostic, "probe_tls", return_value=SUCCESS),
            patch.object(diagnostic, "probe_urllib", return_value=SUCCESS),
            patch.object(diagnostic, "probe_curl") as curl_probe,
        ):
            report = diagnostic.run_diagnostic(timeout_seconds=5.0, delay_seconds=2.0)
        self.assertTrue(report["production_urllib_transport_ok"])
        self.assertEqual(report["classification"], "transport_ok")
        curl_probe.assert_not_called()

    def test_failed_urllib_runs_plasma_curl_before_default_curl(self) -> None:
        sleeps: list[float] = []
        curl_profiles: list[bool] = []

        def fake_curl(url: str, *, timeout_seconds: float, plasma_headers: bool):
            self.assertEqual(url, diagnostic.TARGET_URL)
            self.assertEqual(timeout_seconds, 5.0)
            curl_profiles.append(plasma_headers)
            return FAILURE

        with (
            patch.object(diagnostic, "probe_dns", return_value=SUCCESS),
            patch.object(diagnostic, "probe_tcp", return_value=SUCCESS),
            patch.object(diagnostic, "probe_tls", return_value=SUCCESS),
            patch.object(diagnostic, "probe_urllib", return_value=FAILURE),
            patch.object(diagnostic, "probe_curl", side_effect=fake_curl),
        ):
            report = diagnostic.run_diagnostic(
                timeout_seconds=5.0,
                delay_seconds=2.0,
                sleeper=sleeps.append,
            )
        self.assertFalse(report["production_urllib_transport_ok"])
        self.assertEqual(report["classification"], "upstream_http_response_failure_or_filter")
        self.assertEqual(curl_profiles, [True, False])
        self.assertEqual(sleeps, [2.0, 2.0])

    def test_plasma_curl_success_stops_before_default_curl(self) -> None:
        sleeps: list[float] = []
        curl_profiles: list[bool] = []

        def fake_curl(url: str, *, timeout_seconds: float, plasma_headers: bool):
            del url, timeout_seconds
            curl_profiles.append(plasma_headers)
            return SUCCESS

        with (
            patch.object(diagnostic, "probe_dns", return_value=SUCCESS),
            patch.object(diagnostic, "probe_tcp", return_value=SUCCESS),
            patch.object(diagnostic, "probe_tls", return_value=SUCCESS),
            patch.object(diagnostic, "probe_urllib", return_value=FAILURE),
            patch.object(diagnostic, "probe_curl", side_effect=fake_curl),
        ):
            report = diagnostic.run_diagnostic(
                timeout_seconds=5.0,
                delay_seconds=2.0,
                sleeper=sleeps.append,
            )
        self.assertEqual(report["classification"], "urllib_specific_failure")
        self.assertEqual(curl_profiles, [True])
        self.assertEqual(sleeps, [2.0])

    def test_diagnostic_rejects_aggressive_request_delay(self) -> None:
        with self.assertRaisesRegex(AcquisitionError, "at least 1.0 seconds"):
            diagnostic.run_diagnostic(timeout_seconds=5.0, delay_seconds=0.5)

    def test_target_is_fixed_to_single_control_device(self) -> None:
        self.assertEqual(diagnostic.TARGET_BASE_DEVICE, "STM32F100C8")
        self.assertEqual(
            diagnostic.TARGET_URL,
            "https://www.st.com/en/microcontrollers-microprocessors/stm32f100c8.html",
        )

    def test_live_workflow_runs_preflight_before_six_target_pilot(self) -> None:
        workflow = (
            HERE.parents[2] / ".github" / "workflows" / "stm32f1-live-acquisition-pilot.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn("diagnose_st_transport.py", workflow)
        self.assertIn("transport-diagnostic.json", workflow)
        self.assertIn("steps.transport_preflight.outcome == 'success'", workflow)
        self.assertIn("--timeout 20", workflow)
        self.assertIn("--delay 2.0", workflow)
        self.assertIn("if: always()", workflow)


if __name__ == "__main__":
    unittest.main()
