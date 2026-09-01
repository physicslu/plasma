from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-armv7-runtime-acceptance.py"
SPEC = importlib.util.spec_from_file_location("ppu_armv7_runtime_acceptance", SCRIPT)
assert SPEC and SPEC.loader
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


def test_armv7_acceptance_requires_armv7_userspace() -> None:
    assert acceptance._validate_architecture("armv7l") == "armv7l"
    assert acceptance._validate_architecture("ARMV7") == "armv7"
    with pytest.raises(acceptance.ARMv7AcceptanceError, match="not executing as ARMv7"):
        acceptance._validate_architecture("x86_64")


def test_armv7_acceptance_requires_python_311_or_newer() -> None:
    assert acceptance._validate_python((3, 11, 0)) == "3.11.0"
    assert acceptance._validate_python((3, 12, 7)) == "3.12.7"
    with pytest.raises(acceptance.ARMv7AcceptanceError, match="required 3.11"):
        acceptance._validate_python((3, 10, 14))


def test_armv7_loopback_validation_requires_real_ps_evidence() -> None:
    encoded = "AA=="
    crc32 = "d202ef8d"
    loopback = acceptance._validate_loopback_response(
        status=200,
        response={
            "ok": True,
            "loopback": {
                "endpoint": "ps",
                "source": "ps",
                "tx_crc32": crc32,
                "rx_crc32": crc32,
            },
            "payload_base64": encoded,
        },
        encoded=encoded,
        crc32=crc32,
    )
    assert loopback["source"] == "ps"

    with pytest.raises(acceptance.ARMv7AcceptanceError, match="did not originate from PS"):
        acceptance._validate_loopback_response(
            status=200,
            response={
                "ok": True,
                "loopback": {
                    "endpoint": "ps",
                    "source": "mock",
                    "tx_crc32": crc32,
                    "rx_crc32": crc32,
                },
                "payload_base64": encoded,
            },
            encoded=encoded,
            crc32=crc32,
        )
