from __future__ import annotations

import asyncio
import unittest

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.site_safety import SiteSafetyControl, SiteSafetySequencer


class RecordingSiteSafetyControl(SiteSafetyControl):
    def __init__(
        self,
        *,
        fail_power_good: bool = False,
        fail_reclaim_reset: bool = False,
    ) -> None:
        self.events: list[str] = []
        self.powered = False
        self.site_reset_asserted = False
        self.backend_owns_reset = False
        self.fail_power_good = fail_power_good
        self.fail_reclaim_reset = fail_reclaim_reset

    async def assert_reset(self) -> None:
        self.events.append("assert_reset")
        if self.backend_owns_reset and self.fail_reclaim_reset:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "injected reset-reclaim failure",
            )
        self.site_reset_asserted = True
        self.backend_owns_reset = False

    async def power_on(self) -> None:
        self.events.append("power_on")
        if not self.site_reset_asserted:
            raise AssertionError("target power must not be enabled before Site reset is asserted")
        self.powered = True

    async def wait_power_good(self, timeout_s: float) -> None:
        self.events.append(f"wait_power_good:{timeout_s}")
        if not self.powered:
            raise AssertionError("power-good cannot be checked while target power is off")
        if self.fail_power_good:
            raise PlasmaError(
                ErrorCode.INTERFACE_FAILURE,
                "injected target power-good failure",
                recoverable=True,
            )

    async def transfer_reset_control_to_execution_backend(self) -> None:
        self.events.append("transfer_reset_to_backend")
        if not self.powered or not self.site_reset_asserted:
            raise AssertionError("reset ownership handoff requires powered target held in reset")
        self.site_reset_asserted = False
        self.backend_owns_reset = True

    async def power_off(self) -> None:
        self.events.append("power_off")
        self.powered = False


class SiteSafetySequencerTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_sequence_has_no_uncontrolled_power_on_window(self) -> None:
        control = RecordingSiteSafetyControl()
        sequencer = SiteSafetySequencer(control, power_good_timeout_s=0.25)

        async def operation() -> str:
            control.events.append("operation_started")
            self.assertTrue(control.powered)
            self.assertTrue(control.backend_owns_reset)
            control.events.append("operation_completed")
            return "ok"

        result = await sequencer.run(operation)

        self.assertEqual(result, "ok")
        self.assertEqual(
            control.events,
            [
                "assert_reset",
                "power_on",
                "wait_power_good:0.25",
                "transfer_reset_to_backend",
                "operation_started",
                "operation_completed",
                "assert_reset",
                "power_off",
            ],
        )
        self.assertFalse(control.powered)
        self.assertTrue(control.site_reset_asserted)
        self.assertFalse(control.backend_owns_reset)

    async def test_operation_failure_reclaims_reset_then_powers_off(self) -> None:
        control = RecordingSiteSafetyControl()
        sequencer = SiteSafetySequencer(control)

        async def operation() -> None:
            control.events.append("operation_started")
            raise RuntimeError("injected backend failure")

        with self.assertRaisesRegex(RuntimeError, "injected backend failure"):
            await sequencer.run(operation)

        self.assertEqual(control.events[-2:], ["assert_reset", "power_off"])
        self.assertFalse(control.powered)
        self.assertTrue(control.site_reset_asserted)

    async def test_cancel_asserts_reset_before_backend_task_is_cancelled(self) -> None:
        control = RecordingSiteSafetyControl()
        sequencer = SiteSafetySequencer(control)
        operation_started = asyncio.Event()

        async def operation() -> None:
            control.events.append("operation_started")
            operation_started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                control.events.append("operation_cancelled")
                raise

        task = asyncio.create_task(sequencer.run(operation))
        await asyncio.wait_for(operation_started.wait(), timeout=1.0)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task

        assert_positions = [
            index for index, event in enumerate(control.events) if event == "assert_reset"
        ]
        self.assertEqual(len(assert_positions), 2)
        cancel_position = control.events.index("operation_cancelled")
        power_off_position = control.events.index("power_off")
        self.assertLess(assert_positions[1], cancel_position)
        self.assertLess(cancel_position, power_off_position)
        self.assertFalse(control.powered)
        self.assertTrue(control.site_reset_asserted)

    async def test_power_good_failure_rolls_back_to_reset_asserted_power_off(self) -> None:
        control = RecordingSiteSafetyControl(fail_power_good=True)
        sequencer = SiteSafetySequencer(control, power_good_timeout_s=0.1)
        operation_called = False

        async def operation() -> None:
            nonlocal operation_called
            operation_called = True

        with self.assertRaises(PlasmaError) as caught:
            await sequencer.run(operation)

        self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_FAILURE)
        self.assertFalse(operation_called)
        self.assertEqual(
            control.events,
            [
                "assert_reset",
                "power_on",
                "wait_power_good:0.1",
                "assert_reset",
                "power_off",
            ],
        )
        self.assertFalse(control.powered)
        self.assertTrue(control.site_reset_asserted)

    async def test_reset_reclaim_failure_still_attempts_emergency_power_off(self) -> None:
        control = RecordingSiteSafetyControl(fail_reclaim_reset=True)
        sequencer = SiteSafetySequencer(control)

        async def operation() -> None:
            control.events.append("operation_started")

        with self.assertRaises(PlasmaError) as caught:
            await sequencer.run(operation)

        self.assertEqual(caught.exception.code, ErrorCode.INTERFACE_FAILURE)
        self.assertEqual(control.events[-2:], ["assert_reset", "power_off"])
        self.assertFalse(control.powered)
        self.assertTrue(control.backend_owns_reset)

    async def test_invalid_power_good_timeout_is_rejected(self) -> None:
        control = RecordingSiteSafetyControl()
        with self.assertRaises(ValueError):
            SiteSafetySequencer(control, power_good_timeout_s=0)


if __name__ == "__main__":
    unittest.main()
