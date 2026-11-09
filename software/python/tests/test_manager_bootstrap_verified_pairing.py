from __future__ import annotations

from pathlib import Path

import pytest

from plasma_manager.bootstrap import (
    BootstrapCredentialError,
    BootstrapCredentialStore,
    BootstrapManagerError,
)
from plasma_manager.config import PPURegistryEntry
from plasma_manager.registry import PPURegistryStore
from plasma_manager.verified_bootstrap import VerifiedManagerBootstrapCoordinator


DEVICE_ID = "ppu-device-0123456789abcdef"
VALID_TOKEN = "v" * 40
WRONG_TOKEN = "w" * 40


def _registry(tmp_path: Path) -> PPURegistryStore:
    return PPURegistryStore(
        (PPURegistryEntry(endpoint="http://192.168.2.99:18080", alias="z2"),),
        tmp_path / "registry.json",
    )


class FakeVerifiedBootstrapClient:
    """Coordinator-level fake; wire MACs are covered in test_ppu_bootstrap_request_auth."""

    instances: list["FakeVerifiedBootstrapClient"] = []

    def __init__(self, endpoint: str, timeout_s: float):
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.calls: list[tuple[str, object, object]] = []
        self.__class__.instances.append(self)

    def status(self, credential=None, device_id=None):
        self.calls.append(("status", credential, device_id))
        if credential is not None and credential != VALID_TOKEN:
            return 401, {"ok": False, "error": "unauthorized"}
        return 200, {
            "bootstrap": {"state": "bootstrap_ready"},
            "identity": {"device_id": DEVICE_ID},
            "runtime": {"state": "runtime_active"},
            "capabilities": {"runtime_deployment": True, "fpga_update": False},
        }


def _coordinator(tmp_path: Path, factory=FakeVerifiedBootstrapClient):
    store = BootstrapCredentialStore(tmp_path / "credentials.json")
    return store, VerifiedManagerBootstrapCoordinator(_registry(tmp_path), store, 2.0,
                                                      client_factory=factory)


def test_pairing_verifies_device_token_before_persisting(tmp_path: Path) -> None:
    FakeVerifiedBootstrapClient.instances.clear()
    store, coordinator = _coordinator(tmp_path)

    result = coordinator.pair("z2", VALID_TOKEN)

    assert result["pairing"]["paired"] is True
    assert result["pairing"]["device_verified"] is True
    assert result["request_authentication"] == "plasma.ppu.bootstrap-request-auth.v1"
    assert store.credential_for("z2") == (DEVICE_ID, VALID_TOKEN)
    calls = FakeVerifiedBootstrapClient.instances[0].calls
    # Proof is one MACed status for the observed device; no upload probe.
    assert calls == [("status", None, None), ("status", VALID_TOKEN, DEVICE_ID)]


def test_wrong_pairing_token_fails_without_credential_state(tmp_path: Path) -> None:
    FakeVerifiedBootstrapClient.instances.clear()
    store, coordinator = _coordinator(tmp_path)

    with pytest.raises(BootstrapCredentialError, match="could not be verified"):
        coordinator.pair("z2", WRONG_TOKEN)

    assert store.paired("z2") is False
    assert not (tmp_path / "credentials.json").exists()


def test_unproven_ppu_response_is_never_pairing_proof(tmp_path: Path) -> None:
    class Unproven(FakeVerifiedBootstrapClient):
        def status(self, credential=None, device_id=None):
            if credential is not None:
                raise BootstrapManagerError(
                    "PPU Bootstrap response is not authenticated by the paired device")
            return super().status()

    store, coordinator = _coordinator(tmp_path, Unproven)
    with pytest.raises(BootstrapCredentialError, match="could not be verified"):
        coordinator.pair("z2", VALID_TOKEN)
    assert store.paired("z2") is False


def test_authenticated_status_for_another_device_is_rejected(tmp_path: Path) -> None:
    class Swapped(FakeVerifiedBootstrapClient):
        def status(self, credential=None, device_id=None):
            status, payload = super().status(credential, device_id)
            if credential is not None:
                payload["identity"] = {"device_id": "ppu-device-fedcba9876543210"}
            return status, payload

    store, coordinator = _coordinator(tmp_path, Swapped)
    with pytest.raises(BootstrapCredentialError, match="could not be verified"):
        coordinator.pair("z2", VALID_TOKEN)
    assert store.paired("z2") is False
