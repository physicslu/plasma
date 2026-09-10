from __future__ import annotations

import json
from pathlib import Path

import pytest

from plasma_manager.bootstrap import (
    BootstrapCredentialError,
    BootstrapCredentialStore,
    BootstrapManagerError,
    ManagerBootstrapCoordinator,
    bootstrap_endpoint_for_gateway,
)
from plasma_manager.config import PPURegistryEntry
from plasma_manager.registry import PPURegistryStore

DEVICE_ID = "ppu-device-0123456789abcdef"
TOKEN = "t" * 40


def _registry(tmp_path: Path):
    return PPURegistryStore(
        (PPURegistryEntry(endpoint="http://192.168.2.99:18080", alias="z2"),),
        tmp_path / "registry.json",
    )


def test_bootstrap_endpoint_is_derived_without_changing_gateway_registry_semantics():
    assert bootstrap_endpoint_for_gateway("http://192.168.2.99:18080") == "http://192.168.2.99:18081"
    assert bootstrap_endpoint_for_gateway("http://ppu-a.local:18080") == "http://ppu-a.local:18081"
    with pytest.raises(BootstrapManagerError, match="private HTTP"):
        bootstrap_endpoint_for_gateway("https://ppu-a.example:18080")


def test_credentials_are_separate_0600_state_and_never_exposed(tmp_path: Path):
    path = tmp_path / "bootstrap-credentials.json"
    store = BootstrapCredentialStore(path)
    store.set("z2", DEVICE_ID, TOKEN)

    assert path.stat().st_mode & 0o777 == 0o600
    assert store.token_for("z2", DEVICE_ID) == TOKEN
    state = store.public_state("z2")
    assert state["paired"] is True
    assert state["device_id"] == DEVICE_ID
    assert "token" not in state

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["credentials"]["z2"]["device_id"] == DEVICE_ID
    assert on_disk["credentials"]["z2"]["token"] == TOKEN

    loaded = BootstrapCredentialStore(path)
    assert loaded.token_for("z2", DEVICE_ID) == TOKEN
    loaded.remove("z2")
    assert loaded.public_state("z2")["paired"] is False


def test_device_bound_credential_rejects_alias_reuse_for_another_appliance(tmp_path: Path):
    store = BootstrapCredentialStore(tmp_path / "bootstrap-credentials.json")
    store.set("z2", DEVICE_ID, TOKEN)
    with pytest.raises(BootstrapCredentialError, match="different Bootstrap device_id"):
        store.token_for("z2", "ppu-device-fedcba9876543210")


def test_insecure_credential_permissions_fail_closed(tmp_path: Path):
    path = tmp_path / "bootstrap-credentials.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "credentials": {
                    "z2": {
                        "device_id": DEVICE_ID,
                        "token": TOKEN,
                        "updated_at": "now",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    path.chmod(0o644)
    with pytest.raises(BootstrapCredentialError, match="0600"):
        BootstrapCredentialStore(path)


def test_credential_store_requires_manager_runtime_state_for_persistence():
    store = BootstrapCredentialStore(None)
    with pytest.raises(BootstrapCredentialError, match="persistence is disabled"):
        store.set("z2", DEVICE_ID, TOKEN)


class FakeBootstrapClient:
    instances = []

    def __init__(self, endpoint: str, timeout_s: float):
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.calls = []
        self.__class__.instances.append(self)

    def status(self):
        self.calls.append(("status", None, None))
        return 200, {
            "bootstrap": {"state": "bootstrap_ready"},
            "identity": {"device_id": DEVICE_ID},
            "runtime": {"state": "runtime_absent"},
            "capabilities": {"runtime_deployment": True, "fpga_update": False},
        }

    def create_upload(self, token, body):
        self.calls.append(("create_upload", token, dict(body)))
        return 201, {"ok": True, "upload": {"upload_id": "a" * 32}}

    def append_chunk(self, token, upload_id, body):
        self.calls.append(("append_chunk", token, {"upload_id": upload_id, **dict(body)}))
        return 200, {"ok": True}

    def commit_upload(self, token, upload_id):
        self.calls.append(("commit_upload", token, {"upload_id": upload_id}))
        return 200, {"ok": True}

    def start_deployment(self, token, body):
        self.calls.append(("start_deployment", token, dict(body)))
        return 202, {"ok": True, "deployment": {"state": "queued"}}


def test_manager_owns_bootstrap_target_and_secret_after_pairing(tmp_path: Path):
    FakeBootstrapClient.instances.clear()
    registry = _registry(tmp_path)
    credentials = BootstrapCredentialStore(tmp_path / "credentials.json")
    coordinator = ManagerBootstrapCoordinator(
        registry,
        credentials,
        2.0,
        client_factory=FakeBootstrapClient,
    )

    before = coordinator.status("z2")
    assert before["ppu_alias"] == "z2"
    assert before["pairing"]["paired"] is False
    assert before["pairing"]["device_match"] is True
    assert before["bootstrap_endpoint_policy"] == "same-host:18081"
    assert FakeBootstrapClient.instances[-1].endpoint == "http://192.168.2.99:18081"

    paired = coordinator.pair("z2", TOKEN)
    assert paired["pairing"]["paired"] is True
    assert paired["pairing"]["device_id"] == DEVICE_ID
    assert paired["token_verification"] == "deferred_until_authenticated_operation"
    assert TOKEN not in json.dumps(paired)

    status, _ = coordinator.create_upload("z2", {"size": 123, "sha256": "0" * 64})
    assert status == 201
    call = FakeBootstrapClient.instances[-1].calls[-1]
    assert call[0] == "create_upload"
    assert call[1] == TOKEN


def test_unpaired_mutation_fails_before_authenticated_ppu_request(tmp_path: Path):
    FakeBootstrapClient.instances.clear()
    coordinator = ManagerBootstrapCoordinator(
        _registry(tmp_path),
        BootstrapCredentialStore(tmp_path / "credentials.json"),
        2.0,
        client_factory=FakeBootstrapClient,
    )
    with pytest.raises(BootstrapCredentialError, match="not paired"):
        coordinator.create_upload("z2", {"size": 1, "sha256": "0" * 64})
    assert FakeBootstrapClient.instances[-1].calls == [("status", None, None)]
