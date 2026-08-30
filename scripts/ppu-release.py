#!/usr/bin/env python3
"""Build a canonical Plasma PPU release from a validated PPU runtime payload."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


class PPUReleaseError(ValueError):
    pass


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PPUReleaseError(f"cannot load build tool: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_ppu_release(
    *,
    repo_root: Path,
    runtime_dir: Path,
    output_dir: Path,
    git_sha: str | None = None,
    build_timestamp: str | None = None,
) -> Path:
    repo_root = repo_root.resolve()
    runtime_dir = runtime_dir.resolve()
    runtime_tool = _load_script(repo_root / "scripts" / "ppu-runtime.py", "plasma_ppu_runtime")
    release_tool = _load_script(repo_root / "scripts" / "product-release.py", "plasma_ppu_product_release")
    runtime_tool.validate_runtime(runtime_dir)
    return release_tool.build_release(
        repo_root=repo_root,
        runtime_dir=runtime_dir,
        output_dir=output_dir.resolve(),
        role=release_tool.ROLE_PPU,
        platform_name="linux",
        architecture="armv7l",
        git_sha=git_sha,
        build_timestamp=build_timestamp,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Plasma PPU linux-armv7l release")
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--git-sha")
    parser.add_argument("--build-timestamp")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        artifact = build_ppu_release(
            repo_root=args.repo_root,
            runtime_dir=args.runtime_dir,
            output_dir=args.output_dir,
            git_sha=args.git_sha,
            build_timestamp=args.build_timestamp,
        )
    except (OSError, PPUReleaseError, ValueError) as exc:
        print(f"ppu-release: {exc}", file=sys.stderr)
        return 2
    print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
