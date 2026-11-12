"""PR-B1 (B1-b): the trusted Runtime Job context and its lifecycle.

One context per Job attempt, built by the PPU Runtime alone, carrying at most
one authorization source. An interface consumes the source it is built for and
refuses the other; nothing shaped like a context is accepted in its place; a
context never outlives the Job it was bound for.

The last test here is the regression the hook upgrade required: SiteWorker
calls ``bind_runtime_job`` outside the attempt's own ``try``, so a failure in
it leaves the attempt loop entirely. It must still resolve the Job, run the
safe shutdown and release the PPU execution lease, and must never report
SUCCESS.
"""
from __future__ import annotations

import asyncio
import math
from pathlib import Path
from types import MappingProxyType

import pytest

from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.enums import JobState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_interfaces.fpga import FPGAInterface
from plasma_interfaces.mock import MockInterface
from plasma_interfaces.openocd import OpenOCDInterface
from plasma_interfaces.package_provider import PackageProviderInterface, TrustedProviderAction
from plasma_interfaces.runtime_context import RuntimeJobContext, freeze, thaw
from plasma_server.site_manager import SiteManager

BINDING = {
    "schema": "plasma.ppu.job-binding.v1",
    "operation": "programming",
    "operations": ["erase", "program", "verify"],
    "range": {"address": 0x08004000, "length": 2048},
    "site_id": 2,
    "ppu_id": "local-ppu",
}


def context(**overrides) -> RuntimeJobContext:
    fields = {"job_id": "job-1", "site_id": 2, "deadline_monotonic": 1.0}
    fields.update(overrides)
    return RuntimeJobContext(**fields)


class _Route:
    asset_set_sha256 = "a" * 64
    site_id = 2
    target = "MOCK"
    provider_package = "p"
    profile_package = "q"
    operation = "flash_cycle"


class _AssetRequest:
    job_id = "job-1"


def trusted() -> TrustedProviderAction:
    return TrustedProviderAction(asset_request=_AssetRequest(), authorization={},
                                 owner_credential=None, route=_Route())


# ------------------------------------------------------------------- the context


def test_two_authorization_sources_are_refused():
    with pytest.raises(PlasmaError, match="AUTHORIZATION_NOT_EXCLUSIVE"):
        context(admitted_job_binding=dict(BINDING), trusted_provider=trusted())


@pytest.mark.parametrize("overrides, code", [
    ({"job_id": ""}, "JOB_ID_INVALID"),
    ({"job_id": None}, "JOB_ID_INVALID"),
    ({"site_id": 0}, "SITE_INVALID"),
    ({"site_id": True}, "SITE_INVALID"),
    ({"deadline_monotonic": math.nan}, "DEADLINE_INVALID"),
    ({"admitted_job_binding": ["not", "a", "mapping"]}, "BINDING_INVALID"),
    ({"active_asset_set": "not a mapping"}, "ACTIVE_SET_INVALID"),
])
def test_an_ill_formed_context_is_refused(overrides, code):
    with pytest.raises(PlasmaError, match=code):
        context(**overrides)


def test_the_snapshot_is_deep_and_cannot_be_reached_through_the_source():
    source = {"range": {"address": 1, "length": 2}, "operations": ["erase"]}
    bound = context(admitted_job_binding=source)
    source["range"]["address"] = 999
    source["operations"].append("program")
    assert bound.admitted_job_binding["range"]["address"] == 1
    assert bound.admitted_job_binding["operations"] == ("erase",)


def test_the_snapshot_cannot_be_mutated_by_its_consumer():
    bound = context(admitted_job_binding=dict(BINDING))
    assert isinstance(bound.admitted_job_binding, MappingProxyType)
    assert isinstance(bound.admitted_job_binding["range"], MappingProxyType)
    with pytest.raises(TypeError):
        bound.admitted_job_binding["range"]["address"] = 0
    with pytest.raises(TypeError):
        bound.admitted_job_binding["operation"] = "read"


def test_thaw_hands_collaborators_plain_containers():
    plain = thaw(freeze(BINDING))
    assert type(plain) is dict and type(plain["range"]) is dict
    assert type(plain["operations"]) is list
    assert plain == BINDING


# -------------------------------------------------------- authorization isolation


def test_a_forged_context_is_never_accepted():
    """Anything that merely looks like a context is refused by every interface."""
    class Forged:
        job_id = "job-1"
        site_id = 2
        deadline_monotonic = 1.0
        active_asset_set = None
        admitted_job_binding = dict(BINDING)
        trusted_provider = None
        has_authorization = True

        def matches(self, job_id, site_id):
            return True

    interfaces = [
        MockInterface(),
        OpenOCDInterface({"site_worker_socket": "/nonexistent.sock"}),
        PackageProviderInterface(),
        FPGAInterface(2, 0x4000_0000),
    ]
    for interface in interfaces:
        for forged in (Forged(), dict(BINDING), None):
            with pytest.raises(PlasmaError, match="RUNTIME_CONTEXT_NOT_TRUSTED"):
                interface.bind_runtime_job(forged)


def test_an_interface_that_consumes_no_context_refuses_an_authorization():
    fpga = FPGAInterface(2, 0x4000_0000)
    # No authorization source: nothing to misuse, so the default accepts it.
    fpga.bind_runtime_job(context())
    with pytest.raises(PlasmaError, match="cannot consume"):
        fpga.bind_runtime_job(context(admitted_job_binding=dict(BINDING)))
    with pytest.raises(PlasmaError, match="cannot consume"):
        fpga.bind_runtime_job(context(trusted_provider=trusted()))
    assert FPGAInterface.CONSUMES_JOB_BINDING is False


def test_a_binding_never_stands_in_for_a_provider_action():
    provider = PackageProviderInterface()
    provider.wire_runtime(lambda *a, **k: {})
    with pytest.raises(PlasmaError, match="PROVIDER_JOB_NOT_AUTHORIZED"):
        provider.bind_runtime_job(context(admitted_job_binding=dict(BINDING)))


def test_a_provider_action_never_stands_in_for_a_binding():
    for interface in (MockInterface(),
                      OpenOCDInterface({"site_worker_socket": "/nonexistent.sock"})):
        with pytest.raises(PlasmaError, match="not a Provider Action"):
            interface.bind_runtime_job(context(trusted_provider=trusted()))
        assert type(interface).CONSUMES_JOB_BINDING is True


def test_a_provider_action_for_another_site_is_refused():
    provider = PackageProviderInterface()
    provider.wire_runtime(lambda *a, **k: {})
    active = {"asset_set_sha256": _Route.asset_set_sha256}
    provider.bind_runtime_job(context(trusted_provider=trusted(), active_asset_set=active))
    with pytest.raises(PlasmaError, match="PROVIDER_JOB_NOT_AUTHORIZED"):
        provider.bind_runtime_job(context(site_id=3, trusted_provider=trusted(),
                                          active_asset_set=active))


# --------------------------------------------------------------- the lifecycle


def test_a_context_from_an_earlier_job_never_authorizes_this_one():
    interface = MockInterface()
    interface.bind_runtime_job(context(job_id="job-1", admitted_job_binding=dict(BINDING)))
    with pytest.raises(PlasmaError, match="RUNTIME_CONTEXT_JOB_MISMATCH"):
        interface.prepare_request(JobRequest(site_id=2, operation=Operation.ERASE,
                                             job_id="job-2"))
    with pytest.raises(PlasmaError, match="RUNTIME_CONTEXT_JOB_MISMATCH"):
        interface.prepare_request(JobRequest(site_id=3, operation=Operation.ERASE,
                                             job_id="job-1"))


def test_safe_shutdown_clears_the_context():
    async def scenario():
        interface = MockInterface()
        interface.bind_runtime_job(context(admitted_job_binding=dict(BINDING)))
        await interface.safe_shutdown()
        # With no context there is no Binding, and no default to fall back on.
        with pytest.raises(PlasmaError, match="requires an admitted Job Binding"):
            await interface.run_operations(("erase",), b"")
    asyncio.run(scenario())


# ------------------------------------------------- the hook-failure regression


class BindingHookFailureMock(MockInterface):
    """Fails the binding hook once, then behaves like any other Mock Site."""

    failures_remaining = 1

    def bind_runtime_job(self, context) -> None:
        if self.failures_remaining:
            self.failures_remaining -= 1
            raise PlasmaError(ErrorCode.INTERFACE_FAILURE, "injected binding hook failure")
        super().bind_runtime_job(context)


def test_a_binding_hook_failure_resolves_the_job_and_releases_the_lease(tmp_path: Path):
    """The hook runs outside the attempt's own try; it must still fail closed."""
    async def scenario():
        config = PlasmaConfig(
            server=ServerConfig(output_root=tmp_path / "out", log_root=tmp_path / "log"),
            sites=[SiteConfig(id=1, enabled=True, interface="mock",
                              operation_timeout_s=5.0)],
        )
        interface = BindingHookFailureMock()
        manager = SiteManager(config, interface_factory=lambda site: interface)
        await manager.start()
        try:
            assert not manager.execution_lease_snapshot()["busy"]
            result = await manager.submit(JobRequest(site_id=1, operation=Operation.ERASE))
            # Never a false success.
            assert result.state is not JobState.SUCCESS
            assert result.state is JobState.ERROR
            assert "injected binding hook failure" in result.error.message
            # The safe shutdown still ran.
            assert interface.shutdown_count >= 1
            # And the PPU execution lease is not leaked.
            assert not manager.execution_lease_snapshot()["busy"]
            assert manager.execution_lease_snapshot()["active_job_count"] == 0
            # The Site is still usable: the failure took the Job down, not the PPU.
            again = await manager.submit(JobRequest(site_id=1, operation=Operation.ERASE))
            assert again.state is JobState.SUCCESS
            assert not manager.execution_lease_snapshot()["busy"]
        finally:
            await manager.shutdown()
    asyncio.run(scenario())
