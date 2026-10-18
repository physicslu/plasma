#!/usr/bin/env python3
"""PLASMA Issue #981: OFFLINE software-pr candidate / trusted publisher handoff.

This module never runs Codex, creates GitHub refs, pushes, opens a PR, or
authorizes anything. The synthetic source tree is confined to TemporaryDirectory
during hosted CI; all outcomes explicitly deny production-runtime readiness.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory

import plasma_engineering_dispatch_v1 as core

TARGET = "docs/development/software-pr-pilot/RESULT.md"
BASE = b"# PLASMA offline software PR fixture\nStatus: PENDING\n"
EXPECTED = b"# PLASMA offline software PR fixture\nStatus: VERIFIED\n"
DENIED = "OFFLINE_SOFTWARE_PR_CANDIDATE_DENIED"
ACCEPTED = "OFFLINE_FAKE_SOFTWARE_CHANGE_VALIDATED_NO_PR_CREATED"
SCHEMA = "plasma.engineering.software-pr.offline.v1"
MAX_BYTES = 1024
REQUIRED_DENY = frozenset({
    "usb", "z2", "fpga", "mmio", "dut",
    "hub-power", "network-instrument", "host-root",
})


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject(reason: str) -> None:
    raise core.ContractDenied(reason)


def admit(order: object, policy: object) -> dict:
    rule = core.validate_work_order(order, policy)
    if (order["capability"] != "software-pr"
            or order["entrypoint"] != "software-pr"
            or order["authorization_kind"] != "gate1-implementation"
            or order["issue_number"] != 981
            or order["scope"]["allow_repo_paths"] != [TARGET]
            or rule["worker_class"] != "software-isolated"
            or rule["runtime_enabled"] is not False
            or rule["hardware_authorization"] is not False
            or not REQUIRED_DENY.issubset(set(order["scope"]["deny_resources"]))):
        reject("SOFTWARE_PR_SCOPE_OR_RUNTIME_DENIED")
    # This is a schema/scope preflight, NOT authentic owner-event authorization.
    return {
        "work_order_sha256": core.digest(order),
        "reviewed_main_sha": order["reviewed_main_sha"],
        "work_order_id": order["work_order_id"],
        "revision": order["revision"],
        "capability": "software-pr",
        "executor": "FAKE_CODEX_OFFLINE_ONLY",
        "owner_approval_verified": False,
        "runtime_enabled": False,
    }


def _inventory(root: Path) -> dict[str, bytes]:
    """Fail closed on unexpected/symlink/special objects; never follow links."""
    if root.is_symlink() or not root.is_dir():
        reject("WORKSPACE_ROOT_INVALID")
    files: dict[str, bytes] = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            reject("WORKSPACE_SYMLINK_DENIED")
        if stat.S_ISDIR(mode):
            if rel not in {
                    "docs", "docs/development",
                    "docs/development/software-pr-pilot"}:
                reject("WORKSPACE_UNEXPECTED_DIRECTORY")
            continue
        if not stat.S_ISREG(mode) or rel != TARGET:
            reject("WORKSPACE_UNAPPROVED_FILE")
        if path.stat().st_size > MAX_BYTES:
            reject("WORKSPACE_FILE_TOO_LARGE")
        data = path.read_bytes()
        if len(data) > MAX_BYTES or b"\x00" in data:
            reject("WORKSPACE_NON_TEXT_OR_OVERSIZED")
        try:
            data.decode("utf-8")
        except UnicodeError:
            reject("WORKSPACE_NON_UTF8")
        files[rel] = data
    if set(files) != {TARGET}:
        reject("WORKSPACE_EXPECTED_FILE_MISSING")
    return files


def seed_fixture(root: Path) -> str:
    if root.exists() and (root.is_symlink() or any(root.iterdir())):
        reject("WORKSPACE_NOT_EMPTY")
    target = root / TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(BASE)
    assert _inventory(root)[TARGET] == BASE
    return sha256(BASE)


def fake_codex_write(root: Path) -> None:
    """Trusted deterministic CI fixture; never call a real model or shell."""
    path = root / TARGET
    if _inventory(root)[TARGET] != BASE:
        reject("FAKE_INPUT_NOT_BASELINE")
    path.write_bytes(EXPECTED)


def candidate_receipt(order: dict, policy: dict, root: Path,
                      baseline_sha256: str, model_exit: int,
                      tests_success: bool) -> tuple[dict, bytes]:
    plan = admit(order, policy)
    if not isinstance(baseline_sha256, str) or baseline_sha256 != sha256(BASE):
        reject("BASELINE_PROVENANCE_MISMATCH")
    if type(model_exit) is not int or model_exit != 0:
        reject("FAKE_MODEL_NONZERO")
    if tests_success is not True:
        reject("TRUSTED_TESTS_NOT_PASSED")
    data = _inventory(root)[TARGET]
    if data == BASE:
        reject("NO_CHANGE_REJECTED")
    # The offline canary is intentionally a single exact deterministic edit.
    # This is NOT a generic safe patch parser or live-Codex admission rule.
    if data != EXPECTED:
        reject("UNREVIEWED_CONTENT_REJECTED")
    patch = "".join(difflib.unified_diff(
        BASE.decode().splitlines(keepends=True),
        data.decode().splitlines(keepends=True),
        fromfile="a/" + TARGET, tofile="b/" + TARGET,
    )).encode("utf-8")
    if not patch or len(patch) > 2048:
        reject("CANDIDATE_PATCH_INVALID")
    receipt = {
        "schema_version": SCHEMA,
        "status": ACCEPTED,
        "source": "SYNTHETIC_FIXTURE_NOT_REPOSITORY_CHECKOUT",
        "work_order_sha256": plan["work_order_sha256"],
        "reviewed_main_sha": plan["reviewed_main_sha"],
        "work_order_id": plan["work_order_id"],
        "revision": plan["revision"],
        "base_sha256": baseline_sha256,
        "changed_files": [TARGET],
        "candidate_sha256": sha256(data),
        "patch_sha256": sha256(patch),
        "trusted_fixture_test": "PASS",
        "model_exit": model_exit,
        "real_codex_executed": False,
        "owner_approval_verified": False,
        "hardware_access_verified": False,
        "os_sandbox_isolation_verified": False,
        "credential_isolation_verified": False,
        "github_claim_created": False,
        "github_pr_created": False,
        "publisher_enabled": False,
        "runtime_enabled": False,
        "gate2_merge_required": True,
    }
    return receipt, patch


def write_bundle(directory: Path, receipt: dict, patch: bytes) -> None:
    """Artifacts for human/broker design review only, no GitHub write."""
    if directory.is_symlink() or not directory.is_dir() or any(directory.iterdir()):
        reject("BUNDLE_DIRECTORY_UNSAFE_OR_NOT_EMPTY")
    data = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    entries = {"candidate-receipt.json": data, "candidate.patch": patch}
    checksums = []
    for filename, blob in entries.items():
        path = directory / filename
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
        checksums.append(sha256(blob) + "  " + filename)
    (directory / "SHA256SUMS").write_text("\n".join(checksums) + "\n")


def simulate(order: dict, policy: dict, artifacts: Path) -> dict:
    admit(order, policy)
    with TemporaryDirectory(prefix="plasma-software-pr-mock-") as temp:
        root = Path(temp) / "isolated-fixture"
        baseline = seed_fixture(root)
        fake_codex_write(root)
        # Trusted independent canary test; not a model self-reported success.
        tests_success = _inventory(root)[TARGET] == EXPECTED
        receipt, patch = candidate_receipt(
            order, policy, root, baseline, 0, tests_success)
        write_bundle(artifacts, receipt, patch)
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline only; no GitHub publish")
    parser.add_argument("--work-order", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    try:
        order = core.load_json(args.work_order)
        policy = core.load_json(args.policy)
        print(json.dumps(simulate(order, policy, args.artifacts), sort_keys=True))
        return 0
    except (core.ContractDenied, OSError, ValueError, TypeError) as exc:
        # Do not print arbitrary caller-controlled paths or contents.
        reason = str(exc) if isinstance(exc, core.ContractDenied) else "INPUT_IO_DENIED"
        print(json.dumps({"status": DENIED, "reason": reason,
                          "runtime_enabled": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
