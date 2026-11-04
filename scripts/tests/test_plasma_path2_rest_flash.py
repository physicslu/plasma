#!/usr/bin/env python3
"""Host-only REST smoke/negative tests; all HTTP, FPGA, Z2 and DUT are fake."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_path2_rest_flash as script  # noqa: E402


class FakePPU:
    def __init__(self):
        self.calls = []
        self.ppu_id = "ppu-test-A"
        self.status_ppu_id = None
        self.site_id = 2
        self.target = "EXACT-TARGET"
        self.execution_busy = False
        self.activation_active = False
        self.interface = "openocd"
        self.site_enabled = True
        self.site_state = "idle"
        self.queued = 0
        self.current_job = None
        self.expected = None
        self.verified = True
        self.posted = False
        self.job_state = "success"
        self.fail_post = False
        self.fail_observation = False

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if path == "/api/health/ready":
            return {"ok": True, "execution": "ready"}
        if path == "/api/node":
            return {"ok": True, "ppu": {"ppu_id": self.ppu_id}}
        if path == "/api/status?site=2":
            return {"ppu": {
                "ppu_id": self.status_ppu_id or self.ppu_id,
                "execution": {"busy": self.execution_busy,
                              "active_job_count": 1 if self.execution_busy else 0},
                "runtime_activation": {"active": self.activation_active},
                # FLASH_CYCLE absent from capabilities in the current server.
                "capabilities": {"operations": ["erase", "program", "verify", "read"]},
            }, "sites": [{
                "site_id": self.site_id, "enabled": self.site_enabled,
                "interface": self.interface, "target": self.target,
                "state": self.site_state, "current_job_id": self.current_job,
                "queued_jobs": self.queued,
            }]}
        if path == "/api/jobs":
            if self.fail_post:
                raise script.PreflightError("CONNECTION_CLOSED_DURING_POST")
            if method != "POST":
                raise AssertionError("expected POST")
            self.posted = True
            self.expected = body
            return {"job": {"job_id": "job-host-only-1"}}
        if path == "/api/status?job=job-host-only-1":
            if self.fail_observation:
                raise script.PreflightError("STATUS_CONNECTION_CLOSED")
            cycle = {"result": "PASS", "safe_off": True,
                     "bytes_verified": self.expected["asset_size"],
                     "readback_sha256": self.expected["asset_sha256"]
                         if self.verified else "0" * 64,
                     "icpn": self.target}
            return {"job": {"job_id": "job-host-only-1",
                            "state": self.job_state,
                            "result": {"details": {"flash_cycle": cycle}}}}
        raise AssertionError("unexpected HTTP request " + path)


class Path2RestFlashHostOnlyTests(unittest.TestCase):
    def preflight(self, ppu):
        return script.preflight(ppu, site=2, ppu_id="ppu-test-A", target="EXACT-TARGET")

    def test_readonly_preflight_never_sends_post_even_without_capability_advertisement(self):
        ppu = FakePPU()
        receipt = self.preflight(ppu)
        self.assertEqual(receipt["result"], "READ_ONLY_PREFLIGHT_PASS")
        self.assertFalse(receipt["physical_hardware_verified"])
        self.assertFalse(receipt["c3_engine_verified"])
        self.assertFalse(receipt["external_ssh_owner_verified"])
        self.assertEqual([x[0] for x in ppu.calls], ["GET", "GET", "GET"])

    def test_readonly_discovers_live_ppu_identity_without_any_prebound_id(self):
        ppu = FakePPU()
        ppu.ppu_id = "not-an-installer-default"
        receipt = script.preflight(ppu, site=2, ppu_id=None, target=ppu.target)
        self.assertEqual(receipt["ppu_id"], ppu.ppu_id)
        self.assertEqual(receipt["ppu_id_source"], "live_node_and_status")
        self.assertFalse(receipt["ppu_id_expected_checked"])
        self.assertEqual([m for m, _, _ in ppu.calls], ["GET", "GET", "GET"])
        self.assertFalse(ppu.posted)

    def test_dynamic_discovery_still_requires_node_and_status_identity_to_match(self):
        ppu = FakePPU()
        ppu.status_ppu_id = "another-hardware"
        with self.assertRaisesRegex(script.PreflightError, "STATUS_PPU_MISMATCH"):
            script.preflight(ppu, site=2, ppu_id=None, target=ppu.target)
        self.assertFalse(ppu.posted)

    def test_destructive_execution_requires_explicit_runtime_discovered_ppu(self):
        ppu = FakePPU()
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "fw.bin"
            source.write_bytes(b"1")
            with self.assertRaisesRegex(script.PreflightError, "EXPLICIT_PPU_ID_REQUIRED_FOR_FLASH"):
                script.execute_flash(
                    ppu, site=2, ppu_id=None, target=ppu.target,
                    image_file=source, image_sha256=hashlib.sha256(b"1").hexdigest(),
                    deadline_s=30)
        self.assertEqual(ppu.calls, [])

    def test_command_line_unpinned_readonly_is_allowed_but_flash_without_id_is_denied(self):
        ppu = FakePPU()
        base = ["--url", "http://127.0.0.1:8000", "--site-id", "2",
                "--target", ppu.target]
        with patch.object(script, "RestClient", return_value=ppu):
            with redirect_stdout(io.StringIO()) as stdout:
                code = script.main(base)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["ppu_id"], ppu.ppu_id)
            with redirect_stderr(io.StringIO()) as stderr:
                code = script.main(base + ["--execute-flash", "--confirm-site", "2",
                    "--image-file", "fake.bin", "--image-sha256", "a" * 64])
            self.assertEqual(code, 69)
            self.assertIn("EXPLICIT_FLASH_CONFIRMATION_REQUIRED", stderr.getvalue())
            self.assertFalse(ppu.posted)

    def test_wrong_ppu_site_target_busy_quiesced_and_disabled_deny_without_post(self):
        for name, value, reason in (
            ("ppu_id", "ppu-other", "WRONG_PPU"),
            ("site_id", 3, "SITE_ID_MISMATCH"),
            ("target", "different", "SITE_TARGET_MISMATCH"),
            ("execution_busy", True, "PPU_EXECUTION_BUSY"),
            ("activation_active", True, "PPU_RUNTIME_QUIESCED"),
            ("site_enabled", False, "SITE_NOT_OPENOCD_ENABLED"),
            ("interface", "mock", "SITE_NOT_OPENOCD_ENABLED"),
            ("site_state", "running", "SITE_NOT_IDLE"),
            ("queued", 1, "SITE_NOT_IDLE"),
            ("current_job", "job-other", "SITE_NOT_IDLE"),
        ):
            with self.subTest(case=name):
                ppu = FakePPU()
                setattr(ppu, name, value)
                with self.assertRaisesRegex(script.PreflightError, reason):
                    self.preflight(ppu)
                self.assertFalse(any(method == "POST" for method, _, _ in ppu.calls))

    def test_bad_url_missing_port_credentials_path_and_fragment_denied(self):
        for url in (
            "https://ppu.example", "http://user:secret@host:8000",
            "http://host:8000/api/jobs", "http://host:8000/#frag",
            "ftp://host:8000", "http://host:8000/?token=bad",
        ):
            with self.subTest(url=url), self.assertRaises(script.PreflightError):
                script.RestClient(url)
        r = script.RestClient("http://127.0.0.1:8000")
        self.assertEqual((r.host, r.port), ("127.0.0.1", 8000))

    def test_image_sha_and_missing_file_rejected_before_post(self):
        ppu = FakePPU()
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "actual.bin"
            source.write_bytes(b"GOOD-FIRMWARE")
            digest = hashlib.sha256(b"GOOD-FIRMWARE").hexdigest()
            for image, sha in (
                (source, "0" * 64),
                (source, "invalid"),
                (Path(td) / "missing", digest),
            ):
                with self.subTest(image=image, sha=sha):
                    with self.assertRaises(script.PreflightError):
                        script.execute_flash(
                            ppu, site=2, ppu_id=ppu.ppu_id, target=ppu.target,
                            image_file=image, image_sha256=sha, deadline_s=30,
                            sleep=lambda _: None)
                    self.assertFalse(ppu.posted)

    def test_explicit_flash_post_and_verified_result_are_host_only(self):
        ppu = FakePPU()
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "arbitrary-name.bin"
            payload = b"FIRMWARE-DATA"
            digest = hashlib.sha256(payload).hexdigest()
            source.write_bytes(payload)
            receipt = script.execute_flash(
                ppu, site=2, ppu_id=ppu.ppu_id, target=ppu.target,
                image_file=source, image_sha256=digest, deadline_s=30,
                sleep=lambda _: None)
            self.assertEqual(receipt["result"], "FLASH_READBACK_PASS")
            self.assertFalse(receipt["cdc_heartbeat_verified"])
            self.assertEqual(ppu.expected["target"], ppu.target)
            self.assertEqual(ppu.expected["operation"], "flash_cycle")
            self.assertEqual(ppu.expected["asset_sha256"], digest)
            self.assertEqual(base64.b64decode(ppu.expected["asset_base64"]), payload)
            self.assertEqual([x[0] for x in ppu.calls], ["GET", "GET", "GET", "POST", "GET"])

    def test_wrong_readback_or_failed_job_cannot_report_pass(self):
        for mutate in ("readback", "failed"):
            ppu = FakePPU()
            if mutate == "readback":
                ppu.verified = False
            else:
                ppu.job_state = "failed"
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as td:
                source = Path(td) / "fw.bin"
                data = b"A"
                source.write_bytes(data)
                receipt = script.execute_flash(
                    ppu, site=2, ppu_id=ppu.ppu_id, target=ppu.target,
                    image_file=source, image_sha256=hashlib.sha256(data).hexdigest(),
                    deadline_s=30, sleep=lambda _: None)
                self.assertEqual(receipt["result"], "FLASH_UNPROVEN_OR_FAILED")

    def test_post_network_failure_and_lost_job_observation_are_unknown_not_notrun(self):
        for case in ("post", "observation"):
            ppu = FakePPU()
            ppu.fail_post = case == "post"
            ppu.fail_observation = case == "observation"
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                source = Path(td) / "test.bin"
                source.write_bytes(b"ONE")
                with self.assertRaisesRegex(script.FlashExecutionError,
                                            "OUTCOME_UNKNOWN|OBSERVATION_UNKNOWN"):
                    script.execute_flash(
                        ppu, site=2, ppu_id=ppu.ppu_id, target=ppu.target,
                        image_file=source,
                        image_sha256=hashlib.sha256(b"ONE").hexdigest(),
                        deadline_s=30, sleep=lambda _: None)

    def test_command_line_defaults_to_get_only_and_requires_explicit_consent(self):
        ppu = FakePPU()
        base_args = ["--url", "http://127.0.0.1:8000", "--ppu-id", ppu.ppu_id,
                     "--site-id", "2", "--target", ppu.target]
        with patch.object(script, "RestClient", return_value=ppu):
            with redirect_stdout(io.StringIO()) as stdout:
                code = script.main(base_args)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["result"], "READ_ONLY_PREFLIGHT_PASS")
            self.assertFalse(ppu.posted)
            with redirect_stderr(io.StringIO()) as stderr:
                code = script.main(base_args + ["--execute-flash"])
            self.assertEqual(code, 69)
            self.assertIn("EXPLICIT_FLASH_CONFIRMATION_REQUIRED", stderr.getvalue())
            self.assertFalse(ppu.posted)
            with redirect_stderr(io.StringIO()):
                code = script.main(base_args + ["--image-file", "random.bin"])
            self.assertEqual(code, 69)
            self.assertFalse(ppu.posted)


if __name__ == "__main__":
    unittest.main()
