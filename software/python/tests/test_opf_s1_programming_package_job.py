"""S1-01: signed non-OpenOCD Package in the real SiteManager Job path.

Host-only: real Python child / UNIX sockets / C3 mock transport; never DUT,
OpenOCD, FPGA, MMIO or Root. Process exit 0 must NOT become Flash PASS.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import threading
from contextlib import nullcontext
from pathlib import Path

import pytest

from plasma_core.config import PlasmaConfig, PPUConfig, ServerConfig, SiteConfig
from plasma_core.enums import Operation
from plasma_core.models import JobRequest
from plasma_server.package_actions import PackageActionRuntime
from plasma_server.runtime_control import RuntimeControlServer
from plasma_server.site_manager import SiteManager

from .ppu_owner_authorization_fixture import OWNER_TOKEN, owner
from .test_ppu_bundle_v3_packages_contract import ROOT, TARGET, bundle_v3, contract
from .test_ppu_b3_z2_install_gate1 import b3_request, make_coordinator
from .test_ppu_stage_c3_site_worker import MockAdapter

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_site_worker as c3  # noqa: E402

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux") or os.geteuid() == 0,
    reason="requires non-root Linux SO_PEERCRED and isolated Python child",
)

JOB = "d" * 32
DEVICE = "ppu-device-" + "a" * 24
PROVIDER = "user-python"
PROFILE = "target-profile"
FIRMWARE = "firmware-asset"
TARGET_ID = "user-specific-ic-without-catalog"
IMAGE = b"\x42\x25\x96\x01"

PYTHON = b"""import json
import os
import socket
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(os.environ['PLASMA_SITE_WORKER_SOCKET'])
s.sendall((json.dumps({'protocol': 'plasma.ppu.site-worker.v2',
                      'op': 'probe', 'site': 2}) + '\\n').encode())
data = b''
while not data.endswith(b'\\n'):
    part = s.recv(4096)
    if not part:
        break
    data += part
s.close()
assert json.loads(data)['ok'] is True
print('FAKE_PYTHON_PROVIDER_RAN_NOT_FLASH_PASS', flush=True)
""".encode()


def fixture(tmp_path: Path, *, with_authorization=True):
    descriptor = {
        "schema": "plasma.ppu.provider-capabilities.v1",
        "target": TARGET_ID, "provider_package": PROVIDER,
        "operations": ["flash_cycle"], "sites": [2], "transport": "ps-only",
        "driver_abi": None, "fpga_package": None, "max_image_bytes": 4096,
    }
    parts = [
        (PROVIDER, "python", [], {
            "python/main.py": PYTHON,
            "config/plasma-package-resources.json": json.dumps({
                "schema": "plasma.ppu.package-resources.v1",
                "sites": [2], "max_runtime_s": 15,
            }).encode(),
            "config/plasma-provider-options.json": json.dumps({
                "schema": "plasma.ppu.provider-options.v1",
                "options": {"type": "object", "properties": {}},
            }).encode(),
        }),
        (PROFILE, "programming-profile", [PROVIDER], {
            "data/plasma-provider.json": json.dumps(descriptor).encode(),
        }),
        (FIRMWARE, "firmware-asset", [PROFILE], {
            "data/firmware.bin": IMAGE,
        }),
    ]
    archive, digest = bundle_v3(
        tmp_path / "src", parts=parts,
        mutate=lambda manifest: manifest.__setitem__("actions", ["install", "verify"]),
    )
    co = make_coordinator(tmp_path / "installed")
    assert co.execute_bundle_v3_install(b3_request(archive, digest))["result"] == "PASS"
    assert co.activate_staged_asset_set(digest, quiescence_lease=nullcontext)["result"] == "PASS"
    verified = contract.verify_host_only_artifact(
        archive, expected_sha256=digest, target_profile=TARGET)
    package = next(p for p in verified.packages if p.id == PROVIDER)
    identity = contract.bundle_package_identity(package)
    authorization = owner.issue(
        credential=OWNER_TOKEN, action=owner.EXECUTE, device_id=DEVICE,
        subject_sha256=digest, transaction_id=JOB,
        package_identity_sha256=identity,
    ) if with_authorization else {}
    req = {
        "asset_set_sha256": digest, "package_id": PROVIDER,
        "package_version": package.version, "package_kind": "python",
        "package_identity_sha256": identity, "job_id": JOB,
        "programming": {
            "site_id": 2, "target": TARGET_ID, "operation": "flash_cycle",
            "profile": PROFILE, "firmware_package": FIRMWARE,
            "firmware_sha256": hashlib.sha256(IMAGE).hexdigest(),
        },
    }
    return co.paths.product_root, req, authorization


async def run_scenario(tmp_path, *, mutate=None, observer=True):
    product, request, authorization = fixture(tmp_path)
    if mutate:
        mutate(request, authorization)
    config = PlasmaConfig(
        ppu=PPUConfig(id="ppu-hostonly", facility_id="lab"),
        server=ServerConfig(
            host="127.0.0.1", port=0, output_root=tmp_path / "output",
            log_root=tmp_path / "logs", max_supported_sites=2,
            max_concurrent_jobs=1),
        sites=[SiteConfig(id=2, enabled=True, interface="provider", target=TARGET_ID)],
    )
    manager = SiteManager(config)
    await manager.start()
    control = RuntimeControlServer(manager, tmp_path / "runtime.sock")
    await control.start()
    adapter = MockAdapter()
    core = c3.SiteWorkerCore(
        adapter, runtime_pid=os.getpid(),
        lease_verifier=c3.runtime_lease_verifier(tmp_path / "runtime.sock"),
        seal_dir=tmp_path / "seals", image_root=tmp_path / "images",
    )
    service = c3.SiteWorkerServer(core, tmp_path / "c3.sock", mode=0o600)
    service.start()
    package = PackageActionRuntime(
        manager, control_plane=ROOT / "scripts", product_root=product,
        state_root=tmp_path / "package-state", owner_credential=None,
        spawner=None, python_executable=Path(sys.executable),
        site_worker=c3.SiteWorkerClient(tmp_path / "c3.sock"),
        hardware_observer=(lambda _site: {
            "platform": TARGET["platform"], "board": TARGET["board"],
            "fpga_part": TARGET["fpga_part"], "sites": [2],
            "ps_transport_ready": True,
        }) if observer else None,
    )
    try:
        try:
            result = await package.run_programming_control(
                request, authorization, OWNER_TOKEN, DEVICE, threading.Event())
            return result, manager, core, adapter
        except Exception as exc:
            return exc, manager, core, adapter
    finally:
        service.close()
        await control.close()
        await manager.shutdown()


def test_signed_python_provider_uses_real_programming_job_and_c3_but_never_flash_pass(tmp_path):
    result, manager, core, adapter = asyncio.run(run_scenario(tmp_path))
    assert isinstance(result, dict), result
    assert result["job_id"] == JOB
    assert result["state"] != "success"  # exit 0 is NOT programming evidence
    assert "PROVIDER_PROGRAMMING_EVIDENCE_NOT_QUALIFIED" in str(result)
    interface = manager.interfaces[2]
    receipt = interface.last_receipt
    assert receipt is not None
    assert receipt["executor_result"]["result"] == "SUCCEEDED"
    assert "FAKE_PYTHON_PROVIDER_RAN_NOT_FLASH_PASS" in receipt["executor_result"]["stdout"]["tail"]
    assert receipt["executor_result"]["site_transport"]["session"] == "CLOSED"
    assert adapter.calls == [(2, "probe")]
    assert not core._sessions and not core._site_owners
    assert manager.execution_lease_snapshot()["busy"] is False
    assert manager.ic_support_resolver is None  # no ICPN / OpenOCD registry


@pytest.mark.parametrize("mutation", [
    lambda req, auth: auth.update(mac="0" * 64),
    lambda req, auth: req["programming"].update(profile="wrong-profile"),
    lambda req, auth: req["programming"].update(site_id=1),
    lambda req, auth: req.update(package_identity_sha256="f" * 64),
    lambda req, auth: req["programming"].update(firmware_sha256="0" * 64),
])
def test_invalid_authorization_or_bundle_selection_never_spawns_provider(tmp_path, mutation):
    result, manager, core, adapter = asyncio.run(run_scenario(tmp_path, mutate=mutation))
    assert isinstance(result, Exception)
    assert not adapter.calls
    assert manager.execution_lease_snapshot()["busy"] is False
    assert not core._sessions


def test_unobserved_ps_transport_denied_even_with_valid_owner_token(tmp_path):
    result, manager, core, adapter = asyncio.run(run_scenario(tmp_path, observer=False))
    assert isinstance(result, ValueError)
    assert "PROVIDER_PROGRAMMING_NOT_QUALIFIED" in str(result)
    assert not adapter.calls
    assert not core._sessions


def test_plain_rest_or_protocol_cannot_claim_trusted_provider_authority(tmp_path):
    config = PlasmaConfig(
        server=ServerConfig(output_root=tmp_path / "o", log_root=tmp_path / "l"),
        sites=[SiteConfig(id=2, enabled=True, interface="provider", target=TARGET_ID)],
    )

    async def scenario():
        manager = SiteManager(config)
        await manager.start()
        try:
            with pytest.raises(Exception, match="PROVIDER_JOB_NOT_AUTHORIZED"):
                manager.enqueue(JobRequest(
                    site_id=2, operation=Operation.FLASH_CYCLE,
                    image=IMAGE, job_id=JOB, target=TARGET_ID,
                    metadata={"provider": PROVIDER, "profile": PROFILE}))
        finally:
            await manager.shutdown()
    asyncio.run(scenario())
