"""PR-B1: a Mock Site runs ``programming`` through the real admission path.

A Mock Site is not a shortcut. Its Job Bindings go through the same
``SiteManager._admit_job_binding`` a Z2 uses, its evidence is read back out of
the Mock Flash state rather than copied from the request, and its ``safe_off``
reports a closing step that has already run.

What these tests deliberately do NOT claim: a Mock Site models no NOR Flash
write physics, so "Program on a non-erased IC fails" cannot be reproduced here
and is not asserted. That behaviour is covered on the C-3 path only
(test_c3_programming_operations.py). Nothing here is hardware evidence.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest

from plasma_core.config import PlasmaConfig, ServerConfig, SiteConfig
from plasma_core.enums import JobState, Operation
from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import JobRequest
from plasma_interfaces.base import BaseInterface
from plasma_interfaces.fpga import FPGAInterface
from plasma_interfaces.mock import MockInterface
from plasma_interfaces.package_provider import PackageProviderInterface, TrustedProviderAction
from plasma_interfaces.runtime_context import RuntimeJobContext, freeze
from plasma_opf import bundle_v3
from plasma_server import mock_resources
from plasma_server.site_manager import SiteManager

ICPN = "MOCK-STM32F103C8T6"
FLASH_BASE = 0x08000000
FLASH_SIZE = 64 * 1024
GRANULARITY = 1024
# Deliberately not the bank base: a Binding address is not an offset of zero.
LOAD_ADDRESS = FLASH_BASE + 0x4000
LENGTH = 2 * GRANULARITY
SITE = 2
PPU_ID = "local-ppu"

IMAGE_A = bytes((index * 7 + 11) & 0xFF for index in range(LENGTH))
IMAGE_B = bytes((index * 13 + 3) & 0xFF for index in range(LENGTH))

LEGAL_LISTS = [
    ("erase",),
    ("program",),
    ("verify",),
    ("erase", "program"),
    ("program", "verify"),
    ("erase", "program", "verify"),
]


def mock_config(tmp_path: Path, *, site_ids=(1, SITE), **options) -> PlasmaConfig:
    mock_options = {
        "flash_base": FLASH_BASE,
        "flash_size": FLASH_SIZE,
        "erase_granularity": GRANULARITY,
        **options,
    }
    return PlasmaConfig(
        server=ServerConfig(output_root=tmp_path / "out", log_root=tmp_path / "log"),
        sites=[SiteConfig(id=site_id, enabled=True, interface="mock", target=ICPN,
                          operation_timeout_s=10.0, mock=dict(mock_options))
               for site_id in site_ids],
    )


async def started_manager(config: PlasmaConfig, **kwargs) -> tuple[SiteManager, dict]:
    manager = SiteManager(config, **kwargs)
    identity = mock_resources.install_mock_resources(manager)
    await manager.start()
    return manager, identity


def programming_request(identity: dict, operations: tuple[str, ...], image: bytes, *,
                        site_id: int = SITE, load_address: int = LOAD_ADDRESS,
                        address: int | None = None, length: int | None = None,
                        ppu_id: str = PPU_ID, target: str = ICPN) -> JobRequest:
    resource = identity["resource_set"]
    takes_image = bundle_v3.operations_take_image(list(operations))
    asset = (bundle_v3.image_asset_descriptor(resource, image, load_address=load_address)
             if takes_image else None)
    binding = bundle_v3.job_image_binding(
        resource, asset, ppu_id=ppu_id, site_id=site_id, operation="programming",
        operations=list(operations), address=address, length=length)
    kinds = {package["kind"]: package["id"] for package in resource["packages"]}
    metadata = {"provider": kinds["platform-provider"],
                "profile": kinds["programming-profile"],
                "job_binding": binding}
    if asset is not None:
        metadata["job_image_asset"] = asset
    return JobRequest(site_id=site_id, operation=Operation.PROGRAMMING,
                      image=image if takes_image else b"", target=target,
                      max_retries=0, timeout_s=10.0, metadata=metadata)


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def site_flash(manager: SiteManager, site_id: int, address: int, length: int) -> bytes:
    interface = manager.interfaces[site_id]
    assert isinstance(interface, MockInterface)
    return interface.flash_state.read(interface.image_store, address - FLASH_BASE, length)


async def program_image(manager: SiteManager, identity: dict, image: bytes,
                        *, site_id: int = SITE):
    """Leave ``image`` on the Site through the ordinary admitted path."""
    result = await manager.submit(programming_request(
        identity, ("erase", "program", "verify"), image, site_id=site_id))
    assert result.state is JobState.SUCCESS
    return result


# --------------------------------------------------------------- the ordered list


@pytest.mark.parametrize("operations", LEGAL_LISTS, ids=["+".join(x) for x in LEGAL_LISTS])
def test_every_legal_list_runs_one_job_with_evidence_for_exactly_its_steps(
        tmp_path: Path, operations: tuple[str, ...]):
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            if operations in (("verify",), ("program", "verify")):
                # Verify compares the IC with the Image; it needs one there.
                await program_image(manager, identity, IMAGE_A)
            takes_image = bundle_v3.operations_take_image(list(operations))
            request = programming_request(
                identity, operations, IMAGE_A if takes_image else b"",
                address=None if takes_image else LOAD_ADDRESS,
                length=None if takes_image else LENGTH)
            result = await manager.submit(request)
            assert result.state is JobState.SUCCESS, result.error
            evidence = result.details["programming"]
            assert evidence["result"] == "PASS"
            assert evidence["safe_off"] is True
            assert evidence["operations"] == list(operations)
            # Exactly the listed steps ran: nothing skipped, nothing added.
            assert set(evidence["steps"]) == set(operations)
            assert result.details["stages"] == list(operations)

            steps = evidence["steps"]
            if "erase" in operations:
                assert steps["erase"]["erase_address"] == LOAD_ADDRESS
                assert steps["erase"]["erase_length"] == LENGTH
            if "program" in operations:
                assert steps["program"] == {"write_address": LOAD_ADDRESS,
                                            "bytes_written": LENGTH,
                                            "image_sha256": sha(IMAGE_A)}
            if "verify" in operations:
                assert steps["verify"] == {"verify_address": LOAD_ADDRESS,
                                           "bytes_verified": LENGTH,
                                           "readback_sha256": sha(IMAGE_A)}
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_erase_only_proves_the_bound_range_blank(tmp_path: Path):
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            await program_image(manager, identity, IMAGE_A)
            result = await manager.submit(programming_request(
                identity, ("erase",), b"", address=LOAD_ADDRESS, length=LENGTH))
            assert result.state is JobState.SUCCESS
            erase = result.details["programming"]["steps"]["erase"]
            assert erase["blank_verified"] is True
            assert erase["bytes_verified"] == LENGTH
            assert erase["readback_sha256"] == sha(b"\xff" * LENGTH)
            assert site_flash(manager, SITE, LOAD_ADDRESS, LENGTH) == b"\xff" * LENGTH
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


# ------------------------------------------------------------------- the address


def test_programming_writes_at_the_binding_address_not_offset_zero(tmp_path: Path):
    """The Binding address is the write target; the bank base is not a default."""
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            await program_image(manager, identity, IMAGE_A)
            assert site_flash(manager, SITE, LOAD_ADDRESS, LENGTH) == IMAGE_A
            # Everything below the bound window is untouched.
            assert site_flash(manager, SITE, FLASH_BASE, LENGTH) == b"\xff" * LENGTH
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_erase_in_a_list_covers_only_the_bound_window(tmp_path: Path):
    """A Mock erase is the Image's erase window, never the whole device."""
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            low = FLASH_BASE
            await manager.submit(programming_request(
                identity, ("erase", "program", "verify"), IMAGE_B, load_address=low))
            await program_image(manager, identity, IMAGE_A)
            # Erasing for IMAGE_A must not have disturbed the other window.
            assert site_flash(manager, SITE, low, LENGTH) == IMAGE_B
            assert site_flash(manager, SITE, LOAD_ADDRESS, LENGTH) == IMAGE_A
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_a_binding_outside_the_simulated_window_is_refused(tmp_path: Path):
    async def scenario():
        # The Site simulates a smaller device than the Resource Set describes.
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            interface = manager.interfaces[SITE]
            assert isinstance(interface, MockInterface)
            object.__setattr__(interface, "flash_base", FLASH_BASE + FLASH_SIZE)
            result = await manager.submit(programming_request(
                identity, ("erase", "program", "verify"), IMAGE_A))
            assert result.state is not JobState.SUCCESS
            assert "outside the mock target" in str(result.error.message)
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


# ------------------------------------------------------------------ safe failure


def test_verify_mismatch_is_a_safe_failure_and_never_writes(tmp_path: Path):
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            await program_image(manager, identity, IMAGE_A)
            result = await manager.submit(programming_request(
                identity, ("verify",), IMAGE_B))
            assert result.state is not JobState.SUCCESS
            assert result.error.error_code == ErrorCode.VERIFY_FAILED.value
            assert result.error.failure_source == "mismatch"
            # A failed Verify wrote nothing.
            assert site_flash(manager, SITE, LOAD_ADDRESS, LENGTH) == IMAGE_A
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_program_only_emits_no_erase_step(tmp_path: Path):
    """Program never erases: a program-only Job reports only what it did."""
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            result = await manager.submit(programming_request(
                identity, ("program",), IMAGE_A))
            assert result.state is JobState.SUCCESS
            assert set(result.details["programming"]["steps"]) == {"program"}
            interface = manager.interfaces[SITE]
            assert isinstance(interface, MockInterface)
            assert interface.calls["erase"] == 0
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_a_failed_closing_step_never_reports_safe_off(tmp_path: Path):
    async def scenario():
        manager, identity = await started_manager(
            mock_config(tmp_path, safe_off_fails=True))
        try:
            result = await manager.submit(programming_request(
                identity, ("erase", "program", "verify"), IMAGE_A))
            assert result.state is not JobState.SUCCESS
            assert "did not leave the Site safe" in str(result.error.message)
            assert result.error.context.get("safe_off") is False
            interface = manager.interfaces[SITE]
            assert isinstance(interface, MockInterface)
            assert interface.site_safe is False
            assert interface.safe_off_count == 0
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


# ------------------------------------------------------- admission is not skipped


def test_programming_without_an_admitted_binding_is_refused(tmp_path: Path):
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            # No job_binding metadata at all: nothing admits this Job, and
            # the interface has no default list or range to fall back on.
            result = await manager.submit(JobRequest(
                site_id=SITE, operation=Operation.PROGRAMMING, image=IMAGE_A,
                target=ICPN, max_retries=0, timeout_s=10.0))
            assert result.state is not JobState.SUCCESS
            assert "requires a Job Binding operations list" in result.error.message
            assert "programming" not in (result.details or {})
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_a_binding_for_another_site_is_refused(tmp_path: Path):
    async def scenario():
        manager, identity = await started_manager(mock_config(tmp_path))
        try:
            request = programming_request(
                identity, ("erase", "program", "verify"), IMAGE_A, site_id=1)
            # Same Binding, submitted against the other Site.
            moved = JobRequest(site_id=SITE, operation=Operation.PROGRAMMING,
                               image=IMAGE_A, target=ICPN, max_retries=0,
                               timeout_s=10.0, metadata=dict(request.metadata))
            with pytest.raises(PlasmaError, match="JOB_BINDING_DENIED"):
                await manager.submit(moved)
        finally:
            await manager.shutdown()
    asyncio.run(scenario())


def test_a_resource_set_from_another_ppu_is_refused(tmp_path: Path):
    async def scenario():
        manager, _ = await started_manager(mock_config(tmp_path))
        try:
            other = mock_resources.mock_resource_identity(mock_resources.mock_route(
                icpn=ICPN, flash_base=FLASH_BASE,
                flash_size=FLASH_SIZE, erase_granularity=GRANULARITY,
                profile_id="some-other-programming-profile"))
            with pytest.raises(PlasmaError, match="JOB_RESOURCE_PACKAGE_MISMATCH"):
                await manager.submit(programming_request(
                    other, ("erase", "program", "verify"), IMAGE_A))
        finally:
            await manager.shutdown()
    asyncio.run(scenario())
