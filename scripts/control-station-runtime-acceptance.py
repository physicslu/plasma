#!/usr/bin/env python3
"""Build, release, extract, and smoke-test the Control Station runtime on the current host."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


class AcceptanceError(RuntimeError):
    pass


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AcceptanceError(f"cannot load acceptance dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_sha(repo_root: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    return completed.stdout.strip()


def run_acceptance(*, repo_root: Path, work_dir: Path) -> dict[str, object]:
    repo_root = repo_root.resolve()
    work_dir = work_dir.resolve()
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    runtime_tool = _load(
        repo_root / "scripts" / "control-station-runtime.py",
        "plasma_control_station_runtime_acceptance",
    )
    control_release = _load(
        repo_root / "scripts" / "control-station-release.py",
        "plasma_control_station_release_acceptance",
    )
    product_release = _load(
        repo_root / "scripts" / "product-release.py",
        "plasma_product_release_acceptance",
    )
    smoke = _load(
        repo_root / "scripts" / "control-station-runtime-smoke.py",
        "plasma_control_station_runtime_smoke_acceptance",
    )

    platform_name, architecture = runtime_tool.host_target()
    standalone = repo_root / "software" / "web" / "dist" / "standalone"
    runtime_dir = runtime_tool.build_runtime(
        repo_root=repo_root,
        standalone_console=standalone,
        output_dir=work_dir / "runtime",
    )

    build_timestamp = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    artifact = control_release.build_control_station_release(
        repo_root=repo_root,
        runtime_dir=runtime_dir,
        output_dir=work_dir / "releases",
        platform_name=platform_name,
        architecture=architecture,
        git_sha=_git_sha(repo_root),
        build_timestamp=build_timestamp,
    )

    extract_root = work_dir / "clean-extract"
    verified = product_release.verify_release(
        artifact,
        extract_to=extract_root,
        expect_role="control-station",
        expect_platform=platform_name,
        expect_architecture=architecture,
    )
    extracted_runtime = extract_root / "plasma-release" / "runtime"
    runtime_tool.validate_runtime(extracted_runtime)
    smoke.run_smoke(extracted_runtime)

    return {
        "ok": True,
        "platform": platform_name,
        "architecture": architecture,
        "artifact": artifact.name,
        "artifact_sha256": verified["artifact_sha256"],
        "runtime": "control-station",
        "console": "vinext-standalone",
        "manager": "python-zipapp",
        "source_tree_runtime_dependency": False,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Plasma Control Station runtime packaging acceptance")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_acceptance(repo_root=args.repo_root, work_dir=args.work_dir)
    except Exception as exc:
        print(f"control-station-runtime-acceptance: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
