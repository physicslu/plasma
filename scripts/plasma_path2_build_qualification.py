#!/usr/bin/env python3
"""Read-only F1-B Vivado Build Qualification for existing Path 2 receipts.

This reviewer consumes files from the exact pinned candidate worktree.
It does not run Vivado, access devices, authorize hardware or sign evidence.
The trusted Dispatcher must authenticate source SHA and execute the existing
Vivado Build first. A hash receipt alone is never a Build PASS.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
MARKER = b"FIXED_F1_BITSTREAM_BUILD_PASS_HOST_ONLY_NOT_Z2"
REPORTS = ("timing_summary.rpt", "drc.rpt", "methodology.rpt",
           "utilization.rpt", "check_timing.rpt")
ROOT = Path(__file__).resolve().parents[1]


class QualificationDenied(ValueError):
    """Never infer hardware qualification from an invalid artifact."""


def need(test: bool, reason: str) -> None:
    if not test:
        raise QualificationDenied(reason)


def sha(value: object, width: int = 64) -> bool:
    return type(value) is str and (SHA40 if width == 40 else SHA64).fullmatch(value) is not None


def actual_file(path: Path, root: Path, maximum: int) -> bytes:
    """Bound reads to non-symlink, workspace-contained regular files."""
    need(path.is_file() and not path.is_symlink(), "BUILD_FILE_MISSING")
    need(path.resolve(strict=True).is_relative_to(root), "BUILD_FILE_ESCAPE")
    size = path.stat().st_size
    need(0 < size <= maximum, "BUILD_FILE_SIZE_DENIED")
    data = path.read_bytes()
    need(len(data) == size, "BUILD_FILE_CHANGED")
    return data


def _verify_hwh(bit: Path, hwh: Path, reports: Path, source: str) -> dict:
    """Reuse canonical HWH/BIT/report verifier from the trusted main checkout."""
    verifier = ROOT / "pl/projects/z2-fixed-unified-site1/verify_hwh.py"
    need(verifier.is_file() and not verifier.is_symlink(), "BUILD_VERIFIER_MISSING")
    spec = importlib.util.spec_from_file_location("plasma_path2_reviewed_hwh", verifier)
    need(spec is not None and spec.loader is not None, "BUILD_VERIFIER_INVALID")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_artifacts(hwh=hwh, bit=bit, reports=reports,
                                   source_sha=source)


def qualify_host_build(raw: dict, *, workspace: Path, pinned_sha: str) -> dict:
    """Return the *host-only* APPROVED decision consumed by the existing adapter.

    Independent checks: pinned source, exact reviewed output directory, actual
    BIT/HWH/reports/log bytes, the build success marker, canonical HWH mapping,
    and digest equality. Not an assertion that Z2 was programmed.
    """
    need(sha(pinned_sha, 40) and type(raw) is dict,
         "BUILD_SOURCE_OR_RECEIPT_DENIED")
    need(raw.get("status") == "HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED"
         and raw.get("execution_capability") == "vivado-host-build"
         and raw.get("source_sha") == pinned_sha
         and raw.get("physical_load") == "NOT_RUN"
         and raw.get("z2_hil") == "NOT_RUN", "BUILD_RECEIPT_NOT_HOST_ONLY")
    need(sha(raw.get("bit_sha256")) and sha(raw.get("hwh_sha256"))
         and type(raw.get("report_sha256")) is dict
         and set(raw["report_sha256"]) == set(REPORTS)
         and all(sha(x) for x in raw["report_sha256"].values())
         and sha(raw.get("vivado_stdout_sha256"))
         and sha(raw.get("vivado_stderr_sha256")), "BUILD_RECEIPT_DIGEST_DENIED")

    root = workspace.resolve(strict=True)
    build_root = root / "pl/build"
    need(build_root.is_dir() and not build_root.is_symlink(),
         "BUILD_OUTPUT_ROOT_DENIED")
    build_text = raw.get("build_dir")
    need(type(build_text) is str, "BUILD_OUTPUT_PATH_DENIED")
    build = Path(build_text)
    need(build.is_absolute() and build.parent == build_root
         and re.fullmatch(r"fixed-f1-[a-z0-9_-]{4,50}", build.name) is not None
         and build.is_dir() and not build.is_symlink()
         and build.resolve(strict=True) == build,
         "BUILD_OUTPUT_PATH_DENIED")
    project = build / "project"
    bit = project / "z2_fixed_unified_site1.runs/impl_1/system_wrapper.bit"
    hwh = project / "z2_fixed_unified_site1.gen/sources_1/bd/system/hw_handoff/system.hwh"
    reports = build / "reports"
    logs = (build / "vivado-stdout.log", build / "vivado-stderr.log")
    root = root.resolve(strict=True)
    bit_bytes = actual_file(bit, root, 16_000_000)
    hwh_bytes = actual_file(hwh, root, 4_000_000)
    need(hashlib.sha256(bit_bytes).hexdigest() == raw["bit_sha256"]
         and hashlib.sha256(hwh_bytes).hexdigest() == raw["hwh_sha256"],
         "BUILD_BINARY_HASH_MISMATCH")
    for name in REPORTS:
        data = actual_file(reports / name, root, 8_000_000)
        need(hashlib.sha256(data).hexdigest() == raw["report_sha256"][name],
             "BUILD_REPORT_HASH_MISMATCH")
    stdout = actual_file(logs[0], root, 2_000_000)
    # Vivado may emit an empty stderr log on success.
    need(logs[1].is_file() and not logs[1].is_symlink()
         and logs[1].resolve(strict=True).is_relative_to(root)
         and logs[1].stat().st_size <= 2_000_000, "BUILD_STDERR_DENIED")
    stderr = logs[1].read_bytes()
    need(MARKER in stdout and hashlib.sha256(stdout).hexdigest() ==
         raw["vivado_stdout_sha256"]
         and hashlib.sha256(stderr).hexdigest() == raw["vivado_stderr_sha256"],
         "BUILD_VIVADO_LOG_DENIED")
    try:
        verified = _verify_hwh(bit, hwh, reports, pinned_sha)
    except (OSError, ValueError) as exc:
        raise QualificationDenied("BUILD_HWH_VERIFICATION_DENIED") from exc
    need(verified["bit_sha256"] == raw["bit_sha256"]
         and verified["hwh_sha256"] == raw["hwh_sha256"]
         and verified["report_sha256"] == raw["report_sha256"]
         and verified["map"] == raw.get("map")
         and verified["map"]["hardware_runtime_ready"] is False
         and verified["map"]["regions"]["site2_8"] == "ABSENT",
         "BUILD_HWH_OR_MAP_MISMATCH")
    proof = {"source_sha": pinned_sha, "bit_sha256": raw["bit_sha256"],
             "hwh_sha256": raw["hwh_sha256"],
             "report_sha256": raw["report_sha256"],
             "vivado_stdout_sha256": raw["vivado_stdout_sha256"],
             "vivado_stderr_sha256": raw["vivado_stderr_sha256"],
             "qualification_scope": "HOST_ONLY_ARTIFACTS_NOT_Z2"}
    digest = hashlib.sha256(json.dumps(proof, sort_keys=True,
              separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"decision": "APPROVED", "source_sha": pinned_sha,
            "bit_sha256": raw["bit_sha256"], "hwh_sha256": raw["hwh_sha256"],
            "qualification_evidence_sha256": digest}
