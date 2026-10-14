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
    get_default_manufacturer_device_basic_resolver,
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
        self.assertIsNone(payload["io_supply_v"])
        self.assertIsNone(payload["vdda_v"])
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

    def test_default_registry_covers_all_admitted_m1_family_profiles(self) -> None:
        registry = get_default_manufacturer_device_basic_resolver()
        self.assertEqual(registry.size, 1660)
        self.assertEqual(
            registry.profile_ids,
            (
                "stm32c0-device-basic-v1",
                "stm32f1-device-basic-v1",
                "stm32f2-device-basic-v1",
                "stm32g0-device-basic-v1",
                "stm32g4-device-basic-v1",
                "stm32h7rs-device-basic-v1",
                "stm32l5-device-basic-v1",
                "stm32n6-device-basic-v1",
                "stm32u0-device-basic-v1",
                "stm32u3-device-basic-v1",
                "stm32wl3-device-basic-v1",
                "stm32wlx-device-basic-v1",
            ),
        )

        c0 = registry.resolve_exact(
            "STM32C011F4P6",
            manufacturer="STMicroelectronics",
            family="STM32C0",
            series="STM32C011",
            base_device="STM32C011F4",
            package="TSSOP",
            pin_count="20",
            flash_size="16 KiB",
            temperature_grade="-40 to 85 C",
        )
        self.assertIsNotNone(c0)
        assert c0 is not None
        self.assertEqual(c0.ram_size, "6 KiB")
        self.assertEqual(c0.operating_vdd_v, {"min": 2.0, "max": 3.6})
        self.assertIsNone(c0.io_supply_v)
        self.assertIsNone(c0.vdda_v)

        f2 = registry.resolve_exact(
            "STM32F205RBT6",
            manufacturer="STMicroelectronics",
            family="STM32F2",
            series="STM32F205",
            base_device="STM32F205RB",
            package="LQFP",
            pin_count="64",
            flash_size="128 KiB",
            temperature_grade="-40 to 85 C",
        )
        self.assertIsNotNone(f2)
        assert f2 is not None
        self.assertEqual(f2.ram_size, "64 KiB")
        self.assertEqual(f2.operating_vdd_v, {"min": 1.8, "max": 3.6})
        self.assertIsNone(f2.io_supply_v)
        self.assertIsNone(f2.vdda_v)

        g0 = registry.resolve_exact(
            "STM32G031K8T3",
            manufacturer="STMicroelectronics",
            family="STM32G0",
            series="STM32G031",
            base_device="STM32G031K8",
            package="LQFP",
            pin_count="32",
            flash_size="64 KiB",
            temperature_grade="-40 to 125 C",
        )
        self.assertIsNotNone(g0)
        assert g0 is not None
        self.assertEqual(g0.ram_size, "8 KiB")
        self.assertEqual(g0.operating_vdd_v, {"min": 1.7, "max": 3.6})
        self.assertIsNone(g0.io_supply_v)
        self.assertIsNone(g0.vdda_v)

        g4 = registry.resolve_exact(
            "STM32G474VCH3TR",
            manufacturer="STMicroelectronics",
            family="STM32G4",
            series="STM32G474",
            base_device="STM32G474VC",
            package="TFBGA",
            pin_count="100",
            flash_size="256 KiB",
            temperature_grade="-40 to 125 C",
        )
        self.assertIsNotNone(g4)
        assert g4 is not None
        self.assertEqual(g4.ram_size, "128 KiB")
        self.assertEqual(g4.operating_vdd_v, {"min": 1.71, "max": 3.6})
        self.assertIsNone(g4.io_supply_v)
        self.assertEqual(g4.vdda_v, {"min": 1.71, "max": 3.6})

        l5 = registry.resolve_exact(
            "STM32L552QCI6Q",
            manufacturer="STMicroelectronics",
            family="STM32L5",
            series="STM32L552",
            base_device="STM32L552QC",
            package="UFBGA",
            pin_count="132",
            flash_size="256 KiB",
            temperature_grade="-40..85 C",
        )
        self.assertIsNotNone(l5)
        assert l5 is not None
        self.assertEqual(l5.ram_size, "256 KiB")
        self.assertEqual(l5.operating_vdd_v, {"min": 1.71, "max": 3.6})
        self.assertEqual(l5.operating_temperature_c, {"min": -40, "max": 85})

        n6 = registry.resolve_exact(
            "STM32N657A0H3Q",
            manufacturer="STMicroelectronics",
            family="STM32N6",
            series="STM32N657",
            base_device="STM32N657A0",
            package="VFBGA",
            pin_count="169",
            flash_size="0-1 KiB",
            temperature_grade="-40 to 125 C",
        )
        self.assertIsNotNone(n6)
        assert n6 is not None
        self.assertEqual(n6.ram_size, "4.2 MB")
        self.assertEqual(n6.flash_size, "0-1 KiB")
        self.assertEqual(n6.operating_vdd_v, {"min": 1.71, "max": 3.6})
        self.assertIsNone(n6.io_supply_v)
        self.assertIsNone(n6.vdda_v)

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

    def test_optional_voltage_evidence_must_be_a_valid_range(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["groups"]["stm32f103-64k"]["vdda_v"] = {"min": 3.6, "max": 1.8}
        path = self.write_payload(payload)
        try:
            with self.assertRaisesRegex(ICSupportIntegrityError, "invalid VDDA"):
                ManufacturerDeviceBasicResolver.from_file(path)
        finally:
            path.unlink(missing_ok=True)

    def test_non_st_or_non_selector_evidence_and_fake_content_lock_are_rejected(self) -> None:
        for mutation, pattern in (
            (
                lambda p: p["groups"]["stm32f103-64k"]["evidence"].__setitem__(
                    "authority", "OpenOCD"
                ),
                "non-ST authority",
            ),
            (
                lambda p: p["groups"]["stm32f103-64k"]["evidence"].__setitem__(
                    "source_surface", "st_product_page"
                ),
                "unsupported source surface",
            ),
            (
                lambda p: p["groups"]["stm32f103-64k"]["evidence"].__setitem__(
                    "selector_url",
                    "https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html",
                ),
                "Product Selector URL",
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
