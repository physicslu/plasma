#!/usr/bin/env python3
"""Deterministic orchestration of eight previously separate STM32 metadata replay checks.

Gate 1: no catalogue writes, vendor calls, HIL, SWPC, deployments or manual dispatch.
Each family executes the exact two Python commands its archived original workflow owned.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ".github/workflows/device-catalog-stm32-metadata-replay-dispatch.yml"
RUNNER = "scripts/ci/icpn_stm32_metadata_replay_dispatch.py"
CONTRACT_TEST = "scripts/tests/test-icpn-stm32-metadata-replay-dispatch.py"
FAMILY_CI = "scripts/device-catalog-family-ci.py"
ARCHIVED = {
    "c5": {"analysis": "data/device-catalog/research/analyze_stm32c5_metadata_replay_v42.py", "test": "data/device-catalog/research/test_analyze_stm32c5_metadata_replay_v42.py", "authority": "data/device-catalog/research/stm32c5-ordering-authority-v4.2.json", "doc": "data/device-catalog/research/STM32C5_METADATA_REPLAY_V42.md", "original": ".github/workflows/device-catalog-stm32c5-metadata-replay-v42.yml", "archive": "docs/archive/ci-workflows/stm32-metadata-replay/device-catalog-stm32c5-metadata-replay-v42.yml", "sha": "9b62f68fd8b5a707dd93122968af63260505b47d"},
    "f2": {"analysis": "data/device-catalog/research/analyze_stm32f2_metadata_replay_v39.py", "test": "data/device-catalog/research/test_analyze_stm32f2_metadata_replay_v39.py", "authority": "data/device-catalog/research/stm32f2-ordering-authority-v3.9.json", "doc": "data/device-catalog/research/STM32F2_METADATA_REPLAY_V39.md", "original": ".github/workflows/device-catalog-stm32f2-metadata-replay-v39.yml", "archive": "docs/archive/ci-workflows/stm32-metadata-replay/device-catalog-stm32f2-metadata-replay-v39.yml", "sha": "3ffc36d7d28e784e8ee362e7ea9ddc84be1c8f13"},
    "f3": {"analysis": "data/device-catalog/research/analyze_stm32f3_metadata_replay_v31.py", "test": "data/device-catalog/research/test_analyze_stm32f3_metadata_replay_v31.py", "authority": "data/device-catalog/research/stm32f3-ordering-authority-v3.1.json", "doc": "data/device-catalog/research/STM32F3_METADATA_REPLAY_V31.md", "original": ".github/workflows/device-catalog-stm32f3-metadata-replay-v31.yml", "archive": "docs/archive/ci-workflows/stm32-metadata-replay/device-catalog-stm32f3-metadata-replay-v31.yml", "sha": "f98baed55d7f1a43f4ebb22cba4ec0f7c9d7c809"},
    "f7": {"analysis": "data/device-catalog/research/analyze_stm32f7_metadata_replay_v35.py", "test": "data/device-catalog/research/test_analyze_stm32f7_metadata_replay_v35.py", "authority": "data/device-catalog/research/stm32f7-ordering-authority-v3.5.json", "doc": "data/device-catalog/research/STM32F7_METADATA_REPLAY_V35.md", "original": ".github/workflows/device-catalog-stm32f7-metadata-replay-v35.yml", "archive": "docs/archive/ci-workflows/stm32-metadata-replay/device-catalog-stm32f7-metadata-replay-v35.yml", "sha": "c63b8910528cb20f84746d43b1262c96ffb4ace0"},
    "h5": {"analysis": "data/device-catalog/research/analyze_stm32h5_metadata_replay_v27.py", "test": "data/device-catalog/research/test_analyze_stm32h5_metadata_replay_v27.py", "authority": "data/device-catalog/research/stm32h5-ordering-authority-v2.7.json", "doc": "data/device-catalog/research/STM32H5_METADATA_REPLAY_V27.md", "original": ".github/workflows/device-catalog-stm32h5-metadata-replay-v27.yml", "archive": "docs/archive/ci-workflows/stm32-metadata-replay/device-catalog-stm32h5-metadata-replay-v27.yml", "sha": "00b45a06fbb396a8e495c5e75e3e0aefc92cb92c"},
    "n6": {"analysis": "data/device-catalog/research/analyze_stm32n6_metadata_replay_v48.py", "test": "data/device-catalog/research/test_analyze_stm32n6_metadata_replay_v48.py", "authority": "data/device-catalog/research/stm32n6-ordering-authority-v4.8.json", "doc": "data/device-catalog/research/STM32N6_METADATA_REPLAY_V48.md", "original": ".github/workflows/device-catalog-stm32n6-metadata-replay-v48.yml", "archive": "docs/archive/ci-workflows/stm32-metadata-replay/device-catalog-stm32n6-metadata-replay-v48.yml", "sha": "fd3c0b8eb5180036e75230f204e28f5aa678214d"},
    "wb0": {"analysis": "data/device-catalog/research/analyze_stm32wb0_metadata_replay_v51.py", "test": "data/device-catalog/research/test_analyze_stm32wb0_metadata_replay_v51.py", "authority": "data/device-catalog/research/stm32wb0-ordering-authority-v5.1.json", "doc": "data/device-catalog/research/STM32WB0_METADATA_REPLAY_V51.md", "original": ".github/workflows/device-catalog-stm32wb0-metadata-replay-v51.yml", "archive": "docs/archive/ci-workflows/stm32-metadata-replay/device-catalog-stm32wb0-metadata-replay-v51.yml", "sha": "0350fecb10bf4c18fdf6aef4cf9546941f955bd9"},
    "wl3": {"analysis": "data/device-catalog/research/analyze_stm32wl3_metadata_replay_v45.py", "test": "data/device-catalog/research/test_analyze_stm32wl3_metadata_replay_v45.py", "authority": "data/device-catalog/research/stm32wl3-ordering-authority-v4.5.json", "doc": "data/device-catalog/research/STM32WL3_METADATA_REPLAY_V45.md", "original": ".github/workflows/device-catalog-stm32wl3-metadata-replay-v45.yml", "archive": "docs/archive/ci-workflows/stm32-metadata-replay/device-catalog-stm32wl3-metadata-replay-v45.yml", "sha": "3cc95316463c59ca8050767e7c9efa9975d41e6d"},
}
FAMILIES = tuple(ARCHIVED)

def blob_sha(body: bytes) -> str:
    return hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()

def path_owners() -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for family, item in ARCHIVED.items():
        for key in ("analysis", "test", "authority", "doc", "original", "archive"):
            owners.setdefault(item[key], set()).add(family)
    owners[FAMILY_CI] = {"f2", "f7"}
    return owners

def affected_families(changed: list[str]) -> list[str]:
    change_set = {path.strip().replace("\\", "/") for path in changed if path.strip()}
    if change_set.intersection({WORKFLOW, RUNNER, CONTRACT_TEST}):
        return list(FAMILIES)
    owners = path_owners()
    found: set[str] = set()
    for path in change_set:
        found.update(owners.get(path, ()))
    return [family for family in FAMILIES if family in found]

def matrix_for(families: list[str]) -> dict:
    return {"include": [{"family": f, "runner": "ubuntu-24.04"} for f in families]}

def diff_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACDMRT", base, head],
        cwd=ROOT, check=True, text=True, capture_output=True,
    )
    return result.stdout.splitlines()

def self_test() -> None:
    if len(ARCHIVED) != 8:
        raise SystemExit("expected eight exact metadata replay profiles")
    owners = path_owners()
    if any(len(owners[p[k]]) != 1 for p in ARCHIVED.values() for k in ("analysis", "test", "authority", "doc", "original", "archive")):
        raise SystemExit("overlapping trigger owners")
    for f, p in ARCHIVED.items():
        original = ROOT / p["archive"]
        body = original.read_bytes()
        if blob_sha(body) != p["sha"]:
            raise SystemExit(f"{f}: frozen original workflow Git blob changed")
        text = body.decode("utf-8")
        if "pull_request:" not in text or "runs-on: ubuntu-24.04" not in text:
            raise SystemExit(f"{f}: original trigger/runner boundary drift")
        for k in ("analysis", "test", "authority", "doc", "original"):
            if p[k] not in text:
                raise SystemExit(f"{f}: original trigger/test path missing: {p[k]}")
        for k in ("analysis", "test", "authority", "doc"):
            if not (ROOT / p[k]).is_file():
                raise SystemExit(f"{f}: missing source: {p[k]}")
        if affected_families([p["analysis"]]) != [f]:
            raise SystemExit(f"{f}: route mismatch")
        if affected_families([p["archive"]]) != [f]:
            raise SystemExit(f"{f}: archived workflow edit not routed")
        if affected_families([p["original"]]) != [f]:
            raise SystemExit(f"{f}: deleted original workflow not routed")
    if affected_families([FAMILY_CI]) != ["f2", "f7"]:
        raise SystemExit("shared family CLI must preserve f2/f7 only")
    if affected_families([WORKFLOW]) != list(FAMILIES):
        raise SystemExit("dispatcher change must validate all eight")
    if affected_families(["data/device-catalog/production/icpn-v1-manifest.json"]):
        raise SystemExit("Production is not the owner of historical metadata replay")
    if affected_families(["docs/README.md"]):
        raise SystemExit("unrelated docs should not trigger metadata replay")
    # The GitHub event filter must be an exact union of the frozen original
    # path owners plus this dispatcher and its contract. Missing a trigger
    # silently drops validation; extra triggers introduce unintended fanout.
    workflow_body = (ROOT / WORKFLOW).read_text(encoding="utf-8")
    token = "on:\n  pull_request:\n    paths:\n"
    if workflow_body.count(token) != 1 or "\npermissions:" not in workflow_body:
        raise SystemExit("expected explicit pull_request path-scoped dispatch")
    trigger_section = workflow_body.split(token, 1)[1].split("\npermissions:", 1)[0]
    got = set()
    for line in trigger_section.splitlines():
        if not line.startswith("      - '") or not line.endswith("'"):
            raise SystemExit("unexpected pull_request path filter syntax")
        got.add(line.split("'", 2)[1])
    expected = {WORKFLOW, RUNNER, CONTRACT_TEST, FAMILY_CI}
    for item in ARCHIVED.values():
        expected.update(item[k] for k in ("analysis", "test", "authority", "doc", "original", "archive"))
    if got != expected or len(trigger_section.splitlines()) != len(expected):
        raise SystemExit(f"metadata replay workflow filter parity drift: missing={sorted(expected - got)} extra={sorted(got - expected)}")
    print("STM32 metadata replay dispatch route/ownership self-test: PASS")

def execute(family: str) -> None:
    profile = ARCHIVED[family]
    subprocess.run([sys.executable, profile["analysis"]], cwd=ROOT, check=True)
    subprocess.run([
        sys.executable, "-m", "unittest", "discover",
        "-s", "data/device-catalog/research",
        "-p", Path(profile["test"]).name, "-v"
    ], cwd=ROOT, check=True)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("self-test")
    detect = sub.add_parser("detect")
    detect.add_argument("--base", required=True)
    detect.add_argument("--head", required=True)
    run = sub.add_parser("run")
    run.add_argument("--family", choices=FAMILIES, required=True)
    args = parser.parse_args()
    if args.command == "self-test":
        self_test()
    elif args.command == "detect":
        print(json.dumps(matrix_for(affected_families(diff_paths(args.base, args.head))), separators=(",", ":")))
    else:
        execute(args.family)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
