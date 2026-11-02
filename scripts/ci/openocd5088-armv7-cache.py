#!/usr/bin/env python3
"""Fail-closed content-addressed ARMv7 OpenOCD build cache (not a trust root)."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import stat
import sys

SCHEMA = "plasma.openocd5088.armv7.build-cache.v1"
BUILD_RECIPE = "scripts/ci/build-openocd5088-armv7.sh"
INJECTOR = "scripts/ci/inject-plasma-openocd5088-native.py"
SELF = "scripts/ci/openocd5088-armv7-cache.py"


def injected_paths(root: Path) -> list[str]:
    tree = ast.parse((root / INJECTOR).read_text(encoding="utf-8"))
    assignments = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "COPIES" for t in node.targets)
    ]
    if len(assignments) != 1:
        raise ValueError("Injector COPIES must be exactly one literal assignment")
    copies = ast.literal_eval(assignments[0])
    if not isinstance(copies, tuple) or not copies or len(copies) != len(set(copies)):
        raise ValueError("Invalid or duplicate injector source list")
    for item in copies:
        if not isinstance(item, str) or not item.endswith((".c", ".h")) or Path(item).name != item:
            raise ValueError("Unsafe injector source name")
    return [str(Path("software/native/swd") / item) for item in copies]


def build_key(root: Path) -> str:
    paths = sorted([BUILD_RECIPE, INJECTOR, SELF, *injected_paths(root)])
    h = hashlib.sha256()
    h.update((SCHEMA + "\n").encode())
    for relative in paths:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Missing/unsafe build input: {relative}")
        content = path.read_bytes()
        h.update(relative.encode("utf-8") + b"\0")
        h.update(len(content).to_bytes(8, "big"))
        h.update(content)
    return h.hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tcl_inventory(root: Path) -> list[dict[str, str]]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Missing or symlinked Tcl directory")
    items = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink forbidden: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"Non-regular Tcl entry: {path}")
        items.append({"path": path.relative_to(root).as_posix(), "sha256": sha256(path)})
    if not items:
        raise ValueError("Empty Tcl payload")
    return items


def expected_manifest(directory: Path, key: str) -> dict:
    if len(key) != 64 or any(c not in "0123456789abcdef" for c in key):
        raise ValueError("Invalid build key")
    binary = directory / "openocd"
    if binary.is_symlink() or not binary.is_file() or not binary.stat().st_mode & stat.S_IXUSR:
        raise ValueError("Missing, symlinked, or non-executable OpenOCD binary")
    return {
        "schema": SCHEMA,
        "build_key": key,
        "openocd_sha256": sha256(binary),
        "tcl": tcl_inventory(directory / "tcl"),
    }


def seal(directory: Path, key: str) -> None:
    if set(p.name for p in directory.iterdir()) != {"openocd", "tcl"}:
        raise ValueError("Unexpected contents before sealing build cache")
    payload = expected_manifest(directory, key)
    (directory / "cache-manifest.json").write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def verify(directory: Path, key: str) -> None:
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Missing/unsafe build cache root")
    if set(p.name for p in directory.iterdir()) != {"openocd", "tcl", "cache-manifest.json"}:
        raise ValueError("Unexpected or missing cache entries")
    record = directory / "cache-manifest.json"
    if record.is_symlink() or not record.is_file():
        raise ValueError("Missing/unsafe cache manifest")
    actual = json.loads(record.read_text(encoding="utf-8"))
    expected = expected_manifest(directory, key)
    if actual != expected:
        raise ValueError("Cache key, binary, or Tcl digest mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("key", "seal", "verify"))
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--key")
    args = parser.parse_args()
    try:
        if args.command == "key":
            print(build_key(args.repository.resolve()))
        else:
            if args.directory is None or args.key is None:
                raise ValueError("--directory and --key are required")
            if args.command == "seal":
                seal(args.directory, args.key)
            else:
                verify(args.directory, args.key)
                print("OPENOCD5088_ARMV7_CACHE_INTEGRITY_PASS")
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"OPENOCD5088_ARMV7_CACHE_FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
