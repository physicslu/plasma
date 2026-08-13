from __future__ import annotations

import unittest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.fpga import FPGAInterface
from plasma_interfaces.mock import MockInterface
from plasma_interfaces.openocd import OpenOCDInterface


class MockInterfaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_program_verify_read_and_erase(self) -> None:
        interface = MockInterface(flash_size=32)
        await interface.program(b"abcd", 4)
        await interface.verify(b"abcd", 4)
        self.assertEqual(await interface.read(4, 4), b"abcd")
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

    async def test_fpga_placeholder_is_explicit(self) -> None:
        interface = FPGAInterface(channel_id=0, register_base=0)
        with self.assertRaises(PlasmaError) as caught:
            await interface.read(0, 4)
        self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_NOT_CONFIGURED)
