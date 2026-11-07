"""Host-only Path 2 dispatch adapter regression. No SWPC, SSH, Z2 or hardware."""
from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT
from .test_opf_platform_bundle_v3_build import source

sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "opf_site2_path2_adapter", ROOT / "scripts/opf_site2_path2_bundle_deploy.py")
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def payload(tmp_path):
    inputs = source(tmp_path)
    return {
        "target": {"platform": "linux-armv7", "board": "pynq-z2",
                   "fpga_part": "xc7z020clg400-1"},
        "files": {p.name: base64.b64encode(p.read_bytes()).decode()
                  for p in inputs.iterdir()},
    }


def test_z2_source_read_uses_pinned_host_and_fixed_sudo_python(tmp_path):
    answer = payload(tmp_path)
    receipt = base64.b64encode(json.dumps(answer).encode()).decode()
    commands = []
    class Helper:
        def z2_login_credentials(self, _home):
            return {"ssh_host": "192.168.2.99"}, Path("/tmp/test-known-hosts")
        def password_ssh_z2(self, command, credentials, hosts, timeout):
            commands.append(command)
            return (0, "PLASMA_OPF_GEN7_SOURCE:" + receipt)
    assert runner.retrieve_source("192.168.2.99", helper=Helper()) == answer
    assert commands and commands[0][:3] == ["python3", "-I", "-c"]
    with pytest.raises(runner.DeployDenied, match="APPROVED_Z2_HOST_MISMATCH"):
        runner.retrieve_source("192.168.2.98", helper=Helper())


@pytest.mark.parametrize("rc,output", [
    (1, ""), (0, "no receipt"), (0, "PLASMA_OPF_GEN7_SOURCE:%%%")
])
def test_source_read_fail_closed(rc, output):
    class Helper:
        def z2_login_credentials(self, _home):
            return {"ssh_host": "192.168.2.99"}, Path("/tmp/known")
        def password_ssh_z2(self, *args, **kwargs):
            return rc, output
    with pytest.raises(runner.DeployDenied):
        runner.retrieve_source("192.168.2.99", helper=Helper())


@pytest.mark.parametrize("terminal", ["succeeded", "failed", "recovery_required"])
def test_bounded_path2_b3_uses_real_builder_and_no_fpga_load(tmp_path, monkeypatch, terminal):
    answer = payload(tmp_path)
    events = []
    class Api:
        def __init__(self, host, module, token):
            assert host == "192.168.2.99" and token == "sample-owner-token"
            self.module = module
        def upload(self, blob):
            events.append(("B1", len(blob)))
            return "a" * 32
        def submit(self, *, kind, upload_id, archive_sha256):
            assert kind == "bundle" and upload_id == "a" * 32
            events.append(("B2", archive_sha256))
            return SimpleNamespace(upload_id=upload_id, transaction_id="b" * 32,
                                   state="admitted", archive_sha256=archive_sha256)
        def deployment_state(self, tx):
            assert tx == "c" * 32
            events.append(("B3-status", terminal))
            return {"state": terminal,
                    "result": {"result": "PASS"} if terminal == "succeeded" else {}}

    class ClientModule:
        class BootstrapAPIClient:
            @staticmethod
            def install_bundle(self, admitted, *, mode, fpga_load):
                assert mode == "activate" and fpga_load is False
                events.append(("B3", mode))
                return SimpleNamespace(transaction_id="c" * 32)

    monkeypatch.setattr(runner, "retrieve_source", lambda host, helper: answer)
    common = SimpleNamespace(
        DirectSSHAuthenticatedBootstrap=Api,
        _existing_bootstrap_token_via_z2_ssh=lambda host: "sample-owner-token",
        _load_client=lambda: ClientModule(),
    )
    monkeypatch.setattr(
        runner, "_load",
        lambda path, name: common if path == "ppu_path2_hardware_baseline.py" else object(),
    )
    if terminal == "succeeded":
        result = runner.run("192.168.2.99")
        assert result["result"] == "PASS"
        assert result["dut_flash"] == "NOT_RUN"
        assert result["fpga_reload"] == "NOT_RUN"
        assert result["new_asset_set_sha256"] == events[1][1]
    else:
        with pytest.raises(runner.DeployDenied, match="B3_" + terminal.upper()):
            runner.run("192.168.2.99")
    assert [e[0] for e in events] == ["B1", "B2", "B3", "B3-status"]
