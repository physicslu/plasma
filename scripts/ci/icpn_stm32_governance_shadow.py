#!/usr/bin/env python3
"""Fail-closed historical governance shadow: original three workflows stay live."""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHADOW = ".github/workflows/device-catalog-stm32-governance-shadow.yml"
RUNNER = "scripts/ci/icpn_stm32_governance_shadow.py"
TEST = "scripts/tests/test-icpn-stm32-governance-shadow.py"
SOURCES = {
    "post_u5": {
        "file": ".github/workflows/device-catalog-post-u5-frontier-selection-validation.yml",
        "sha": "e4f95807c08c4c10858fb8084fc8206902b11989",
        "command": "python validate_stm32_post_u5_frontier_selection.py",
        "cwd": "data/device-catalog/research",
    },
    "h7_scope": {
        "file": ".github/workflows/device-catalog-stm32h7-partitioned-scope-selection-validation.yml",
        "sha": "56b50b27536d05552b4413d55b31d0ca2dcf4aea",
        "command": "python data/device-catalog/research/validate_stm32h7_partitioned_scope_selection.py",
        "cwd": ".",
    },
    "h7rs_evidence": {
        "file": ".github/workflows/device-catalog-stm32h7rs-evidence-accessibility-validation.yml",
        "sha": "e2b6a1e03b7269f52ec2765651685849d23b27d1",
        "command": "python data/device-catalog/research/validate_stm32h7rs_evidence_accessibility.py",
        "cwd": ".",
    },
}
TARGETS = tuple(SOURCES)
SHARED = frozenset((SHADOW, RUNNER, TEST))


def git_blob_sha(body: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(body)).encode() + b"\0" + body).hexdigest()


def event_paths(text: str, event: str) -> tuple[str, ...]:
    m = re.search(
        rf"(?ms)^  {re.escape(event)}:\n(.*?)(?=^  (?:pull_request|push|workflow_dispatch):|^permissions:|^jobs:)",
        text,
    )
    if m is None:
        raise ValueError(f"missing event: {event}")
    paths = tuple(re.findall(r"^      - ['\"]([^'\"]+)['\"]\s*$", m.group(1), re.M))
    if not paths or len(set(paths)) != len(paths):
        raise ValueError(f"missing/duplicate trigger paths: {event}")
    return paths


def validate_source(target: str, data: bytes | None = None) -> tuple[str, ...]:
    spec = SOURCES[target]
    body = data if data is not None else (ROOT / spec["file"]).read_bytes()
    if git_blob_sha(body) != spec["sha"]:
        raise ValueError(f"{target}: pinned original YAML drift")
    text = body.decode("utf-8")
    pr, push = event_paths(text, "pull_request"), event_paths(text, "push")
    if pr != push or len(pr) != 6:
        raise ValueError(f"{target}: PR/push path parity or count drift")
    if "  workflow_dispatch:" in text:
        raise ValueError(f"{target}: unexpected manual trigger")
    required = ("permissions:\n  contents: read", "runs-on: ubuntu-24.04",
                "timeout-minutes: 10", "actions/checkout@v4",
                "actions/setup-python@v5", "python-version: '3.12'")
    if any(item not in text for item in required):
        raise ValueError(f"{target}: original runner/timeout/permission drift")
    commands = re.findall(r"^\s+run: (python [^\r\n]+)$", text, re.M)
    if commands != [spec["command"]]:
        raise ValueError(f"{target}: validator command drift")
    dirs = re.findall(r"^\s+working-directory: (.+)$", text, re.M)
    if dirs != ([] if spec["cwd"] == "." else [spec["cwd"]]):
        raise ValueError(f"{target}: working directory changed")
    if any(path.startswith("data/device-catalog/production/") for path in pr):
        raise ValueError(f"{target}: Production trigger forbidden")
    return pr


def expected_paths() -> set[str]:
    return set().union(*(set(validate_source(t)) for t in TARGETS), SHARED)


def verify_shadow(text: str | None = None) -> None:
    body = text if text is not None else (ROOT / SHADOW).read_text()
    pr, push = event_paths(body, "pull_request"), event_paths(body, "push")
    expected = expected_paths()
    if pr != push or set(pr) != expected or len(pr) != len(expected):
        raise ValueError("shadow trigger union drift")
    required = ("permissions:\n  contents: read", "runs-on: ubuntu-24.04",
                "timeout-minutes: 10", "timeout-minutes: 5",
                "fetch-depth: 0", "persist-credentials: false",
                "python-version: '3.12'", "strategy:", "fail-fast: false",
                "matrix: \x24{{ fromJSON(needs.detect.outputs.matrix) }}",
                "run --target \"\x24{{ matrix.target }}\"",
                "python scripts/ci/icpn_stm32_governance_shadow.py self-test",
                "python scripts/tests/test-icpn-stm32-governance-shadow.py")
    if any(token not in body for token in required) or "workflow_dispatch:" in body:
        raise ValueError("shadow runtime/permissions/stage contract drift")
    if any(p.startswith("data/device-catalog/production/") for p in pr):
        raise ValueError("shadow Production trigger forbidden")


def affected(changed: list[str]) -> list[str]:
    if any(path in SHARED for path in changed):
        return list(TARGETS)
    owners = {target: validate_source(target) for target in TARGETS}
    return [target for target in TARGETS
            if any(fnmatch.fnmatchcase(path, pattern)
                   for path in changed for pattern in owners[target])]


def diff_paths(base: str, head: str, event: str) -> list[str]:
    if event not in ("pull_request", "push"):
        raise ValueError("unsupported shadow event")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("unsafe head SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", base or ""):
        if event == "push" and (not base or base == "0" * 40):
            return [SHADOW]  # initial push: conservative all-target replay
        raise ValueError("unsafe base SHA")
    compare = base + ("..." if event == "pull_request" else "") + head
    result = subprocess.run(["git", "diff", "--name-only", "-z", "--no-renames", compare],
                            cwd=ROOT, capture_output=True, check=True)
    return [p.decode("utf-8") for p in result.stdout.split(b"\0") if p]


def self_test() -> None:
    verify_shadow()
    if len(expected_paths()) != 18:
        raise ValueError("expected 15 original paths + three shadow control paths")
    for target in TARGETS:
        if affected([SOURCES[target]["file"]]) != [target]:
            raise ValueError(f"{target}: source owner mismatch")
    if affected(["data/device-catalog/research/stm32-post-u5-frontier-selection.json"]) != ["post_u5", "h7_scope"]:
        raise ValueError("post-U5 shared path fan-out lost")
    if affected(["data/device-catalog/research/stm32h7-partition-source.json"]) != ["h7_scope", "h7rs_evidence"]:
        raise ValueError("H7 shared path fan-out lost")
    if affected(["data/device-catalog/research/evidence/stm32h7rs-accessibility-live-2026-09-16/a/b.json"]) != ["h7rs_evidence"]:
        raise ValueError("H7RS recursive evidence pattern lost")
    if affected(["data/device-catalog/production/icpn-v1-manifest.json"]):
        raise ValueError("unexpected Production routing")
    print("Shadow source blobs, PR/push triggers, 3 overlap paths, Production negative routing: PASS")


def execute(target: str) -> None:
    verify_shadow()
    spec = SOURCES[target]
    command = spec["command"].split()
    if command[0] != "python" or len(command) != 2:
        raise ValueError("not a whitelisted Python command")
    subprocess.run(command, cwd=ROOT / spec["cwd"], check=True)
    status = subprocess.run(["git", "status", "--porcelain", "--",
                             "data/device-catalog/production"],
                            cwd=ROOT, check=True, capture_output=True, text=True)
    if status.stdout.strip():
        raise ValueError("Production files modified by shadow validator")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    sub.add_parser("self-test")
    d = sub.add_parser("detect")
    d.add_argument("--base", required=True)
    d.add_argument("--head", required=True)
    d.add_argument("--event", choices=("push", "pull_request"), required=True)
    run = sub.add_parser("run")
    run.add_argument("--target", choices=TARGETS, required=True)
    args = p.parse_args()
    if args.action == "self-test":
        self_test()
    elif args.action == "detect":
        self_test()
        matches = affected(diff_paths(args.base, args.head, args.event))
        print(json.dumps({"include": [{"target": target} for target in matches]}, separators=(",", ":")))
    else:
        execute(args.target)


if __name__ == "__main__":
    main()
