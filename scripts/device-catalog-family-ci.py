#!/usr/bin/env python3
"""Deterministic CI dispatcher for bounded STM32 family validation.

This script centralizes two concerns that were previously repeated across
family-specific GitHub Actions workflows:

1. map changed repository paths to the affected STM32 families;
2. execute the existing, family-specific deterministic validation commands.

It does not perform live acquisition and it does not write canonical catalog
state. Family command profiles intentionally preserve the current workflow
semantics instead of pretending every family has an identical lifecycle.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("stm32f0", "stm32f2", "stm32f3", "stm32f7", "stm32g0", "stm32g4")
RUNNERS = {
    "stm32f0": "ubuntu-latest",
    "stm32f2": "ubuntu-latest",
    "stm32f3": "ubuntu-latest",
    "stm32f7": "ubuntu-latest",
    "stm32g0": "ubuntu-24.04",
    "stm32g4": "ubuntu-24.04",
}

DISPATCHER_PATH = ".github/workflows/device-catalog-stm32-family-validation.yml"
RUNNER_PATH = "scripts/device-catalog-family-ci.py"
OLD_WORKFLOW_FAMILY = {
    ".github/workflows/device-catalog-stm32f0-validation.yml": "stm32f0",
    ".github/workflows/device-catalog-stm32f2-bounded-validation.yml": "stm32f2",
    ".github/workflows/device-catalog-stm32f3-foundation-validation.yml": "stm32f3",
    ".github/workflows/device-catalog-stm32f7-validation.yml": "stm32f7",
    ".github/workflows/device-catalog-stm32g0-validation.yml": "stm32g0",
    ".github/workflows/device-catalog-stm32g4-validation.yml": "stm32g4",
}


def _py(relative_path: str, *args: str) -> list[str]:
    return [sys.executable, relative_path, *args]


def command_profile(family: str) -> list[list[str]]:
    profiles: dict[str, list[list[str]]] = {
        "stm32f0": [
            _py("data/device-catalog/research/test_stm32f0_phase4_5a_foundation.py"),
            _py("data/device-catalog/research/test_stm32f0_dual_surface_evidence.py"),
            _py("data/device-catalog/research/test_stm32f0_phase4_5b_discovery.py"),
            ["sha256sum", "data/device-catalog/research/stm32f0-phase4.5b-discovery-baseline.json"],
            _py("data/device-catalog/research/validate_stm32f0_phase4_5b_retained_evidence.py"),
            _py("data/device-catalog/research/test_stm32f0_phase4_5c_policy.py"),
            _py("data/device-catalog/research/test_stm32f0_phase4_5d_admission.py"),
        ],
        "stm32f2": [
            _py("data/device-catalog/research/test_stm32f2_bounded_historical_golden_replay.py"),
            _py("data/device-catalog/research/stm32f2_phase4_3i_policy.py"),
            _py("data/device-catalog/research/test_stm32f2_bounded_policy_admission.py"),
            _py("data/device-catalog/research/test_stm32f2_phase4_3j_admission.py"),
            _py("data/device-catalog/research/test_stm32f2_bounded_shadow_compare.py"),
            _py(
                "data/device-catalog/research/stm32f2_bounded_shadow.py",
                "compare",
                "--phase",
                "4.3H",
                "--live-summary",
                "data/device-catalog/research/evidence/stm32f2-phase4.3h-official-st-discovery-live-2026-09-07/pilot-summary.json",
            ),
        ],
        "stm32f3": [
            _py("data/device-catalog/research/test_stm32f3_phase4_4a_foundation.py"),
            _py("data/device-catalog/research/test_stm32f3_phase4_4b_discovery.py"),
            _py("data/device-catalog/research/test_stm32f3_dual_surface_evidence.py"),
            _py("data/device-catalog/research/test_st_browser_acquisition.py"),
            _py("data/device-catalog/research/validate_stm32f3_phase4_4b_retained_evidence.py"),
            _py("data/device-catalog/research/test_stm32f3_phase4_4c_policy.py"),
            _py("data/device-catalog/research/test_stm32f3_phase4_4d_admission.py"),
        ],
        "stm32f7": [
            _py("data/device-catalog/research/test_stm32f7_phase4_6a_foundation.py"),
            _py("data/device-catalog/research/test_stm32f7_dual_surface_evidence.py"),
            _py("data/device-catalog/research/test_stm32f7_phase4_6b_discovery.py"),
            _py("data/device-catalog/research/validate_stm32f7_phase4_6b_retained_evidence.py"),
            _py("data/device-catalog/research/test_stm32f7_phase4_6c_policy.py"),
            _py("data/device-catalog/research/test_stm32f7_phase4_6c_policy_plan.py"),
            _py("data/device-catalog/research/stm32f7_phase4_6c_policy.py"),
            _py("data/device-catalog/research/test_stm32f7_phase4_6d_admission.py"),
            _py("data/device-catalog/research/validate_stm32f7_phase4_6d_admission_plan.py"),
            _py("data/device-catalog/research/test_stm32f7_phase4_6e_publication.py"),
        ],
        "stm32g0": [
            _py("data/device-catalog/research/test_stm32g0_phase4_8a_foundation.py"),
            _py("data/device-catalog/research/test_stm32g0_dual_surface_evidence.py"),
            _py("data/device-catalog/research/test_stm32g0_phase4_8b_discovery.py"),
            _py("data/device-catalog/research/test_stm32g0_phase4_8b_live_evidence_contract.py"),
            _py("data/device-catalog/research/validate_stm32g0_phase4_8b_retained_evidence.py"),
            _py("data/device-catalog/research/test_stm32g0_phase4_8c_policy.py"),
            _py("data/device-catalog/research/test_stm32g0_phase4_8c_policy_plan.py"),
            _py("data/device-catalog/research/stm32g0_phase4_8c_policy.py"),
            _py("data/device-catalog/research/test_stm32g0_phase4_8d_admission.py"),
            _py("data/device-catalog/research/validate_stm32g0_phase4_8d_admission_plan.py"),
            _py("data/device-catalog/research/test_stm32g0_phase4_8e_publication.py"),
        ],
        "stm32g4": [
            _py("data/device-catalog/research/test_stm32g4_phase4_9a_foundation.py"),
            _py("data/device-catalog/research/test_stm32g4_dual_surface_evidence.py"),
            _py("data/device-catalog/research/test_stm32g4_phase4_9b_discovery.py"),
            _py("data/device-catalog/research/validate_stm32g4_phase4_9b_retained_evidence.py"),
            _py("data/device-catalog/research/test_stm32g4_phase4_9c_policy.py"),
            _py("data/device-catalog/research/stm32g4_phase4_9c_policy.py"),
            _py("data/device-catalog/research/test_stm32g4_phase4_9d_admission.py"),
            _py("data/device-catalog/research/validate_stm32g4_phase4_9d_admission_plan.py"),
            _py("data/device-catalog/research/test_stm32g4_phase4_9e_publication.py"),
        ],
    }
    try:
        return profiles[family]
    except KeyError as exc:
        raise SystemExit(f"unsupported family: {family}") from exc


def affected_families(changed_paths: Iterable[str]) -> list[str]:
    affected: set[str] = set()
    for raw_path in changed_paths:
        path = raw_path.strip().replace("\\", "/")
        if not path:
            continue

        if path in {DISPATCHER_PATH, RUNNER_PATH}:
            return list(FAMILIES)
        if path.startswith("data/device-catalog/production/"):
            return list(FAMILIES)
        if path == "data/device-catalog/research/openocd-parts-canonical.csv":
            return list(FAMILIES)
        if path.startswith("data/device-catalog/research/device_catalog_"):
            return list(FAMILIES)
        if path.startswith("data/device-catalog/research/st_"):
            return list(FAMILIES)
        if path.startswith("data/device-catalog/research/test_st_"):
            return list(FAMILIES)

        old_family = OLD_WORKFLOW_FAMILY.get(path)
        if old_family:
            affected.add(old_family)
            continue

        for family in FAMILIES:
            if family in path.lower():
                affected.add(family)

    return [family for family in FAMILIES if family in affected]


def changed_paths_from_git(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMRT", base, head],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.splitlines()


def matrix_for(families: Iterable[str]) -> dict[str, list[dict[str, str]]]:
    return {
        "include": [
            {"family": family, "runner": RUNNERS[family]}
            for family in families
        ]
    }


def run_family(family: str) -> None:
    commands = command_profile(family)
    print(f"family={family} commands={len(commands)} runner={RUNNERS[family]}", flush=True)
    for command in commands:
        print("+ " + " ".join(command), flush=True)
        subprocess.run(command, cwd=REPO_ROOT, check=True)


def self_test() -> None:
    assert affected_families(["data/device-catalog/research/stm32g4_phase4_9d_admission.py"]) == ["stm32g4"]
    assert affected_families(["data/device-catalog/research/device-catalog-phase4.5c-stm32f0-policy.md"]) == ["stm32f0"]
    assert affected_families([".github/workflows/device-catalog-stm32f2-bounded-validation.yml"]) == ["stm32f2"]
    assert affected_families(["data/device-catalog/research/openocd-parts-canonical.csv"]) == list(FAMILIES)
    assert affected_families([RUNNER_PATH]) == list(FAMILIES)
    for family in FAMILIES:
        assert command_profile(family), family
        assert RUNNERS[family]
    print("device-catalog-family-ci self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser("detect")
    detect.add_argument("--base", required=True)
    detect.add_argument("--head", required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--family", choices=FAMILIES, required=True)

    subparsers.add_parser("self-test")

    args = parser.parse_args()
    if args.command == "detect":
        families = affected_families(changed_paths_from_git(args.base, args.head))
        print(json.dumps(matrix_for(families), separators=(",", ":")))
        return 0
    if args.command == "run":
        run_family(args.family)
        return 0
    self_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
