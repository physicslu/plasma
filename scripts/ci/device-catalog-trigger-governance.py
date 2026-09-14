#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
DEBT_PATH = ROOT / ".github" / "device-catalog-ci-trigger-debt.json"
DEBT_REPO_PATH = ".github/device-catalog-ci-trigger-debt.json"

PRODUCTION_PREFIX = "data/device-catalog/production/"
PRODUCTION_MANIFEST = "data/device-catalog/production/icpn-v1-manifest.json"
FAMILY_DISPATCHER = ".github/workflows/device-catalog-stm32-family-validation.yml"
PHASE_ROLE_RE = re.compile(
    r"^device-catalog-stm32[a-z0-9]+-.*(?:foundation|discovery|metadata|admission|publication).*\.yml$"
)


def fail(message: str) -> None:
    raise SystemExit(message)


def trigger_paths(text: str) -> set[str]:
    lines = text.splitlines()
    in_on = False
    result: set[str] = set()

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
        result.add(value)

    return result


def governed_violations() -> set[tuple[str, str]]:
    violations: set[tuple[str, str]] = set()

    for workflow in sorted(WORKFLOWS.glob("device-catalog-*.yml")):
        relative = workflow.relative_to(ROOT).as_posix()
        paths = trigger_paths(workflow.read_text(encoding="utf-8"))
        production_paths = {path for path in paths if path.startswith(PRODUCTION_PREFIX)}

        if relative == FAMILY_DISPATCHER:
            for path in production_paths:
                violations.add((relative, path))
            continue

        if not PHASE_ROLE_RE.match(workflow.name):
            continue

        if "publication" in workflow.name:
            forbidden = production_paths - {PRODUCTION_MANIFEST}
        else:
            forbidden = production_paths

        for path in forbidden:
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
            if not isinstance(path, str) or not path.startswith(PRODUCTION_PREFIX):
                fail(f"{source}: invalid production trigger path for {workflow}: {path!r}")
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


def main() -> int:
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

    print(f"Device Catalog CI trigger governance PASS; retained_debt={len(debt)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
