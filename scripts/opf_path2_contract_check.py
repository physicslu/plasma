#!/usr/bin/env python3
"""Path 2 CPU-only, source-pinned OPF-1 contract acceptance.

No network, external processes, installer, FPGA, Z2, DUT or file writes.
Designed for the existing Issue #981 / SWPC bwrap Python -I -S runner.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software" / "python"))

from plasma_opf import (  # noqa: E402
    OPF_PROGRAMMING_SCHEMA,
    OpfContractError,
    TimeoutPolicy,
    parse_programming_selection,
)


def descriptor(**changes: object) -> dict:
    value = {
        "schema": OPF_PROGRAMMING_SCHEMA,
        "provider": "external-provider",
        "profile": "new-mcu-profile",
    }
    value.update(changes)
    return value


def denied(value: dict, policy: TimeoutPolicy, code: str) -> None:
    try:
        parse_programming_selection(value, policy=policy)
    except OpfContractError as exc:
        assert exc.code == code, (exc.code, code)
    else:
        raise AssertionError("invalid descriptor was accepted: " + code)


def main() -> int:
    policy = TimeoutPolicy(default_timeout_ms=60000, maximum_timeout_ms=3600000)
    count = 0

    p = parse_programming_selection(descriptor(), policy=policy)
    assert (p.timeout_ms, p.timeout_source) == (60000, "ppu_default")
    count += 1

    p = parse_programming_selection(
        descriptor(timeout_ms=1200000, options={"custom_bus": [1, "spi", True]}),
        policy=policy,
    )
    assert p.timeout_ms == 1200000 and p.timeout_source == "bundle_override"
    assert p.options["custom_bus"] == [1, "spi", True]
    count += 1

    denied(descriptor(timeout_ms=0), policy, "TIMEOUT_INVALID")
    count += 1

    denied(descriptor(timeout_ms=3600001), policy, "TIMEOUT_EXCEEDS_PPU_POLICY")
    count += 1

    denied(descriptor(options={"non_json": {1, 2}}), policy, "OPTIONS_NON_JSON_VALUE")
    count += 1

    denied(descriptor(provider="../legacy"), policy, "PROVIDER_REF_INVALID")
    count += 1

    assert (ROOT / "docs/architecture/opf-architecture.md").is_file()
    assert '"plasma_opf"' in (ROOT / "software/python/pyproject.toml").read_text()
    count += 1

    print(f"OPF_PATH2_CONTRACT_SMOKE_PASS cases={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
