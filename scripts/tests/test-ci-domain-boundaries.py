#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
REGISTRY = ROOT / ".github" / "ci-workstreams.json"


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def read_repo(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, needle: str, *, owner: str) -> None:
    if needle not in text:
        raise SystemExit(f"{owner}: required CI boundary token missing: {needle}")


def require_count(text: str, needle: str, count: int, *, owner: str) -> None:
    actual = text.count(needle)
    if actual != count:
        raise SystemExit(
            f"{owner}: required CI boundary token count drift: {needle}; "
            f"expected {count}, got {actual}"
        )


def forbid(text: str, needle: str, *, owner: str) -> None:
    if needle in text:
        raise SystemExit(f"{owner}: forbidden cross-domain CI coupling present: {needle}")


def validate_workstream_registry() -> None:
    payload = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("status") != "current":
        raise SystemExit("CI workstream registry must be schema_version=1 and status=current")

    workstreams = payload.get("workstreams")
    if not isinstance(workstreams, dict):
        raise SystemExit("CI workstream registry workstreams must be an object")

    expected_keys = {"sw_ppu", "icpn", "ai_ic_support", "repo"}
    if set(workstreams) != expected_keys:
        raise SystemExit(
            f"CI workstream registry must contain exactly {sorted(expected_keys)}; "
            f"got {sorted(workstreams)}"
        )

    expected_labels = {
        "sw_ppu": "SW/PPU",
        "icpn": "ICPN",
        "ai_ic_support": "AI IC Support",
        "repo": "REPO",
    }
    seen_workflows: dict[str, str] = {}
    for key, expected_label in expected_labels.items():
        item = workstreams[key]
        if item.get("label") != expected_label:
            raise SystemExit(
                f"CI workstream {key} label drift: expected {expected_label!r}, "
                f"got {item.get('label')!r}"
            )
        workflows = item.get("core_workflows")
        if not isinstance(workflows, list) or not workflows:
            raise SystemExit(f"CI workstream {key} must own at least one core workflow")
        for workflow in workflows:
            if not isinstance(workflow, str) or not workflow.startswith(".github/workflows/"):
                raise SystemExit(f"CI workstream {key} has invalid workflow path: {workflow!r}")
            path = ROOT / workflow
            if not path.is_file():
                raise SystemExit(f"CI workstream {key} references missing workflow: {workflow}")
            previous = seen_workflows.get(workflow)
            if previous is not None:
                raise SystemExit(
                    f"workflow {workflow} has multiple primary workstreams: {previous}, {key}"
                )
            seen_workflows[workflow] = key

    required_core_ownership = {
        ".github/workflows/python-tests.yml": "sw_ppu",
        ".github/workflows/ppu-release.yml": "sw_ppu",
        ".github/workflows/z2-ps-release.yml": "sw_ppu",
        ".github/workflows/device-catalog-validation.yml": "icpn",
        ".github/workflows/device-catalog-current-validation.yml": "icpn",
        ".github/workflows/ic-support-validation.yml": "ai_ic_support",
        ".github/workflows/ic-evidence-live-validation.yml": "ai_ic_support",
        ".github/workflows/repository-contracts.yml": "repo",
    }
    for workflow, expected_owner in required_core_ownership.items():
        actual_owner = seen_workflows.get(workflow)
        if actual_owner != expected_owner:
            raise SystemExit(
                f"workflow {workflow} ownership drift: expected {expected_owner}, got {actual_owner}"
            )

    invariants = payload.get("invariants")
    if not isinstance(invariants, dict) or not invariants:
        raise SystemExit("CI workstream registry invariants must be a non-empty object")
    false_invariants = sorted(key for key, value in invariants.items() if value is not True)
    if false_invariants:
        raise SystemExit(f"CI workstream registry has non-true invariants: {false_invariants}")


def main() -> int:
    validate_workstream_registry()

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
        forbid(python_tests, token, owner="SW/PPU Python/PL")
    forbid(ppu_release, '"data/device-catalog/production/**"', owner="SW/PPU PPU release")
    forbid(z2_release, '"data/device-catalog/production/**"', owner="SW/PPU Z2 release")

    # REPO governance tests are not SW/PPU source tests.
    require_count(
        python_tests,
        '"!scripts/tests/test-ci-domain-boundaries.py"',
        2,
        owner="SW/PPU Python/PL",
    )

    # Preserve positive SW/PPU ownership.
    require(python_tests, '"software/python/**"', owner="SW/PPU Python/PL")
    require(python_tests, '"pl/rtl/**"', owner="SW/PPU Python/PL")
    require(ppu_release, '"scripts/ppu-release.py"', owner="SW/PPU PPU release")
    require(ppu_release, '"software/python/plasma_server/**"', owner="SW/PPU PPU release")
    require(z2_release, '"scripts/z2-python-runtime.py"', owner="SW/PPU Z2 release")
    require(z2_release, '"software/python/plasma_server/**"', owner="SW/PPU Z2 release")

    # AI IC Support is manufacturer-evidence / programming-method research.
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

    # Lock the code-level promotion boundary as well as CI trigger ownership.
    # SW/PPU runtime may only consume a caller-selected, runtime-owned capability
    # source. Research under data/ic-support/ cannot be an implicit default.
    runtime_resolver = read_repo("software/python/plasma_core/ic_support.py")
    site_manager = read_repo("software/python/plasma_server/site_manager.py")
    for token in (
        "data/ic-support",
        "PLASMA_IC_SUPPORT_ROOT",
        "IC_SUPPORT_RELATIVE_ROOT",
        "def default_ic_support_root",
        "def get_default_ic_support_resolver",
    ):
        forbid(runtime_resolver, token, owner="SW/PPU runtime capability")
    forbid(
        site_manager,
        "get_default_ic_support_resolver",
        owner="SW/PPU SiteManager capability injection",
    )
    require(
        site_manager,
        "self.ic_support_resolver = ic_support_resolver",
        owner="SW/PPU SiteManager capability injection",
    )

    print("CI workstream/domain-boundary contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
