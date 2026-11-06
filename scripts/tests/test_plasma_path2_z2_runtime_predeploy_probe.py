"""Host-only tests for source-pinned runtime predeployment (no GitHub/SSH/Z2)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "plasma_path2_z2_runtime_predeploy_probe",
    ROOT / "scripts/plasma_path2_z2_runtime_predeploy_probe.py")
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class ReadonlyRuntimePredeployTests(unittest.TestCase):
    def test_trusted_delivery_requires_exact_archive_and_sidecar_sha256(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            archive = directory / (mod.EXPECTED_ARTIFACT_NAME + ".tar.gz")
            sidecar = directory / (archive.name + ".sha256")
            archive.write_bytes(b"example validated kit")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            sidecar.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
            with patch.object(mod, "EXPECTED_KIT_SHA256", digest):
                receipt = mod.artifact_readability(directory=directory)
                self.assertTrue(receipt["artifact_fetch_qualified"])
                self.assertEqual(receipt["verification"], "TRUSTED_DELIVERY_AND_SHA256")
                archive.write_bytes(b"modified kit")
                self.assertEqual(
                    mod.artifact_readability(directory=directory)["reason"],
                    "PINNED_KIT_SHA256_MISMATCH")
                archive.write_bytes(b"example validated kit")
                sidecar.write_text("bad sidecar", encoding="ascii")
                self.assertEqual(
                    mod.artifact_readability(directory=directory)["reason"],
                    "KIT_SIDECAR_MISMATCH")
                sidecar.unlink()
                self.assertEqual(
                    mod.artifact_readability(directory=directory)["reason"],
                    "PINNED_KIT_MISSING_OR_UNTRUSTED")

    def test_artifact_delivery_fails_closed_without_credentials_or_path(self):
        with patch.dict(os.environ, {"PLASMA_Z2_KIT_ARTIFACT_DIR": ""}):
            receipt = mod.artifact_readability()
        self.assertEqual(receipt["reason"], "TRUSTED_ARTIFACT_NOT_DELIVERED")
        self.assertFalse(receipt["artifact_fetch_qualified"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "symlink").symlink_to(root, target_is_directory=True)
            self.assertEqual(
                mod.artifact_readability(directory=root / "symlink")["reason"],
                "TRUSTED_ARTIFACT_DIR_INVALID")

    def test_z2_accepts_installer_absolute_release_and_checks_target(self):
        helper = Mock()
        helper.z2_login_credentials.return_value = (
            {"ssh_host": "192.168.2.99", "password": "PRIVATE"},
            Path("/owner/known_hosts"))
        answer = {
            "bootstrap_stage_c_renderer_available": True,
            "site_worker_unit_installed": True,
            "current_release_symlink": "/opt/plasma/releases/0.2.1-previous",
            "current_release_target_valid": True,
            "installed_openocd_engine_manifest": True,
            "runtime_control_socket_present": True,
        }
        helper.password_ssh_z2.return_value = (
            0, "PLASMA_READONLY_Z2_STATE=" + json.dumps(answer))
        result = mod.z2_readiness("192.168.2.99", helper=helper, home=Path("/owner"))
        self.assertEqual(result["current_release_symlink"], "releases/0.2.1-previous")
        self.assertTrue(result["current_release_target_valid"])
        args = helper.password_ssh_z2.call_args.args[0]
        self.assertEqual(args[:3], ["python3", "-I", "-c"])
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("sudo", args[2])
        self.assertNotIn("write_text", args[2])
        self.assertNotIn("systemctl restart", args[2])

    def test_z2_wrong_enrolled_target_fails_without_network(self):
        helper = Mock()
        helper.z2_login_credentials.return_value = (
            {"ssh_host": "192.168.2.30"}, Path("/owner/known_hosts"))
        with self.assertRaisesRegex(mod.ProbeError, "ENROLLED_HOST_MISMATCH"):
            mod.z2_readiness("192.168.2.99", helper=helper)
        helper.password_ssh_z2.assert_not_called()
        with self.assertRaisesRegex(mod.ProbeError, "Z2_HOST_NOT_PRIVATE"):
            mod.z2_readiness("1.1.1.1", helper=helper)

    def test_unknown_current_release_path_redacted(self):
        helper = Mock()
        helper.z2_login_credentials.return_value = (
            {"ssh_host": "192.168.2.99"}, Path("/tmp/hosts"))
        state = {
            "bootstrap_stage_c_renderer_available": True,
            "site_worker_unit_installed": True,
            "current_release_symlink": "../../secrets",
            "current_release_target_valid": False,
            "installed_openocd_engine_manifest": True,
            "runtime_control_socket_present": True,
        }
        helper.password_ssh_z2.return_value = (
            0, "PLASMA_READONLY_Z2_STATE=" + json.dumps(state))
        result = mod.z2_readiness("192.168.2.99", helper=helper)
        self.assertEqual(result["current_release_symlink"], "UNRECOGNIZED_SOURCE_PATH")

    def test_ready_only_when_every_runtime_binding_is_real(self):
        state = {
            "bootstrap_stage_c_renderer_available": True,
            "site_worker_unit_installed": True,
            "current_release_symlink": "releases/v1",
            "current_release_target_valid": True,
            "installed_openocd_engine_manifest": True,
            "runtime_control_socket_present": True,
        }
        ready = lambda: {"artifact_fetch_qualified": True}
        result = mod.run("host", artifact_probe=ready, z2_probe=lambda _: state)
        self.assertEqual(result["result"], "READ_ONLY_PREDEPLOY_READY")
        self.assertTrue(result["no_install"])
        state["current_release_target_valid"] = False
        result = mod.run("host", artifact_probe=ready, z2_probe=lambda _: state)
        self.assertEqual(result["result"], "READ_ONLY_PREDEPLOY_BLOCKED")
        self.assertFalse(result["physical_hil_verified"])
        state["current_release_target_valid"] = True
        state["bootstrap_stage_c_renderer_available"] = False
        result = mod.run("host", artifact_probe=ready, z2_probe=lambda _: state)
        self.assertEqual(result["result"], "READ_ONLY_PREDEPLOY_BLOCKED")


if __name__ == "__main__":
    unittest.main()
