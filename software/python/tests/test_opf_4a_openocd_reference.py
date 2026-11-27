"""OPF-4A: real Bundle v3/Active Set -> C-3 socket -> ABI-v5 interface.

Host-only: the physical OpenOCD child and admission subprocess are simulated
at the existing ABI-v5 process edge. No FPGA load, Z2 access, or DUT
operation is performed.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from plasma_core.enums import Operation
from plasma_core.models import JobRequest
from plasma_core.errors import PlasmaError
from plasma_interfaces.site_worker_c3 import SiteWorkerControlClient, SiteWorkerRefused
from plasma_opf import OPF_PROGRAMMING_SCHEMA, TimeoutPolicy

from .ppu_fpga_qualification_fixture import synthetic_image
from .test_c3_rest_flash_cycle import FlashSim, make_engine, write_selection, run
from .test_ppu_b3_z2_install_gate1 import b3_request, make_coordinator
from .test_ppu_bundle_v3_packages_contract import ROOT, TARGET, bundle_v3

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_opf_reference_openocd as reference  # noqa: E402
import ppu_site_adapter_abi5 as abi5  # noqa: E402
import ppu_site_engine as engine  # noqa: E402
import ppu_site_worker as worker  # noqa: E402
import ppu_asset_set as assets  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith("linux"),
                                reason="Linux AF_UNIX + SO_PEERCRED")

ICPN = "STM32F103C8T6"
DRIVER_ABI = "plasma_swd:5"
PROVIDER = "openocd-reference"
PROFILE = "stm32f103-c8"
FPGA = "qualified-fpga"
OPENOCD = b"\x7fELF-reference-openocd-host-only"
POLICY = TimeoutPolicy(5000, 12000)
IMAGE = bytes(range(256)) * 9


def _json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


@contextmanager
def installed_bundle(*, profile_change=None, descriptor_change=None,
                     engine_binary=OPENOCD, options_schema=None,
                     with_control_socket=False, verified_worker=True,
                     with_fpga=True, platform_provider=False, platform_extra_files=None,
                     profile_count=1, target_icpn=ICPN, other_target=None,
                     programming_bundle=None):
    """``programming_bundle``: a canonical route-built Bundle v3 (OFE-1B
    ``build_image_bundle``) installed through the real B3 coordinator instead of
    the synthetic Provider/Profile/FPGA parts."""
    with tempfile.TemporaryDirectory(prefix="opf4a-", dir="/tmp") as directory:
        path = Path(directory)
        c3_profile = {"icpn": target_icpn, "target_config": "target/stm32f1x.cfg",
                      "flash_base": 0x08000000, "flash_size": 65536,
                      "erase_granularity": 1024}
        desc = {"schema": "plasma.ppu.provider-capabilities.v2", "target": target_icpn,
                "provider_package": PROVIDER, "operations": ["erase", "program", "verify"],
                "transport": "fpga", "driver_abi": DRIVER_ABI,
                "fpga_package": FPGA, "max_image_bytes": 65536}
        desc.update(descriptor_change or {})
        if not with_fpga:
            desc["fpga_package"] = None
        profile = {"schema": reference.PROFILE_SCHEMA, **c3_profile}
        profile.update(profile_change or {})
        schema = options_schema or {
            "schema": "plasma.ppu.provider-options.v1",
            "options": {"type": "object", "properties": {}},
        }
        parts = [
            (PROVIDER, "native-c", [], {
                "bin/openocd": OPENOCD,
                "config/plasma-provider-options.json": _json(schema),
            }),
            (PROFILE, "programming-profile", [PROVIDER] + ([FPGA] if with_fpga else []), {
                "data/plasma-provider.json": _json(desc),
                reference.PROFILE_FILE: _json(profile),
            }),
            (FPGA, "fpga-image", [], synthetic_image()[0]),
        ]
        if not with_fpga:
            parts.pop()
        if platform_provider:
            parts[0] = (PROVIDER, "platform-provider", [], {
                reference.ppu_provider_contract.PLATFORM_OPTIONS: _json(schema),
                **(platform_extra_files or {}),
            })
        if profile_count == 0:
            parts = [part for part in parts if part[0] != PROFILE]
        elif profile_count == 2:
            other_files = dict(parts[1][3])
            if other_target is not None:
                other_files["data/plasma-provider.json"] = _json({**desc, "target": other_target})
                other_files[reference.PROFILE_FILE] = _json({**profile, "icpn": other_target})
            parts.append(("other-profile", parts[1][1], parts[1][2], other_files))
        if programming_bundle is not None:
            with_fpga = False
            archive = path / "archive.zip"
            archive.write_bytes(programming_bundle.archive)
            digest = programming_bundle.archive_sha256
        else:
            archive, digest = bundle_v3(
                path / "archive", parts=parts,
                mutate=lambda manifest: manifest.update(actions=["install", "verify"]))
        co = make_coordinator(path)
        install = co.execute_bundle_v3_install(b3_request(archive, digest))
        assert install["result"] == "PASS"
        # This is explicit *test-only* activation of an already verified Set;
        # the OPF reference module never publishes active.json.
        co.activate_staged_asset_set(digest, quiescence_lease=nullcontext)

        engine_data = make_engine(path / "openocd", "selected", binary=engine_binary)
        engine_record = write_selection(path / "engine.json", engine_data)
        selected_engine = engine.load_engine(engine_record, base=path / "openocd",
                                             require_root=False)
        sim = FlashSim(c3_profile["flash_base"], c3_profile["flash_size"])
        journal = path / "journal.json"
        fpga = (assets.resolve_staged_fpga_handoff(co.paths.product_root, digest)["fpga_image"]
                if with_fpga else {"image_id": "independently-installed-universal",
                                   "bin_sha256": hashlib.sha256(b"installed PL").hexdigest(),
                                   "manifest_sha256": hashlib.sha256(b"installed manifest").hexdigest()})
        journal.write_text(json.dumps({
            "schema": "plasma.fpga.image-deployment.v3", "status": "IMAGE",
            "image_id": fpga["image_id"], "session_id": "test",
            "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
            "firmware_sha256": fpga["bin_sha256"],
            "manifest_sha256": fpga["manifest_sha256"], "test_count": 1}))
        (path / "records").mkdir()
        adapter = abi5.Abi5OpenocdAdapter(
            openocd_root=Path(engine_data["openocd_root"]), python=Path(sys.executable),
            adapter_khz=engine_data["adapter_khz"], journal=journal,
            verified_engine=selected_engine if verified_worker else None,
            record_dir=path / "records", run=sim.run, popen=sim.popen,
            openocd_running=lambda: False, poll_s=0.01,
            evidence_dir=path / "openocd-evidence")
        image_root = path / "images"
        allowed_jobs = {"job-1", "job-2"}
        core = worker.SiteWorkerCore(
            adapter, runtime_pid=os.getpid,
            lease_verifier=lambda job, kind: job in allowed_jobs,
            seal_dir=path / "seals", image_root=image_root)
        server = worker.SiteWorkerServer(core, path / "c3.sock", role="control", mode=0o600)
        if with_control_socket:
            server.start()
        client = SiteWorkerControlClient(path / "c3.sock")
        if not with_control_socket:
            def local_call(op, *, timeout_s=None, **fields):
                reply = core.handle({"protocol": worker.PROTOCOL, "op": op, **fields},
                                    (os.getpid(), os.getuid(), os.getgid()), "control")
                if not reply["ok"]:
                    from plasma_interfaces.site_worker_c3 import SiteWorkerRefused
                    raise SiteWorkerRefused(reply["error"])
                return reply["result"]
            client.call = local_call
        try:
            yield {
                "product_root": co.paths.product_root, "asset_set_sha256": digest,
                "active_asset_set": assets.read_active(co.paths.product_root),
                "selection": {"schema": OPF_PROGRAMMING_SCHEMA,
                              "provider": PROVIDER, "profile": PROFILE,
                              "timeout_ms": 5000, "options": {}},
                "policy": POLICY, "target": target_icpn, "site_id": 2,
                "hardware": {"platform": TARGET["platform"], "board": TARGET["board"],
                             "fpga_part": TARGET["fpga_part"], "sites": [1, 2],
                             "loaded_fpga_package": FPGA, "driver_abi": DRIVER_ABI,
                             "fpga_identity_proven": True,
                             "worker_identity": dict(adapter.identity())},
                "runtime_profile": c3_profile,
                "engine_record": engine_record, "engine_base": path / "openocd",
                "require_root": False, "image_root": image_root,
                "client": client,
                "job_id": "job-1", "image": IMAGE,
                "job_deadline_monotonic": time.monotonic() + 5,
                "job_timeout_s": 5.0,
                "core": core, "sim": sim, "adapter": adapter,
                "allowed_jobs": allowed_jobs, "engine_data": engine_data,
            }
        finally:
            server.close()


def _execute(env, **changes):
    payload = {key: value for key, value in env.items()
               if key in {"client", "product_root", "asset_set_sha256", "selection",
                          "policy", "job_id", "site_id", "target", "image",
                          "image_root", "hardware",
                          "job_deadline_monotonic", "job_timeout_s", "engine_record",
                          "engine_base", "require_root"}}
    payload["job_binding"] = {"operation": "programming", "operations": ["erase", "program", "verify"],
                              "site_id": env["site_id"], "profile": env["selection"]["profile"],
                              "range": {"address": env["runtime_profile"]["flash_base"], "length": len(env["image"])}}
    payload.update(changes)
    if "job_binding" not in changes:
        payload["job_binding"]["site_id"] = payload["site_id"]
    return run(reference.execute_reference_flash(**payload))


def _qualify(env, **changes):
    payload = {key: value for key, value in env.items()
               if key in {"product_root", "asset_set_sha256", "selection",
                          "policy", "site_id", "target", "hardware",
                          "engine_record", "engine_base", "require_root"}}
    payload["image_size"] = len(env["image"])
    payload["operations"] = ("erase", "program", "verify")
    payload.update(changes)
    return reference.qualify_reference(**payload)


def test_bundle_profile_accepts_new_icpn_without_core_registry():
    unknown = "VENDOR-NEW-PART-A"
    with installed_bundle(target_icpn=unknown) as env:
        preflight = reference.preflight_runtime_flash(
            product_root=env["product_root"], active_asset_set=env["active_asset_set"],
            target=unknown, site_id=2, image_size=len(IMAGE), job_binding=_binding(address=0x08000000, length=len(IMAGE)))
        assert preflight["profile"]["icpn"] == unknown
        result = _execute(env)
        assert result["result"] == "PASS" and result["safe_off"] is True
        assert result["opf_profile_sha256"] == preflight["profile_sha256"]


def test_two_targets_select_their_declared_profiles_in_one_active_bundle():
    other = "NEW-EXACT-TARGET-B"
    with installed_bundle(profile_count=2, other_target=other) as env:
        for target, profile_id in ((ICPN, PROFILE), (other, "other-profile")):
            pinned = reference.preflight_runtime_flash(
                product_root=env["product_root"], active_asset_set=env["active_asset_set"],
                target=target, site_id=2, image_size=len(IMAGE), job_binding=_binding(address=0x08000000, length=len(IMAGE), profile=profile_id),
                provider=PROVIDER, profile=profile_id)
            assert pinned["profile_package"] == profile_id
            assert pinned["profile"]["icpn"] == target
        assert not env["sim"].argvs


def test_bundle_profile_image_bounds_and_target_claim_fail_closed():
    with installed_bundle() as env:
        with pytest.raises(ValueError, match="IMAGE_OUT_OF_BOUNDS"):
            reference.preflight_runtime_flash(
                product_root=env["product_root"], active_asset_set=env["active_asset_set"],
                target=ICPN, site_id=2, image_size=65537, job_binding=_binding(address=0x08000000, length=len(IMAGE)))
        with pytest.raises(ValueError, match="REFERENCE_TARGET_MISMATCH"):
            reference.preflight_runtime_flash(
                product_root=env["product_root"], active_asset_set=env["active_asset_set"],
                target="ANOTHER-UNLISTED-MCU", site_id=2, image_size=len(IMAGE), job_binding=_binding(address=0x08000000, length=len(IMAGE)))
        assert not env["sim"].argvs and not env["core"]._sessions


def test_verified_reference_executes_existing_c3_abi5_flash_and_readback():
    with installed_bundle() as env:
        result = _execute(env)
        assert result["result"] == "PASS" and result["safe_off"] is True
        assert result["steps"]["verify"]["readback_sha256"] == result["image_sha256"] == hashlib.sha256(IMAGE).hexdigest()
        assert result["steps"]["verify"]["bytes_verified"] == len(IMAGE)
        assert result["opf_provider_package"] == PROVIDER
        assert result["opf_profile_package"] == PROFILE
        assert result["opf_asset_set_sha256"] == env["asset_set_sha256"]
        assert result["opf_openocd_sha256"] == hashlib.sha256(OPENOCD).hexdigest()
        assert result["opf_driver_abi"] == DRIVER_ABI
        assert result["opf_worker_engine_selection_sha256"] == result["opf_engine_selection_sha256"]
        assert result["opf_worker_epoch"] == env["core"].epoch
        assert len(env["sim"].argvs) == 1
        assert bytes(env["sim"].memory[:len(IMAGE)]) == IMAGE
        assert list(env["image_root"].iterdir()) == []
        assert env["core"]._site_owners == {} and env["core"]._sealed == set()


@pytest.mark.parametrize("site_id", [1, 2])
def test_bundle_profile_5mhz_overrides_engine_default_per_job_for_both_sites(site_id):
    # One verified Profile sets the same clock for any selected Site.
    setting = {"protocol": "swd", "clock_hz": 5_000_000}
    with installed_bundle(profile_change={"transport_settings": setting}) as env:
        before = env["engine_record"].read_bytes()
        result = _execute(env, site_id=site_id)
        assert result["result"] == "PASS"
        assert "adapter speed 5000" in env["sim"].argvs[0]
        assert result["adapter_khz"] == 5000
        assert result["swclk_requested_hz"] == result["swclk_nominal_hz"] == 5_000_000
        assert result["swclk_half_period"] == 10
        assert result["opf_profile_sha256"] == reference.preflight_runtime_flash(
            product_root=env["product_root"],
            active_asset_set=env["active_asset_set"], target=ICPN,
            site_id=site_id, image_size=len(IMAGE), job_binding=_binding(address=0x08000000, length=len(IMAGE), site_id=site_id),
        )["profile_sha256"]
        assert env["engine_record"].read_bytes() == before
        assert env["adapter"].adapter_khz == env["engine_data"]["adapter_khz"] == 500


def test_non_divisor_profile_clock_records_nominal_fpga_rate_not_requested():
    with installed_bundle(profile_change={
            "transport_settings": {"protocol": "swd", "clock_hz": 4_000_000}}) as env:
        result = _execute(env)
        assert result["result"] == "PASS"
        assert "adapter speed 4000" in env["sim"].argvs[0]
        assert result["swclk_requested_hz"] == 4_000_000
        assert result["swclk_half_period"] == 13
        assert result["swclk_nominal_hz"] == 3_846_153


def test_legacy_bundle_profile_uses_selected_engine_default():
    with installed_bundle() as env:
        assert _execute(env)["result"] == "PASS"
        assert "adapter speed 500" in env["sim"].argvs[0]


@pytest.mark.parametrize("settings,code", [
    ({"protocol": "swd", "clock_hz": True}, "PROFILE_CLOCK_INVALID"),
    ({"protocol": "swd", "clock_hz": 0}, "PROFILE_CLOCK_INVALID"),
    ({"protocol": "swd", "clock_hz": 12_501_000}, "PROFILE_CLOCK_INVALID"),
    ({"protocol": "swd", "clock_hz": 5_000_001}, "PROFILE_CLOCK_INVALID"),
    ({"protocol": "spi", "clock_hz": 5_000_000}, "PROFILE_TRANSPORT_INVALID"),
    ({"clock_hz": 5_000_000}, "PROFILE_TRANSPORT_INVALID"),
])
def test_bundle_profile_invalid_swd_clock_refused_before_site_admission(settings, code):
    with installed_bundle(profile_change={"transport_settings": settings}) as env:
        with pytest.raises(ValueError, match=code):
            _qualify(env)
        assert not env["sim"].argvs and not env["core"]._sessions


def test_reselection_without_worker_restart_denies_before_site_ownership():
    with installed_bundle() as env:
        # An operator selects a different speed/record but has not restarted
        # this Worker. Its actual adapter remains pinned to the old selection.
        changed = {**env["engine_data"], "adapter_khz": 2000}
        write_selection(env["engine_record"], changed)
        with pytest.raises(Exception, match="WORKER_ENGINE_SELECTION_MISMATCH"):
            _execute(env)
        assert env["core"]._sessions == {} and env["core"]._site_owners == {}
        assert not env["sim"].argvs


def test_worker_without_verified_startup_engine_denies_reference_route():
    with installed_bundle(verified_worker=False) as env:
        with pytest.raises(Exception, match="WORKER_ENGINE_UNVERIFIED"):
            _execute(env)
        assert env["core"]._sessions == {} and not env["sim"].argvs


@pytest.mark.parametrize("tamper", ["missing_sha", "wrong_sha", "wrong_epoch"])
def test_invalid_in_band_worker_receipt_closes_qualified_session(tamper):
    class AlteredReceipt:
        def __init__(self, client):
            self.client = client

        def open_job_session(self, **kwargs):
            opened = self.client.open_job_session(**kwargs)
            if tamper == "missing_sha":
                del opened["worker_engine_selection_sha256"]
            elif tamper == "wrong_sha":
                opened["worker_engine_selection_sha256"] = "f" * 64
            else:
                opened["epoch"] = "invalid-epoch"
            return opened

        def call(self, *args, **kwargs):
            return self.client.call(*args, **kwargs)

    with installed_bundle() as env:
        with pytest.raises(ValueError, match="WORKER_ENGINE_RECEIPT_MISMATCH"):
            _execute(env, client=AlteredReceipt(env["client"]))
        assert env["core"]._sessions == {} and env["core"]._site_owners == {}
        assert not env["sim"].argvs


@pytest.mark.parametrize("change,code", [
    ({"asset_set_sha256": "0" * 64}, "ACTIVE_SET_MISMATCH"),
    ({"hardware": {"platform": "linux-armv7", "board": "pynq-z2", "sites": [1, 2]}},
     "FPGA_DRIVER_UNVERIFIED"),
    ({"selection": {"schema": OPF_PROGRAMMING_SCHEMA,
                     "provider": PROVIDER, "profile": PROFILE,
                     "options": {"speed_khz": 10}}}, "OPTIONS_UNKNOWN_FIELD"),
    ({"site_id": 3}, "SITE_NOT_SUPPORTED"),
    ({"job_timeout_s": 3.0}, "REFERENCE_JOB_DEADLINE_MISMATCH"),
])
def test_untrusted_selection_fails_before_c3_session(change, code):
    with installed_bundle(with_control_socket=False) as env:
        with pytest.raises(ValueError, match=code):
            _execute(env, **change)
        assert not env["core"]._sessions and not env["sim"].argvs
        assert not env["image_root"].exists()


@pytest.mark.parametrize("property_change,code", [
    ({"engine_binary": b"wrong engine bytes"}, "REFERENCE_ENGINE_BINARY_MISMATCH"),
    ({"descriptor_change": {"driver_abi": "plasma_swd:6"}}, "FPGA_DRIVER_UNVERIFIED"),
    ({"profile_change": {"flash_size": 65537}}, "PROFILE_GEOMETRY_INVALID"),
    ({"descriptor_change": {"transport": "ps-only", "driver_abi": None,
                             "fpga_package": None}}, "PS_TRANSPORT_UNVERIFIED"),
])
def test_bad_engine_abi_profile_or_transport_is_never_executed(property_change, code):
    with installed_bundle(with_control_socket=False, **property_change) as env:
        with pytest.raises(ValueError, match=code):
            _qualify(env)
        assert not env["core"]._sessions and not env["sim"].argvs


def test_worker_lease_denial_no_second_site_lock_or_flash():
    with installed_bundle() as env:
        env["allowed_jobs"].clear()
        with pytest.raises(Exception, match="LEASE|OWNER"):
            _execute(env)
        assert not env["core"]._sessions and not env["sim"].argvs
        assert list(env["image_root"].iterdir()) == []


def test_verified_safe_failure_does_not_seal_site_or_schedule_a_new_retry_owner():
    with installed_bundle() as env:
        env["sim"].corrupt = True
        with pytest.raises(Exception, match="VERIFY_MISMATCH"):
            _execute(env)
        assert env["core"]._sealed == set()
        assert env["core"]._site_owners == {}
        env["sim"].corrupt = False
        result = _execute(env, job_id="job-2", job_deadline_monotonic=time.monotonic() + 5)
        assert result["result"] == "PASS" and result["safe_off"] is True
        assert len(env["sim"].argvs) == 2


def test_real_worker_unproven_safe_off_seals_site_and_blocks_next_job():
    with installed_bundle() as env:
        env["sim"].hang.set()
        selection = {**env["selection"], "timeout_ms": 1000}
        with pytest.raises(Exception, match=(
            "OUTCOME_UNKNOWN|SITE_SEALED|SAFE_OFF|"
            "close did not confirm hardware release"
        )):
            _execute(env, selection=selection, job_timeout_s=1.0,
                     job_deadline_monotonic=time.monotonic() + 1)
        assert 2 in env["core"]._sealed
        assert (env["core"].seal_dir / "site2.sealed").exists()
        # The first failed Job may launch a *second*, bounded OpenOCD child
        # for the existing SAFE_OFF probe; that is not a second programming
        # attempt or a retry. A sealed Site must launch no further child.
        children_before_denial = len(env["sim"].argvs)
        assert children_before_denial >= 1
        env["sim"].hang.clear()
        with pytest.raises(Exception, match="SITE_SEALED"):
            _execute(env, job_id="job-2", job_deadline_monotonic=time.monotonic() + 5)
        assert len(env["sim"].argvs) == children_before_denial


def _runtime_execute(env, monkeypatch, *, pinned_profile=None):
    """Real Runtime/Worker/ABI5; only socket and physical process edges replaced."""
    original_load = engine.load_engine

    def test_engine(*args, **kwargs):
        assert kwargs.get("require_root", True) is True
        return original_load(env["engine_record"], base=env["engine_base"], require_root=False)

    monkeypatch.setattr(engine, "load_engine", test_engine)

    def no_fpga_handoff(*args, **kwargs):
        raise AssertionError("Profile-only Job must not request an FPGA handoff/load")

    monkeypatch.setattr(assets, "resolve_staged_fpga_handoff", no_fpga_handoff)
    calls = env["worker_calls"] = []

    def worker_call(op, *, timeout_s=None, **fields):
        calls.append(op)
        reply = env["core"].handle({"protocol": worker.PROTOCOL, "op": op, **fields},
                                     (os.getpid(), os.getuid(), os.getgid()), "control")
        if not reply["ok"]:
            raise SiteWorkerRefused(reply["error"])
        return reply["result"]

    monkeypatch.setattr(env["client"], "call", worker_call)
    request = JobRequest(job_id="job-1", site_id=2, target=env["target"],
                         operation=Operation.PROGRAMMING, image=IMAGE, timeout_s=5.0, metadata={"job_binding": {"operation": "programming", "operations": ["erase", "program", "verify"]}})
    return run(reference.execute_runtime_flash(
        env["client"], product_root=env["product_root"], request=request,
        active_asset_set=env["active_asset_set"],
        job_deadline_monotonic=time.monotonic() + 5,
        image_root=env["image_root"], job_binding=_binding(address=0x08000000, length=len(IMAGE)),
        pinned_profile=pinned_profile))


def _prepared_profile(env):
    """What OpenOCDInterface.prepare_request computes for the same Job."""
    return reference.preflight_runtime_flash(
        product_root=env["product_root"], active_asset_set=env["active_asset_set"],
        target=env["target"], site_id=2, image_size=len(IMAGE),
        job_binding=_binding(address=0x08000000, length=len(IMAGE)),
        operation="programming")


def test_prepared_profile_is_reused_without_a_second_active_set_verification(monkeypatch):
    """U4: one Active-Set verification per Job; execution reuses preparation's."""
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True) as env:
        prepared = _prepared_profile(env)

        def second_verification(*args, **kwargs):
            raise AssertionError("the prepared Job must not verify its Active Set again")

        monkeypatch.setattr(reference, "preflight_runtime_flash", second_verification)
        result = _runtime_execute(env, monkeypatch, pinned_profile=prepared)
        assert result["result"] == "PASS" and result["safe_off"] is True
        assert bytes(env["sim"].memory[:len(IMAGE)]) == IMAGE


def test_a_prepared_profile_of_another_set_is_refused_before_any_session(monkeypatch):
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True) as env:
        foreign = {**_prepared_profile(env), "asset_set_sha256": "f" * 64}
        with pytest.raises(Exception, match="PINNED_PROFILE_SET_MISMATCH"):
            _runtime_execute(env, monkeypatch, pinned_profile=foreign)
        assert env["sim"].argvs == []


def test_profile_provider_only_runtime_flash_uses_installed_platform(monkeypatch):
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True) as env:
        result = _runtime_execute(env, monkeypatch)
        assert result["result"] == "PASS" and result["safe_off"] is True
        assert result["steps"]["verify"]["readback_sha256"] == hashlib.sha256(IMAGE).hexdigest()
        assert result["steps"]["verify"]["bytes_verified"] == len(IMAGE)
        assert bytes(env["sim"].memory[:len(IMAGE)]) == IMAGE
        assert len(env["sim"].argvs) == 1
        assert set(env["worker_calls"]) == {
            "status", "open_job_session", "bind_image", "run", "close_session"}
        assert not env["core"]._sessions and not env["core"]._site_owners
        staged = env["product_root"] / "assets/staged" / env["asset_set_sha256"]
        manifest = json.loads((staged / "manifest.json").read_bytes())
        assert {p["kind"] for p in manifest["packages"]} == {
            "platform-provider", "programming-profile"}
        assert all(not f["executable"] for p in manifest["packages"] for f in p["files"])


@pytest.mark.parametrize("updated_engine", [
    b"\x7fELF-updated-plasma-swd-v5",
    b"\x7fELF-independent-plasma-swd-v5-next",
])
def test_platform_provider_accepts_new_verified_engine_without_bundle_pins(monkeypatch, updated_engine):
    # #1329: two distinct qualified installed Engine identities must both PASS
    # without editing Bundle bytes or adding a version-specific SHA allowlist.
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True, engine_binary=updated_engine) as env:
        result = _runtime_execute(env, monkeypatch)
        assert result["result"] == "PASS" and result["safe_off"] is True
        assert result["opf_openocd_sha256"] == hashlib.sha256(updated_engine).hexdigest()
        assert result["opf_worker_engine_selection_sha256"] == result["opf_engine_selection_sha256"]
        staged = env["product_root"] / "assets/staged" / env["asset_set_sha256"]
        manifest = json.loads((staged / "manifest.json").read_bytes())
        provider = next(p for p in manifest["packages"] if p["kind"] == "platform-provider")
        assert [f["path"] for f in provider["files"]] == [
            f"payload/packages/{PROVIDER}/data/plasma-provider-options.json"]
        assert sum(len(p["files"]) for p in manifest["packages"]) == 3


def test_platform_provider_rejects_retired_engine_reference_file(monkeypatch):
    with installed_bundle(
            with_control_socket=False, with_fpga=False, platform_provider=True,
            platform_extra_files={"data/plasma-platform-engine.json": _json({
                "schema": "plasma.ppu.platform-openocd-reference.v1",
                "openocd_sha256": "0" * 64,
                "admission_sha256": "0" * 64,
                "driver_abi": DRIVER_ABI,
            })}) as env:
        with pytest.raises(PlasmaError, match="PROVIDER_ENTRYPOINT_MISSING"):
            _runtime_execute(env, monkeypatch)
        assert not env["sim"].argvs and not env["core"]._sessions


def test_platform_provider_rejects_modified_installed_engine(monkeypatch):
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True) as env:
        selected = Path(env["engine_data"]["openocd_root"]) / "bin" / "openocd"
        selected.write_bytes(b"tampered-installed-engine")
        with pytest.raises(PlasmaError, match="OPENOCD_SHA256_MISMATCH"):
            _runtime_execute(env, monkeypatch)
        assert not env["sim"].argvs and not env["core"]._sessions


@pytest.mark.parametrize("observation", [
    {"fpga_identity_proven": False}, {"worker_identity": {}},
    {"driver_abi": "plasma_swd:6"}, {"sites": [1]},
])
def test_no_fpga_package_still_requires_trusted_hardware(observation):
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True) as env:
        with pytest.raises(ValueError, match="FPGA_DRIVER_UNVERIFIED|SITE_NOT_SUPPORTED"):
            _qualify(env, hardware={**env["hardware"], **observation})
        assert not env["core"]._sessions and not env["sim"].argvs


@pytest.mark.parametrize("options,mutation,code", [
    ({"profile_change": {"flash_size": 65537}}, None, "PROFILE_GEOMETRY_INVALID"),
    ({"descriptor_change": {"driver_abi": "plasma_swd:6"}}, None, "FPGA_DRIVER_UNVERIFIED"),
    ({"profile_count": 0}, None, "OPF_PROFILE_MISSING_OR_AMBIGUOUS"),
    ({"profile_count": 2}, None, "OPF_PROFILE_MISSING_OR_AMBIGUOUS"),
    ({}, "boot", "OPF_FPGA_IDENTITY_UNVERIFIED"),
    ({}, "image", "OPF_FPGA_IDENTITY_UNVERIFIED"),
    ({}, "platform", "PLATFORM_MISMATCH"),
    ({}, "tamper", "ASSET_SET_FILE_MISMATCH"),
    ({}, "engine_record", "WORKER_ENGINE_SELECTION_MISMATCH"),
])
def test_profile_only_runtime_denies_before_session_or_flash(monkeypatch, options, mutation, code):
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True, **options) as env:
        if mutation in ("boot", "image"):
            journal = env["adapter"].journal
            value = json.loads(journal.read_bytes())
            value["boot_id" if mutation == "boot" else "status"] = "invalid"
            journal.write_text(json.dumps(value))
        elif mutation == "platform":
            monkeypatch.setattr(env["adapter"], "platform", {**TARGET, "board": "wrong-board"})
        elif mutation == "tamper":
            staged = env["product_root"] / "assets/staged" / env["asset_set_sha256"]
            profile_file = staged / f"payload/packages/{PROFILE}/{reference.PROFILE_FILE}"
            profile_file.chmod(0o644)  # model corruption of normally immutable bytes
            profile_file.write_bytes(b"tamper")
        elif mutation == "engine_record":
            write_selection(env["engine_record"], {**env["engine_data"], "adapter_khz": 2000})
        with pytest.raises(PlasmaError, match=code):
            _runtime_execute(env, monkeypatch)
        assert "bind_image" not in env.get("worker_calls", [])
        if mutation != "engine_record":
            assert "open_job_session" not in env.get("worker_calls", [])
        assert not env["core"]._sessions and not env["core"]._site_owners
        assert not env["sim"].argvs
        assert not env["image_root"].exists() or not list(env["image_root"].iterdir())


# --- Job Binding write window (OFE-1B PR-A) -------------------------------------------
F103_PROFILE = {"icpn": ICPN, "target_config": "target/stm32f1x.cfg",
                "flash_base": 0x08000000, "flash_size": 65536, "erase_granularity": 1024}


def _binding(address=0x08000400, length=20, **changes):
    return {"operation": "programming", "operations": ["erase", "program", "verify"], "site_id": 2, "profile": PROFILE,
            "range": {"address": address, "length": length}, **changes}


def test_job_window_uses_the_binding_address_not_flash_base():
    window = reference.job_flash_window(F103_PROFILE, profile_package=PROFILE, site_id=2,
                                        image_size=1500, job_binding=_binding(length=1500))
    assert window == {"load_address": 0x08000400, "erase_length": 2048}




@pytest.mark.parametrize("binding,code", [
    (_binding(operation="program"), "JOB_BINDING_RANGE_MISMATCH"),
    (_binding(site_id=1), "JOB_BINDING_RANGE_MISMATCH"),
    (_binding(profile="other-profile"), "JOB_BINDING_RANGE_MISMATCH"),
    (_binding(length=21), "JOB_BINDING_RANGE_MISMATCH"),     # not this Image
    (_binding(address="0x08000400"), "JOB_BINDING_RANGE_MISMATCH"),
    (_binding(address=True), "JOB_BINDING_RANGE_MISMATCH"),
    ({**_binding(), "range": {"address": 0x08000400}}, "JOB_BINDING_RANGE_MISMATCH"),
    (_binding(address=0x08000200), "JOB_FLASH_RANGE_INVALID"),  # misaligned
    (_binding(address=0x07FFFC00), "JOB_FLASH_RANGE_INVALID"),  # below the bank
    (_binding(address=0x08010000), "JOB_FLASH_RANGE_INVALID"),  # at the bank end
])
def test_job_window_fails_closed(binding, code):
    with pytest.raises(ValueError, match=code):
        reference.job_flash_window(F103_PROFILE, profile_package=PROFILE, site_id=2,
                                   image_size=20, job_binding=binding)


def test_job_window_counts_the_rounded_erase_end():
    with pytest.raises(ValueError, match="JOB_FLASH_RANGE_INVALID"):
        reference.job_flash_window(F103_PROFILE, profile_package=PROFILE, site_id=2,
                                   image_size=1025,
                                   job_binding=_binding(address=0x0800FC00, length=1025))


def test_preflight_pins_the_binding_window_before_any_session():
    with installed_bundle() as env:
        pinned = reference.preflight_runtime_flash(
            product_root=env["product_root"], active_asset_set=env["active_asset_set"],
            target=ICPN, site_id=2, image_size=len(IMAGE),
            job_binding=_binding(length=len(IMAGE)), provider=PROVIDER, profile=PROFILE)
        assert pinned["load_address"] == 0x08000400
        with pytest.raises(ValueError, match="JOB_FLASH_RANGE_INVALID"):
            reference.preflight_runtime_flash(
                product_root=env["product_root"], active_asset_set=env["active_asset_set"],
                target=ICPN, site_id=2, image_size=len(IMAGE),
                job_binding=_binding(address=0x08000001, length=len(IMAGE)),
                provider=PROVIDER, profile=PROFILE)
        assert not env["sim"].argvs and not env["core"]._sessions


def test_job_without_binding_is_refused():
    with pytest.raises(ValueError, match="JOB_BINDING_REQUIRED"):
        reference.job_flash_window(F103_PROFILE, profile_package=PROFILE, site_id=2,
                                   image_size=20, job_binding=None)


def test_runtime_flash_records_stage_timing_and_site_worker_timing(monkeypatch):
    """Each pre-admission check and the Worker admission/OpenOCD/revoke split
    land in the Job timing sink; the Flash outcome is unchanged."""
    from plasma_core import job_timing

    records = []
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True) as env:
        admitted = env["sim"].run

        def admission_with_root_timing(argv, **kw):
            done = admitted(argv, **kw)
            if argv[-2] == "admit":
                done.stdout += "\nPLASMA_SWD_SITE_ADMISSION=" + json.dumps(
                    {"result": "SITE_ADMISSION_RECORD_ISSUED",
                     "timing_ms": {"total": 12.5, "lock_and_fence": 0.4}})
            return done

        monkeypatch.setattr(env["sim"], "run", admission_with_root_timing)
        monkeypatch.setattr(env["adapter"], "_run", admission_with_root_timing)
        token = job_timing.bind(lambda phase, **fields: records.append((phase, fields)))
        try:
            result = _runtime_execute(env, monkeypatch)
        finally:
            job_timing.unbind(token)
    assert result["result"] == "PASS" and result["safe_off"] is True
    phases = [phase for phase, _ in records]
    for phase in ("preflight", "staged_manifest", "load_engine", "worker_status",
                  "qualify_reference", "stage_image", "open_session", "bind_image",
                  "worker_run", "site_worker"):
        assert phase in phases, phase
    fields = dict(records)
    for phase in ("preflight", "staged_manifest", "load_engine", "qualify_reference"):
        assert fields[phase]["thread"] is True
    worker_timing = fields["site_worker"]
    for key in ("admission_ms", "openocd_ms", "revoke_ms",
                "admission_start_unix_ms", "openocd_start_unix_ms"):
        assert type(worker_timing[key]) is float and worker_timing[key] >= 0, key
    assert worker_timing["admission_root_total"] == 12.5
    assert worker_timing["admission_root_lock_and_fence"] == 0.4
    assert result["timing_ms"] == worker_timing


def test_runtime_flash_blocking_verification_leaves_the_event_loop_free(monkeypatch):
    """A slow Bundle/Engine check of one Site's Job must not stall the loop
    (the other Site's Job and the HTTP server share it)."""
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True) as env:
        slow_engine = engine.load_engine

        def slow_load(*args, **kwargs):
            time.sleep(0.4)
            return slow_engine(*args, **kwargs)

        monkeypatch.setattr(engine, "load_engine", slow_load)
        ticks = []
        original = reference.execute_runtime_flash

        async def with_ticker(*args, **kwargs):
            async def ticker():
                while True:
                    ticks.append(time.monotonic())
                    await asyncio.sleep(0.01)

            task = asyncio.create_task(ticker())
            try:
                return await original(*args, **kwargs)
            finally:
                task.cancel()

        monkeypatch.setattr(reference, "execute_runtime_flash", with_ticker)
        result = _runtime_execute(env, monkeypatch)
    assert result["result"] == "PASS"
    # Two load_engine calls (Runtime + qualify_reference) sleep 0.8 s in total;
    # a blocked loop would show one long gap instead of steady 10 ms ticks.
    assert len(ticks) >= 40
    assert max(b - a for a, b in zip(ticks, ticks[1:])) < 0.3
