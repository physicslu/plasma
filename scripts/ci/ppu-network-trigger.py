#!/usr/bin/env python3
"""Route PPU release changes to the heavy PPU network qualification gates.

The PPU release workflow owns two different risks:

1. packaging / ARMv7 runtime integrity; and
2. network commissioning / Static IPv4 behavior.

A change in the packaged PPU payload may require (1) without plausibly changing
(2). In particular, ADR-0002 OpenOCD software-qualification projection is part
of plasma_web and therefore changes the PPU payload, but it must not force the
Static IPv4 fault-injection/repeatability suite.

Input is a newline-separated changed-file list on stdin. Output is exactly
"true" or "false" for workflow consumption.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable


NETWORK_EXACT = frozenset(
    {
        ".github/workflows/ppu-release.yml",
        ".github/workflows/persistent-integration-host.yml",
        "scripts/ppu-runtime.py",
        "scripts/ppu-release.py",
        "scripts/ppu-network-phase1-acceptance.py",
        "scripts/ppu-network-phase2-acceptance.py",
        "scripts/virtual-ppu-network-lab.py",
        "scripts/static-ipv4-fault-injection-lab.py",
        "scripts/static-ipv4-fault-injection-repeatability.py",
        "scripts/private-ppu-evidence-verifier.py",
        "scripts/ci-environment-fingerprint.py",
        "scripts/static-ipv4-fault-helper.py",
        "scripts/manager-network-commissioning-crash-injector.py",
        "software/python/pyproject.toml",
        "software/python/plasma_web/gateway.py",
        "software/python/plasma_web/gateway_base.py",
        "software/python/plasma_web/gateway_runner.py",
        "software/python/plasma_web/gateway_phase2.py",
        "software/python/plasma_web/gateway_phase3.py",
        "software/python/plasma_web/ppu_network_settings.py",
        "software/python/plasma_web/ppu_network_activation.py",
        "software/python/plasma_web/secure_gateway.py",
        "software/python/plasma_web/secure_gateway_app.py",
        "software/python/plasma_web/gateway_security.py",
        "software/python/tests/test_ppu_network_phase1_acceptance.py",
        "software/python/tests/test_ppu_network_phase2_bootstrap.py",
        "software/python/tests/test_ppu_network_activation.py",
        "software/python/tests/test_ppu_network_activation_rest.py",
        "software/python/tests/test_ppu_network_activation_security.py",
        "software/python/tests/test_ppu_network_settings.py",
        "software/python/tests/test_ppu_network_settings_rest.py",
        "software/python/tests/test_ppu_network_settings_security.py",
        "software/python/tests/test_manager_network_commissioning.py",
        "software/python/tests/test_manager_network_commissioning_rest.py",
        "software/python/tests/test_virtual_ppu_network_lab.py",
        "software/python/tests/test_static_ipv4_fault_injection_lab.py",
        "software/python/tests/test_persistent_integration_host_security.py",
        "software/python/tests/test_manager_ps_only_topology.py",
    }
)

NETWORK_PREFIXES = (
    "software/python/plasma_core/",
    "software/python/plasma_interfaces/",
    "software/python/plasma_handlers/",
    "software/python/plasma_server/",
    "software/python/plasma_manager/",
)


def requires_network_qualification(paths: Iterable[str]) -> bool:
    for raw in paths:
        path = raw.strip()
        if not path:
            continue
        if path in NETWORK_EXACT:
            return True
        if any(path.startswith(prefix) for prefix in NETWORK_PREFIXES):
            return True
    return False


def self_test() -> None:
    positives = (
        ".github/workflows/ppu-release.yml",
        "scripts/ppu-runtime.py",
        "scripts/static-ipv4-fault-injection-repeatability.py",
        "software/python/plasma_manager/network_commissioning.py",
        "software/python/plasma_web/ppu_network_activation.py",
        "software/python/plasma_web/gateway_phase2.py",
        "software/python/plasma_core/errors.py",
        "software/python/tests/test_static_ipv4_fault_injection_lab.py",
    )
    negatives = (
        "release/openocd-qualification/openocd-0.12.0-stm32f103-v6.json",
        "release/openocd.json",
        "software/python/plasma_web/openocd_software_qualification.py",
        "software/python/tests/test_openocd_software_qualification_v1.py",
        "data/ic-support/profiles/programming/stm32f1-high-density-flash-v0.json",
        "data/device-catalog/research/stm32f1-commercial-icpn.csv",
        "docs/architecture/openocd-software-qualification-v6.md",
    )

    for path in positives:
        assert requires_network_qualification([path]), path
    for path in negatives:
        assert not requires_network_qualification([path]), path
    assert requires_network_qualification([negatives[0], positives[2]])
    assert not requires_network_qualification(negatives)
    print("PPU network heavy-gate trigger self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0

    changed = [line.strip() for line in sys.stdin if line.strip()]
    print("true" if requires_network_qualification(changed) else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
