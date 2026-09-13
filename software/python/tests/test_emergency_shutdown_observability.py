from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_client.client import PlasmaClient
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_interfaces.mock import MockInterface
from plasma_server.server import PlasmaServer
from plasma_server.site_manager import SiteManager

from tests.helpers import make_config


class EmergencyShutdownFailureMock(MockInterface):
    async def safe_shutdown(self) -> None:
        raise PlasmaError(
            ErrorCode.INTERFACE_FAILURE,
            "injected emergency safe-shutdown failure",
        )


class EmergencyRuntimeShutdownFailureMock(MockInterface):
    async def safe_shutdown(self) -> None:
        raise RuntimeError("injected raw emergency safe-shutdown failure")


class EmergencyShutdownObservabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.server: PlasmaServer | None = None

    async def asyncTearDown(self) -> None:
        if self.server is not None:
            await self.server.close()

    async def start_server(self, interface_factory) -> PlasmaClient:
        config = make_config(self.root, enabled_sites=1)
        manager = SiteManager(config, interface_factory=interface_factory)
        self.server = PlasmaServer(config, manager)
        await self.server.start()

        def fail_state_write(*_args, **_kwargs) -> None:
            raise OSError("injected output persistence failure")

        manager.output.write_state = fail_state_write  # type: ignore[method-assign]
        return PlasmaClient(*self.server.address, response_timeout_s=3.0)

    async def test_emergency_safe_shutdown_failure_is_authoritative_job_error(self) -> None:
        client = await self.start_server(lambda _site: EmergencyShutdownFailureMock())
        result = (await client.erase(1))["result"]

        self.assertEqual(result["state"], "error")
        self.assertEqual(result["error"]["error_code"], ErrorCode.INTERFACE_FAILURE.value)
        self.assertEqual(result["error"]["failure_source"], "infrastructure")
        self.assertEqual(result["error"]["context"]["phase"], "emergency_safe_shutdown")
        self.assertEqual(
            result["error"]["context"]["prior_error_code"],
            ErrorCode.OUTPUT_WRITE_FAILED.value,
        )
        self.assertEqual(
            result["error"]["context"]["prior_error_message"],
            "job infrastructure write failed",
        )

    async def test_raw_emergency_safe_shutdown_failure_is_normalized(self) -> None:
        client = await self.start_server(lambda _site: EmergencyRuntimeShutdownFailureMock())
        result = (await client.erase(1))["result"]

        self.assertEqual(result["state"], "error")
        self.assertEqual(result["error"]["error_code"], ErrorCode.INTERFACE_FAILURE.value)
        self.assertEqual(result["error"]["context"]["phase"], "emergency_safe_shutdown")
        self.assertIn("RuntimeError", result["error"]["original_exception"])
        self.assertEqual(
            result["error"]["context"]["prior_error_code"],
            ErrorCode.OUTPUT_WRITE_FAILED.value,
        )


if __name__ == "__main__":
    unittest.main()
