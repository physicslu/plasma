"""OPF-4A: real Bundle v3/Active Set -> C-3 socket -> ABI-v5 interface.

Host-only: the physical OpenOCD child and admission subprocess are simulated
at the existing ABI-v5 process edge. No Mock Provider, PS Runtime cutover,
FPGA load, Z2 access, or DUT operation is performed.
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

from plasma_core.ic_support import get_default_ic_support_resolver
from plasma_interfaces.openocd import c3_flash_profile
from plasma_interfaces.site_worker_c3 import SiteWorkerControlClient
from plasma_opf import OPF_PROGRAMMING_SCHEMA, TimeoutPolicy

from .ppu_fpga_qualification_fixture import synthetic_image
from .test_c3_rest_flash_cycle import FlashSim, make_engine, write_selection
from .test_ppu_b3_z2_install_gate1 import b3_request, make_coordinator
from .test_ppu_bundle_v3_packages_contract import ROOT, TARGET, bundle_v3

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_opf_reference_openocd as reference  # noqa: E402
import ppu_site_adapter_abi5 as abi5  # noqa: E402
import ppu_site_worker as worker  # noqa: E402

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
                     with_control_socket=True):
    with tempfile.TemporaryDirectory(prefix="opf4a-", dir="/tmp") as directory:
        path = Path(directory)
        c3_profile = c3_flash_profile(get_default_ic_support_resolver().require_exact(ICPN))
        desc = {"schema": "plasma.ppu.provider-capabilities.v1", "target": ICPN,
                "provider_package": PROVIDER, "operations": ["flash_cycle"],
                "sites": [1, 2], "transport": "fpga", "driver_abi": DRIVER_ABI,
                "fpga_package": FPGA, "max_image_bytes": 65536}
        desc.update(descriptor_change or {})
        profile = {"schema": reference.PROFILE_SCHEMA, **c3_profile.to_wire()}
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
            (PROFILE, "programming-profile", [PROVIDER, FPGA], {
                "data/plasma-provider.json": _json(desc),
                reference.PROFILE_FILE: _json(profile),
            }),
            (FPGA, "fpga-image", [], synthetic_image()[0]),
        ]
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
        sim = FlashSim(c3_profile.flash_base, c3_profile.flash_size)
        journal = path / "journal.json"
        journal.write_text('{"status":"IMAGE","image_id":"test","session_id":"test"}')
        (path / "records").mkdir()
        adapter = abi5.Abi5OpenocdAdapter(
            openocd_root=Path(engine_data["openocd_root"]), python=Path(sys.executable),
            adapter_khz=engine_data["adapter_khz"], journal=journal,
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
                "selection": {"schema": OPF_PROGRAMMING_SCHEMA,
                              "provider": PROVIDER, "profile": PROFILE,
                              "timeout_ms": 5000, "options": {}},
                "policy": POLICY, "target": ICPN, "site_id": 2,
                "hardware": {"platform": TARGET["platform"], "board": TARGET["board"],
                             "fpga_part": TARGET["fpga_part"], "sites": [1, 2],
                             "loaded_fpga_package": FPGA, "driver_abi": DRIVER_ABI,
                             "fpga_identity_proven": True},
                "runtime_profile": c3_profile,
                "engine_record": engine_record, "engine_base": path / "openocd",
                "require_root": False, "image_root": image_root,
                "client": SiteWorkerControlClient(path / "c3.sock"),
                "job_id": "job-1", "image": IMAGE,
                "job_deadline_monotonic": time.monotonic() + 5,
                "job_timeout_s": 5.0,
                "core": core, "sim": sim, "adapter": adapter,
                "allowed_jobs": allowed_jobs,
            }
        finally:
            server.close()


def _execute(env, **changes):
    payload = {key: value for key, value in env.items()
               if key in {"client", "product_root", "asset_set_sha256", "selection",
                          "policy", "job_id", "site_id", "target", "image",
                          "image_root", "hardware", "runtime_profile",
                          "job_deadline_monotonic", "job_timeout_s", "engine_record",
                          "engine_base", "require_root"}}
    payload.update(changes)
    return asyncio.run(reference.execute_reference_flash(**payload))


def _qualify(env, **changes):
    payload = {key: value for key, value in env.items()
               if key in {"product_root", "asset_set_sha256", "selection",
                          "policy", "site_id", "target", "hardware", "runtime_profile",
                          "engine_record", "engine_base", "require_root"}}
    payload["image_size"] = len(env["image"])
    payload.update(changes)
    return reference.qualify_reference(**payload)


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
        assert len(env["sim"].argvs) == 1
        assert bytes(env["sim"].memory[:len(IMAGE)]) == IMAGE
        assert list(env["image_root"].iterdir()) == []
        assert env["core"]._site_owners == {} and env["core"]._sealed == set()


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
    ({"profile_change": {"flash_size": 131072}}, "REFERENCE_PROFILE_RUNTIME_MISMATCH"),
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


def test_real_worker_unknown_outcome_seals_site_and_rejects_new_session():
    with installed_bundle() as env:
        env["sim"].corrupt = True
        with pytest.raises(Exception, match="OUTCOME_UNKNOWN|READBACK_MISMATCH"):
            _execute(env)
        assert 2 in env["core"]._sealed
        assert (env["core"].seal_dir / "site2.sealed").exists()
        env["sim"].corrupt = False
        with pytest.raises(Exception, match="SITE_SEALED"):
            _execute(env, job_id="job-2", job_deadline_monotonic=time.monotonic() + 5)
        assert len(env["sim"].argvs) == 1
