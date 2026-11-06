#!/usr/bin/env python3
"""Host-only tests: never open SSH or touch a DUT."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_path2_gateway_log_readonly as cli  # noqa: E402


class GatewayJournalReadOnlyTests(unittest.TestCase):
    def test_only_exact_post_jobs_gateway_events_are_returned(self):
        raw = "\n".join((
            "not-json",
            json.dumps({"component": "not-plasma", "event": "request_error",
                        "method": "POST", "path": "/api/jobs", "message": "ignore"}),
            json.dumps({"component": cli.COMPONENT, "event": "request_error",
                        "method": "POST", "path": "/api/settings", "message": "ignore"}),
            json.dumps({"component": cli.COMPONENT, "event": "request_error",
                        "method": "GET", "path": "/api/jobs", "message": "ignore"}),
            json.dumps({"component": cli.COMPONENT, "event": "request_error",
                        "method": "POST", "path": "/api/jobs",
                        "error_type": "ValueError",
                        "message": "State-changing requests require an Idempotency-Key"}),
            json.dumps({"component": cli.COMPONENT, "event": "security_authentication_failed",
                        "method": "POST", "path": "/api/jobs"}),
        ))
        receipt = cli.classify_gateway_log(raw)
        self.assertEqual(receipt["matching_event_count"], 2)
        self.assertEqual([x["reason_category"] for x in receipt["matches"]],
                         ["IDEMPOTENCY_KEY_REQUIRED", "AUTHENTICATION_REQUIRED"])
        self.assertTrue(receipt["no_mutations"])
        self.assertFalse(receipt["retry_authorized"])
        self.assertFalse(receipt["physical_flash_outcome_proven"])
        self.assertNotIn("State-changing requests", json.dumps(receipt))

    def test_bounded_utc_window(self):
        a,b=cli.utc_window("2026-11-04T05:57:00Z","2026-11-04T05:58:00+00:00")
        self.assertEqual(a,"2026-11-04 05:57:00 UTC")
        self.assertEqual(b,"2026-11-04 05:58:00 UTC")
        for a,b in (
            ("2026-11-04T05:00:00Z", "2026-11-04T05:06:00Z"),
            ("2026-11-04T05:00:00Z", "2026-11-04T04:59:00Z"),
            ("2026-11-04T05:00:00", "2026-11-04T05:01:00Z"),
            ("2026-11-04T13:00:00+08:00", "2026-11-04T13:01:00+08:00"),
        ):
            with self.subTest(a=a,b=b), self.assertRaises(cli.DiagnosticDenied):
                cli.utc_window(a,b)

    def test_only_fixed_journalctl_command_runs_via_enrolled_host(self):
        helper=Mock()
        helper.z2_login_credentials.return_value=({"ssh_host":"z2-test","ssh_password":"private"},
                                                   Path("/tmp/host-pinned"))
        helper.password_ssh_z2.return_value=(0,json.dumps({
            "component":cli.COMPONENT,"event":"request_error","method":"POST",
            "path":"/api/jobs","error_type":"ValueError","message":"invalid body"})+"\n")
        out=cli.run("z2-test","2026-11-04T05:57:00Z","2026-11-04T05:58:00Z",
                    helper=helper,home=Path("/tmp/host-only"))
        self.assertEqual(out["matching_event_count"],1)
        self.assertEqual(out["matches"][0]["reason_category"],
                         "UNCLASSIFIED_GATEWAY_REQUEST_ERROR")
        cmd,creds,hosts=helper.password_ssh_z2.call_args.args
        self.assertEqual(cmd,["journalctl","--no-pager","--utc","--output=cat",
                              "-u","plasma-web.service","--since","2026-11-04 05:57:00 UTC",
                              "--until","2026-11-04 05:58:00 UTC"])
        self.assertEqual(creds["ssh_host"],"z2-test")
        self.assertNotIn("private",json.dumps(out))
        self.assertTrue(out["no_mutations"])

    def test_wrong_host_or_denied_ssh_never_leaks_credentials(self):
        helper=Mock()
        helper.z2_login_credentials.return_value=({"ssh_host":"enrolled-z2","ssh_password":"secret"},Path("/tmp/hosts"))
        with self.assertRaisesRegex(cli.DiagnosticDenied,"ENROLLED_HOST_MISMATCH"):
            cli.run("different-z2","2026-11-04T05:57:00Z","2026-11-04T05:58:00Z",helper=helper)
        helper.password_ssh_z2.assert_not_called()
        helper.password_ssh_z2.return_value=(1,"secret")
        with self.assertRaisesRegex(cli.DiagnosticDenied,"Z2_JOURNAL_READ_DENIED"):
            cli.run("enrolled-z2","2026-11-04T05:57:00Z","2026-11-04T05:58:00Z",helper=helper)


if __name__ == "__main__":
    unittest.main()
