from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from plasma_core.programming_hardware import (
    ProgrammingHardwareIntegrityError,
    ProgrammingHardwareRegistry,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
IC_SUPPORT_ROOT = REPOSITORY_ROOT / "data" / "ic-support"


class ProgrammingHardwareRegistryTests(unittest.TestCase):
    def test_c8_exact_socket_design_input_is_resolvable_and_fail_closed(self) -> None:
        registry = ProgrammingHardwareRegistry.from_root(IC_SUPPORT_ROOT)

        self.assertEqual(registry.size, 1)
        self.assertEqual(registry.exact_icpns, ("STM32F103C8T6",))

        record = registry.require_exact("stm32f103c8t6")
        self.assertEqual(record.profile_id, "stm32f103c8t6-lqfp48-swd-socket-v1")
        self.assertEqual(record.manufacturer, "STMicroelectronics")
        self.assertEqual(record.base_device, "STM32F103C8")
        self.assertEqual(record.package, "LQFP")
        self.assertEqual(record.pin_count, 48)
        self.assertEqual(record.programming_interface, "SWD")

        data = record.data
        self.assertEqual(
            data["design_input_state"],
            "socket_schematic_ready_not_physically_qualified",
        )
        self.assertEqual(data["package_mechanical"]["body_size_mm"], {"x": 7.0, "y": 7.0})
        self.assertEqual(data["package_mechanical"]["overall_span_mm"], {"x": 9.0, "y": 9.0})
        self.assertEqual(data["package_mechanical"]["lead_pitch_mm"], 0.5)
        self.assertEqual(data["programming_interface"]["signals"]["SWDIO"]["package_pin"], 34)
        self.assertEqual(data["programming_interface"]["signals"]["SWCLK"]["package_pin"], 37)
        self.assertEqual(data["programming_interface"]["signals"]["NRST"]["package_pin"], 7)
        self.assertEqual(data["fixture_contact_contract"]["minimum_contact_count"], 11)
        self.assertEqual(
            {item["package_pin"] for item in data["fixture_contact_contract"]["mandatory_contacts"]},
            {7, 8, 9, 23, 24, 34, 35, 36, 37, 47, 48},
        )

        physical = data["physical_validation"]
        self.assertFalse(physical["fixture_qualified"])
        self.assertFalse(physical["hardware_runtime_ready"])
        self.assertFalse(physical["physical_programming_qualified"])
        self.assertFalse(physical["hil_pass"])

        payload = record.to_dict()
        self.assertFalse(payload["execution_authorized"])
        self.assertFalse(payload["catalog_level_authority"])

    def test_same_package_cbt6_does_not_inherit_c8_hardware_evidence(self) -> None:
        registry = ProgrammingHardwareRegistry.from_root(IC_SUPPORT_ROOT)

        self.assertIsNone(registry.resolve_exact("STM32F103CBT6"))
        with self.assertRaisesRegex(KeyError, "no Programming Hardware design input"):
            registry.require_exact("STM32F103CBT6")

    def test_summary_is_not_catalog_or_execution_authority(self) -> None:
        summary = ProgrammingHardwareRegistry.from_root(IC_SUPPORT_ROOT).summary()

        self.assertEqual(summary["design_input_exact_icpns"], 1)
        self.assertEqual(summary["exact_icpns"], ["STM32F103C8T6"])
        self.assertFalse(summary["execution_authorized_by_registry"])
        self.assertFalse(summary["catalog_level_authority"])

    def test_duplicate_exact_hardware_profile_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ic-support"
            shutil.copytree(IC_SUPPORT_ROOT, root)
            original = (
                root
                / "profiles"
                / "package-hardware"
                / "stm32f103c8t6-lqfp48-swd-socket-v1.json"
            )
            duplicate = json.loads(original.read_text(encoding="utf-8"))
            duplicate["profile_id"] = "stm32f103c8t6-lqfp48-swd-socket-duplicate"
            (
                root
                / "profiles"
                / "package-hardware"
                / "stm32f103c8t6-lqfp48-swd-socket-duplicate.json"
            ).write_text(json.dumps(duplicate), encoding="utf-8")

            with self.assertRaisesRegex(
                ProgrammingHardwareIntegrityError,
                "duplicate Programming Hardware profile for exact ICPN",
            ):
                ProgrammingHardwareRegistry.from_root(root)

    def test_design_input_cannot_claim_hil(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ic-support"
            shutil.copytree(IC_SUPPORT_ROOT, root)
            path = (
                root
                / "profiles"
                / "package-hardware"
                / "stm32f103c8t6-lqfp48-swd-socket-v1.json"
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["data"]["physical_validation"]["hil_pass"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(
                ProgrammingHardwareIntegrityError,
                "design input must keep hil_pass=false",
            ):
                ProgrammingHardwareRegistry.from_root(root)


if __name__ == "__main__":
    unittest.main()
