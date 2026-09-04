#!/usr/bin/env python3
"""Independently verify private PPU activation evidence without weakening it.

This verifier is intentionally separate from the DUT, fault injector, and Manager
crash injector. The host-side verifier must run as a non-root user. It validates
that the canonical activation journal was produced as root:root 0600, then hashes
it through a disposable read-only container with no network and no capabilities.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
CANONICAL_RELATIVE_PATH = Path("gateway-output/ppu-network-activation.json")
RESULT_MARKER = "PLASMA_PRIVATE_PPU_EVIDENCE_VERIFIER_RESULT="


class EvidenceVerifierError(RuntimeError):
    pass


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )


def _journal_metadata(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise EvidenceVerifierError(f"canonical activation journal must not be a symlink: {path}")
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise EvidenceVerifierError(f"canonical activation journal missing: {path}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise EvidenceVerifierError(f"canonical activation journal is not a regular file: {path}")

    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid != 0 or info.st_gid != 0 or mode != 0o600:
        raise EvidenceVerifierError(
            "private activation journal ownership/mode mismatch: "
            f"uid={info.st_uid} gid={info.st_gid} mode={mode:04o}; expected root:root 0600"
        )
    return {
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": f"{mode:04o}",
        "size": info.st_size,
    }


def _hash_in_locked_reader(ppu_work: Path) -> str:
    reader = (
        "import hashlib\n"
        "from pathlib import Path\n"
        "path = Path('/evidence/gateway-output/ppu-network-activation.json')\n"
        "if not path.is_file():\n"
        "    raise SystemExit('canonical activation journal missing')\n"
        "digest = hashlib.sha256()\n"
        "with path.open('rb') as handle:\n"
        "    for block in iter(lambda: handle.read(1024 * 1024), b''):\n"
        "        digest.update(block)\n"
        "print(digest.hexdigest())\n"
    )
    result = _run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/arm/v7",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            "0:0",
            "--volume",
            f"{ppu_work}:/evidence:ro",
            ARM_IMAGE,
            "python3",
            "-c",
            reader,
        ]
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise EvidenceVerifierError(f"locked reader container failed: {detail}")
    digest = result.stdout.strip()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise EvidenceVerifierError(f"invalid SHA-256 digest from locked reader: {digest!r}")
    return digest


def _main(args: argparse.Namespace) -> int:
    if platform.system() != "Linux":
        raise EvidenceVerifierError("private PPU evidence verification requires Linux")
    if os.geteuid() == 0:
        raise EvidenceVerifierError("host verifier must run as a non-root user")
    if shutil.which("docker") is None:
        raise EvidenceVerifierError("docker is required")

    ppu_work = args.ppu_work.resolve()
    journal = ppu_work / CANONICAL_RELATIVE_PATH
    metadata = _journal_metadata(journal)
    digest = _hash_in_locked_reader(ppu_work)
    result = {
        "overall_result": "PASS",
        "verifier_euid": os.geteuid(),
        "journal": str(journal),
        "owner": "root:root",
        "mode": metadata["mode"],
        "uid": metadata["uid"],
        "gid": metadata["gid"],
        "size": metadata["size"],
        "sha256": digest,
        "reader": {
            "network": "none",
            "capabilities": "none",
            "read_only_bind": True,
            "no_new_privileges": True,
        },
    }
    print(RESULT_MARKER + json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify private PPU activation evidence")
    parser.add_argument("--ppu-work", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return _main(args)
    except (EvidenceVerifierError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"private-ppu-evidence-verifier: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
