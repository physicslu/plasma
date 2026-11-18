#!/usr/bin/env python3
"""Historical replay of the frozen STM32F103C vendor-neutral admission v1 sidecar.

IC Catalog / admission governance is independent of the PPU Runtime. The v1
generator (``stm32f103c_vendor_neutral_admission.py``) and its tests are frozen
historical artifacts and are reused unchanged. v1 verified its retired
compiler evidence by reading ``software/python/plasma_interfaces/openocd_plan.py``
from the working tree; this replay instead reads that evidence from the fixed
``migration_base_commit`` and requires its Git blob to equal the pinned
``git_blob_sha1``. The Runtime compiler may therefore be deleted while the v1
artifacts and digests stay byte-for-byte reproducible.

The replay never reads the working-tree compiler, claims no hardware readiness,
and authorizes no Runtime execution.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterator

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import stm32f103c_vendor_neutral_admission as v1  # noqa: E402

# Original v1 sidecar identity (v1 generator at main 28ee5761 with the in-tree
# compiler blob a3f6f1f9...). The replay must reproduce exactly these bytes.
EXPECTED_V1_RELEASE_DIGEST = "16ad9128f60fa1e99f9ef2a263e0c3d43785e2ceeecdeffeefe79a0dfaa4d9c2"
EXPECTED_V1_FILES = {
    "qualification.json": "ad5f39564e94af2a49befc53290d3ed7f6694269a53c7a73aab90a5f807715e1",
    "stm32f103c8t6-vendor-neutral-admission-package.json":
        "ff203c02d711ec77204ad2b351610c78b3890e350d8ac6248a321b0681ff4420",
    "stm32f103cbt6-vendor-neutral-admission-package.json":
        "071c085766860ed541786bd31cb604b614eab2ec37bcd1d542864cb0b638c872",
}
_HEX40 = re.compile(r"[0-9a-f]{40}")


def _git(*args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(v1.REPO_ROOT), *args],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise v1.MigrationError(
            "retired compiler evidence unavailable in Git history (full history required)"
        ) from exc


def retired_compiler_bytes(contract: dict[str, Any] | None = None) -> bytes:
    """Read the retired compiler from the fixed commit; verify the pinned blob."""
    contract = v1.CONTRACT if contract is None else contract
    commit = contract.get("migration_base_commit")
    entry = contract["legacy_inputs"]["compiler"]
    blob, path = entry.get("git_blob_sha1"), entry.get("path")
    v1.require(isinstance(commit, str) and _HEX40.fullmatch(commit) is not None,
               "migration base commit is invalid")
    v1.require(isinstance(blob, str) and _HEX40.fullmatch(blob) is not None,
               "retired compiler Git blob ID is invalid")
    v1.require(isinstance(path, str) and path and not path.startswith("/") and ".." not in path,
               "retired compiler historical path is invalid")
    resolved = _git("rev-parse", "--verify", "--quiet", f"{commit}:{path}").decode().strip()
    v1.require(resolved == blob, "retired compiler blob at migration base commit drifted")
    v1.require(_git("cat-file", "-t", blob).decode().strip() == "blob",
               "retired compiler evidence is not a Git blob")
    raw = _git("cat-file", "blob", blob)
    v1.require(_blob_id(raw) == blob, "retired compiler Git blob content mismatch")
    return raw


def _blob_id(raw: bytes) -> str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


@contextlib.contextmanager
def historical_compiler_evidence() -> Iterator[None]:
    """Serve v1's compiler input from Git history instead of the working tree."""
    raw = retired_compiler_bytes()
    compiler_path = v1.CONTRACT["legacy_inputs"]["compiler"]["path"]
    original = v1._repo_path
    with tempfile.TemporaryDirectory(prefix="stm32f103c-retired-compiler-") as temp:
        frozen = Path(temp) / "retired-compiler-evidence.py"
        frozen.write_bytes(raw)

        def repo_path(relative: str) -> Path:
            return frozen if relative == compiler_path else original(relative)

        v1._repo_path = repo_path
        try:
            yield
        finally:
            v1._repo_path = original


def build_sidecar(output_dir: Path) -> dict[str, Any]:
    with historical_compiler_evidence():
        manifest = v1.build_sidecar(output_dir)
    v1.require(manifest.get("files") == EXPECTED_V1_FILES,
               "replayed v1 artifact digests differ from the original v1 sidecar")
    v1.require(manifest.get("release_digest") == EXPECTED_V1_RELEASE_DIGEST,
               "replayed v1 release digest differs from the original v1 sidecar")
    return manifest


def validate() -> dict[str, Any]:
    with historical_compiler_evidence():
        v1.validate_frozen_inputs()
        return {
            target: v1.validate_projection(v1.build_package(target), target)
            for target in sorted(v1.CONTRACT["targets"])
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    result = build_sidecar(args.output_dir) if args.output_dir is not None else validate()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
