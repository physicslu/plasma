"""User Bundle v3 contract: stdlib-only host tests, no PPU/hardware access.

Uses real B1/B2 validation, owner MACs with a synthetic test credential, B3
Coordinator/Installer, and the HTTPS client with an in-process transport.
Only Runtime quiescence is simulated. No uploaded code is executed.
Run: python3 -m unittest software.python.tests.test_ppu_user_bundle_v3 -v
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from .ppu_owner_authorization_fixture import (
    OWNER_TOKEN, admit_body, device_id, install_body, machine_id_file,
    provision_owner,
)
from .ppu_fpga_qualification_fixture import synthetic_image, write_contracts

ROOT = Path(__file__).resolve().parents[3]
TARGET = {"platform": "linux-armv7", "board": "pynq-z2", "fpga_part": "xc7z020clg400-1"}


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load("user_bundle_contract", "ppu_unified_deployment.py")
engine = load("user_bundle_engine", "ppu-bootstrap-deployment.py")
installer = load("user_bundle_installer", "ppu-z2-installer.py")
bootstrap = load("user_bundle_bootstrap", "ppu-bootstrap-service.py")
client = load("user_bundle_client", "ppu_deploy_api.py")
builder = load("user_bundle_builder", "ppu-bundle-v3-smoke.py")


class UserBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive = self.root / "local.zip"
        self.digest = builder.make_bundle(self.archive)
        self.paths = bootstrap.ServicePaths(
            state_root=self.root / "state", product_root=self.root / "product",
            package_target_file=self.root / "target.json",
            bundle_install_policy=self.root / "policy.json",
            machine_id_path=machine_id_file(self.root),
            fpga_image_contracts=self.root / "fpga-contracts.json",
            deployment_engine_script=ROOT / "scripts/ppu-bootstrap-deployment.py",
            z2_installer_script=ROOT / "scripts/ppu-z2-installer.py",
        )
        self.paths.package_target_file.write_text(json.dumps(TARGET))
        self.paths.package_target_file.chmod(0o600)
        self.paths.bundle_install_policy.write_bytes((ROOT / "scripts/ppu-bundle-install-policy.json").read_bytes())
        self.paths.bundle_install_policy.chmod(0o600)
        provision_owner(self.paths)  # synthetic credential only
        self.server = object.__new__(bootstrap.BootstrapHTTPServer)
        self.server.bootstrap_paths = self.paths
        self.server.mutation_lock = threading.RLock()
        self.server.deployment_thread = None
        self.co = engine.DeploymentCoordinator(
            paths=engine.DeploymentPaths(
                bootstrap_state_root=self.paths.state_root,
                product_root=self.paths.product_root,
                config_root=self.root / "unused-config",
                runtime_state_root=self.root / "unused-runtime",
                log_root=self.root / "unused-logs", systemd_root=self.root / "unused-systemd",
            ), installer=installer,
        )
        self.held = False
        self.co.quiescence_lease = self.lease
        self.co.root_bundle_loader = Mock(side_effect=AssertionError("HARDWARE_FORBIDDEN"))
        self.server.bundle_install_runner = self.runner

    @contextmanager
    def lease(self):
        self.held = True
        try:
            yield {"lease_kind": "connection_held", "active_job_count": 0}
        finally:
            self.held = False

    def runner(self, paths, upload_id, request):
        self.assertNotIn("source_commit", request)
        return self.co.execute_bundle_v3_install(engine.BundleV3InstallRequest(
            archive=bootstrap._upload_paths(paths, upload_id).committed,
            artifact_sha256=request["archive_sha256"], target_profile=request["target"],
            api_transaction_id=request["api_transaction_id"],
            mode=request["mode"], fpga_load=request["fpga_load"],
        ))

    def rewrite(self, mutate=lambda m: None, *, payload=None):
        with zipfile.ZipFile(self.archive) as source:
            members = {n: source.read(n) for n in source.namelist()}
        manifest = json.loads(members.pop("manifest.json"))
        mutate(manifest)
        members.update(payload or {})
        with zipfile.ZipFile(self.archive, "w") as dest:
            dest.writestr("manifest.json", json.dumps(manifest))
            for name, data in members.items():
                dest.writestr(name, data)
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()

    def commit(self):
        raw = self.archive.read_bytes()
        upload = bootstrap.create_upload(self.paths, size=len(raw), sha256=self.digest)
        uid = upload["upload_id"]
        bootstrap.append_chunk(self.paths, uid, offset=0,
                               data_base64=base64.b64encode(raw).decode(), sha256=self.digest)
        self.assertEqual(bootstrap.commit_upload(self.paths, uid)["state"], "committed")
        return uid

    def admit(self):
        uid = self.commit()
        return self.server.start_deployment(admit_body(self.paths, "bundle", uid))

    def finish(self):
        self.server.deployment_thread.join(timeout=10)
        self.assertFalse(self.server.deployment_thread.is_alive())
        return bootstrap._deployment_api_record(self.paths)

    def fpga(self):
        files, entry = synthetic_image()
        members = {f"payload/packages/image/{n}": data for n, data in files.items()}
        package = {"id": "image", "kind": "fpga-image", "version": "1", "requires": [],
                   "files": [{"path": n, "sha256": hashlib.sha256(v).hexdigest(),
                              "size": len(v), "executable": False} for n, v in members.items()]}
        self.rewrite(lambda m: m["packages"].append(package), payload=members)
        write_contracts(self.paths.fpga_image_contracts, entry)

    def test_local_zip_b1_b2_b3_activate_and_repeat_without_provenance(self):
        with zipfile.ZipFile(self.archive) as source:
            manifest = json.loads(source.read("manifest.json"))
        self.assertNotIn("source_commit", manifest)
        self.assertNotIn("publisher", manifest)
        b2 = self.admit()
        self.assertIsNone(b2["result"]["plan"]["source_commit"])
        # An omitted informational receipt field is equally acceptable at B3.
        record = bootstrap._deployment_api_record(self.paths)
        del record["result"]["plan"]["source_commit"]
        bootstrap._atomic_json(self.paths.deployment_record, record)
        helper = self.co._asset_helper()
        original = helper.activate_verified

        def publish(*args, **kwargs):
            self.assertTrue(self.held)
            return original(*args, **kwargs)

        helper.activate_verified = publish
        self.co._asset_helper = lambda: helper
        for _ in range(2):
            self.server.start_deployment(install_body(self.paths, b2, mode="activate", fpga_load=False))
            result = self.finish()
            self.assertEqual(result["state"], "succeeded", result)
            receipt = result["result"]
            self.assertIsNone(receipt["source_commit"])
            self.assertIsNone(receipt["transaction"]["source_commit"])
            self.assertEqual(receipt["stage"], "bundle_install_and_activate")
            self.assertEqual(receipt["active_asset_set"]["asset_set_sha256"], self.digest)
            self.assertFalse(receipt["ready"])
            self.assertEqual(receipt["fpga"], "NOT_RUN")
            self.assertEqual(receipt["dut"], "NOT_RUN")
            self.assertFalse(receipt["runtime_activation_executed"])
            self.assertFalse(self.held)
            b2 = self.server.start_deployment(admit_body(self.paths, "bundle", b2["upload_id"]))
        self.co.root_bundle_loader.assert_not_called()
        self.assertFalse(self.co.paths.systemd_root.exists())
        staged = self.paths.product_root / "assets/staged" / self.digest
        self.assertIsNone(json.loads((staged / "b3-install.json").read_text())["source_commit"])

    def test_optional_unknown_git_commit_is_provenance_only(self):
        self.rewrite(lambda m: m.update(source_commit="f" * 40))
        b2 = self.admit()
        self.assertEqual(b2["result"]["plan"]["source_commit"], "f" * 40)
        self.server.start_deployment(install_body(self.paths, b2, mode="stage_only", fpga_load=False))
        result = self.finish()
        self.assertEqual(result["state"], "succeeded", result)
        self.assertEqual(result["result"]["source_commit"], "f" * 40)
        self.assertFalse((self.paths.product_root / "assets/active.json").exists())

    def test_subprocess_engine_stage_only_accepts_no_source_argument(self):
        b2 = self.admit()
        self.server.bundle_install_runner = bootstrap.run_bundle_install_subprocess
        self.server.start_deployment(install_body(self.paths, b2, mode="stage_only", fpga_load=False))
        result = self.finish()
        self.assertEqual(result["state"], "succeeded", result)
        self.assertIsNone(result["result"]["source_commit"])

    def test_host_simulator_uses_content_identity_without_git(self):
        result = self.co.execute_package_host_only(engine.HostOnlyPackageRequest(
            self.archive, self.digest, TARGET), install_only=True)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["release_id"], "0.1.0-" + self.digest[:16])

    def test_client_b1_b2_b3_with_real_validators_and_synthetic_owner(self):
        calls = []

        def transport(method, path, raw, headers):
            self.assertEqual(headers["Authorization"], "Bearer " + OWNER_TOKEN)
            body = json.loads(raw) if raw else None
            calls.append((method, path, body))
            if path == "/v1/status":
                result = {"identity": {"device_id": device_id(self.paths)}}
            elif path == "/v1/uploads":
                result = {"upload": bootstrap.create_upload(self.paths, **body)}
            elif path.endswith("/chunks"):
                uid = path.split("/")[3]
                result = {"upload": bootstrap.append_chunk(self.paths, uid, **body)}
            elif path.endswith("/commit"):
                result = {"upload": bootstrap.commit_upload(self.paths, path.split("/")[3])}
            elif method == "POST" and path == "/v1/deployments":
                result = {"deployment": self.server.start_deployment(body)}
            elif path == "/v1/deployment":
                result = {"deployment": bootstrap._deployment_api_record(self.paths)}
            else:
                raise AssertionError(path)
            return (202 if result.get("deployment", {}).get("state") == "queued" else 200,
                    json.dumps({"ok": True, **result}).encode())

        api = client.BootstrapAPIClient("https://ppu.example.test", OWNER_TOKEN, transport=transport)
        uid = api.upload(self.archive.read_bytes())
        admitted = api.submit(kind="bundle", upload_id=uid, archive_sha256=self.digest)
        api.install_bundle(admitted, mode="activate", fpga_load=False)
        self.assertEqual(self.finish()["state"], "succeeded")
        for _, _, body in calls:
            if body:
                self.assertNotIn("source_commit", body)
                self.assertNotIn("publisher", body)

    def test_diagnostic_b2_client_accepts_bundle_without_source_provenance(self):
        baseline = load("user_bundle_baseline_client", "ppu_path2_hardware_baseline.py")
        b2 = self.admit()
        api = Mock()
        api.submit.return_value.state = "admitted"
        api.submit.return_value.transaction_id = b2["transaction_id"]
        api.deployment_state.return_value = b2
        result = baseline.b2_admission(api, b2["upload_id"], "a" * 40,
                                       TARGET, self.digest, kind="bundle")
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(self.paths.product_root.exists())

    def test_bad_zip_and_digest_are_denied(self):
        for content, digest in ((b"not-zip", None), (self.archive.read_bytes(), "0" * 64)):
            with self.subTest(digest=digest):
                path = self.root / "bad.zip"
                path.write_bytes(content)
                with self.assertRaises(contract.UnifiedDeploymentError):
                    contract.verify_host_only_artifact(path, expected_sha256=digest or hashlib.sha256(content).hexdigest(),
                                                       target_profile=TARGET)
        self.assertFalse(self.paths.product_root.exists())

    def test_file_sha_dependency_target_and_schema_denials(self):
        original = self.archive.read_bytes()
        mutations = {
            "file_sha": lambda m: m["packages"][0]["files"][0].update(sha256="0" * 64),
            "unknown_dependency": lambda m: m["packages"][0].update(requires=["absent"]),
            "duplicate_id": lambda m: m["packages"][1].update(id="python-smoke"),
            "cycle": lambda m: m["packages"][2].update(requires=["python-smoke"]),
            "target": lambda m: m["target"].update(board="wrong-board"),
            "schema": lambda m: m.update(schema="plasma.ppu.bundle.v2"),
            "malformed_provenance": lambda m: m.update(source_commit={"not": "text"}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                self.archive.write_bytes(original)
                self.rewrite(mutate)
                uid = self.commit()
                with self.assertRaises(bootstrap.BootstrapServiceError):
                    self.server.start_deployment(admit_body(self.paths, "bundle", uid))
                self.assertFalse(self.paths.product_root.exists())

    def test_b1_chunk_and_committed_digest_mismatch(self):
        raw = self.archive.read_bytes()
        uid = bootstrap.create_upload(self.paths, size=len(raw), sha256="0" * 64)["upload_id"]
        with self.assertRaises(bootstrap.BootstrapServiceError):
            bootstrap.append_chunk(self.paths, uid, offset=0,
                                   data_base64=base64.b64encode(raw).decode(), sha256="0" * 64)
        bootstrap.append_chunk(self.paths, uid, offset=0,
                               data_base64=base64.b64encode(raw).decode(), sha256=self.digest)
        with self.assertRaises(bootstrap.BootstrapServiceError):
            bootstrap.commit_upload(self.paths, uid)

    def test_invalid_owner_actions_are_denied_without_product_mutation(self):
        uid = self.commit()
        body = admit_body(self.paths, "bundle", uid)
        body["authorization"]["mac"] = "0" * 64
        with self.assertRaisesRegex(bootstrap.BootstrapServiceError, "OWNER_AUTHORIZATION_INVALID"):
            self.server.start_deployment(body)
        b2 = self.server.start_deployment(admit_body(self.paths, "bundle", uid))
        for field, value in (("mac", "0" * 64), ("device_id", "ppu-device-" + "e" * 24),
                             ("subject_sha256", "0" * 64), ("transaction_id", "0" * 32)):
            with self.subTest(field=field):
                body = install_body(self.paths, b2, mode="activate", fpga_load=False)
                body["authorization"][field] = value
                with self.assertRaises(bootstrap.BootstrapServiceError):
                    self.server.start_deployment(body)
        body = install_body(self.paths, b2, mode="activate", fpga_load=False)
        body["authorization"] = admit_body(self.paths, "bundle", uid)["authorization"]
        with self.assertRaisesRegex(bootstrap.BootstrapServiceError, "ACTION_MISMATCH"):
            self.server.start_deployment(body)
        self.assertFalse(self.paths.product_root.exists())

    def test_fpga_requires_explicit_load_and_separate_owner_privilege(self):
        self.fpga()
        b2 = self.admit()
        self.assertEqual(b2["result"]["fpga_static_qualification"], "STATIC_QUALIFIED")
        with self.assertRaisesRegex(bootstrap.BootstrapServiceError, "REQUIRES_EXPLICIT_LOAD"):
            self.server.start_deployment(install_body(self.paths, b2, mode="activate", fpga_load=False))
        body = install_body(self.paths, b2, mode="activate", fpga_load=True)
        body["authorization"] = install_body(self.paths, b2, mode="activate", fpga_load=False)["authorization"]
        with self.assertRaisesRegex(bootstrap.BootstrapServiceError, "ACTION_MISMATCH"):
            self.server.start_deployment(body)
        self.assertFalse(self.paths.product_root.exists())
        self.co.root_bundle_loader.assert_not_called()

    def test_fpga_abi_contract_mismatch_is_denied_at_b2(self):
        self.fpga()
        contracts = json.loads(self.paths.fpga_image_contracts.read_text())
        contracts["contracts"][0]["abi_version"] = 0x00060001
        self.paths.fpga_image_contracts.write_text(json.dumps(contracts))
        uid = self.commit()
        with self.assertRaises(bootstrap.BootstrapServiceError):
            self.server.start_deployment(admit_body(self.paths, "bundle", uid))
        self.assertFalse(self.paths.product_root.exists())
        self.co.root_bundle_loader.assert_not_called()

    def test_busy_runtime_denies_activation_and_preserves_active(self):
        b2 = self.admit()

        @contextmanager
        def busy():
            raise RuntimeError("RUNTIME_BUSY")
            yield

        self.co.quiescence_lease = busy
        self.server.start_deployment(install_body(self.paths, b2, mode="activate", fpga_load=False))
        result = self.finish()
        self.assertNotEqual(result["state"], "succeeded")
        self.assertEqual(self.co.journal.read().error_code, "b3_runtime_quiesce_denied")
        self.assertFalse((self.paths.product_root / "assets/active.json").exists())
        self.co.root_bundle_loader.assert_not_called()

    def test_site_seal_owner_and_safe_off_denials_remain_enforced(self):
        recovery = load("user_bundle_site_recovery", "ppu_site_recovery.py")
        seals = self.root / "seals"
        seals.mkdir()
        marker = seals / "site1.sealed"
        marker.write_text(json.dumps({"site": 1, "reason": "synthetic-seal"}))
        adapter = Mock(supported_sites=(1, 2))
        adapter.startup_sealed_sites.return_value = set()
        adapter._openocd_running.return_value = False
        adapter.verify_safe_off.side_effect = RuntimeError("SYNTHETIC_SAFE_OFF_FAILURE")
        for active, lease, external in ((True, "idle", False),
                                        (False, "busy", False),
                                        (False, "idle", True),
                                        (False, "idle", False)):
            with self.subTest(active=active, lease=lease, external=external):
                adapter._openocd_running.return_value = external
                result = recovery.recover(
                    1, operator="host-test", adapter=adapter, seal_dir=seals,
                    evidence_dir=self.root / "recovery-evidence",
                    worker_active=lambda: active, runtime_lease=lambda: lease,
                )
                self.assertEqual(result["result"], "DENIED_STILL_SEALED")
                self.assertTrue(marker.is_file())
        # Only the fully quiesced case may even attempt SAFE_OFF; its injected
        # failure preserves the seal. These calls never touch a physical Site.
        adapter.verify_safe_off.assert_called_once()

    def test_engineering_release_source_identity_still_required(self):
        with self.assertRaisesRegex(engine.DeploymentError, "ENGINEERING_PROVENANCE_FORMAT_INVALID"):
            self.co.execute_engineering(engine.EngineeringDeploymentRequest(
                release_artifact=self.archive, module="wordport", source_commit="", artifact_sha256=self.digest))
        with self.assertRaises(TypeError):
            engine.BundleV3InstallRequest(archive=self.archive, artifact_sha256=self.digest,
                                         target_profile=TARGET, api_transaction_id="b" * 32,
                                         source_commit="f" * 40)


if __name__ == "__main__":
    unittest.main()
