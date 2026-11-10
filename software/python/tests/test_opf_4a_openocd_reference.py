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
                     with_control_socket=True, verified_worker=True,
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
        desc = {"schema": "plasma.ppu.provider-capabilities.v1", "target": target_icpn,
                "provider_package": PROVIDER, "operations": ["flash_cycle"],
                "sites": [1, 2], "transport": "fpga", "driver_abi": DRIVER_ABI,
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
                "client": SiteWorkerControlClient(path / "c3.sock"),
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
    payload["job_binding"] = None  # inline contract: writes at Profile flash_base
    payload.update(changes)
    return asyncio.run(reference.execute_reference_flash(**payload))


def _qualify(env, **changes):
    payload = {key: value for key, value in env.items()
               if key in {"product_root", "asset_set_sha256", "selection",
                          "policy", "site_id", "target", "hardware",
                          "engine_record", "engine_base", "require_root"}}
    payload["image_size"] = len(env["image"])
    payload.update(changes)
    return reference.qualify_reference(**payload)


def test_bundle_profile_accepts_new_icpn_without_core_registry():
    unknown = "VENDOR-NEW-PART-A"
    with installed_bundle(target_icpn=unknown) as env:
        preflight = reference.preflight_runtime_flash(
            product_root=env["product_root"], active_asset_set=env["active_asset_set"],
            target=unknown, site_id=2, image_size=len(IMAGE), job_binding=None)
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
                target=target, site_id=2, image_size=len(IMAGE), job_binding=None,
                provider=PROVIDER, profile=profile_id)
            assert pinned["profile_package"] == profile_id
            assert pinned["profile"]["icpn"] == target
        assert not env["sim"].argvs


def test_bundle_profile_image_bounds_and_target_claim_fail_closed():
    with installed_bundle() as env:
        with pytest.raises(ValueError, match="IMAGE_OUT_OF_BOUNDS"):
            reference.preflight_runtime_flash(
                product_root=env["product_root"], active_asset_set=env["active_asset_set"],
                target=ICPN, site_id=2, image_size=65537, job_binding=None)
        with pytest.raises(ValueError, match="REFERENCE_TARGET_MISMATCH"):
            reference.preflight_runtime_flash(
                product_root=env["product_root"], active_asset_set=env["active_asset_set"],
                target="ANOTHER-UNLISTED-MCU", site_id=2, image_size=len(IMAGE), job_binding=None)
        assert not env["sim"].argvs and not env["core"]._sessions


def test_verified_reference_executes_existing_c3_abi5_flash_and_readback():
    with installed_bundle() as env:
        result = _execute(env)
        assert result["result"] == "PASS" and result["safe_off"] is True
        assert result["readback_sha256"] == result["image_sha256"] == hashlib.sha256(IMAGE).hexdigest()
        assert result["bytes_verified"] == len(IMAGE)
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
        with pytest.raises(Exception, match="READBACK_MISMATCH"):
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


def _runtime_execute(env, monkeypatch):
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
                         operation=Operation.FLASH_CYCLE, image=IMAGE, timeout_s=5.0)
    return run(reference.execute_runtime_flash(
        env["client"], product_root=env["product_root"], request=request,
        active_asset_set=env["active_asset_set"],
        job_deadline_monotonic=time.monotonic() + 5,
        image_root=env["image_root"], job_binding=None))


def test_profile_provider_only_runtime_flash_uses_installed_platform(monkeypatch):
    with installed_bundle(with_control_socket=False, with_fpga=False,
                          platform_provider=True) as env:
        result = _runtime_execute(env, monkeypatch)
        assert result["result"] == "PASS" and result["safe_off"] is True
        assert result["readback_sha256"] == hashlib.sha256(IMAGE).hexdigest()
        assert result["bytes_verified"] == len(IMAGE)
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


def test_platform_provider_accepts_new_verified_engine_without_bundle_pins(monkeypatch):
    updated_engine = b"\x7fELF-updated-plasma-swd-v5"
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
    return {"operation": "flash_cycle", "site_id": 2, "profile": PROFILE,
            "range": {"address": address, "length": length}, **changes}


def test_job_window_uses_the_binding_address_not_flash_base():
    window = reference.job_flash_window(F103_PROFILE, profile_package=PROFILE, site_id=2,
                                        image_size=1500, job_binding=_binding(length=1500))
    assert window == {"load_address": 0x08000400, "erase_length": 2048}


def test_job_without_binding_is_the_explicit_flash_base_contract():
    window = reference.job_flash_window(F103_PROFILE, profile_package=PROFILE, site_id=2,
                                        image_size=20, job_binding=None)
    assert window == {"load_address": 0x08000000, "erase_length": 1024}


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
