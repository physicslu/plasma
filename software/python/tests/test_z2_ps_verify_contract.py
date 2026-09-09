from __future__ import annotations

import json
import shlex
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
Z2_PS = REPO_ROOT / "scripts" / "plasmactl-z2-ps"


def test_z2_ps_verify_request_matches_current_loopback_contract() -> None:
    source = Z2_PS.read_text(encoding="utf-8")
    line = next(
        line.strip()
        for line in source.splitlines()
        if line.strip().startswith('loopback_request="')
    )
    assignment = shlex.split(line)[0]
    body = assignment.split("=", 1)[1].replace("$test_id", "z2-regression")
    request = json.loads(body)

    assert request == {
        "endpoint": "ps",
        "test_id": "z2-regression",
        "sequence": 1,
        "pattern": "zero",
        "seed": "",
        "payload_length": 1,
        "payload_base64": "AA==",
        "tx_crc32": "d202ef8d",
        "timeout_ms": 5000,
    }
    assert '-H "Idempotency-Key: $test_id"' in source


def test_z2_ps_verify_matches_current_readiness_contract() -> None:
    source = Z2_PS.read_text(encoding="utf-8")

    assert 'ready.get("gateway") != "alive"' in source
    assert 'ready.get("execution") != "ready"' in source
    assert 'ready.get("gateway") != "ready"' not in source


def test_z2_ps_verify_reads_nested_loopback_evidence() -> None:
    source = Z2_PS.read_text(encoding="utf-8")

    assert 'response = json.loads(sys.argv[2])' in source
    assert 'response.get("ok") is not True' in source
    assert 'loopback = response.get("loopback")' in source
    assert 'loopback.get("endpoint") != "ps"' in source
    assert 'loopback.get("source") != "ps"' in source
    assert 'loopback.get("tx_crc32") != "d202ef8d"' in source
    assert 'loopback.get("rx_crc32") != "d202ef8d"' in source
    assert 'response.get("payload_base64") != "AA=="' in source
