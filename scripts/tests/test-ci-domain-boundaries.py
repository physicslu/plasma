#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def require(text: str, needle: str, *, owner: str) -> None:
    if needle not in text:
        raise SystemExit(f"{owner}: required CI boundary token missing: {needle}")


def forbid(text: str, needle: str, *, owner: str) -> None:
    if needle in text:
        raise SystemExit(f"{owner}: forbidden cross-domain CI coupling present: {needle}")


def main() -> int:
    python_tests = read("python-tests.yml")
    ppu_release = read("ppu-release.yml")
    z2_release = read("z2-ps-release.yml")
    ai_support = read("ic-support-validation.yml")

    # Device Catalog owns user-selectable ICPN inventory. A data-only catalog
    # expansion must not fan out into the generic software or release domains.
    for token in (
        '"data/device-catalog/production/**"',
        '"data/device-catalog/research/*-commercial-icpn.csv"',
    ):
        forbid(python_tests, token, owner="Python/PL")
    forbid(ppu_release, '"data/device-catalog/production/**"', owner="PPU release")
    forbid(z2_release, '"data/device-catalog/production/**"', owner="Z2 release")

    # Preserve positive ownership so trigger cleanup cannot be satisfied by
    # accidentally deleting the workflows' real source boundaries.
    require(python_tests, '"software/python/**"', owner="Python/PL")
    require(python_tests, '"pl/rtl/**"', owner="Python/PL")
    require(ppu_release, '"scripts/ppu-release.py"', owner="PPU release")
    require(ppu_release, '"software/python/plasma_server/**"', owner="PPU release")
    require(z2_release, '"scripts/z2-python-runtime.py"', owner="Z2 release")
    require(z2_release, '"software/python/plasma_server/**"', owner="Z2 release")

    # AI IC Support is a manufacturer-evidence / programming-method research
    # domain. It may bind a precise benchmark catalog input, but it must not own
    # software runtime, OpenOCD execution or execution-admission validation.
    require(ai_support, "name: AI IC Support research validation", owner="AI IC Support")
    require(ai_support, '"data/ic-support/**"', owner="AI IC Support")
    require(
        ai_support,
        '"data/device-catalog/research/stm32f1-commercial-icpn.csv"',
        owner="AI IC Support",
    )

    forbidden_ai_tokens = (
        '"data/device-catalog/production/icpn-v1-manifest.json"',
        '"data/device-catalog/research/stm32f2-commercial-icpn.csv"',
        '"data/device-catalog/research/stm32f3-commercial-icpn.csv"',
        '"data/device-catalog/research/stm32f4-commercial-icpn.csv"',
        '"software/python/plasma_core/ic_support.py"',
        '"software/python/plasma_interfaces/openocd.py"',
        '"software/python/plasma_interfaces/openocd_plan.py"',
        '"software/python/plasma_interfaces/openocd_executor.py"',
        '"software/python/plasma_server/execution_router.py"',
        '"software/python/plasma_server/site_manager.py"',
        "python -m pip install -e software/python",
        "python -m plasma_core.ic_support --summary",
        "software/python/tests/test_ic_support_resolver.py",
        "software/python/tests/test_openocd_plan.py",
        "software/python/tests/test_openocd_executor.py",
        "software/python/tests/test_execution_router.py",
    )
    for token in forbidden_ai_tokens:
        forbid(ai_support, token, owner="AI IC Support")

    print("CI domain-boundary contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
