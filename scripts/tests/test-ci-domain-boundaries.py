#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
REGISTRY = ROOT / ".github" / "ci-workstreams.json"


def read(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


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
        ".github/workflows/z2like-demo-qemu.yml": "sw_ppu",
        ".github/workflows/persistent-integration-host.yml": "sw_ppu",
        ".github/workflows/openocd-software-qualification.yml": "sw_ppu",
        ".github/workflows/device-catalog-validation.yml": "icpn",
        ".github/workflows/device-catalog-current-validation.yml": "icpn",
        ".github/workflows/device-catalog-stm32-family-validation.yml": "icpn",
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



def validate_catalog_family_trigger_parity() -> None:
    """Fail closed when the shared STM32 dispatcher silently omits U0 or stale YAML paths."""
    workflow = read("device-catalog-stm32-family-validation.yml")
    required = {
        "data/device-catalog/research/*stm32u0*",
        "data/device-catalog/research/evidence/stm32u0*/**",
        ".github/workflows/device-catalog-stm32c0-c05-publication-validation.yml",
    }
    event_paths: dict[str, set[str]] = {}
    current_event: str | None = None
    in_paths = False
    for line in workflow.splitlines():
        if line in ("  push:", "  pull_request:"):
            current_event = line.strip().rstrip(":")
            event_paths[current_event] = set()
            in_paths = False
        elif current_event and line.startswith("  ") and not line.startswith("    ") and line.strip():
            current_event = None
            in_paths = False
        elif current_event and line == "    paths:":
            in_paths = True
        elif current_event and in_paths and line.startswith("      - "):
            event_paths[current_event].add(line[8:].strip().strip("'\\\""))

    for event in ("push", "pull_request"):
        paths = event_paths.get(event)
        if paths is None:
            raise SystemExit(f"STM32 family dispatcher missing {event} paths")
        missing = required - paths
        if missing:
            raise SystemExit(f"{event}: STM32 dispatcher trigger parity missing: {sorted(missing)}")
        for path in paths:
            if path.startswith(".github/workflows/") and not (ROOT / path).is_file():
                raise SystemExit(f"{event}: stale workflow trigger reference: {path}")
        if any(path.startswith("data/device-catalog/production/") for path in paths):
            raise SystemExit(f"{event}: forbidden Production trigger in family dispatcher")
    if event_paths["push"] != event_paths["pull_request"]:
        raise SystemExit("STM32 family dispatcher PR/main trigger parity drift")

    u5 = read("device-catalog-stm32u5-catalog-runtime-governance-correction-validation.yml")
    if ".github/workflows/device-catalog-stm32u5-hil-observer-debug-readiness-validation.yml" in u5:
        raise SystemExit("STM32U5 governance trigger still refers to a missing workflow")

def main() -> int:
    validate_catalog_family_trigger_parity()
    validate_workstream_registry()

    python_tests = read("python-tests.yml")
    repository_contracts = read("repository-contracts.yml")
    ppu_release = read("ppu-release.yml")
    z2_release = read("z2-ps-release.yml")
    z2like_qemu = read("z2like-demo-qemu.yml")
    ai_support = read("ic-support-validation.yml")
    openocd_qualification = read("openocd-software-qualification.yml")
    ppu_network_trigger = (ROOT / "scripts/ci/ppu-network-trigger.py").read_text(encoding="utf-8")

    # Device Catalog owns user-selectable ICPN inventory. A data-only catalog
    # expansion must not fan out into the generic software or release domains.
    for token in (
        '"data/device-catalog/production/**"',
        '"data/device-catalog/research/*-commercial-icpn.csv"',
    ):
        forbid(python_tests, token, owner="SW/PPU Python/PL")
    forbid(ppu_release, '"data/device-catalog/production/**"', owner="SW/PPU PPU release")
    forbid(z2_release, '"data/device-catalog/production/**"', owner="SW/PPU Z2 release")
    for token in (
        '"data/device-catalog/production/**"',
        '"data/device-catalog/research/*-commercial-icpn.csv"',
    ):
        forbid(z2like_qemu, token, owner="SW/PPU QEMU acceptance")

    # QEMU acceptance still owns executable Gateway/runtime changes, but catalog-only
    # modules are an explicit narrow cross-workstream exclusion. Keep both push and
    # pull_request filters aligned so IC Selector evidence updates do not compile ARMv7.
    require_count(
        z2like_qemu,
        '"software/python/plasma_web/**"',
        2,
        owner="SW/PPU QEMU acceptance",
    )
    for token in (
        '"!software/python/plasma_web/device_catalog.py"',
        '"!software/python/plasma_web/*_manufacturer_device_evidence.py"',
    ):
        require_count(z2like_qemu, token, 2, owner="SW/PPU QEMU acceptance")
    require_count(
        repository_contracts,
        '".github/workflows/z2like-demo-qemu.yml"',
        3,
        owner="REPO QEMU CI-boundary governance",
    )

    # REPO governance tests are not SW/PPU source tests. Because python-tests
    # still owns the broad scripts/tests/** software-helper surface, explicitly
    # exclude this repository-boundary guard on both push and pull_request.
    require_count(
        python_tests,
        '"!scripts/tests/test-ci-domain-boundaries.py"',
        2,
        owner="SW/PPU Python/PL",
    )

    # Persistent L4 workflow policy is part of PPU qualification, not the
    # generic Python source-test trigger surface. Keep its dedicated security
    # test and workflow path bound to the PPU release gate, and route workflow
    # changes through repository CI-boundary governance as well.
    require(
        ppu_release,
        '".github/workflows/persistent-integration-host.yml"',
        owner="SW/PPU persistent L4 qualification",
    )
    require(
        ppu_release,
        "software/python/tests/test_persistent_integration_host_security.py",
        owner="SW/PPU persistent L4 qualification",
    )
    require_count(
        repository_contracts,
        '".github/workflows/persistent-integration-host.yml"',
        3,
        owner="REPO persistent L4 governance",
    )

    # Preserve positive ownership so trigger cleanup cannot be satisfied by
    # accidentally deleting the workflows' real source boundaries.
    require(python_tests, '"software/python/**"', owner="SW/PPU Python/PL")
    require(python_tests, '"pl/rtl/**"', owner="SW/PPU Python/PL")
    require(ppu_release, '"scripts/ppu-release.py"', owner="SW/PPU PPU release")
    require(ppu_release, '"scripts/ci/ppu-network-trigger.py"', owner="SW/PPU PPU network routing")
    require(ppu_release, "route-ppu-network:", owner="SW/PPU PPU network routing")
    require_count(
        ppu_release,
        "if: needs.route-ppu-network.outputs.network_changed == 'true'",
        4,
        owner="SW/PPU PPU network routing",
    )
    require(
        ppu_network_trigger,
        '"software/python/plasma_web/openocd_software_qualification.py"',
        owner="SW/PPU PPU network routing self-test",
    )
    require(
        ppu_network_trigger,
        '"release/openocd-qualification/openocd-0.12.0-stm32f103-v6.json"',
        owner="SW/PPU PPU network routing self-test",
    )
    require(
        ppu_network_trigger,
        '"software/python/plasma_web/ppu_network_activation.py"',
        owner="SW/PPU PPU network routing self-test",
    )
    require(
        repository_contracts,
        '"scripts/ci/ppu-network-trigger.py"',
        owner="REPO PPU network routing governance",
    )
    require(ppu_release, '"software/python/plasma_server/**"', owner="SW/PPU PPU release")
    require(z2_release, '"scripts/z2-python-runtime.py"', owner="SW/PPU Z2 release")
    require(z2_release, '"software/python/plasma_server/**"', owner="SW/PPU Z2 release")

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

    # ADR-0002 Phase 2 software qualification is a SW/PPU-owned promotion
    # boundary. It may consume only explicit research/catalog inputs and must
    # never turn the entire AI IC Support tree into runtime authority.
    require(
        openocd_qualification,
        "name: OpenOCD software qualification",
        owner="SW/PPU OpenOCD software qualification",
    )
    for token in (
        '"release/openocd.json"',
        '"release/openocd-qualification/**"',
        '"software/python/plasma_web/openocd_software_qualification.py"',
        '"software/python/tests/test_openocd_software_qualification_v1.py"',
        '"data/device-catalog/research/stm32f1-commercial-icpn.csv"',
        '"data/device-catalog/research/stm32f1-ordering-authority-v2.4.json"',
        '"data/ic-support/profiles/memory-geometry/stm32f103r8-64k-v0.json"',
        '"data/ic-support/profiles/memory-geometry/stm32f103rb-128k-v0.json"',
        '"data/ic-support/profiles/memory-geometry/stm32f103v8-64k-v0.json"',
        '"data/ic-support/profiles/memory-geometry/stm32f103vb-128k-v0.json"',
        '"data/ic-support/openocd-comparison/stm32f103c8t6-openocd-v0.12.0-v1.json"',
        '"data/ic-support/benchmarks/stm32f103c/vendor-neutral-admission-contract-v1.json"',
        '"data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json"',
        '"data/ic-support/bindings/stm32f103c-pilot-v0.json"',
    ):
        require(
            openocd_qualification,
            token,
            owner="SW/PPU OpenOCD software qualification",
        )
    for token in (
        '"data/ic-support/**"',
        '"data/device-catalog/research/*-commercial-icpn.csv"',
    ):
        forbid(
            openocd_qualification,
            token,
            owner="SW/PPU OpenOCD software qualification",
        )
    require_count(
        repository_contracts,
        '".github/workflows/openocd-software-qualification.yml"',
        3,
        owner="REPO OpenOCD qualification governance",
    )

    print("CI workstream/domain-boundary contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())