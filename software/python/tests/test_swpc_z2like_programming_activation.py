from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "plasmactl-swpc-z2like-programming"
PHASE3 = ROOT / "software" / "python" / "plasma_web" / "gateway_phase3.py"
PROVIDER = ROOT / "software" / "python" / "plasma_web" / "configured_mock_provider.py"


def test_z2like_programming_activation_is_explicit_and_single_ppu() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "--engineering-configured-mock" in text
    assert "--engineering-mock " not in text
    assert "configured_mock" in text
    assert '"gateway_bind": "127.0.0.1:18080"' in text
    assert "http://127.0.0.1:18080/api/engineering/targets" in text
    assert "configured mock Programming refuses non-mock Sites" in text
    assert "legacy 32-PPU demo topology is not instantiated" in text
    assert "facility_count" in text and "ppu_count" in text


def test_activation_requires_capable_runtime_and_rolls_back_failed_mutation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'provider = "plasma_web/configured_mock_provider.py"' in text
    assert "installed PPU runtime does not contain configured Mock Programming support" in text
    assert "restore_dropin" in text
    assert "previous Programming activation restored" in text
    assert "Programming deactivation failed; previous activation restored" in text


def test_activation_waits_for_gateway_readiness_before_rollback() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "wait_for_catalog()" in text
    assert "PLASMA_SWPC_Z2LIKE_PROGRAMMING_READY_TIMEOUT_S" in text
    assert 'topology="$(wait_for_catalog)"' in text
    assert "systemctl is-active --quiet plasma-web.service || return 1" in text
    assert "sleep 0.2" in text
    assert "timeout=1" in text


def test_activation_parses_canonical_yaml_with_qualified_plasma_python() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'plasma_python="$(base_field plasma_python)"' in text
    assert '"$plasma_python" - "$ppu_config"' in text
    assert 'python3 - "$base_evidence" "$ppu_config"' not in text


def test_configured_provider_refuses_hardware_interfaces_and_reuses_local_server() -> None:
    text = PROVIDER.read_text(encoding="utf-8")

    assert 'site.interface != "mock"' in text
    assert "may bind only to the local Plasma Server" in text
    assert "does not create the legacy 8-Facility / 32-PPU demo topology" in text
    assert "PlasmaClient(self._identity[2], self._ports[key])" in text
    assert '"provider": "configured_mock"' in text
    assert "image=image.data" in text
    assert "image_ref" not in text


def test_phase3_configured_provider_is_opt_in_and_excludes_legacy_mock() -> None:
    text = PHASE3.read_text(encoding="utf-8")

    assert '"--engineering-configured-mock"' in text
    assert "ConfiguredMockEngineeringPPUProvider" in text
    assert 'if "--engineering-mock" in sys.argv' in text
    assert "mutually exclusive" in text
    assert "canonical_gateway.serve(" in text
