#!/usr/bin/env python3
"""Build Control Station releases from a validated Control Station runtime payload.

The generic Common Release Format deliberately rejects arbitrary node_modules
payloads. Vinext standalone output, however, contains a curated runtime-only
node_modules tree. This orchestrator first validates the Control Station runtime
contract and then delegates archive construction to product-release.py while
allowing only console/node_modules/** through that build-side policy boundary.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


class ControlStationReleaseError(ValueError):
    pass


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ControlStationReleaseError(f"cannot load build tool: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_runtime_node_modules(runtime_dir: Path) -> None:
    for path in runtime_dir.rglob("*"):
        relative = path.relative_to(runtime_dir)
        lowered = tuple(part.casefold() for part in relative.parts)
        if "node_modules" not in lowered:
            continue
        if len(lowered) < 2 or lowered[0] != "console" or lowered[1] != "node_modules":
            raise ControlStationReleaseError(
                "runtime node_modules is only allowed under console/node_modules: "
                f"{relative.as_posix()}"
            )


def build_control_station_release(
    *,
    repo_root: Path,
    runtime_dir: Path,
    output_dir: Path,
    platform_name: str,
    architecture: str,
    git_sha: str | None = None,
    build_timestamp: str | None = None,
) -> Path:
    repo_root = repo_root.resolve()
    runtime_dir = runtime_dir.resolve()
    runtime_tool = _load_script(
        repo_root / "scripts" / "control-station-runtime.py",
        "plasma_control_station_runtime",
    )
    release_tool = _load_script(
        repo_root / "scripts" / "product-release.py",
        "plasma_product_release",
    )

    runtime_tool.validate_runtime(runtime_dir)
    _validate_runtime_node_modules(runtime_dir)

    original_forbidden = set(release_tool.FORBIDDEN_PATH_SEGMENTS)
    try:
        release_tool.FORBIDDEN_PATH_SEGMENTS.discard("node_modules")
        return release_tool.build_release(
            repo_root=repo_root,
            runtime_dir=runtime_dir,
            output_dir=output_dir.resolve(),
            role=release_tool.ROLE_CONTROL_STATION,
            platform_name=platform_name,
            architecture=architecture,
            git_sha=git_sha,
            build_timestamp=build_timestamp,
        )
    finally:
        release_tool.FORBIDDEN_PATH_SEGMENTS.clear()
        release_tool.FORBIDDEN_PATH_SEGMENTS.update(original_forbidden)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a Plasma Control Station release from a validated runtime payload"
    )
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--git-sha")
    parser.add_argument("--build-timestamp")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        artifact = build_control_station_release(
            repo_root=args.repo_root,
            runtime_dir=args.runtime_dir,
            output_dir=args.output_dir,
            platform_name=args.platform,
            architecture=args.architecture,
            git_sha=args.git_sha,
            build_timestamp=args.build_timestamp,
        )
    except (ControlStationReleaseError, OSError, ValueError) as exc:
        print(f"control-station-release: {exc}", file=sys.stderr)
        return 2
    print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
