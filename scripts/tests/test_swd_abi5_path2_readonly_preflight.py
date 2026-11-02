"""Host-only tests: SWPC/Z2 credentials, FPGA, MMIO and DUT never used."""
from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "swd_abi5_path2_readonly_preflight.py"
spec = importlib.util.spec_from_file_location("swd5_readonly_preflight", SCRIPT)
assert spec is not None and spec.loader is not None
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SOURCE = "a" * 40
DEVICE = "ppu-device-" + "7ed4b30913a9bf6101da5a7a"
HOST = "192.168.2.99"


def facts():
    return {
        "schema": "plasma.swd5.z2-readonly-facts.v1",
        "uid_root": True, "board_compatible": True,
        "boot_id_present": True, "manager_state": "operating",
        "manager_last_firmware": "base.bin",
        "uio_overlaps": [{"uio": "uio0",
                          "platform_node": "43c00000.audio-codec-ctrl",
                          "driver": "uio_pdrv_genirq",
                          "maps": [[0x43C00000, 0x10000]],
                          "runtime": "suspended"}],
        "platform_overlaps": ["43c00000.audio-codec-ctrl"],
        "candidate_sha256": "NOT_STAGED", "golden_sha256": "b" * 64,
        "root_source_commit": "NOT_STAGED", "native_python_present": False,
        "proc_consumer_census": "NOT_RUN_ROOT_G5_REQUIRED",
        "axi_mmio": "NOT_RUN", "fpga_load": "NOT_RUN",
        "site_identity": "NOT_RUN", "bluepill_dpidr": "NOT_RUN",
        "electrical_qualification": "NOT_RUN",
    }


def interfaces(receipt=None, *, rc=0, host=HOST, device=DEVICE):
    report = facts() if receipt is None else receipt
    transcript = mod.PREFIX + json.dumps(report, sort_keys=True) + "\n"
    common = SimpleNamespace(_private_ipv4=lambda x: x,
                             probe_status=lambda h: {"device_id_observed": device})
    ssh = SimpleNamespace(z2_login_credentials=lambda home: (
        {"ssh_host": host, "ssh_username": "xilinx", "ssh_password": "[test-only]"},
        Path("/invalid-test-only-known-hosts")),
        password_ssh_z2=lambda argv, credentials, hosts, timeout: (rc, transcript))
    return common, ssh


def test_remote_command_is_ast_valid_and_metadata_only():
    ast.parse(mod.REMOTE_READ_ONLY)
    assert "Path('/proc/device-tree/compatible')" in mod.REMOTE_READ_ONLY
    for forbidden in ("/dev/mem", "/dev/uio", "fpga_manager/fpga0/firmware",
                      "mmap", "OpenOCD", "os.system", "subprocess.Popen",
                      ".write_text(", ".write_bytes(", "os.open("):
        assert forbidden not in mod.REMOTE_READ_ONLY


def test_read_only_preflight_carries_only_verified_enrolled_evidence():
    common, ssh = interfaces()
    called = []
    original = ssh.password_ssh_z2

    def remote(argv, credentials, hosts, timeout):
        called.append((argv, timeout))
        return original(argv, credentials, hosts, timeout)

    ssh.password_ssh_z2 = remote
    r = mod.read_only_preflight(host=HOST, device_id=DEVICE,
                                source_sha=SOURCE, common=common, ssh=ssh)
    assert r["status"] == "PASS_READ_ONLY_FACTS_ONLY"
    assert r["owner_admission"] == "NOT_VERIFIED"
    assert r["physical_identity"] == r["dpidr"] == "NOT_RUN"
    assert r["facts"]["candidate_sha256"] == "NOT_STAGED"
    assert called[0][0][:3] == ["python3", "-I", "-c"]
    assert called[0][0][3] == mod.REMOTE_READ_ONLY
    assert called[0][1] == 45


@pytest.mark.parametrize("bad", [
    {"uid_root": False}, {"board_compatible": False},
    {"boot_id_present": False}, {"site_identity": "PASS"},
    {"fpga_load": "PASS"}, {"bluepill_dpidr": "PASS"},
    {"axi_mmio": "PASS"}, {"electrical_qualification": "PASS"},
    {"proc_consumer_census": "COMPLETE"},
    {"schema": "wrong"}, {"unexpected": "untrusted"},
])
def test_forged_or_mutating_receipt_denied(bad):
    common, ssh = interfaces(facts() | bad)
    with pytest.raises(RuntimeError, match="READ_ONLY_Z2_RECEIPT_INVALID"):
        mod.read_only_preflight(host=HOST, device_id=DEVICE,
                                source_sha=SOURCE, common=common, ssh=ssh)


def test_wrong_device_host_sha_and_ssh_exit_denied():
    common, ssh = interfaces()
    for sha in ("wrong", "b" * 39):
        with pytest.raises(RuntimeError, match="WORK_ORDER_PIN_INVALID"):
            mod.read_only_preflight(host=HOST, device_id=DEVICE,
                                    source_sha=sha, common=common, ssh=ssh)
    with pytest.raises(RuntimeError, match="WORK_ORDER_PIN_INVALID"):
        mod.read_only_preflight(host=HOST, device_id="wrong",
                                source_sha=SOURCE, common=common, ssh=ssh)
    common, ssh = interfaces(device="ppu-device-" + "0" * 24)
    with pytest.raises(RuntimeError, match="DEVICE_ID_MISMATCH"):
        mod.read_only_preflight(host=HOST, device_id=DEVICE,
                                source_sha=SOURCE, common=common, ssh=ssh)
    common, ssh = interfaces(host="192.168.2.100")
    with pytest.raises(RuntimeError, match="SSH_HOST_MISMATCH"):
        mod.read_only_preflight(host=HOST, device_id=DEVICE,
                                source_sha=SOURCE, common=common, ssh=ssh)
    common, ssh = interfaces(rc=77)
    with pytest.raises(RuntimeError, match="READ_ONLY_Z2_SSH_DENIED"):
        mod.read_only_preflight(host=HOST, device_id=DEVICE,
                                source_sha=SOURCE, common=common, ssh=ssh)


def test_main_rejects_nonmatching_checkout_without_ssh(capsys):
    with patch.object(mod.subprocess, "run", return_value=SimpleNamespace(stdout="b" * 40)):
        rc = mod.main(["--host", HOST, "--device-id", DEVICE,
                       "--source-sha", SOURCE])
    assert rc == 69
    output = capsys.readouterr().out
    assert "EXACT_PR_HEAD_MISMATCH" in output
    assert '"dpidr":"NOT_RUN"' in output
