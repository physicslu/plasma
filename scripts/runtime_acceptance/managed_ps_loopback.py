from __future__ import annotations

import base64

from common import AcceptanceError, Client

SCENARIO = "ps-loopback"


def run(client: Client) -> dict:
    payload = b"\x00"
    status, response = client.request(
        "POST",
        "/api/diagnostics/loopback",
        json_body={
            "endpoint": "ps",
            "test_id": f"runtime-acceptance-{client._run_id}",
            "sequence": 1,
            "pattern": "zero",
            "payload_base64": base64.b64encode(payload).decode("ascii"),
        },
        headers={"Idempotency-Key": client.idem("ps-loopback")},
    )
    if status != 200 or response.get("ok") is not True:
        raise AcceptanceError("managed PS Loopback request failed")
    loopback = response.get("loopback") or {}
    manager = response.get("manager") or {}
    if loopback.get("endpoint") != "ps" or loopback.get("source") != "ps":
        raise AcceptanceError("PS Loopback response did not originate from PS endpoint")
    if loopback.get("tx_crc32") != loopback.get("rx_crc32"):
        raise AcceptanceError("PS Loopback CRC mismatch")
    if response.get("payload_base64") != base64.b64encode(payload).decode("ascii"):
        raise AcceptanceError("PS Loopback payload mismatch")
    if manager.get("relay") != "pass-through" or not manager.get("ppu_alias"):
        raise AcceptanceError("Manager relay evidence is missing")
    return {
        "result": "PASS",
        "endpoint": "ps",
        "ppu_alias": manager["ppu_alias"],
        "manager_rtt_ms": manager.get("manager_rtt_ms"),
        "ppu_rtt_ms": loopback.get("ppu_rtt_ms"),
        "tx_crc32": loopback.get("tx_crc32"),
        "rx_crc32": loopback.get("rx_crc32"),
    }
