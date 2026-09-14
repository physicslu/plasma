from __future__ import annotations

from pathlib import Path

import pytest

from plasma_manager.bootstrap import BootstrapCredentialError, BootstrapCredentialStore
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
    instances: list["FakeVerifiedBootstrapClient"] = []

    def __init__(self, endpoint: str, timeout_s: float):
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.calls: list[tuple[str, object, object]] = []
        self.__class__.instances.append(self)

    def status(self):
        self.calls.append(("status", None, None))
        return 200, {
            "bootstrap": {"state": "bootstrap_ready"},
            "identity": {"device_id": DEVICE_ID},
            "runtime": {"state": "runtime_active"},
            "capabilities": {"runtime_deployment": True, "fpga_update": False},
        }

    def create_upload(self, token, body):
        self.calls.append(("create_upload", token, dict(body)))
        if token != VALID_TOKEN:
            return 401, {"ok": False, "error": "unauthorized"}
        return 409, {
            "ok": False,
            "error": "bootstrap_request_rejected",
            "message": "size must be an integer in range 1..536870912",
        }


def test_pairing_verifies_device_token_before_persisting(tmp_path: Path) -> None:
    FakeVerifiedBootstrapClient.instances.clear()
    credential_path = tmp_path / "credentials.json"
    store = BootstrapCredentialStore(credential_path)
    coordinator = VerifiedManagerBootstrapCoordinator(
        _registry(tmp_path),
        store,
        2.0,
        client_factory=FakeVerifiedBootstrapClient,
    )

    result = coordinator.pair("z2", VALID_TOKEN)

    assert result["pairing"]["paired"] is True
    assert result["pairing"]["device_verified"] is True
    assert store.token_for("z2", DEVICE_ID) == VALID_TOKEN
    probe = next(call for call in FakeVerifiedBootstrapClient.instances[0].calls if call[0] == "create_upload")
    assert probe[1] == VALID_TOKEN
    assert probe[2] == {"size": 0, "sha256": "0" * 64}


def test_wrong_pairing_token_fails_without_credential_state(tmp_path: Path) -> None:
    FakeVerifiedBootstrapClient.instances.clear()
    credential_path = tmp_path / "credentials.json"
    store = BootstrapCredentialStore(credential_path)
    coordinator = VerifiedManagerBootstrapCoordinator(
        _registry(tmp_path),
        store,
        2.0,
        client_factory=FakeVerifiedBootstrapClient,
    )

    with pytest.raises(BootstrapCredentialError, match="could not be verified"):
        coordinator.pair("z2", WRONG_TOKEN)

    assert store.paired("z2") is False
    assert not credential_path.exists()


def test_pair_probe_requires_exact_authenticated_validation_rejection(tmp_path: Path) -> None:
    class UnexpectedClient(FakeVerifiedBootstrapClient):
        def create_upload(self, token, body):
            self.calls.append(("create_upload", token, dict(body)))
            return 200, {"ok": True}

    store = BootstrapCredentialStore(tmp_path / "credentials.json")
    coordinator = VerifiedManagerBootstrapCoordinator(
        _registry(tmp_path),
        store,
        2.0,
        client_factory=UnexpectedClient,
    )

    with pytest.raises(BootstrapCredentialError, match="could not be verified"):
        coordinator.pair("z2", VALID_TOKEN)
    assert store.paired("z2") is False
