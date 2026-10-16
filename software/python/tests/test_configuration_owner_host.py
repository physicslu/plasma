"""PPU Configuration Owner Phase 2A.1 Host-only tests.

Only regular files and synthetic /sys/class/uio. These tests never open
/dev/uio*, /dev/mem, FPGA Manager, Kernel/PL bridge or actual Z2.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import os
from threading import Event, Thread

import pytest

from plasma_interfaces.linux_mmio import MMIOAperture
from plasma_interfaces.uio_backend import UIOBackend, UIOPin
from plasma_interfaces.configuration_owner import (
    ConfigurationOwner, HostAudit, HostSafety, HostVerification,
    OwnerClosed, OwnerError, Phase,
)

BASE = 0x40000000
SITES = [BASE + 0x4000 + i * 0x1000 for i in range(8)]


@pytest.fixture
def host(tmp_path):
    root = tmp_path / "fake-sys/class/uio/uio0"
    m = root / "maps/map0"
    m.mkdir(parents=True)
    for name, value in (("addr", "0x40000000"), ("size", "0x10000"),
                        ("offset", "0"), ("name", "fabric")):
        (m / name).write_text(value)
    (root / "name").write_text("fabric")
    device = tmp_path / "platform/40000000.fabric"
    driver = tmp_path / "drivers/uio_pdrv_genirq"
    device.mkdir(parents=True)
    driver.mkdir(parents=True)
    (root / "device").symlink_to(device, target_is_directory=True)
    (device / "driver").symlink_to(driver, target_is_directory=True)
    ram = tmp_path / "host-only-regular-file"
    with ram.open("wb") as f:
        f.truncate(0x20000)
    return {
        "root": tmp_path / "fake-sys", "ram": ram,
        "pin": UIOPin("uio0", "fabric", "40000000.fabric",
                      "uio_pdrv_genirq", 0, BASE, 0x10000),
        "owner_lock": tmp_path / "ppu-config.lock",
        "mmio_lock": tmp_path / "ppu-mmio.lock",
    }


def backend(host, generation=3, num_sites=8):
    apertures = tuple(MMIOAperture(
        base, frozenset((0, 4)), frozenset((4,))
    ) for base in SITES[:num_sites])
    return UIOBackend(
        host["pin"], apertures, sysroot=host["root"],
        device_file=host["ram"], owner_lock=host["mmio_lock"],
        generation=generation, readonly=False,
    )


def owner(host, generation=3):
    return ConfigurationOwner(
        config_lock=host["owner_lock"], generation=generation,
        boot_id="synthetic-boot-123", resource_id="synthetic-dt-and-map-v1",
        source_id="synthetic-runtime-revision",
    )


def running(host, generation=3):
    o = owner(host, generation)
    o.open()
    b = backend(host, generation)
    o.attach_host_backend(b)
    o.admit_existing_host_fixture()
    return o, b


def audit(o):
    return HostAudit(
        boot_id=o.boot_id, resource_id=o.resource_id,
        source_id=o.source_id, proc_scan_complete=True,
        known_users_only=True, no_retained_mappings=True,
        dma_stopped=True, kernel_consumers_stopped=True,
    )


def safety():
    return HostSafety(assumed_external_io_safe=True,
                      assumed_axi_isolation=True)


def verification(o, candidate="mock-image-B"):
    return HostVerification(
        candidate=candidate, boot_id=o.boot_id, identity_match=True,
        resources_match=True, kernel_healthy=True, gateway_healthy=True,
        ssh_healthy=True, recovery_artifact_present=True,
    )


def reach_release(o):
    o.begin_quiesce()
    o.confirm_sites_idle()
    o.submit_synthetic_audit(audit(o))
    o.submit_synthetic_safe_io(safety())
    assert o.status().phase is Phase.RELEASE


def test_owner_requires_explicit_open_backend_and_model_admission(host):
    o = owner(host)
    assert not o.status().admissions_open
    with pytest.raises(OwnerClosed):
        o.admit_existing_host_fixture()
    with o:
        assert o.status().phase is Phase.IDLE
        with pytest.raises(OwnerError, match="attached"):
            o.admit_existing_host_fixture()
        o.attach_host_backend(backend(host))
        o.admit_existing_host_fixture()
        assert o.status().admissions_open and o.status().host_only
    assert o.status().phase is Phase.CLOSED
    with pytest.raises(OwnerClosed):
        o.open()


def test_two_sites_same_exact_ic_and_word_permissions(host):
    o, b = running(host)
    try:
        with o.claim_site(1, SITES[0], exact_ic="STM32F103C8T6 / SWD") as s1:
            with o.claim_site(2, SITES[1], exact_ic="STM32F103C8T6 / SWD") as s2:
                s1.write32(SITES[0] + 4, 0x12345678)
                s2.write32(SITES[1] + 4, 0xC0FFEE)
                assert s1.read32(SITES[0] + 4) == 0x12345678
                assert s2.read32(SITES[1] + 4) == 0xC0FFEE
                with pytest.raises(OwnerError, match="same|exact"):
                    o.claim_site(3, SITES[2], exact_ic="LPC812 / SWD")
                with pytest.raises(OwnerError, match="already"):
                    o.claim_site(1, SITES[0], exact_ic="STM32F103C8T6 / SWD")
                assert o.status().active_sites == (1, 2)
        assert o.status().batch_ic is None
        with o.claim_site(1, SITES[0], exact_ic="LPC812 / SWD") as replacement:
            assert replacement.site_id == 1
        with pytest.raises(OwnerClosed):
            s1.read32(SITES[0])
    finally:
        o.close()


def test_quiesce_seals_new_jobs_before_waiting_for_old_ones(host):
    o, _ = running(host)
    try:
        s = o.claim_site(1, SITES[0], exact_ic="DUT-X")
        o.begin_quiesce()
        assert not o.status().admissions_open
        with pytest.raises(OwnerError, match="READY"):
            o.claim_site(2, SITES[1], exact_ic="DUT-X")
        # Existing inflight job remains valid during cooperative QUIESCE.
        s.write32(SITES[0] + 4, 77)
        with pytest.raises(OwnerError, match="Active Site"):
            o.confirm_sites_idle()
        s.close()
        o.confirm_sites_idle()
        assert o.status().phase is Phase.OWNERSHIP_AUDIT
        with pytest.raises(OwnerClosed):
            s.read32(SITES[0] + 4)
    finally:
        o.close()


def test_synthetic_full_transition_retires_old_map_and_requires_new_backend(host):
    o, original = running(host)
    try:
        old = o.claim_site(1, SITES[0], exact_ic="IC-A")
        old.write32(SITES[0] + 4, 1)
        old.close()
        reach_release(o)
        o.release_host_mapping()
        assert original._retired and original._fd is None
        assert o.status().phase is Phase.MODEL_LOAD
        with pytest.raises(OwnerClosed):
            old.read32(SITES[0] + 4)
        o.simulate_image_switch("mock-image-B")
        o.submit_synthetic_verification(verification(o))
        assert o.status().phase is Phase.NEW_MAPPING_GENERATION
        assert o.publish_host_generation() == 4
        assert o.status().phase is Phase.IDLE
        assert not o.status().admissions_open
        with pytest.raises(OwnerError, match="Stale"):
            o.attach_host_backend(backend(host, generation=3))
        replacement = backend(host, generation=4)
        o.attach_host_backend(replacement)
        o.admit_existing_host_fixture()
        with o.claim_site(2, SITES[1], exact_ic="IC-B") as new:
            new.write32(SITES[1] + 4, 0xCAFE)
            assert new.read32(SITES[1] + 4) == 0xCAFE
        assert o.status().generation == 4
        assert not original._owners
        assert o.status().host_only
    finally:
        o.close()


@pytest.mark.parametrize("field,value", [
    ("proc_scan_complete", False),
    ("known_users_only", False),
    ("no_retained_mappings", False),
    ("dma_stopped", False),
    ("kernel_consumers_stopped", False),
    ("boot_id", "rebooted-synthetic-boot"),
    ("resource_id", "changed-DT-and-map"),
    ("source_id", "different-runtime-source"),
    ("kind", "LIVE_HARDWARE_ISOLATION"),
    ("proc_scan_complete", None),
    ("known_users_only", 1),
])
def test_audit_unknown_owner_dma_vma_kernel_or_source_fails_closed(host, field, value):
    o, _ = running(host)
    try:
        o.begin_quiesce()
        o.confirm_sites_idle()
        with pytest.raises(OwnerError, match="unknown or failed"):
            o.submit_synthetic_audit(replace(audit(o), **{field: value}))
        assert o.status().phase is Phase.FAULT
        assert not o.status().admissions_open
        with pytest.raises(OwnerError):
            o.submit_synthetic_audit(audit(o))
    finally:
        o.close()


@pytest.mark.parametrize("field,value", [
    ("assumed_external_io_safe", False),
    ("assumed_axi_isolation", False),
    ("assumed_axi_isolation", None),
    ("assumed_external_io_safe", 1),
    ("kind", "PHYSICAL_PROOF"),
])
def test_isolation_or_dut_state_unknown_fails_closed(host, field, value):
    o, _ = running(host)
    try:
        o.begin_quiesce()
        o.confirm_sites_idle()
        o.submit_synthetic_audit(audit(o))
        with pytest.raises(OwnerError, match="safe-IO"):
            o.submit_synthetic_safe_io(replace(safety(), **{field: value}))
        assert o.status().phase is Phase.FAULT
    finally:
        o.close()


@pytest.mark.parametrize("field,value", [
    ("candidate", "wrong-image"), ("boot_id", "new-boot"),
    ("identity_match", False), ("resources_match", False),
    ("kernel_healthy", False), ("gateway_healthy", False),
    ("ssh_healthy", False), ("recovery_artifact_present", False),
    ("kind", "ACTUAL_PL"), ("identity_match", None),
])
def test_image_health_identity_recovery_mismatch_never_publishes_ready(host, field, value):
    o, _ = running(host)
    try:
        reach_release(o)
        o.release_host_mapping()
        o.simulate_image_switch("mock-image-B")
        with pytest.raises(OwnerError, match="identity/health/recovery"):
            o.submit_synthetic_verification(replace(
                verification(o), **{field: value}))
        assert o.status().phase is Phase.FAULT
        assert o.status().generation == 3
        assert not o.status().admissions_open
        with pytest.raises(OwnerError):
            o.publish_host_generation()
    finally:
        o.close()


def test_raw_uio_backend_claim_blocks_owner_release_even_without_managed_lease(host):
    o, b = running(host)
    try:
        reach_release(o)
        bypass = b.claim_site(1, SITES[0])  # illustrates cooperative boundary
        with pytest.raises(OwnerError, match="release failed"):
            o.release_host_mapping()
        assert o.status().phase is Phase.FAULT
        assert o.status().generation == 3
        bypass.close()
    finally:
        o.close()


def test_external_stall_requires_explicit_external_recovery_not_auto_retry(host):
    o, _ = running(host)
    try:
        s = o.claim_site(1, SITES[0], exact_ic="DUT-A")
        with pytest.raises(OwnerError, match="External recovery"):
            o.external_recovery_required("AXI completion unknown")
        assert o.status().phase is Phase.EXTERNAL_RECOVERY_REQUIRED
        assert not o.status().admissions_open
        with pytest.raises(OwnerClosed):
            s.read32(SITES[0])
        with pytest.raises(OwnerError):
            o.begin_quiesce()
    finally:
        o.close()


def test_concurrent_admissions_and_eight_independent_managed_sites(host):
    o, _ = running(host)
    try:
        def worker(i):
            with o.claim_site(i + 1, SITES[i], exact_ic="same-exact-IC") as site:
                for n in range(40):
                    site.write32(site.base + 4, (i << 24) + n)
                    assert site.read32(site.base + 4) == (i << 24) + n
                return site.site_id
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert sorted(pool.map(worker, range(8))) == list(range(1, 9))
        assert o.status().active_sites == ()
        assert o.status().batch_ic is None
    finally:
        o.close()


def test_concurrent_seal_blocks_future_admissions(host):
    o, _ = running(host)
    try:
        existing = o.claim_site(1, SITES[0], exact_ic="IC-A")
        begun = Event()
        seal = Event()
        results = []
        def barrier():
            begun.set()
            seal.wait(timeout=2)
            o.begin_quiesce()
        t = Thread(target=barrier)
        t.start()
        assert begun.wait(2)
        seal.set()
        t.join(5)
        assert not t.is_alive()
        for _ in range(100):
            with pytest.raises(OwnerError):
                o.claim_site(2, SITES[1], exact_ic="IC-A")
        existing.close()
        o.confirm_sites_idle()
        assert o.status().phase is Phase.OWNERSHIP_AUDIT
    finally:
        o.close()


def test_global_config_lock_rejects_second_cooperating_owner(host):
    first = owner(host)
    second = owner(host)
    with first:
        with pytest.raises(OwnerError, match="another|Another"):
            second.open()
    with second:
        assert second.status().phase is Phase.IDLE
    assert first.epoch != second.epoch


def test_forked_owner_token_rejected_without_reopening_device(host, monkeypatch):
    o, _ = running(host)
    try:
        lease = o.claim_site(1, SITES[0], exact_ic="DUT-X")
        current_pid = os.getpid()
        with monkeypatch.context() as patch:
            patch.setattr("plasma_interfaces.configuration_owner.os.getpid",
                          lambda: current_pid + 1000)
            with pytest.raises(OwnerClosed, match="Fork"):
                lease.read32(SITES[0])
            assert not o.status().admissions_open
        lease.close()
    finally:
        o.close()


def test_uncertain_backend_access_poisons_owner_and_denies_new_jobs(host):
    o, _ = running(host)
    try:
        lease = o.claim_site(1, SITES[0], exact_ic="DUT-X")
        (host["root"] / "class/uio/uio0/maps/map0/size").write_text("0x2000")
        with pytest.raises(OwnerError, match="Uncertain"):
            lease.read32(SITES[0])
        assert o.status().phase is Phase.FAULT
        with pytest.raises(OwnerError):
            o.claim_site(2, SITES[1], exact_ic="DUT-X")
    finally:
        o.close()


def test_bad_init_and_lock_alias_fail_before_mmap(host):
    for kw in ({"generation": True}, {"generation": 0},
               {"boot_id": ""}, {"resource_id": None},
               {"config_lock": Path("/dev/null")}):
        params = dict(config_lock=host["owner_lock"], generation=3,
                      boot_id="boot", resource_id="resource", source_id="source")
        params.update(kw)
        with pytest.raises(OwnerError):
            ConfigurationOwner(**params)
    with owner(host) as o:
        clash = UIOBackend(
            host["pin"], (MMIOAperture(SITES[0], frozenset({0}),
                                       frozenset({4})),),
            sysroot=host["root"], device_file=host["ram"],
            owner_lock=host["owner_lock"], generation=3, readonly=False)
        with pytest.raises(OwnerError, match="separate"):
            o.attach_host_backend(clash)


def test_bad_ic_identity_refused_without_open_site(host):
    o, _ = running(host)
    try:
        for bad in ("", "   ", None, 123, "x" * 129):
            with pytest.raises(OwnerError, match="exact IC"):
                o.claim_site(1, SITES[0], exact_ic=bad)
        assert not o.status().active_sites
    finally:
        o.close()


def test_close_retirement_invalidates_all_jobs_and_host_mapping(host):
    o, b = running(host)
    port = o.claim_site(1, SITES[0], exact_ic="IC-A")
    port.write32(SITES[0] + 4, 9)
    o.close()
    o.close()
    assert b._retired and b._fd is None and b._map is None
    assert o.status().phase is Phase.CLOSED
    with pytest.raises(OwnerClosed):
        port.read32(SITES[0] + 4)

def test_cross_site_mmio_escape_poisoned_and_all_admission_blocked(host):
    o, _ = running(host)
    try:
        first = o.claim_site(1, SITES[0], exact_ic="IC-A")
        with pytest.raises(OwnerError, match="Uncertain"):
            first.read32(SITES[1] + 4)
        assert o.status().phase is Phase.FAULT
        with pytest.raises(OwnerError):
            o.claim_site(2, SITES[1], exact_ic="IC-A")
    finally:
        o.close()
