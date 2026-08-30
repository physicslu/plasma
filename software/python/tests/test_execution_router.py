from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.ic_support import get_default_ic_support_resolver
from plasma_core.models import JobRequest
from plasma_interfaces.base import BaseInterface, ProgressCallback
from plasma_server.execution_router import (
    MOCK_ROUTE,
    OPENOCD_ROUTE,
    RESOLVED_IC_SUPPORT_METADATA_KEY,
    RoutedProgrammingHandler,
    SiteExecutionRouter,
    normalize_openocd_target_config,
)
from plasma_server.site_manager import SiteManager


class StubInterface(BaseInterface):
    async def erase(self, progress: ProgressCallback | None = None) -> None:
        if progress:
            await progress(1, 1)

    async def program(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        if progress:
            await progress(len(image), len(image))

    async def verify(
        self,
        image: bytes,
        address: int = 0,
        progress: ProgressCallback | None = None,
    ) -> None:
        if progress:
            await progress(len(image), len(image))

    async def read(
        self,
        address: int,
        length: int,
        progress: ProgressCallback | None = None,
    ) -> bytes:
        if progress:
            await progress(length, length)
        return bytes(length)

    async def safe_shutdown(self) -> None:
        return None


class ExecutionRouterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.resolver = get_default_ic_support_resolver()
        self.interface = StubInterface()

    def test_openocd_target_normalization_accepts_catalog_and_runtime_forms(self) -> None:
        self.assertEqual(
            normalize_openocd_target_config("tcl/target/stm32f1x.cfg"),
            "target/stm32f1x.cfg",
        )
        self.assertEqual(
            normalize_openocd_target_config("target/stm32f1x.cfg"),
            "target/stm32f1x.cfg",
        )
        self.assertEqual(
            normalize_openocd_target_config("/usr/share/openocd/scripts/target/stm32f1x.cfg"),
            "target/stm32f1x.cfg",
        )

    def test_mock_route_accepts_unbound_catalog_target_without_hardware_claim(self) -> None:
        site = SiteConfig(id=1, enabled=True, interface="mock")
        router = SiteExecutionRouter(site, self.interface, None)
        admitted = router.admit(
            JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F407VGT6")
        )
        route = admitted.metadata[RESOLVED_IC_SUPPORT_METADATA_KEY]
        self.assertEqual(route["mode"], MOCK_ROUTE)
        self.assertFalse(route["hardware_support_claimed"])
        self.assertIsInstance(router.handler_for(admitted), object)

    def test_openocd_route_resolves_f103_and_binds_programming_profile(self) -> None:
        site = SiteConfig(
            id=1,
            enabled=True,
            interface="openocd",
            openocd={
                "interface_cfg": "interface/cmsis-dap.cfg",
                "target_cfg": "target/stm32f1x.cfg",
            },
        )
        router = SiteExecutionRouter(site, self.interface, self.resolver)
        admitted = router.admit(
            JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F103CBT6")
        )
        route = admitted.metadata[RESOLVED_IC_SUPPORT_METADATA_KEY]
        self.assertEqual(route["mode"], OPENOCD_ROUTE)
        self.assertEqual(
            route["selected_programming_profile_id"],
            "stm32f1-medium-density-flash-v0",
        )
        self.assertEqual(route["selected_openocd_target_config"], "target/stm32f1x.cfg")
        self.assertFalse(route["runtime_ready"])
        self.assertIsInstance(router.handler_for(admitted), object)

    def test_unbound_f4_is_rejected_before_real_execution(self) -> None:
        site = SiteConfig(
            id=1,
            enabled=True,
            interface="openocd",
            openocd={
                "interface_cfg": "interface/cmsis-dap.cfg",
                "target_cfg": "target/stm32f4x.cfg",
            },
        )
        router = SiteExecutionRouter(site, self.interface, self.resolver)
        with self.assertRaises(PlasmaError) as caught:
            router.admit(
                JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F407VGT6")
            )
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)
        self.assertEqual(caught.exception.context["ic_support_state"], "unresolved")

    def test_openocd_target_mismatch_fails_closed(self) -> None:
        site = SiteConfig(
            id=1,
            enabled=True,
            interface="openocd",
            openocd={
                "interface_cfg": "interface/cmsis-dap.cfg",
                "target_cfg": "target/stm32f4x.cfg",
            },
        )
        router = SiteExecutionRouter(site, self.interface, self.resolver)
        with self.assertRaises(PlasmaError) as caught:
            router.admit(
                JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F103C8T6")
            )
        self.assertEqual(caught.exception.code, ErrorCode.CONFIG_INVALID)
        self.assertEqual(
            caught.exception.context["expected_target_config"],
            "target/stm32f1x.cfg",
        )

    def test_native_fpga_route_fails_before_interface_execution(self) -> None:
        site = SiteConfig(id=1, enabled=True, interface="fpga")
        router = SiteExecutionRouter(site, self.interface, self.resolver)
        with self.assertRaises(PlasmaError) as caught:
            router.admit(
                JobRequest(site_id=1, operation=Operation.ERASE, target="STM32F103C8T6")
            )
        self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)
        self.assertEqual(
            caught.exception.context["programming_profile_id"],
            "stm32f1-medium-density-flash-v0",
        )

    def test_client_cannot_supply_server_owned_resolution_metadata(self) -> None:
        site = SiteConfig(id=1, enabled=True, interface="mock")
        router = SiteExecutionRouter(site, self.interface, None)
        with self.assertRaises(PlasmaError) as caught:
            router.admit(
                JobRequest(
                    site_id=1,
                    operation=Operation.ERASE,
                    target="STM32F103C8T6",
                    metadata={RESOLVED_IC_SUPPORT_METADATA_KEY: {"mode": "forged"}},
                )
            )
        self.assertEqual(caught.exception.code, ErrorCode.INVALID_ARGUMENT)

    async def test_site_manager_admission_happens_before_registry_or_execution_lease(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            config = PlasmaConfig(
                server=ServerConfig(
                    host="127.0.0.1",
                    port=0,
                    output_root=root_path / "output",
                    log_root=root_path / "logs",
                    max_supported_sites=1,
                    max_concurrent_jobs=1,
                ),
                sites=[
                    SiteConfig(
                        id=1,
                        enabled=True,
                        interface="openocd",
                        openocd={
                            "interface_cfg": "interface/cmsis-dap.cfg",
                            "target_cfg": "target/stm32f4x.cfg",
                        },
                    )
                ],
            )
            manager = SiteManager(
                config,
                interface_factory=lambda _site: self.interface,
                ic_support_resolver=self.resolver,
            )
            await manager.start()
            try:
                with self.assertRaises(PlasmaError) as caught:
                    manager.enqueue(
                        JobRequest(
                            site_id=1,
                            operation=Operation.ERASE,
                            target="STM32F407VGT6",
                            job_id="unresolved-f4",
                        )
                    )
                self.assertEqual(caught.exception.code, ErrorCode.OPERATION_UNSUPPORTED)
                self.assertEqual(manager.registry.all(), [])
                self.assertFalse(manager.execution_lease_snapshot()["busy"])
            finally:
                await manager.shutdown()

    async def test_site_manager_uses_routed_handler_for_mock_without_resolver_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            config = PlasmaConfig(
                server=ServerConfig(
                    host="127.0.0.1",
                    port=0,
                    output_root=root_path / "output",
                    log_root=root_path / "logs",
                    max_supported_sites=1,
                    max_concurrent_jobs=1,
                ),
                sites=[SiteConfig(id=1, enabled=True, interface="mock")],
            )
            manager = SiteManager(
                config,
                interface_factory=lambda _site: self.interface,
            )
            self.assertIsNone(manager.ic_support_resolver)
            self.assertIsInstance(manager.workers[1].handler, RoutedProgrammingHandler)
            await manager.start()
            try:
                result = await manager.submit(
                    JobRequest(
                        site_id=1,
                        operation=Operation.ERASE,
                        target="STM32F407VGT6",
                        job_id="mock-f4",
                    )
                )
                self.assertTrue(result.success)
            finally:
                await manager.shutdown()


if __name__ == "__main__":
    unittest.main()
