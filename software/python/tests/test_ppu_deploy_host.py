"""Host-only ppu-deploy contract: no SSH, Z2, FPGA, OpenOCD or DUT access."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


REPO = Path(__file__).resolve().parents[3]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


client = load("ppu_deploy_client_host_only", REPO / "scripts/ppu_deploy.py")
target_module = load("ppu_deploy_target_host_only", REPO / "scripts/ppu_deploy_target.py")


class EngineeringDeployHostOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="plasma-ppu-deploy-host-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.z2 = self.folder / "z2-bundle"
        self.z2.mkdir()
        self.swpc = self.folder / "swpc-releases"
        self.target = target_module.Target(self.z2, enforce_host=False)
        self.original = {}
        for relative in client.Z2_FILES:
            path = self.z2 / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            old = ("previous version:" + relative).encode()
            self.original[relative] = old
            path.write_bytes(old)

    def bundle(self, commit: str = "a" * 40, module: str = "abtest"):
        return client.build_bundle(module, commit)

    def remote(self, action: str, payload: bytes = b"") -> dict:
        if action == "status":
            return {"result": "PASS", "current": self.target.current()}
        if action == "deploy":
            return self.target.deploy(payload)
        if action == "verify":
            return self.target.verify(json.loads(payload))
        if action == "rollback":
            return self.target.rollback()
        self.fail("unexpected remote action")

    def test_three_modules_have_bounded_exact_allowlisted_payloads(self):
        for module in client.MODULES:
            with self.subTest(module=module):
                manifest, archive, local = self.bundle(module=module)
                self.assertLess(len(archive), 70_000)
                self.assertEqual(set(manifest["z2_files"]), set(target_module.ALLOWED))
                self.assertEqual(set(manifest["swpc_files"]), set(local))
                self.assertEqual(len(local), 2 if module == "abtest" else 1)
                with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                    self.assertEqual(set(zipped.namelist()), set(client.Z2_FILES) | {"manifest.json"})
                    for relative in client.Z2_FILES:
                        self.assertEqual(hashlib.sha256(zipped.read(relative)).hexdigest(),
                                         manifest["z2_files"][relative])

    def test_target_deploy_verify_no_change_and_restore_original_files(self):
        manifest, archive, _ = self.bundle()
        self.assertEqual(self.target.deploy(archive)["mode"], "ACTIVATED")
        self.assertEqual(self.target.verify(manifest)["result"], "PASS")
        self.assertEqual(self.target.deploy(archive)["mode"], "NO_CHANGE")
        self.assertEqual(self.target.current()["bundle_sha256"], manifest["bundle_sha256"])
        self.assertEqual(self.target.rollback()["mode"], "ROLLED_BACK")
        self.assertIsNone(self.target.current())
        for relative, original in self.original.items():
            self.assertEqual((self.z2 / relative).read_bytes(), original)

    def test_target_upgrade_then_rollback_to_previous_verified_version(self):
        first, archive_one, _ = self.bundle("a" * 40)
        second, archive_two, _ = self.bundle("b" * 40)
        self.target.deploy(archive_one)
        self.target.deploy(archive_two)
        self.assertEqual(self.target.current()["bundle_sha256"], second["bundle_sha256"])
        self.target.rollback()
        self.assertEqual(self.target.current()["bundle_sha256"], first["bundle_sha256"])
        self.assertEqual(self.target.verify(first)["result"], "PASS")

    def test_target_rejects_tampered_manifest_package_and_active_files(self):
        manifest, archive, _ = self.bundle()
        with zipfile.ZipFile(io.BytesIO(archive)) as original:
            contents = {name: original.read(name) for name in original.namelist()}
        altered = dict(contents)
        altered[client.Z2_FILES[0]] = b"tampered"
        with io.BytesIO() as buffer:
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
                for name, data in altered.items():
                    zipped.writestr(name, data)
            with self.assertRaisesRegex(target_module.DeploymentError, "PACKAGE_SHA_MISMATCH"):
                self.target.deploy(buffer.getvalue())
        self.assertIsNone(self.target.current())
        self.target.deploy(archive)
        mismatched = dict(manifest)
        mismatched["source_commit"] = "c" * 40
        with self.assertRaisesRegex(target_module.DeploymentError, "BUNDLE_MANIFEST_SHA_MISMATCH"):
            self.target.verify(mismatched)
        (self.z2 / client.Z2_FILES[0]).write_bytes(b"tampered")
        with self.assertRaisesRegex(target_module.DeploymentError, "Z2_FILE_SHA_MISMATCH"):
            self.target.verify(manifest)
        with self.assertRaisesRegex(target_module.DeploymentError, "Z2_FILE_SHA_MISMATCH"):
            self.target.rollback()

    def test_target_rejects_unreviewed_path_duplicate_and_symlink(self):
        manifest, archive, _ = self.bundle()
        with zipfile.ZipFile(io.BytesIO(archive)) as original:
            entries = {name: original.read(name) for name in original.namelist()}
        entries["../../unsafe.py"] = b"not permitted"
        with io.BytesIO() as buffer:
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zipped:
                for name, data in entries.items():
                    zipped.writestr(name, data)
            with self.assertRaisesRegex(target_module.DeploymentError, "PACKAGE_FILE_SET_MISMATCH"):
                self.target.deploy(buffer.getvalue())
        self.assertIsNone(self.target.current())
        link = self.z2 / client.Z2_FILES[0]
        link.unlink()
        link.symlink_to(self.folder / "no-write-outside-bundle")
        with self.assertRaisesRegex(target_module.DeploymentError, "SYMLINK_TARGET_DENIED"):
            self.target.deploy(archive)
        self.assertFalse((self.folder / "no-write-outside-bundle").exists())

    def test_active_owner_guard_fails_closed(self):
        _, archive, _ = self.bundle()
        with patch.object(self.target, "_require_safe", side_effect=target_module.DeploymentError("HARDWARE_OWNER_BUSY_OR_UNKNOWN")):
            with self.assertRaisesRegex(target_module.DeploymentError, "HARDWARE_OWNER_BUSY_OR_UNKNOWN"):
                self.target.deploy(archive)
        self.assertIsNone(self.target.current())

    def test_swpc_z2_coordinated_install_verify_and_rollback(self):
        deployer = client.Deployer(self.swpc)
        with patch.object(client, "committed_main", return_value="a" * 40), \
             patch.object(deployer, "_remote", side_effect=self.remote):
            self.assertEqual(deployer.deploy("abtest")["mode"], "ACTIVATED")
            self.assertEqual(deployer.verify()["result"], "PASS")
            self.assertEqual(deployer.deploy("abtest")["mode"], "NO_CHANGE")
            self.assertTrue((self.swpc / "current" / "scripts/plasma_ab_burn_in.py").is_file())
            self.assertEqual(deployer.rollback()["mode"], "ROLLED_BACK")
            self.assertEqual(deployer.state()["current"], None)
            self.assertIsNone(self.target.current())

    def test_swpc_activation_failure_compensates_remote_activation(self):
        deployer = client.Deployer(self.swpc)
        original_activate = deployer._activate_local
        count = 0

        def activation_fails_once(*args):
            nonlocal count
            count += 1
            if count == 1:
                raise client.DeploymentError("SIMULATED_SWPC_ACTIVATION_FAILURE")
            return original_activate(*args)

        with patch.object(client, "committed_main", return_value="a" * 40), \
             patch.object(deployer, "_remote", side_effect=self.remote), \
             patch.object(deployer, "_activate_local", side_effect=activation_fails_once):
            with self.assertRaisesRegex(client.DeploymentError, "SIMULATED_SWPC_ACTIVATION_FAILURE"):
                deployer.deploy("abtest")
        self.assertIsNone(self.target.current())
        self.assertIsNone(deployer.state()["current"])

    def test_mismatched_active_versions_block_before_mutation(self):
        _, archive, _ = self.bundle()
        self.target.deploy(archive)
        deployer = client.Deployer(self.swpc)
        with patch.object(client, "committed_main", return_value="a" * 40), \
             patch.object(deployer, "_remote", side_effect=self.remote):
            with self.assertRaisesRegex(client.DeploymentError, "SWPC_Z2_PREVIOUS_VERSION_MISMATCH"):
                deployer.deploy("abtest")


if __name__ == "__main__":
    unittest.main()
