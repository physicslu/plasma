#!/usr/bin/env python3
"""Host-only FPGA Build Diagnostic v1: structured, sanitized, stage-aware evidence.

Library only. Importing this module NEVER starts Vivado, a runner or hardware.
A failure is a proven *stage outcome*, not an inferred hardware root cause.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

SCHEMA = "plasma.fpga.build_diagnostics.v1"
STAGES = (
    "PREFLIGHT", "BOARD_PREPARE", "OUTPUT_PREPARE",
    "VIVADO_IMPLEMENTATION", "ARTIFACT_VERIFY", "EVIDENCE_WRITE",
)
_SAFE_CODE = re.compile(r"BUILD_[A-Z0-9_]{3,80}\\Z")
_SAFE_SHA = re.compile(r"[0-9a-f]{40}\\Z")
_SAFE_TYPES = frozenset((
    "PermissionError", "FileNotFoundError", "TimeoutExpired",
    "OSError", "ValueError", "RuntimeError", "CalledProcessError",
))
_ARTIFACT_NAMES = frozenset((
    "vivado_stdout", "vivado_stderr", "timing_summary", "drc",
    "methodology", "check_timing", "bit", "hwh", "host_receipt",
))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class DiagnosticSession:
    """A monotonically ordered stage ledger, with no host paths or secrets."""

    def __init__(self, *, execution_path: str, source_sha: str,
                 evidence_dir: Path):
        if execution_path not in ("path2-cli", "path3-codex"):
            raise ValueError("BUILD_DIAG_PATH_DENIED")
        if not _SAFE_SHA.fullmatch(source_sha):
            raise ValueError("BUILD_DIAG_SHA_DENIED")
        if not evidence_dir.is_dir() or evidence_dir.is_symlink():
            raise ValueError("BUILD_DIAG_EVIDENCE_DIR_DENIED")
        self.execution_path = execution_path
        self.source_sha = source_sha
        self.evidence_dir = evidence_dir
        self.stage = None
        self.events = []
        self.artifacts = {}
        self.checks = {}
        self.status = "RUNNING"
        self.error_code = None
        self.exception_type = None
        self.cause_type = None
        self.root_cause_status = "UNKNOWN"

    def enter(self, stage: str) -> None:
        if stage not in STAGES:
            raise ValueError("BUILD_DIAG_STAGE_DENIED")
        next_index = STAGES.index(stage)
        if self.stage is not None:
            old_index = STAGES.index(self.stage)
            if next_index <= old_index or self.status != "RUNNING":
                raise ValueError("BUILD_DIAG_STAGE_ORDER_DENIED")
            self.events[-1]["status"] = "PASS"
        self.stage = stage
        self.events.append({"stage": stage, "status": "RUNNING"})

    def check(self, name: str, result: bool) -> None:
        if name not in ("license_environment_present", "build_root_writable",
                        "vivado_settings_readable"):
            raise ValueError("BUILD_DIAG_CHECK_DENIED")
        self.checks[name] = bool(result)

    def artifact(self, name: str, path: Path) -> None:
        if name not in _ARTIFACT_NAMES or not path.is_file() or path.is_symlink():
            raise ValueError("BUILD_DIAG_ARTIFACT_DENIED")
        self.artifacts[name] = {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
        }

    def complete(self) -> None:
        if self.stage != "EVIDENCE_WRITE" or self.status != "RUNNING":
            raise ValueError("BUILD_DIAG_INCOMPLETE")
        self.events[-1]["status"] = "PASS"
        self.status = "PASS"

    def fail(self, exc: BaseException) -> None:
        if self.status != "RUNNING":
            return
        self.status = "FAIL"
        if self.events:
            self.events[-1]["status"] = "FAIL"
        error = str(exc)
        self.error_code = error if _SAFE_CODE.fullmatch(error) else "BUILD_UNCLASSIFIED_EXCEPTION"
        cls = type(exc).__name__
        self.exception_type = cls if cls in _SAFE_TYPES else (
            "BuildDenied" if cls == "BuildDenied" else "Exception"
        )
        cause = getattr(exc, "__cause__", None)
        if cause is not None:
            cls = type(cause).__name__
            self.cause_type = cls if cls in _SAFE_TYPES else "Exception"
        # A precise observed failure never establishes an unobserved causal chain.
        self.root_cause_status = ("CONFIRMED" if self.error_code in (
            "BUILD_OUTPUT_PERMISSION_DENIED", "BUILD_OUTPUT_READ_ONLY",
            "BUILD_OUTPUT_NO_SPACE", "BUILD_VIVADO_SETTINGS_UNAVAILABLE",
        ) else "UNKNOWN")

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA,
            "status": self.status,
            "execution_path": self.execution_path,
            "source_commit_sha": self.source_sha,
            "failed_stage": self.stage if self.status == "FAIL" else None,
            "error_code": self.error_code,
            "exception_type": self.exception_type,
            "cause_type": self.cause_type,
            "root_cause_status": self.root_cause_status,
            "stages": self.events,
            "checks": self.checks,
            "artifacts": self.artifacts,
            "physical_load": "NOT_RUN",
            "z2_hil": "NOT_RUN",
            "m1": "NO_GO",
        }

    def persist(self) -> Path:
        """Always write a redacted receipt, even when the build fails."""
        path = self.evidence_dir / "plasma-fpga-build-diagnostics.json"
        manifest = self.evidence_dir / "plasma-fpga-build-diagnostics.json.sha256"
        if path.is_symlink() or manifest.is_symlink():
            raise ValueError("BUILD_DIAG_SYMLINK_DENIED")
        data = (json.dumps(self.as_dict(), sort_keys=True, indent=2) + "\\n").encode("utf-8")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
        digest = hashlib.sha256(data).hexdigest()
        fd = os.open(manifest, flags, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(digest + "  plasma-fpga-build-diagnostics.json\\n")
        return path
