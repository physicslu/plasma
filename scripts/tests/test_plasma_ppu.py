"""Host-only safety tests for the generic PPU diagnostic CLI (Z2 backend)."""
import importlib.util
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "plasma_ppu.py"
spec = importlib.util.spec_from_file_location("plasma_ppu", SCRIPT)
doctor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(doctor)


class DoctorTests(unittest.TestCase):
    def options(self, host=None, paired_host=False):
        return Namespace(repo=Path("/tmp/no-plasma-checkout"), host=host,
                         paired_host=paired_host, ssh_user=None,
                         known_hosts=Path("/tmp/no-pinned-key"))

    def test_paired_host_only_owner_mode(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            config = base / ".config/plasma/z2-login-smoke.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({
                "ssh_host": "z2.local", "ssh_password": "REDACT_ME",
                "sudo_password": "REDACT_ME_TOO"}))
            config.chmod(0o600)
            with mock.patch.object(doctor.Path, "home", return_value=base):
                self.assertEqual(doctor.paired_host(), "z2.local")
                config.chmod(0o644)
                with self.assertRaisesRegex(ValueError, "PAIRED_TARGET_CONFIG_UNTRUSTED"):
                    doctor.paired_host()

    def test_missing_host_no_network(self):
        with mock.patch.object(doctor, "local_repo", return_value=[]), \
                mock.patch.object(doctor, "fetch_status") as status:
            result = doctor.doctor(self.options())
            self.assertEqual(result["overall"], "INCOMPLETE")
            status.assert_not_called()

    def test_recovery_required_denied(self):
        def payload(host, path):
            if path == "/v1/health":
                return "PASS", {"ok": True, "service": "plasma-ppu-bootstrap"}, "ok"
            return "PASS", {"ok": True, "bootstrap": {"state": "bootstrap_ready"},
                            "deployment": {"state": "recovery_required"}}, "ok"
        with mock.patch.object(doctor, "local_repo", return_value=[]), \
                mock.patch.object(doctor, "tcp_probe", return_value=doctor.check("tcp", "PASS", "ok")), \
                mock.patch.object(doctor, "fetch_status", side_effect=payload):
            result = doctor.doctor(self.options(host="z2.local"))
            self.assertEqual(result["overall"], "BLOCKED")

    def test_bare_status_document_accepted(self):
        from unittest.mock import Mock
        record = {"schema_version": 1,
                  "bootstrap": {"state": "bootstrap_ready"},
                  "runtime": {"state": "runtime_active"},
                  "capabilities": {"runtime_deployment": True}}
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *_):
                pass
            def read(self, *_):
                return json.dumps(record).encode()
        opener = Mock(open=Mock(return_value=Response()))
        with mock.patch.object(doctor.urllib.request, "build_opener", return_value=opener):
            status, result, _ = doctor.fetch_status("z2.local", "/v1/status")
        self.assertEqual(status, "PASS")
        self.assertEqual(result["schema_version"], 1)

    def test_deploy_never_runs(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout, \
                mock.patch.object(doctor, "fetch_status") as fetch:
            rc = doctor.main(["deploy", "--json"])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(stdout.getvalue())["reason"], "DEPLOY_DISABLED_BY_DESIGN")
        self.assertEqual(json.loads(stdout.getvalue())["schema"], "plasma.ppu.readonly-doctor.v0")
        fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
