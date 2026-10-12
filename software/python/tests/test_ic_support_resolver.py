from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from plasma_core.ic_support import (
    IC_SUPPORT_ROOT_ENV,
    ICSupportIntegrityError,
    ICSupportResolver,
    default_ic_support_root,
    get_default_ic_support_resolver,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
IC_SUPPORT_ROOT = REPOSITORY_ROOT / "data" / "ic-support"


class ICSupportResolverTests(unittest.TestCase):
    def test_current_pilot_resolves_two_exact_icpns_into_reusable_profiles(self) -> None:
        resolver = ICSupportResolver.from_root(IC_SUPPORT_ROOT)

        self.assertEqual(resolver.size, 2)
        self.assertEqual(
            resolver.exact_icpns,
            ("STM32F103C8T6", "STM32F103CBT6"),
        )

        c8 = resolver.require_exact("STM32F103C8T6")
        cb = resolver.require_exact("stm32f103cbt6")

        self.assertEqual(c8.programming_profile.profile_id, "stm32f1-medium-density-flash-v0")
        self.assertEqual(cb.programming_profile.profile_id, c8.programming_profile.profile_id)
        self.assertEqual(c8.profile("option").profile_id, cb.profile("option").profile_id)
        self.assertEqual(c8.profile("security").profile_id, cb.profile("security").profile_id)
        self.assertEqual(c8.profile("package_hardware").profile_id, cb.profile("package_hardware").profile_id)
        self.assertNotEqual(
            c8.memory_geometry_profile.profile_id,
            cb.memory_geometry_profile.profile_id,
        )
        self.assertEqual(c8.memory_geometry_profile.data["main_flash_size_bytes"], 64 * 1024)
        self.assertEqual(cb.memory_geometry_profile.data["main_flash_size_bytes"], 128 * 1024)
        self.assertEqual(c8.openocd_target_config, "tcl/target/stm32f1x.cfg")
        self.assertEqual(cb.openocd_target_config, c8.openocd_target_config)

        self.assertIsNotNone(c8.manufacturer_profile)
        self.assertIsNone(cb.manufacturer_profile)
        selected = c8.to_selected_profile_payload()
        assert selected is not None
        self.assertEqual(selected["device"]["operating_electrical"]["vdd_v"], {"min": 2.0, "max": 3.6})
        self.assertEqual(selected["device"]["memory_map"]["main_flash"]["size_bytes"], 64 * 1024)
        self.assertEqual(selected["programming"]["electrical"]["vdd_programming_v"], {"min": 2.0, "max": 3.6, "basis": "PM0075 states Program/Erase operations are supported over the whole product voltage range"})
        self.assertIsNone(selected["programming"]["interfaces"]["SWD"]["clock_hz"]["manufacturer_max"])
        self.assertFalse(selected["plasma_compatibility"]["hardware_runtime_ready"])
        self.assertFalse(selected["plasma_compatibility"]["physical_programming_qualified"])

    def test_runtime_payload_separates_profile_resolution_from_backend_implementation(self) -> None:
        payload = ICSupportResolver.from_root(IC_SUPPORT_ROOT).require_exact(
            "STM32F103C8T6"
        ).to_runtime_payload()

        self.assertFalse(payload["runtime_ready"])
        self.assertEqual(payload["backends"]["openocd"]["state"], "target_mapped")
        self.assertEqual(
            payload["backends"]["openocd"]["target_config"],
            "tcl/target/stm32f1x.cfg",
        )
        self.assertFalse(payload["backends"]["plasma_native"]["runtime_implemented"])
        self.assertEqual(
            payload["backends"]["plasma_native"]["programming_profile_id"],
            "stm32f1-medium-density-flash-v0",
        )

    def test_admitted_but_unbound_f4_is_not_silently_promoted(self) -> None:
        resolver = ICSupportResolver.from_root(IC_SUPPORT_ROOT)
        self.assertIsNone(resolver.resolve_exact("STM32F407VGT6"))
        with self.assertRaisesRegex(KeyError, "no evidence-backed IC Support binding"):
            resolver.require_exact("STM32F407VGT6")

    def test_summary_reports_knowledge_not_native_runtime_readiness(self) -> None:
        summary = ICSupportResolver.from_root(IC_SUPPORT_ROOT).summary()
        self.assertEqual(summary["resolved_exact_icpns"], 2)
        self.assertEqual(summary["programming_profiles"], 1)
        self.assertEqual(
            summary["programming_profile_ids"],
            ["stm32f1-medium-density-flash-v0"],
        )
        self.assertEqual(summary["manufacturer_selected_profiles"], 1)
        self.assertEqual(summary["native_ppu_runtime_ready_exact_icpns"], 0)

    def test_environment_root_override_is_authoritative(self) -> None:
        configured = Path("/tmp/plasma-ic-support")
        with patch.dict("os.environ", {IC_SUPPORT_ROOT_ENV: str(configured)}):
            self.assertEqual(default_ic_support_root(), configured)

    def test_duplicate_exact_icpn_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = Path(root) / "ic-support"
            shutil.copytree(IC_SUPPORT_ROOT, test_root)
            source = test_root / "bindings" / "stm32f103c-pilot-v0.json"
            payload = json.loads(source.read_text(encoding="utf-8"))
            duplicate = dict(payload)
            duplicate["binding_set_id"] = "duplicate-test"
            duplicate["bindings"] = [payload["bindings"][0]]
            (test_root / "bindings" / "duplicate.json").write_text(
                json.dumps(duplicate),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ICSupportIntegrityError, "duplicate IC Support binding"):
                ICSupportResolver.from_root(test_root)

    def test_dangling_programming_profile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = Path(root) / "ic-support"
            shutil.copytree(IC_SUPPORT_ROOT, test_root)
            binding = test_root / "bindings" / "stm32f103c-pilot-v0.json"
            payload = json.loads(binding.read_text(encoding="utf-8"))
            payload["bindings"][0]["profiles"]["programming"] = "missing-profile"
            binding.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ICSupportIntegrityError, "dangling IC Support profile"):
                ICSupportResolver.from_root(test_root)

    def test_wrong_profile_kind_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = Path(root) / "ic-support"
            shutil.copytree(IC_SUPPORT_ROOT, test_root)
            binding = test_root / "bindings" / "stm32f103c-pilot-v0.json"
            payload = json.loads(binding.read_text(encoding="utf-8"))
            payload["bindings"][0]["profiles"]["programming"] = "stm32f103c8-64k-v0"
            binding.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ICSupportIntegrityError, "has kind 'memory_geometry'"):
                ICSupportResolver.from_root(test_root)

    def test_malformed_revision_override_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = Path(root) / "ic-support"
            shutil.copytree(IC_SUPPORT_ROOT, test_root)
            binding = test_root / "bindings" / "stm32f103c-pilot-v0.json"
            payload = json.loads(binding.read_text(encoding="utf-8"))
            payload["bindings"][0]["revision_overrides"] = ["not-an-object"]
            binding.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                ICSupportIntegrityError,
                r"revision_overrides\[0\] must be an object",
            ):
                ICSupportResolver.from_root(test_root)

    def test_default_cached_resolver_uses_current_source_tree(self) -> None:
        resolver = get_default_ic_support_resolver()
        self.assertEqual(resolver.size, 2)
        self.assertEqual(resolver.require_exact("STM32F103C8T6").expected_catalog["base_device"], "STM32F103C8")

    def test_manufacturer_profile_fails_closed_when_programming_electrical_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = Path(root) / "ic-support"
            shutil.copytree(IC_SUPPORT_ROOT, test_root)
            baseline = test_root / "manufacturer-baseline" / "stm32f103c8t6-manufacturer-only-v1.json"
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            del payload["programming_profile"]["programming_electrical"]["vdd_programming_v"]
            baseline.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

            import hashlib
            lock = test_root / "manufacturer-baseline" / "stm32f103c8t6-manufacturer-only-v1.lock.json"
            lock_payload = json.loads(lock.read_text(encoding="utf-8"))
            lock_payload["canonical_file_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
            lock.write_text(json.dumps(lock_payload), encoding="utf-8")

            with self.assertRaisesRegex(ICSupportIntegrityError, "programming VDD range is required"):
                ICSupportResolver.from_root(test_root)

    def test_manufacturer_profile_rejects_blue_pill_128k_identity_drift(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = Path(root) / "ic-support"
            shutil.copytree(IC_SUPPORT_ROOT, test_root)
            baseline = test_root / "manufacturer-baseline" / "stm32f103c8t6-manufacturer-only-v1.json"
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            payload["device_profile"]["memory_map"]["main_flash"]["size_bytes"] = 128 * 1024
            payload["device_profile"]["memory_map"]["main_flash"]["end"] = "0x0801FFFF"
            payload["device_profile"]["memory_map"]["main_flash"]["page_count"] = 128
            baseline.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

            import hashlib
            lock = test_root / "manufacturer-baseline" / "stm32f103c8t6-manufacturer-only-v1.lock.json"
            lock_payload = json.loads(lock.read_text(encoding="utf-8"))
            lock_payload["canonical_file_sha256"] = hashlib.sha256(baseline.read_bytes()).hexdigest()
            lock.write_text(json.dumps(lock_payload), encoding="utf-8")

            with self.assertRaisesRegex(ICSupportIntegrityError, "Flash size does not match catalog binding"):
                ICSupportResolver.from_root(test_root)


if __name__ == "__main__":
    unittest.main()
