"""Console B3 body (``installManagerPpuBundle``) is accepted by the Manager.

The Console sends ``mode: "activate"`` for both of its B3 buttons ("Install
Only" = activate without FPGA load, "Install and Load FPGA" = activate with
FPGA load), which is the PPU default the Console relied on before ``mode``
became mandatory. The exact key set is locked against the TypeScript source by
``software/web/tests/ppu-generic-bundle-pr3-contract.test.mjs``.
"""
from __future__ import annotations

import pytest

from plasma_manager.bootstrap import BootstrapManagerError, ManagerBootstrapCoordinator

UPLOAD = "a" * 32
DIGEST = "b" * 64
ADMISSION = "c" * 32
DEVICE = "ppu-device-" + "0" * 32


def console_b3_body(fpga_load: bool) -> dict:
    # Mirrors software/web/app/engineering/ppu-bootstrap-api.ts installManagerPpuBundle.
    return {"kind": "bundle", "upload_id": UPLOAD, "archive_sha256": DIGEST,
            "admission_transaction_id": ADMISSION, "mode": "activate",
            "fpga_load": fpga_load}


class FakeBootstrapClient:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def start_deployment(self, token: str, body: dict):
        self.sent.append(body)
        authorization = body["authorization"]
        return 202, {"ok": True, "deployment": {
            "upload_id": body["upload_id"], "state": "queued",
            "admission_transaction_id": ADMISSION, "mode": body["mode"],
            "fpga_load": body["fpga_load"],
            "owner_authorization": {"status": "OWNER_AUTHORIZED",
                                    "action": authorization["action"],
                                    "subject_sha256": DIGEST},
        }}


def coordinator(client: FakeBootstrapClient) -> ManagerBootstrapCoordinator:
    instance = ManagerBootstrapCoordinator(None, None, 1.0)
    instance._authenticated = lambda alias: (alias, None, client, {}, DEVICE, "t" * 43)
    return instance


@pytest.mark.parametrize(("fpga_load", "action"), [
    (False, "bundle.activate"),
    (True, "bundle.activate-fpga-load"),
])
def test_console_b3_body_is_accepted_and_forwards_activate_mode(fpga_load, action):
    client = FakeBootstrapClient()
    status, response = coordinator(client).start_deployment("z2", console_b3_body(fpga_load))
    assert status == 202 and response["ok"] is True
    (sent,) = client.sent
    assert set(sent) == {"kind", "upload_id", "mode", "fpga_load", "authorization"}
    assert sent["mode"] == "activate" and sent["fpga_load"] is fpga_load
    assert sent["authorization"]["action"] == action


def test_console_b3_body_without_mode_is_still_rejected():
    body = console_b3_body(False)
    del body["mode"]
    client = FakeBootstrapClient()
    with pytest.raises(BootstrapManagerError, match="mode and fpga_load"):
        coordinator(client).start_deployment("z2", body)
    assert client.sent == []
