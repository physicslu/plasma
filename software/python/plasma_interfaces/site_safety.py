from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TypeVar


ResultT = TypeVar("ResultT")


class SiteSafetyControl(ABC):
    """Fail-safe power/reset boundary for exactly one Programming Site.

    This interface intentionally does not define SWD/JTAG operations. It owns
    only the Site-level safety signals needed to prevent an already-programmed
    target from executing uncontrolled code while it is in the socket.
    """

    @abstractmethod
    async def assert_reset(self) -> None:
        """Force the target into reset and reclaim reset ownership for the Site."""
        raise NotImplementedError

    @abstractmethod
    async def power_on(self) -> None:
        """Enable target power while the Site still holds reset asserted."""
        raise NotImplementedError

    @abstractmethod
    async def wait_power_good(self, timeout_s: float) -> None:
        """Wait until target power is valid or fail closed."""
        raise NotImplementedError

    @abstractmethod
    async def transfer_reset_control_to_execution_backend(self) -> None:
        """Transfer reset ownership to a backend that guarantees connect-under-reset.

        This is an ownership handoff, not a request to let the target run.
        A real implementation must not release uncontrolled execution merely
        because this method was called.
        """
        raise NotImplementedError

    @abstractmethod
    async def power_off(self) -> None:
        """Disable target power, including as an emergency fallback if reset fails."""
        raise NotImplementedError


class SiteSafetySequencer:
    """Guard one execution-backend operation with fail-safe power/reset ordering.

    The backend operation is shielded from caller cancellation so the Site can
    first reclaim/assert reset. Only after reset is asserted does this sequencer
    cancel the backend task. Power is then removed.

    This class is a software contract only. It does not make the OpenOCD
    hardware runtime ready by itself.
    """

    def __init__(self, control: SiteSafetyControl, *, power_good_timeout_s: float = 1.0) -> None:
        if power_good_timeout_s <= 0:
            raise ValueError("power_good_timeout_s must be positive")
        self.control = control
        self.power_good_timeout_s = power_good_timeout_s

    async def _safe_off(self) -> None:
        first_error: BaseException | None = None
        try:
            await asyncio.shield(self.control.assert_reset())
        except BaseException as exc:
            first_error = exc

        try:
            await asyncio.shield(self.control.power_off())
        except BaseException as exc:
            if first_error is None:
                first_error = exc

        if first_error is not None:
            raise first_error

    async def _cancel_after_reset(self, backend_task: asyncio.Task[ResultT] | None) -> None:
        first_error: BaseException | None = None
        try:
            await asyncio.shield(self.control.assert_reset())
        except BaseException as exc:
            first_error = exc

        if backend_task is not None and not backend_task.done():
            backend_task.cancel()
            try:
                await backend_task
            except asyncio.CancelledError:
                pass
            except BaseException as exc:
                if first_error is None:
                    first_error = exc

        try:
            await asyncio.shield(self.control.power_off())
        except BaseException as exc:
            if first_error is None:
                first_error = exc

        if first_error is not None:
            raise first_error

    async def run(self, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        """Run one backend operation without an uncontrolled power/reset window."""
        backend_task: asyncio.Task[ResultT] | None = None
        try:
            await self.control.assert_reset()
            await self.control.power_on()
            await self.control.wait_power_good(self.power_good_timeout_s)
            await self.control.transfer_reset_control_to_execution_backend()

            backend_task = asyncio.create_task(operation(), name="plasma-site-backend-operation")
            result = await asyncio.shield(backend_task)
        except asyncio.CancelledError:
            await self._cancel_after_reset(backend_task)
            raise
        except BaseException:
            await self._safe_off()
            raise
        else:
            await self._safe_off()
            return result
