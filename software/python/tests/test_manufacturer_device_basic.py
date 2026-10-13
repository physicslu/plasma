from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from plasma_core.ic_support import default_ic_support_root
from plasma_core.manufacturer_device_basic import (
    DEVICE_BASIC_RELATIVE_PATH,
    ICSupportIntegrityError,
    ManufacturerDeviceBasicResolver,
)


class ManufacturerDeviceBasicResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = default_ic_support_root() / DEVICE_BASIC_RELATIVE_PATH
        cls.resolver = ManufacturerDeviceBasicResolver.from_file(cls.path)
        cls.payload = json.loads(cls.path.read_text(encoding="utf-8"))

    def resolve(self, **overrides):
        values = {
            "icpn": "STM32F103C8T6",
            "manufacturer": "STMicroelectronics",
            "family": "STM32F1",
            "series": "STM32F103",
            "base_device": "STM32F103C8",
            "package": "LQFP",
            "pin_count": "48",
            "flash_size": "64 KiB",
            "temperature_grade": "-40 to 85 C",
        }
        values.update(overrides)
        return self.resolver.resolve_exact(**values)

    def write_payload(self, payload: dict) -> Path:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False)
        with tmp:
            json.dump(payload, tmp)
        return Path(tmp.name)

    def test_current_profile_binds_all_stm32f1_exact_icpns(self) -> None:
        self.assertEqual(self.resolver.size, 280)

    def test_c8_basic_profile_is_independent_from_programming_authority(self) -> None:
        resolved = self.resolve()
        self.assertIsNotNone(resolved)
        assert resolved is not None
        payload = resolved.to_payload()
        self.assertEqual(payload["status"], "manufacturer_device_basic_available")
        self.assertEqual(payload["ram_size"], "20 KiB")
        self.assertEqual(payload["operating_vdd_v"], {"min": 2.0, "max": 3.6})
        self.assertEqual(payload["operating_temperature_c"], {"min": -40, "max": 85})
        self.assertFalse(payload["programming_profile_authority"])
        self.assertFalse(payload["hardware_runtime_ready"])
        self.assertFalse(payload["physical_programming_qualified"])

    def test_representative_density_groups_resolve_expected_ram(self) -> None:
        cases = [
            (
                {
                    "icpn": "STM32F100C4T6B",
                    "series": "STM32F100",
                    "base_device": "STM32F100C4",
                    "package": "LQFP",
                    "pin_count": "48",
                    "flash_size": "16 KiB",
                    "temperature_grade": "-40 to 85 C",
                },
                "4 KiB",
            ),
            (
                {
                    "icpn": "STM32F101RBT6",
                    "series": "STM32F101",
                    "base_device": "STM32F101RB",
                    "package": "LQFP",
                    "pin_count": "64",
                    "flash_size": "128 KiB",
                    "temperature_grade": "-40 to 85 C",
                },
                "16 KiB",
            ),
            (
                {
                    "icpn": "STM32F105R8T6",
                    "series": "STM32F105",
                    "base_device": "STM32F105R8",
                    "package": "LQFP",
                    "pin_count": "64",
                    "flash_size": "64 KiB",
                    "temperature_grade": "-40 to 85 C",
                },
                "64 KiB",
            ),
            (
                {
                    "icpn": "STM32F107RBT6",
                    "series": "STM32F107",
                    "base_device": "STM32F107RB",
                    "package": "LQFP",
                    "pin_count": "64",
                    "flash_size": "128 KiB",
                    "temperature_grade": "-40 to 85 C",
                },
                "64 KiB",
            ),
        ]
        for args, expected_ram in cases:
            with self.subTest(icpn=args["icpn"]):
                resolved = self.resolver.resolve_exact(
                    manufacturer="STMicroelectronics",
                    family="STM32F1",
                    **args,
                )
                self.assertIsNotNone(resolved)
                assert resolved is not None
                self.assertEqual(resolved.ram_size, expected_ram)

    def test_other_family_does_not_gain_implicit_applicability(self) -> None:
        self.assertIsNone(
            self.resolver.resolve_exact(
                "STM32F407VGT6",
                manufacturer="STMicroelectronics",
                family="STM32F4",
                series="STM32F407",
                base_device="STM32F407VG",
                package="LQFP",
                pin_count="100",
                flash_size="1024 KiB",
                temperature_grade="-40 to 85 C",
            )
        )

    def test_group_owned_constraints_fail_closed_but_catalog_owned_fields_compose(self) -> None:
        with self.assertRaisesRegex(ICSupportIntegrityError, "Flash"):
            self.resolve(flash_size="128 KiB")
        with self.assertRaisesRegex(ICSupportIntegrityError, "series"):
            self.resolve(series="STM32F101")

        package_variant = self.resolve(package="UFQFPN")
        self.assertIsNotNone(package_variant)
        assert package_variant is not None
        self.assertEqual(package_variant.package, "UFQFPN")

        temperature_variant = self.resolve(temperature_grade="-40 to 105 C")
        self.assertIsNotNone(temperature_variant)
        assert temperature_variant is not None
        self.assertEqual(
            temperature_variant.operating_temperature_c,
            {"min": -40, "max": 105},
        )

    def test_non_st_evidence_or_fake_content_lock_is_rejected(self) -> None:
        for mutation, pattern in (
            (
                lambda p: p["groups"]["stm32f103-64k"]["evidence"].__setitem__(
                    "authority", "OpenOCD"
                ),
                "non-ST authority",
            ),
            (
                lambda p: p["groups"]["stm32f103-64k"]["evidence"].__setitem__(
                    "content_lock", "pretend-sha"
                ),
                "must not fake a content lock",
            ),
        ):
            payload = copy.deepcopy(self.payload)
            mutation(payload)
            path = self.write_payload(payload)
            try:
                with self.assertRaisesRegex(ICSupportIntegrityError, pattern):
                    ManufacturerDeviceBasicResolver.from_file(path)
            finally:
                path.unlink(missing_ok=True)

    def test_implicit_binding_expansion_is_not_allowed(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["bindings"].pop("STM32F103C8T6")
        path = self.write_payload(payload)
        try:
            with self.assertRaisesRegex(ICSupportIntegrityError, "must bind 280"):
                ManufacturerDeviceBasicResolver.from_file(path)
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
