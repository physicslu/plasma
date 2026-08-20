from __future__ import annotations

import unittest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.fpga import FPGAInterface
from plasma_interfaces.mock import MockInterface
from plasma_interfaces.openocd import OpenOCDInterface


class MockInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_program_verify_read_and_erase(self) -> None:
        interface = MockInterface(flash_size=32)
        image = b"abcd"
        await interface.program(image, 4)
        await interface.verify(image, 4)
        self.assertEqual(await interface.read(4, 4), image)
        await interface.erase()
        self.assertEqual(await interface.read(4, 4), b"\xff" * 4)

    async def test_out_of_range_access_rejected(self) -> None:
        interface = MockInterface(flash_size=8)
        with self.assertRaises(PlasmaError) as caught:
            await interface.read(7, 2)
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_out_of_range_access_fails_before_progress(self) -> None:
        interface = MockInterface(flash_size=8, default_delay_s=0.1)
        progress_calls: list[tuple[int, int]] = []

        async def progress(done: int, total: int) -> None:
            progress_calls.append((done, total))

        with self.assertRaises(PlasmaError):
            await interface.program(b"too-large", address=1, progress=progress)
        self.assertEqual(progress_calls, [])
        self.assertEqual(interface.calls["program"], 0)

    async def test_from_options_does_not_mutate_caller_failure_map(self) -> None:
        options = {"failures": {"program": 1}}
        interface = MockInterface.from_options(options)
        with self.assertRaises(PlasmaError):
            await interface.program(b"data")
        self.assertEqual(options["failures"]["program"], 1)

    def test_size_aware_timing_is_overhead_plus_bytes_over_throughput(self) -> None:
        interface = MockInterface(
            throughput_bytes_per_s={"program": 100.0},
            operation_overheads_s={"program": 0.5},
        )
        self.assertAlmostEqual(interface.estimated_delay_s("program", 100), 1.5)
        self.assertAlmostEqual(interface.estimated_delay_s("program", 400), 4.5)

    def test_explicit_delay_overrides_size_aware_timing(self) -> None:
        interface = MockInterface(
            default_delay_s=9.0,
            delays={"program": 0.25},
            throughput_bytes_per_s={"program": 1.0},
            operation_overheads_s={"program": 1.0},
        )
        self.assertAlmostEqual(interface.estimated_delay_s("program", 4096), 0.25)

    def test_erase_size_basis_can_use_full_mock_flash_size(self) -> None:
        interface = MockInterface(
            flash_size=4096,
            throughput_bytes_per_s={"erase": 2048.0},
            operation_overheads_s={"erase": 0.5},
        )
        self.assertAlmostEqual(interface.estimated_delay_s("erase", interface.flash_size), 2.5)

    def test_invalid_size_aware_timing_options_are_rejected(self) -> None:
        invalid_options = (
            {"throughput_bytes_per_s": {"program": 0}},
            {"throughput_bytes_per_s": {"unknown": 1}},
            {"operation_overheads_s": {"verify": -1}},
        )
        for options in invalid_options:
            with self.subTest(options=options):
                with self.assertRaises(PlasmaError) as caught:
                    MockInterface.from_options(options)
                self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)

    async def test_unknown_mock_option_is_rejected(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            MockInterface.from_options({"delaiys": {"erase": 1.0}})
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)


class HardwareBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_openocd_is_explicit(self) -> None:
        interface = OpenOCDInterface({})
        with self.assertRaises(PlasmaError) as caught:
            await interface.erase()
        self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_NOT_CONFIGURED)

    async def test_fpga_placeholder_uses_one_based_site_identity_only(self) -> None:
        interface = FPGAInterface(site_id=1, register_base=0)
        self.assertEqual(interface.site_id, 1)
        with self.assertRaises(PlasmaError) as caught:
            await interface.read(0, 4)
        self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_NOT_CONFIGURED)
        self.assertEqual(caught.exception.context["site_id"], 1)

    async def test_fpga_rejects_site_zero(self) -> None:
        with self.assertRaises(PlasmaError) as caught:
            FPGAInterface(site_id=0, register_base=0)
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)


if __name__ == "__main__":
    unittest.main()
