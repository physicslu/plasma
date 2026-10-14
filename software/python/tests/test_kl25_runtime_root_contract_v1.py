"""Installed-wheel KL25 backend lock path/integrity and no-authorization regression."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import plasma_interfaces.kl25_openocd_plan as kl25
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import IC_SUPPORT_ROOT_ENV
from plasma_server.execution_router import _default_compiler_registry

ROOT = Path(__file__).resolve().parents[3]
SUPPORT = ROOT / "data/ic-support"
LOCK = SUPPORT / kl25.KL25_IMPLEMENTATION_LOCK_RELATIVE_PATH

class KL25InstalledRuntimeLockTests(unittest.TestCase):
    def test_explicit_support_root_survives_site_packages_module_path(self):
        wheel = ROOT / ".venv/lib/python3.12/site-packages/plasma_interfaces/kl25_openocd_plan.py"
        with patch.dict(os.environ, {IC_SUPPORT_ROOT_ENV: str(SUPPORT)}), patch.object(kl25, "__file__", str(wheel)):
            lock = kl25.load_backend_lock()
        self.assertEqual(lock["lock_digest"], kl25.KL25_IMPLEMENTATION_LOCK_DIGEST)
        self.assertEqual(lock["admitted_constraints"]["target_config"], kl25.KL25_TARGET_CONFIG)
        self.assertFalse(lock["trust_boundary"]["production_admission"])
        self.assertFalse(lock["trust_boundary"]["hardware_behavior_validated"])

    def test_missing_and_invalid_explicit_lock_fail_configuration_error(self):
        with tempfile.TemporaryDirectory() as temp:
            dst = Path(temp) / kl25.KL25_IMPLEMENTATION_LOCK_RELATIVE_PATH
            dst.parent.mkdir(parents=True)
            with patch.dict(os.environ, {IC_SUPPORT_ROOT_ENV: str(temp)}):
                for raw in (None, b"bad-json", b"[]", LOCK.read_bytes().replace(b"0x00000400", b"0x00000800", 1)):
                    with self.subTest(raw=raw[:20] if raw else "missing"):
                        if raw is None:
                            dst.unlink(missing_ok=True)
                        else:
                            dst.write_bytes(raw)
                        with self.assertRaises(PlasmaError) as error:
                            kl25.load_backend_lock()
                        self.assertEqual(error.exception.code, ErrorCode.CONFIG_INVALID)

    def test_resealed_tampered_lock_cannot_override_approved_hash(self):
        v = json.loads(LOCK.read_text(encoding="utf-8"))
        v["admitted_constraints"]["program_start_alignment_bytes"] = 8
        unsigned = {k: val for k,val in v.items() if k!="lock_digest"}
        v["lock_digest"] = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as temp:
            dst = Path(temp) / kl25.KL25_IMPLEMENTATION_LOCK_RELATIVE_PATH
            dst.parent.mkdir(parents=True)
            dst.write_text(json.dumps(v),encoding="utf-8")
            with patch.dict(os.environ,{IC_SUPPORT_ROOT_ENV:str(temp)}):
                with self.assertRaisesRegex(PlasmaError,"digest mismatch") as error:
                    kl25.load_backend_lock()
                self.assertEqual(error.exception.code,ErrorCode.CONFIG_INVALID)

    def test_installed_module_without_explicit_root_fails_closed(self):
        import plasma_core.ic_support as ic_support
        with patch.dict(os.environ,{},clear=True), patch.object(ic_support,"_repository_root",return_value=ROOT/".venv/lib"):
            with self.assertRaisesRegex(PlasmaError,"configured IC Support root") as error:
                kl25.load_backend_lock()
            self.assertEqual(error.exception.code,ErrorCode.CONFIG_INVALID)

    def test_default_compiler_binding_is_not_an_operation_admission(self):
        registry = _default_compiler_registry()
        for operation in (Operation.PROGRAM,Operation.ERASE,Operation.READ,Operation.VERIFY):
            with self.subTest(operation=operation):
                with self.assertRaises(PlasmaError) as error:
                    registry.select("MKL25Z128VLK4",operation)
                self.assertEqual(error.exception.code,ErrorCode.OPERATION_UNSUPPORTED)

    def test_module_relative_root_regression_guard_for_affected_loaders(self):
        modules = (
            "software/python/plasma_interfaces/kl25_openocd_plan.py",
            "software/python/plasma_web/nxp_manufacturer_device_evidence.py",
            "software/python/plasma_web/backend_candidate_registry.py",
            "software/python/plasma_web/backend_source_reference.py",
            "software/python/plasma_web/openocd_provider_registry.py",
        )
        for module in modules:
            with self.subTest(module=module):
                self.assertNotIn("Path(__file__).resolve().parents[3]", (ROOT/module).read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
