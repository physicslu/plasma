#!/usr/bin/env python3
"""KL25 OpenOCD host-only runtime-readiness evidence. Never a silicon/flash qualification.

Executes a pinned installed OpenOCD binary solely with dummy/JTAG configuration
parsing and 'noinit'. It does NOT initialize an adapter or touch a target.
A JTAG parser smoke is deliberately NOT a SWD qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
SOURCE_REVIEW = ROOT / "data/device-catalog/research/nxp-kl25-current-source-review-v2.json"
OPENOCD_RELEASE = ROOT / "release/openocd.json"
EXPECTED_ICPN = "MKL25Z128VLK4"
EXPECTED_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
EXPECTED_RUNTIME = "0.12.0-9ea7f3d647c8"
SCRIPT_PATHS = ("tcl/target/kl25.cfg", "tcl/target/klx.cfg", "tcl/target/swj-dp.tcl")
OPERATIONS = ("READ", "VERIFY", "PROGRAM", "ERASE_SECTOR")
MISSING = (
    "REAL_SWD_SESSION_AND_DEBUG_ID",
    "EXACT_SILICON_SDID_REVISION_FCFG_GEOMETRY",
    "ACTUAL_FCF_MUTATION_AND_SECURITY_BOUNDARY",
    "REAL_TARGET_READ_VERIFY_PROGRAM_ERASE_EVIDENCE",
    "INDEPENDENT_OPERATION_QUALIFICATION_REVIEW",
)
Runner = Callable[..., subprocess.CompletedProcess[str]]


class Kl25ReadinessError(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise Kl25ReadinessError(reason)


def sha256_file(path: Path) -> str:
    try:
        with path.open("rb") as fp:
            digest = hashlib.sha256()
            for chunk in iter(lambda: fp.read(1024 * 1024), b""):
                digest.update(chunk)
            return digest.hexdigest()
    except OSError as exc:
        raise Kl25ReadinessError(f"unreadable file: {path}") from exc


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Kl25ReadinessError(f"invalid evidence: {path}") from exc
    require(isinstance(data, dict), "evidence object required")
    return data


def binary_architecture(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            h = stream.read(20)
    except OSError as exc:
        raise Kl25ReadinessError("binary not readable") from exc
    require(len(h) == 20 and h[:4] == b"\x7fELF" and h[5] in (1, 2),
            "invalid ELF header")
    machine = struct.unpack("<H" if h[5] == 1 else ">H", h[18:20])[0]
    require(machine in (40, 62), "unexpected OpenOCD architecture")
    return {40: "armv7l", 62: "x86_64"}[machine]


def validate_inputs(binary: Path, scripts_root: Path, receipt_path: Path) -> dict[str, Any]:
    release, audit, receipt = (read_json(p) for p in
                               (OPENOCD_RELEASE, SOURCE_REVIEW, receipt_path))
    require(release.get("engine") == "openocd"
            and release.get("version") == "0.12.0"
            and release.get("source_commit") == EXPECTED_COMMIT
            and release.get("runtime_id") == EXPECTED_RUNTIME,
            "OpenOCD release pin changed")
    require(audit.get("review_boundary") == "SOURCE_ONLY_NO_EXECUTION"
            and audit.get("exact") == {
                "manufacturer": "NXP", "icpn": EXPECTED_ICPN,
                "other_kl25_variants_inherited": 0,
            }
            and audit.get("provider", {}).get("source_commit") == EXPECTED_COMMIT,
            "KL25 upstream source review drift")
    require(audit.get("result", {}).get("programming_qualification_state") == "CANDIDATE"
            and audit["result"].get("catalog_level") == 1
            and audit["result"].get("execution_authorized") is False
            and audit["result"].get("supported_exact_icpn_count_new") == 0,
            "source review cannot grant L2 or execution")
    require(receipt.get("result") == "PASS"
            and receipt.get("evidence_level") == "openocd-runtime-local-install"
            and receipt.get("source_commit") == EXPECTED_COMMIT
            and receipt.get("openocd_version") == "0.12.0"
            and receipt.get("runtime_id") == EXPECTED_RUNTIME
            and receipt.get("hardware_runtime_ready") is False
            and receipt.get("starts_openocd_service") is False,
            "installed runtime receipt is not host-only / pinned")
    require(receipt.get("binary") == str(binary)
            and receipt.get("scripts_root") == str(scripts_root),
            "runtime paths do not match install receipt")
    require(binary.is_file() and binary.is_absolute()
            and scripts_root.is_dir() and scripts_root.is_absolute(),
            "installed runtime paths missing / relative")
    architecture = binary_architecture(binary)
    require(receipt.get("architecture") == architecture,
            "installed runtime architecture mismatch")
    digest_fields = ("artifact_sha256", "payload_sha256")
    require(all(isinstance(receipt.get(field), str)
                and re.fullmatch("[0-9a-f]{64}", receipt[field])
                for field in digest_fields),
            "artifact/payload SHA256 provenance missing")
    scripts: dict[str, str] = {}
    for rel in SCRIPT_PATHS:
        path = scripts_root / rel.removeprefix("tcl/")
        require(path.is_file(), f"missing installed Tcl: {rel}")
        payload = path.read_bytes()
        locked = audit.get("source_files", {}).get(rel, {})
        require(len(payload) == locked.get("bytes")
                and git_blob_sha1(payload) == locked.get("git_blob"),
                f"installed Tcl Git blob mismatch: {rel}")
        scripts[rel] = sha256_file(path)
    require(audit.get("source_files", {}).get("src/flash/nor/kinetis.c", {}).get("git_blob")
            == "7137b4aa078719af31122f8276494f006589e8ab",
            "Kinetis driver source lock drift")
    return {
        "architecture": architecture,
        "binary_sha256": sha256_file(binary),
        "artifact_sha256": receipt["artifact_sha256"],
        "payload_sha256": receipt["payload_sha256"],
        "source_commit": EXPECTED_COMMIT,
        "runtime_id": EXPECTED_RUNTIME,
        "script_sha256": scripts,
    }


def build_safe_argv(binary: Path, scripts_root: Path) -> list[str]:
    # This is a config parser smoke; the dummy driver is JTAG, NOT SWD.
    # No 'init', 'reset', 'halt', 'flash', 'mdw' or target commands.
    return [
        str(binary), "-s", str(scripts_root),
        "-c", "noinit",
        "-f", "interface/dummy.cfg",
        "-c", "transport select jtag",
        "-f", "target/kl25.cfg",
        "-c", 'echo "PLASMA_KL25_NOINIT_CONFIG_ONLY=1"',
        "-c", "shutdown",
    ]


def validate_argv(argv: list[str], binary: Path, scripts_root: Path) -> None:
    require(argv == build_safe_argv(binary, scripts_root),
            "unapproved OpenOCD command; noinit-only parser permitted")


def qualification_boundary_claim(payload: dict[str, Any]) -> dict[str, Any]:
    """Never interpret host-only or unverified reported PASS as real DUT evidence."""
    require(payload.get("exact_icpn") == EXPECTED_ICPN, "wrong ICPN")
    require(payload.get("source_commit") == EXPECTED_COMMIT, "wrong Provider commit")
    require(payload.get("evidence_boundary") == "HOST_ONLY_NOINIT",
            "unverified external/hardware evidence is not admissible")
    require(payload.get("software_state") == "CANDIDATE"
            and payload.get("catalog_level") == 1
            and payload.get("job_selectable") is False
            and payload.get("execution_authorized") is False
            and payload.get("installed_runtime_attested") is False
            and payload.get("hardware_runtime_ready") is False,
            "offline evidence must not authorize programming")
    require(payload.get("host_parser") == "PASS"
            and payload.get("parser_adapter") == "dummy"
            and payload.get("parser_transport") == "jtag"
            and payload.get("swd_session_qualified") is False
            and payload.get("real_silicon_observed") is False,
            "host-only parser may not claim real SWD or silicon observation")
    require(payload.get("operations") == {op: "UNKNOWN" for op in OPERATIONS},
            "host-only evidence cannot qualify operations")
    require(payload.get("missing_gates") == list(MISSING), "qualification blockers missing")
    return {
        "admission": "BLOCKED",
        "catalog_level": 1,
        "software_state": "CANDIDATE",
        "missing_gates": list(MISSING),
    }


def run_acceptance(
    binary: Path, scripts_root: Path, receipt: Path,
    *, runner: Runner = subprocess.run, timeout: float = 30.0
) -> dict[str, Any]:
    require(0 < timeout <= 60, "timeout out of safe range")
    provenance = validate_inputs(binary, scripts_root, receipt)
    try:
        version = runner([str(binary), "--version"], check=False,
                         capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Kl25ReadinessError("failed binary version probe") from exc
    banner = (version.stdout or "") + (version.stderr or "")
    require(version.returncode == 0
            and re.search(r"Open On-Chip Debugger\s+0\.12\.0(?:-g[0-9a-f]+)?(?:\s|$)", banner) is not None,
            "installed binary version differs from pinned release")
    argv = build_safe_argv(binary, scripts_root)
    validate_argv(argv, binary, scripts_root)
    try:
        cp = runner(argv, check=False, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Kl25ReadinessError("noinit parser execution failed") from exc
    output = (cp.stdout or "") + (cp.stderr or "")
    require(cp.returncode == 0 and "PLASMA_KL25_NOINIT_CONFIG_ONLY=1" in output,
            f"pinned KL25 Tcl noinit parser failed: {output[-1200:]}")
    evidence = {
        "schema_version": 1,
        "exact_icpn": EXPECTED_ICPN,
        "source_commit": EXPECTED_COMMIT,
        "evidence_boundary": "HOST_ONLY_NOINIT",
        "host_parser": "PASS",
        "parser_adapter": "dummy",
        "parser_transport": "jtag",
        "swd_session_qualified": False,
        "real_silicon_observed": False,
        "source_binary_sha256": provenance["binary_sha256"],
        "runtime_provenance": provenance,
        "software_state": "CANDIDATE",
        "catalog_level": 1,
        "job_selectable": False,
        "execution_authorized": False,
        "installed_runtime_attested": False,
        "hardware_runtime_ready": False,
        "operations": {op: "UNKNOWN" for op in OPERATIONS},
        "missing_gates": list(MISSING),
    }
    evidence["qualification"] = qualification_boundary_claim(evidence)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openocd", type=Path, required=True)
    parser.add_argument("--scripts-root", type=Path, required=True)
    parser.add_argument("--install-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = run_acceptance(args.openocd, args.scripts_root, args.install_receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("NXP_KL25_RUNTIME_READINESS_HOST_ONLY_PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Kl25ReadinessError as exc:
        print(f"NXP_KL25_RUNTIME_READINESS_FAIL: {exc}")
        raise SystemExit(1)
