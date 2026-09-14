#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
DEBT_PATH = ROOT / ".github" / "device-catalog-ci-trigger-debt.json"
DEBT_REPO_PATH = ".github/device-catalog-ci-trigger-debt.json"

PRODUCTION_PREFIX = "data/device-catalog/production/"
PRODUCTION_PROBES = (
    "data/device-catalog/production/icpn-v1-manifest.json",
    "data/device-catalog/production/__ci_governance_probe__.json",
    "data/device-catalog/production/nested/__ci_governance_probe__.json",
)

# Only current-state/global validators may be triggered by canonical Production
# paths.  Family/phase/research workflows are default-denied regardless of
# filename vocabulary.  This prevents new roles such as qualification,
# security-scope, TrustZone, wireless, or H7 partitioning from escaping the
# boundary merely because their names do not match an older regex.
GLOBAL_PRODUCTION_TRIGGER_OWNERS = frozenset(
    {
        ".github/workflows/device-catalog-validation.yml",
        ".github/workflows/device-catalog-current-validation.yml",
        ".github/workflows/device-catalog-production-doc-contract.yml",
    }
)


def fail(message: str) -> None:
    raise SystemExit(message)


def trigger_paths(text: str) -> list[str]:
    lines = text.splitlines()
    in_on = False
    result: list[str] = []

    for line in lines:
        if not in_on:
            if line == "on:":
                in_on = True
            continue

        if line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break

        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result.append(value)

    return result


def _matches(path: str, pattern: str) -> bool:
    # The repository uses simple GitHub path globs.  fnmatch is deliberately
    # conservative here: '*' also matching '/' can only widen detection, which
    # is appropriate for a fail-closed governance check.
    return fnmatch.fnmatchcase(path, pattern)


def production_trigger_patterns(patterns: list[str]) -> set[str]:
    """Return positive trigger patterns that leave any Production probe enabled.

    Ordered !negation is respected so an explicit exclusion can narrow a broad
    positive pattern without being reported as debt.
    """
    offenders: set[str] = set()
    for probe in PRODUCTION_PROBES:
        enabled = False
        enabling_pattern: str | None = None
        for raw in patterns:
            negative = raw.startswith("!")
            pattern = raw[1:] if negative else raw
            if not pattern or not _matches(probe, pattern):
                continue
            enabled = not negative
            enabling_pattern = None if negative else raw
        if enabled and enabling_pattern is not None:
            offenders.add(enabling_pattern)

    # Exact/prefix Production paths that may not coincide with a probe are also
    # forbidden.  This catches future named files without needing to enumerate
    # them in PRODUCTION_PROBES.
    for raw in patterns:
        if raw.startswith("!"):
            continue
        if raw.startswith(PRODUCTION_PREFIX):
            offenders.add(raw)
    return offenders


def governed_violations() -> set[tuple[str, str]]:
    violations: set[tuple[str, str]] = set()
    workflows = sorted(WORKFLOWS.glob("device-catalog-*.yml")) + sorted(
        WORKFLOWS.glob("device-catalog-*.yaml")
    )

    for workflow in workflows:
        relative = workflow.relative_to(ROOT).as_posix()
        production_patterns = production_trigger_patterns(
            trigger_paths(workflow.read_text(encoding="utf-8"))
        )
        if relative in GLOBAL_PRODUCTION_TRIGGER_OWNERS:
            continue
        for path in production_patterns:
            violations.add((relative, path))

    return violations


def load_debt_bytes(data: bytes, *, source: str) -> set[tuple[str, str]]:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        fail(f"{source}: invalid JSON: {exc}")

    if payload.get("schema_version") != 1:
        fail(f"{source}: schema_version must be 1")
    if payload.get("status") != "temporary-ratchet":
        fail(f"{source}: status must be temporary-ratchet")

    entries = payload.get("violations")
    if not isinstance(entries, dict):
        fail(f"{source}: violations must be an object")

    flattened: set[tuple[str, str]] = set()
    for workflow, paths in entries.items():
        if not isinstance(workflow, str) or not workflow.startswith(".github/workflows/device-catalog-"):
            fail(f"{source}: invalid workflow key: {workflow!r}")
        if not isinstance(paths, list) or not paths:
            fail(f"{source}: debt entry {workflow} must have a non-empty path list")
        if paths != sorted(set(paths)):
            fail(f"{source}: debt paths for {workflow} must be unique and sorted")
        for path in paths:
            if not isinstance(path, str):
                fail(f"{source}: invalid trigger debt for {workflow}: {path!r}")
            flattened.add((workflow, path))

    return flattened


def load_current_debt() -> set[tuple[str, str]]:
    return load_debt_bytes(DEBT_PATH.read_bytes(), source=DEBT_REPO_PATH)


def load_base_debt(base: str) -> set[tuple[str, str]] | None:
    if not base or set(base) == {"0"}:
        return None

    result = subprocess.run(
        ["git", "show", f"{base}:{DEBT_REPO_PATH}"],
        cwd=ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        return None
    return load_debt_bytes(result.stdout, source=f"{base}:{DEBT_REPO_PATH}")


def fmt(entries: set[tuple[str, str]]) -> str:
    return "\n".join(f"  - {workflow}: {path}" for workflow, path in sorted(entries)) or "  (none)"


def self_test() -> None:
    assert production_trigger_patterns(["data/device-catalog/production/icpn-v1-manifest.json"])
    assert production_trigger_patterns(["data/device-catalog/production/**"])
    assert production_trigger_patterns(["data/device-catalog/**"])
    assert not production_trigger_patterns(["data/device-catalog/research/**"])
    assert not production_trigger_patterns(
        ["data/device-catalog/**", "!data/device-catalog/production/**"]
    )
    assert production_trigger_patterns(
        [
            "data/device-catalog/**",
            "!data/device-catalog/production/**",
            "data/device-catalog/production/icpn-v1-manifest.json",
        ]
    )
    print("Device Catalog CI trigger governance self-test: PASS")


def main() -> int:
    self_test()
    actual = governed_violations()
    debt = load_current_debt()

    new_unlisted = actual - debt
    stale_debt = debt - actual
    if new_unlisted or stale_debt:
        parts = ["Device Catalog CI trigger debt ledger does not match the governed workflow state."]
        if new_unlisted:
            parts.append("Unlisted/new violations:\n" + fmt(new_unlisted))
        if stale_debt:
            parts.append("Stale debt entries that must be removed:\n" + fmt(stale_debt))
        fail("\n".join(parts))

    base = os.environ.get("PLASMA_CI_GOVERNANCE_BASE", "").strip()
    base_debt = load_base_debt(base)
    if base_debt is not None:
        additions = debt - base_debt
        if additions:
            fail(
                "Device Catalog CI trigger debt is a ratchet and may only shrink; "
                "new debt entries are forbidden:\n" + fmt(additions)
            )

    print(
        "Device Catalog CI trigger governance PASS; "
        f"retained_debt={len(debt)} global_production_owners={len(GLOBAL_PRODUCTION_TRIGGER_OWNERS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
