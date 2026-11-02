"""Path 2 B3 preflight must reject stale factory before any physical write.

No network or SSH call: this test replaces the enrolled SWPC connector with
a minimal stub to prove no B1/B2/B3 mutation can occur on a missing/old kit.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from .test_ppu_bundle_v3_packages_contract import SOURCE, ROOT, load

path2 = load("ppu_path2_b3_preflight_test", "ppu_path2_bundle_v3_b3_acceptance.py")
DEVICE = "ppu-device-7ed4b30913a9bf6101da5a7a"


@pytest.mark.parametrize("capabilities,expected", [
    ({}, "B3_FACTORY_INSTALLER_NOT_INSTALLED"),
    ({"bundle_v3_b3_install": False}, "B3_FACTORY_INSTALLER_NOT_INSTALLED"),
    ({"bundle_v3_b3_install": True,
      "bundle_v3_b3_source_commit": "c" * 40}, "B3_FACTORY_SOURCE_SHA_MISMATCH"),
])
def test_path2_b3_preflight_rejects_before_any_upload(monkeypatch, capabilities, expected):
    calls = []
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def status(self):
            return {
                "identity": {"device_id": DEVICE},
                "bootstrap": {"state": "bootstrap_ready"},
                "runtime": {"state": "not_installed"},
                "deployment": {"state": "admitted"},
                "capabilities": capabilities,
            }

        def _call(self, *args, **kwargs):
            calls.append(("mutation", args))
            raise AssertionError("NO_DEVICE_HTTP_MUTATION_BEFORE_QUALIFIED_PREFLIGHT")

    common = SimpleNamespace(
        _private_ipv4=lambda host: host,
        probe_status=lambda host: {"device_id_observed": DEVICE},
        _existing_bootstrap_token_via_z2_ssh=lambda host: "secret-not-logged",
        DirectSSHAuthenticatedBootstrap=Client,
        _load_client=lambda: object(),
    )
    builder = SimpleNamespace(make_bundle=lambda *args: pytest.fail("builder must not run"))
    monkeypatch.setattr(path2, "load",
                        lambda name, filepath: common if name == "ppu_b3_path2_common" else builder)
    result, code = path2.run("192.168.2.99", DEVICE, SOURCE)
    assert code == 69
    assert result["reason"] == expected
    assert result["b1_receive"] == "NOT_RUN"
    assert result["b3_install"] == "NOT_RUN"
    assert calls == []
