from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-network-phase1-acceptance.py"
SPEC = importlib.util.spec_from_file_location("ppu_network_phase1_acceptance", SCRIPT)
assert SPEC and SPEC.loader
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


def test_network_settings_requires_phase1_activation_boundary() -> None:
    payload = {
        "ok": True,
        "ppu_network_settings": {
            "revision": 1,
            "interface": "eth0",
            "mode": "dhcp",
            "address": None,
            "prefix_length": None,
            "gateway": None,
            "dns_servers": [],
        },
        "activation": {"supported": False, "state": "not_implemented"},
    }
    settings = acceptance._network_settings(payload)
    acceptance._assert_settings(
        settings,
        {
            "mode": "dhcp",
            "address": None,
            "prefix_length": None,
            "gateway": None,
            "dns_servers": [],
        },
        revision=1,
    )

    wrong = dict(payload)
    wrong["activation"] = {"supported": True, "state": "active"}
    with pytest.raises(acceptance.AcceptanceError, match="activation boundary"):
        acceptance._network_settings(wrong)


def test_assert_settings_fails_on_revision_or_interface_drift() -> None:
    settings = {
        "revision": 2,
        "interface": "eth0",
        **acceptance.STATIC_SETTINGS,
    }
    acceptance._assert_settings(settings, acceptance.STATIC_SETTINGS, revision=2)

    with pytest.raises(acceptance.AcceptanceError, match="expected revision"):
        acceptance._assert_settings(settings, acceptance.STATIC_SETTINGS, revision=3)

    wrong_interface = dict(settings)
    wrong_interface["interface"] = "wlan0"
    with pytest.raises(acceptance.AcceptanceError, match="expected interface eth0"):
        acceptance._assert_settings(wrong_interface, acceptance.STATIC_SETTINGS, revision=2)


def test_verify_sidecar_requires_matching_archive_hash(tmp_path: Path) -> None:
    archive = tmp_path / "plasma-ppu-0.1.0-linux-armv7l.tar.gz"
    archive.write_bytes(b"phase1-release")
    digest = acceptance._sha256(archive)
    sidecar = Path(f"{archive}.sha256")
    sidecar.write_text(f"{digest}  {archive.name}\n", encoding="utf-8")

    assert acceptance._verify_sidecar(archive, sidecar) == digest

    sidecar.write_text(f"{'0' * 64}  {archive.name}\n", encoding="utf-8")
    with pytest.raises(acceptance.AcceptanceError, match="SHA-256 mismatch"):
        acceptance._verify_sidecar(archive, sidecar)


def test_parse_result_uses_last_machine_readable_marker() -> None:
    stdout = "noise\n" + acceptance.RESULT_MARKER + '{"overall_result":"FAIL"}\n'
    stdout += acceptance.RESULT_MARKER + '{"overall_result":"PASS","tests":{"default_dhcp":"PASS"}}\n'
    result = acceptance._parse_result(stdout)
    assert result["overall_result"] == "PASS"
    assert result["tests"]["default_dhcp"] == "PASS"


def test_capability_bit_helper_uses_effective_mask(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(acceptance, "_effective_capabilities", lambda: 1 << acceptance.CAP_NET_ADMIN)
    assert acceptance._has_capability(acceptance.CAP_NET_ADMIN) is True
    monkeypatch.setattr(acceptance, "_effective_capabilities", lambda: 0)
    assert acceptance._has_capability(acceptance.CAP_NET_ADMIN) is False
