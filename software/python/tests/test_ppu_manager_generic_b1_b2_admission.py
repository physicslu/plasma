"""PR1224 Manager-only physical B1/B2 admission contract. Pure host-only."""
from __future__ import annotations

from pathlib import Path

import pytest

from plasma_manager.bootstrap import (
    BootstrapCredentialStore, BootstrapManagerError, ManagerBootstrapCoordinator,
)
from .test_manager_bootstrap import _registry, DEVICE_ID, TOKEN, FakeBootstrapClient


class AllGenericAdmissionClient(FakeBootstrapClient):
    def start_deployment(self, token, body):
        self.calls.append(("start_deployment", token, dict(body)))
        return 200, {"ok": True, "deployment": {
            "transaction_id": "a" * 32,
            "state": "admitted",
            "result": {
                "result": "PASS", "stage": "package_admission_only",
                "install_qualified": False,
                "plan": {"kind": body["kind"], "execution_permitted": False},
            },
        }}


def _co(tmp_path: Path, client=AllGenericAdmissionClient):
    credentials = BootstrapCredentialStore(tmp_path / "bootstrap-credentials.json")
    credentials.set("z2", DEVICE_ID, TOKEN)
    return ManagerBootstrapCoordinator(
        _registry(tmp_path), credentials, 2.0, client_factory=client,
    )


@pytest.mark.parametrize("kind", ["python", "native-c", "fpga-image", "bundle"])
def test_all_generic_kinds_share_preexisting_authenticated_nonexecuting_route(tmp_path, kind):
    AllGenericAdmissionClient.instances.clear()
    status, receipt = _co(tmp_path).start_deployment(
        "z2", {"kind": kind, "upload_id": "b" * 32},
    )
    assert status == 200
    assert receipt["deployment"]["state"] == "admitted"
    assert receipt["deployment"]["result"]["plan"]["execution_permitted"] is False
    assert AllGenericAdmissionClient.instances[-1].calls[-1] == (
        "start_deployment", TOKEN, {"kind": kind, "upload_id": "b" * 32},
    )
    assert "gateway_host" not in AllGenericAdmissionClient.instances[-1].calls[-1][2]


@pytest.mark.parametrize("extra", [
    {"activate": True}, {"publisher": "forged"},
    {"gateway_host": "evil"}, {"master_generation": 8},
])
def test_generic_caller_cannot_smuggle_install_authority(tmp_path, extra):
    co = _co(tmp_path)
    with pytest.raises(BootstrapManagerError, match="requires only kind and upload_id"):
        co.start_deployment("z2", {
            "kind": "python", "upload_id": "b" * 32, **extra,
        })


def test_unknown_package_kind_does_not_disguise_as_generic(tmp_path):
    co = _co(tmp_path)
    with pytest.raises(BootstrapManagerError):
        co.start_deployment("z2", {"kind": "engineering-module", "upload_id": "b" * 32})


def test_unpaired_manager_denies_before_sending_bootstrap_token(tmp_path):
    credentials = BootstrapCredentialStore(tmp_path / "unpaired.json")
    co = ManagerBootstrapCoordinator(
        _registry(tmp_path), credentials, 2.0,
        client_factory=AllGenericAdmissionClient,
    )
    with pytest.raises(BootstrapManagerError, match="not paired"):
        co.start_deployment("z2", {"kind": "bundle", "upload_id": "b" * 32})
