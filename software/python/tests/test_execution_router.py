"""S1-C PPU Job-selected Provider routing; no legacy CompilerRegistry Runtime gate."""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_interfaces.mock import MockInterface
from plasma_interfaces.openocd import OpenOCDInterface
from plasma_interfaces.package_provider import PackageProviderInterface, TrustedProviderAction
from plasma_server.execution_router import (
    MOCK_ROUTE, OPENOCD_ROUTE, PACKAGE_PROVIDER_ROUTE, ROUTE_METADATA_KEY,
    SiteExecutionRouter,
)
from plasma_server.site_manager import SiteManager


def test_c3_flash_route_uses_bundle_not_exact_icpn_catalog():
    site = SiteConfig(id=2, enabled=True, interface="openocd",
                      openocd={"site_worker_socket": "/tmp/s1c-test-c3.sock"})
    interface = OpenOCDInterface(site.openocd)
    router = SiteExecutionRouter(site, interface)
    request = JobRequest(site_id=2, operation=Operation.FLASH_CYCLE,
                         target="UNREGISTERED-ICPN", image=b"TEST")
    admitted = router.admit(request)
    assert admitted.metadata[ROUTE_METADATA_KEY]["mode"] == OPENOCD_ROUTE
    assert router.interface_for(admitted) is interface
    with pytest.raises(PlasmaError) as error:
        router.admit(JobRequest(site_id=2, operation=Operation.ERASE,
                                target="UNREGISTERED-ICPN"))
    assert error.value.code == ErrorCode.OPERATION_UNSUPPORTED


def test_mock_route_does_not_claim_hardware_support():
    site = SiteConfig(id=1, enabled=True, interface="mock")
    interface = MockInterface.from_options({})
    router = SiteExecutionRouter(site, interface)
    admitted = router.admit(JobRequest(site_id=1, operation=Operation.ERASE,
                                       target="UNKNOWN-ICPN"))
    route = admitted.metadata[ROUTE_METADATA_KEY]
    assert route["mode"] == MOCK_ROUTE and not route["hardware_support_claimed"]
    assert router.interface_for(admitted) is interface


def test_legacy_non_c3_openocd_runtime_path_is_removed():
    site = SiteConfig(id=2, enabled=True, interface="openocd",
                      openocd={"interface_cfg": "interface/cmsis-dap.cfg",
                               "target_cfg": "target/stm32f1x.cfg"})
    router = SiteExecutionRouter(site, OpenOCDInterface(site.openocd))
    with pytest.raises(PlasmaError, match="NO_QUALIFIED_JOB_PROVIDER"):
        router.admit(JobRequest(site_id=2, operation=Operation.FLASH_CYCLE,
                                target="STM32F103C8T6", image=b"TEST"))


@pytest.mark.parametrize("field", [ROUTE_METADATA_KEY, "resolved_ic_support"])
def test_client_cannot_forge_server_selected_execution_route(field):
    site = SiteConfig(id=1, enabled=True, interface="mock")
    router = SiteExecutionRouter(site, MockInterface.from_options({}))
    with pytest.raises(PlasmaError) as error:
        router.admit(JobRequest(site_id=1, operation=Operation.ERASE,
                                metadata={field: {"mode": OPENOCD_ROUTE}}))
    assert error.value.code == ErrorCode.INVALID_ARGUMENT


def test_signed_package_provider_is_selected_by_job_not_static_site_interface():
    site = SiteConfig(id=2, enabled=True, interface="openocd")
    base = OpenOCDInterface({})
    package = PackageProviderInterface()
    package.wire_runtime(lambda *_: {})
    router = SiteExecutionRouter(site, base, package)
    trusted = TrustedProviderAction(None, {}, None, SimpleNamespace())
    request = JobRequest(site_id=2, operation=Operation.FLASH_CYCLE,
                         target="UNREGISTERED-ICPN", image=b"TEST")
    admitted = router.admit(request, trusted_provider=trusted)
    assert admitted.metadata[ROUTE_METADATA_KEY]["mode"] == PACKAGE_PROVIDER_ROUTE
    assert router.interface_for(admitted) is package
    with pytest.raises(PlasmaError, match="NO_QUALIFIED_JOB_PROVIDER"):
        router.admit(request)


def test_same_site_selects_openocd_or_package_per_authorized_job_without_fallback():
    """Selected Provider is Job-local, not permanently attached to the Site."""
    site = SiteConfig(id=2, enabled=True, interface="openocd",
                      openocd={"site_worker_socket": "/tmp/s1c-two-provider-c3.sock"})
    openocd = OpenOCDInterface(site.openocd)
    package = PackageProviderInterface()
    package.wire_runtime(lambda *_: {})
    router = SiteExecutionRouter(site, openocd, package)
    trusted = TrustedProviderAction(None, {}, None, SimpleNamespace())
    direct = JobRequest(site_id=2, operation=Operation.FLASH_CYCLE,
                        target="STM32F103C8T6", image=b"IMAGE", job_id="direct-job")
    signed = JobRequest(site_id=2, operation=Operation.FLASH_CYCLE,
                        target="EXTERNAL-PROVIDER-TARGET", image=b"IMAGE", job_id="signed-job")
    assert router.interface_for(router.admit(direct)) is openocd
    assert router.interface_for(router.admit(signed, trusted_provider=trusted)) is package
    assert router.interface_for(router.admit(direct)) is openocd
    # A tampered route from public metadata cannot switch a direct Job.
    forged = JobRequest(site_id=2, operation=Operation.FLASH_CYCLE,
                        target="STM32F103C8T6", image=b"IMAGE",
                        metadata={ROUTE_METADATA_KEY: {"mode": PACKAGE_PROVIDER_ROUTE}})
    with pytest.raises(PlasmaError) as error:
        router.admit(forged)
    assert error.value.code == ErrorCode.INVALID_ARGUMENT


def test_site_manager_rejects_legacy_route_before_queue_or_lease(tmp_path: Path):
    async def scenario():
        config = PlasmaConfig(
            server=ServerConfig(output_root=tmp_path / "out", log_root=tmp_path / "log"),
            sites=[SiteConfig(id=2, enabled=True, interface="openocd")],
        )
        manager = SiteManager(config)
        await manager.start()
        try:
            with pytest.raises(PlasmaError, match="NO_QUALIFIED_JOB_PROVIDER"):
                manager.enqueue(JobRequest(site_id=2, operation=Operation.FLASH_CYCLE,
                                           target="STM32F103C8T6", image=b"TEST"))
            assert manager.registry.all() == []
            assert not manager.execution_lease_snapshot()["busy"]
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_mock_job_reuses_existing_site_worker(tmp_path: Path):
    async def scenario():
        config = PlasmaConfig(
            server=ServerConfig(output_root=tmp_path / "out", log_root=tmp_path / "log"),
            sites=[SiteConfig(id=1, enabled=True, interface="mock")],
        )
        manager = SiteManager(config)
        await manager.start()
        try:
            result = await manager.submit(JobRequest(site_id=1, operation=Operation.ERASE))
            assert result.success
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_static_provider_site_interface_is_not_supported():
    config = PlasmaConfig(server=ServerConfig(),
                          sites=[SiteConfig(id=2, enabled=True, interface="provider")])
    with pytest.raises(PlasmaError) as error:
        config.validate()
    assert error.value.code == ErrorCode.CONFIG_INVALID
