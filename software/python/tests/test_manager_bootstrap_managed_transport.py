from __future__ import annotations

from pathlib import Path

import pytest

from plasma_manager.bootstrap import (
    BootstrapCredentialStore,
    BootstrapHttpClient,
    BootstrapManagerError,
    MANAGED_BOOTSTRAP_PATH_PREFIX,
    MANAGED_BOOTSTRAP_RUNTIME_GATEWAY_HOST_ENV,
    MANAGED_BOOTSTRAP_TRANSPORT,
    MANAGED_BOOTSTRAP_TRANSPORT_ENV,
    ManagerBootstrapCoordinator,
    bootstrap_endpoint_for_gateway,
)
from plasma_manager.config import PPURegistryEntry
from plasma_manager.registry import PPURegistryStore


DEVICE_ID = "ppu-device-0123456789abcdef"
TOKEN = "t" * 40
MANAGED_ORIGIN = "https://ppu-managed-lab.example"


def _managed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MANAGED_BOOTSTRAP_TRANSPORT_ENV, MANAGED_BOOTSTRAP_TRANSPORT)


def _registry(tmp_path: Path) -> PPURegistryStore:
    return PPURegistryStore(
        (PPURegistryEntry(endpoint=MANAGED_ORIGIN, alias="z2like-qemu"),),
        tmp_path / "registry.json",
    )


def test_managed_transport_reuses_protected_https_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    assert bootstrap_endpoint_for_gateway(MANAGED_ORIGIN) == MANAGED_ORIGIN
    with pytest.raises(BootstrapManagerError, match="protected HTTPS"):
        bootstrap_endpoint_for_gateway("http://172.30.77.2:18080")


def test_unknown_managed_transport_policy_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(MANAGED_BOOTSTRAP_TRANSPORT_ENV, "future-unqualified-mode")
    with pytest.raises(BootstrapManagerError, match="unsupported Manager Bootstrap transport policy"):
        bootstrap_endpoint_for_gateway(MANAGED_ORIGIN)


class FakeRelay:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []

    def relay(self, method, path, *, headers, body, timeout_s, max_response_bytes):
        self.calls.append((method, path, dict(headers), body))
        return (
            200,
            {"Content-Type": "application/json"},
            b'{"bootstrap":{"state":"bootstrap_ready"},"identity":{"device_id":"ppu-device-0123456789abcdef"}}',
        )


def test_managed_http_client_projects_only_through_fixed_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    _managed(monkeypatch)
    client = BootstrapHttpClient(MANAGED_ORIGIN, 2.0)
    relay = FakeRelay()
    client.client = relay  # type: ignore[assignment]

    status, payload = client.status()

    assert status == 200
    assert payload["bootstrap"]["state"] == "bootstrap_ready"
    assert relay.calls == [
        (
            "GET",
            f"{MANAGED_BOOTSTRAP_PATH_PREFIX}/v1/status",
            {"Accept": "application/json"},
            None,
        )
    ]


class FakeBootstrapClient:
    instances: list["FakeBootstrapClient"] = []

    def __init__(self, endpoint: str, timeout_s: float):
        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.calls: list[tuple[str, str | None, dict[str, object] | None]] = []
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
        return 201, {"ok": True}

    def append_chunk(self, token, upload_id, body):
        self.calls.append(("append_chunk", token, {"upload_id": upload_id, **dict(body)}))
        return 200, {"ok": True}

    def commit_upload(self, token, upload_id):
        self.calls.append(("commit_upload", token, {"upload_id": upload_id}))
        return 200, {"ok": True}

    def start_deployment(self, token, body):
        self.calls.append(("start_deployment", token, dict(body)))
        return 202, {"ok": True, "deployment": {"state": "queued"}}


def test_managed_coordinator_keeps_public_reachability_separate_from_device_bind_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeBootstrapClient.instances.clear()
    _managed(monkeypatch)
    monkeypatch.setenv(MANAGED_BOOTSTRAP_RUNTIME_GATEWAY_HOST_ENV, "172.30.77.2")
    coordinator = ManagerBootstrapCoordinator(
        _registry(tmp_path),
        BootstrapCredentialStore(tmp_path / "bootstrap-credentials.json"),
        2.0,
        client_factory=FakeBootstrapClient,
    )

    before = coordinator.status("z2like-qemu")
    assert before["bootstrap_endpoint_policy"] == MANAGED_BOOTSTRAP_TRANSPORT
    assert FakeBootstrapClient.instances[-1].endpoint == MANAGED_ORIGIN

    coordinator.pair("z2like-qemu", TOKEN)
    status, _ = coordinator.start_deployment(
        "z2like-qemu",
        {
            "upload_id": "a" * 32,
            "ppu_id": "z2like-qemu-01",
            "facility_id": "swpc-simulation",
            "display_name": "SWPC QEMU ARMv7 Z2 Simulation",
        },
    )

    assert status == 202
    client = FakeBootstrapClient.instances[-1]
    assert client.endpoint == MANAGED_ORIGIN
    operation, token, body = client.calls[-1]
    assert operation == "start_deployment"
    assert token == TOKEN
    assert body is not None
    assert body["gateway_host"] == "172.30.77.2"


def test_managed_deployment_requires_manager_owned_private_runtime_gateway_host(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeBootstrapClient.instances.clear()
    _managed(monkeypatch)
    coordinator = ManagerBootstrapCoordinator(
        _registry(tmp_path),
        BootstrapCredentialStore(tmp_path / "bootstrap-credentials.json"),
        2.0,
        client_factory=FakeBootstrapClient,
    )
    coordinator.pair("z2like-qemu", TOKEN)

    for value in (None, "127.0.0.1", "0.0.0.0", "ppu-managed-lab.example"):
        if value is None:
            monkeypatch.delenv(MANAGED_BOOTSTRAP_RUNTIME_GATEWAY_HOST_ENV, raising=False)
        else:
            monkeypatch.setenv(MANAGED_BOOTSTRAP_RUNTIME_GATEWAY_HOST_ENV, value)
        with pytest.raises(BootstrapManagerError, match="runtime Gateway host"):
            coordinator.start_deployment(
                "z2like-qemu",
                {
                    "upload_id": "a" * 32,
                    "ppu_id": "z2like-qemu-01",
                    "facility_id": "swpc-simulation",
                    "display_name": "SWPC QEMU ARMv7 Z2 Simulation",
                },
            )
