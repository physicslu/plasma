"""Host-only tests for read-only predeployment checks (no GitHub / SSH / Z2)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "plasma_path2_z2_runtime_predeploy_probe", ROOT / "scripts/plasma_path2_z2_runtime_predeploy_probe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class ReadonlyRuntimePredeployTests(unittest.TestCase):
    def test_artifact_probe_detects_exact_repo_run_and_id_without_secrets(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout=json.dumps({
            "artifacts": [{"id": mod.EXPECTED_ARTIFACT_ID, "name": mod.EXPECTED_ARTIFACT_NAME,
                           "expired": False, "workflow_run": {"id": mod.EXPECTED_RUN}}]
        }), stderr="SENSITIVE"))
        receipt = mod.artifact_readability(runner=runner, which=lambda _: "/usr/bin/gh")
        self.assertTrue(receipt["artifact_fetch_qualified"])
        self.assertEqual(receipt["expected_kit_sha256"], mod.EXPECTED_KIT_SHA256)
        self.assertNotIn("SENSITIVE", json.dumps(receipt))
        self.assertIn("--method", runner.call_args.args[0])
        self.assertIn("GET", runner.call_args.args[0])

    def test_artifact_probe_fails_closed_without_cli_credentials_or_pin(self):
        self.assertEqual(mod.artifact_readability(which=lambda _: None)["reason"], "GH_CLI_MISSING")
        denied = Mock(return_value=SimpleNamespace(returncode=1, stdout="", stderr="SECRET"))
        receipt = mod.artifact_readability(runner=denied, which=lambda _: "/bin/gh")
        self.assertEqual(receipt["reason"], "GH_ARTIFACT_ACCESS_DENIED")
        self.assertNotIn("SECRET", json.dumps(receipt))
        incorrect = Mock(return_value=SimpleNamespace(returncode=0,
            stdout=json.dumps({"artifacts": [{"id": 3, "name": mod.EXPECTED_ARTIFACT_NAME,
                        "expired": False}]}), stderr=""))
        self.assertEqual(mod.artifact_readability(
            runner=incorrect, which=lambda _: "/bin/gh")["reason"], "PINNED_ARTIFACT_NOT_FOUND")

    def test_z2_ssh_reads_only_literal_python_static_script_and_pinned_owner(self):
        helper = Mock()
        helper.z2_login_credentials.return_value = ({"ssh_host": "192.168.2.99",
                                                       "password": "PRIVATE"},
                                                      Path("/owner/known_hosts"))
        answer = {
            "bootstrap_stage_c_renderer_available": True,
            "site_worker_unit_installed": True,
            "current_release_symlink": "releases/0.2.1-previous",
            "installed_openocd_engine_manifest": True,
            "runtime_control_socket_present": True,
        }
        helper.password_ssh_z2.return_value = (0, "PLASMA_READONLY_Z2_STATE=" + json.dumps(answer))
        result = mod.z2_readiness("192.168.2.99", helper=helper, home=Path("/owner"))
        self.assertEqual(result["current_release_symlink"], "releases/0.2.1-previous")
        args = helper.password_ssh_z2.call_args.args[0]
        self.assertEqual(args[:3], ["python3", "-I", "-c"])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("sudo", args[2])
        self.assertNotIn("write_text", args[2])
        self.assertNotIn("systemctl restart", args[2])

    def test_z2_wrong_enrolled_target_fails_without_network(self):
        helper = Mock()
        helper.z2_login_credentials.return_value = ({"ssh_host": "192.168.2.30"},
                                                      Path("/owner/known_hosts"))
        with self.assertRaisesRegex(mod.ProbeError, "ENROLLED_HOST_MISMATCH"):
            mod.z2_readiness("192.168.2.99", helper=helper)
        helper.password_ssh_z2.assert_not_called()
        with self.assertRaisesRegex(mod.ProbeError, "Z2_HOST_NOT_PRIVATE"):
            mod.z2_readiness("1.1.1.1", helper=helper)

    def test_unknown_current_release_path_redacted(self):
        helper = Mock()
        helper.z2_login_credentials.return_value = ({"ssh_host": "192.168.2.99"}, Path("/tmp/hosts"))
        d = {"bootstrap_stage_c_renderer_available": True,
             "site_worker_unit_installed": True, "current_release_symlink": "../../secrets",
             "installed_openocd_engine_manifest": True, "runtime_control_socket_present": True}
        helper.password_ssh_z2.return_value = (0, "PLASMA_READONLY_Z2_STATE=" + json.dumps(d))
        state = mod.z2_readiness("192.168.2.99", helper=helper)
        self.assertEqual(state["current_release_symlink"], "UNRECOGNIZED_SOURCE_PATH")

    def test_ready_only_when_artifact_and_stage_c_are_present(self):
        state = {"bootstrap_stage_c_renderer_available": True,
                 "current_release_symlink": "releases/v1",
                 "runtime_control_socket_present": True}
        r = mod.run("host", artifact_probe=lambda: {"artifact_fetch_qualified": True},
                    z2_probe=lambda _: state)
        self.assertEqual(r["result"], "READ_ONLY_PREDEPLOY_READY")
        self.assertTrue(r["no_install"])
        state["bootstrap_stage_c_renderer_available"] = False
        r = mod.run("host", artifact_probe=lambda: {"artifact_fetch_qualified": True},
                    z2_probe=lambda _: state)
        self.assertEqual(r["result"], "READ_ONLY_PREDEPLOY_BLOCKED")
        self.assertFalse(r["physical_hil_verified"])


if __name__ == "__main__":
    unittest.main()
