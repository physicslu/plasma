from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import plasma_core.ic_support as ic_support
from plasma_core.ic_support import ICSupportIntegrityError, ICSupportResolver
from tests.runtime_capability_fixture import materialize_test_root


class ICSupportResolverTests(unittest.TestCase):
    def _root(self, root: str) -> Path:
        return materialize_test_root(Path(root) / "runtime-capability")

    def test_explicit_sw_owned_root_resolves_two_exact_icpns(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            resolver = ICSupportResolver.from_root(self._root(root))

        self.assertEqual(resolver.size, 2)
        self.assertEqual(resolver.exact_icpns, ("STM32F103C8T6", "STM32F103CBT6"))
        c8 = resolver.require_exact("STM32F103C8T6")
        cb = resolver.require_exact("stm32f103cbt6")
        self.assertEqual(c8.programming_profile.profile_id, "stm32f1-medium-density-flash-v0")
        self.assertEqual(cb.programming_profile.profile_id, c8.programming_profile.profile_id)
        self.assertNotEqual(c8.memory_geometry_profile.profile_id, cb.memory_geometry_profile.profile_id)
        self.assertEqual(c8.memory_geometry_profile.data["main_flash_size_bytes"], 64 * 1024)
        self.assertEqual(cb.memory_geometry_profile.data["main_flash_size_bytes"], 128 * 1024)

    def test_runtime_payload_separates_profile_resolution_from_backend_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            payload = ICSupportResolver.from_root(self._root(root)).require_exact(
                "STM32F103C8T6"
            ).to_runtime_payload()
        self.assertFalse(payload["runtime_ready"])
        self.assertEqual(payload["backends"]["openocd"]["state"], "target_mapped")
        self.assertFalse(payload["backends"]["plasma_native"]["runtime_implemented"])

    def test_unbound_icpn_is_not_silently_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            resolver = ICSupportResolver.from_root(self._root(root))
        self.assertIsNone(resolver.resolve_exact("STM32F407VGT6"))
        with self.assertRaisesRegex(KeyError, "no promoted runtime capability binding"):
            resolver.require_exact("STM32F407VGT6")

    def test_summary_reports_test_fixture_not_native_runtime_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            summary = ICSupportResolver.from_root(self._root(root)).summary()
        self.assertEqual(summary["resolved_exact_icpns"], 2)
        self.assertEqual(summary["programming_profiles"], 1)
        self.assertEqual(summary["native_ppu_runtime_ready_exact_icpns"], 0)

    def test_runtime_module_has_no_implicit_research_source(self) -> None:
        self.assertFalse(hasattr(ic_support, "IC_SUPPORT_ROOT_ENV"))
        self.assertFalse(hasattr(ic_support, "IC_SUPPORT_RELATIVE_ROOT"))
        self.assertFalse(hasattr(ic_support, "default_ic_support_root"))
        self.assertFalse(hasattr(ic_support, "get_default_ic_support_resolver"))
        source = Path(ic_support.__file__).read_text(encoding="utf-8")
        self.assertNotIn("data/ic-support", source)
        self.assertNotIn("PLASMA_IC_SUPPORT_ROOT", source)

    def test_duplicate_exact_icpn_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = self._root(root)
            source = test_root / "bindings" / "software-test-runtime-capability-v0.json"
            payload = json.loads(source.read_text(encoding="utf-8"))
            duplicate = dict(payload)
            duplicate["binding_set_id"] = "duplicate-test"
            duplicate["bindings"] = [payload["bindings"][0]]
            (test_root / "bindings" / "duplicate.json").write_text(
                json.dumps(duplicate), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ICSupportIntegrityError, "duplicate runtime capability binding"
            ):
                ICSupportResolver.from_root(test_root)

    def test_dangling_programming_profile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = self._root(root)
            binding = test_root / "bindings" / "software-test-runtime-capability-v0.json"
            payload = json.loads(binding.read_text(encoding="utf-8"))
            payload["bindings"][0]["profiles"]["programming"] = "missing-profile"
            binding.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ICSupportIntegrityError, "dangling runtime capability profile"
            ):
                ICSupportResolver.from_root(test_root)

    def test_wrong_profile_kind_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = self._root(root)
            binding = test_root / "bindings" / "software-test-runtime-capability-v0.json"
            payload = json.loads(binding.read_text(encoding="utf-8"))
            payload["bindings"][0]["profiles"]["programming"] = "stm32f103c8-64k-v0"
            binding.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ICSupportIntegrityError, "has kind 'memory_geometry'"):
                ICSupportResolver.from_root(test_root)

    def test_malformed_revision_override_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            test_root = self._root(root)
            binding = test_root / "bindings" / "software-test-runtime-capability-v0.json"
            payload = json.loads(binding.read_text(encoding="utf-8"))
            payload["bindings"][0]["revision_overrides"] = ["not-an-object"]
            binding.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(
                ICSupportIntegrityError, r"revision_overrides\[0\] must be an object"
            ):
                ICSupportResolver.from_root(test_root)


if __name__ == "__main__":
    unittest.main()
