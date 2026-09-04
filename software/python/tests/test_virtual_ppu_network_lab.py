from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts/virtual-ppu-network-lab.py"


def _load_lab():
    spec = importlib.util.spec_from_file_location("virtual_ppu_network_lab", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_virtual_lab_owns_two_distinct_ppu_identities_and_isolated_subnet() -> None:
    lab = _load_lab()

    assert lab.PPU_A_ID != lab.PPU_B_ID
    assert lab.PPU_A_INITIAL_IP != lab.PPU_B_INITIAL_IP
    assert lab.PPU_A_CANDIDATE_IP not in {lab.PPU_A_INITIAL_IP, lab.PPU_B_INITIAL_IP}
    assert lab.LAB_SUBNET == "192.168.78.0/24"
    assert lab.CAP_NET_ADMIN == 12


def test_virtual_lab_manager_config_is_runtime_mutable_and_alias_scoped(tmp_path: Path) -> None:
    lab = _load_lab()
    config = tmp_path / "manager.yaml"
    registry = tmp_path / "manager-ppu-registry.json"

    lab._write_manager_config(config, port=18181, registry_state=registry)
    text = config.read_text(encoding="utf-8")

    assert "host: 127.0.0.1" in text
    assert "registry_state_path:" in text
    assert str(registry.resolve()) in text
    assert "alias: ppu-a" in text
    assert "alias: ppu-b" in text
    assert f"http://{lab.PPU_A_INITIAL_IP}:{lab.PPU_PORT}" in text
    assert f"http://{lab.PPU_B_INITIAL_IP}:{lab.PPU_PORT}" in text


def test_virtual_lab_requires_both_manager_observations_to_be_trusted() -> None:
    lab = _load_lab()
    payload = {
        "ppus": [
            {
                "alias": "ppu-a",
                "gateway_live": True,
                "execution_ready": True,
                "contract_compatible": True,
                "identity_conflict": False,
                "errors": [],
                "ppu": {"ppu_id": lab.PPU_A_ID},
            },
            {
                "alias": "ppu-b",
                "gateway_live": True,
                "execution_ready": True,
                "contract_compatible": True,
                "identity_conflict": False,
                "errors": [],
                "ppu": {"ppu_id": lab.PPU_B_ID},
            },
        ]
    }

    assert lab._fleet_ready(payload) is True
    payload["ppus"][1]["ppu"]["ppu_id"] = lab.PPU_A_ID
    assert lab._fleet_ready(payload) is False


def test_virtual_lab_does_not_use_host_network_or_host_privilege_shortcuts() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert '"--network", "host"' not in source
    assert "--privileged" not in source
    assert "sudo" not in source
    assert '"--cap-add", "NET_ADMIN"' in source
    assert '"--cap-drop", "ALL"' in source
    assert "host_uplink_untouched" in source
    assert "/api/registry/ppu-a/network-commissioning" in source
    assert "registry_compare_and_swap" in source
    assert "durable_manager_journal" in source
