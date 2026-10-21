#!/usr/bin/env python3
"""Issue #981: trusted PR-publisher contract, OFFLINE simulation ONLY.

A passing candidate receipt is not authenticated owner authorization, and
there is no GitHub mutating transport here. Any live publisher must have its
own separate vetted credentials and event/claim verification.
"""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path

import plasma_engineering_dispatch_v1 as core
import plasma_engineering_software_pr_pilot as pilot

SCHEMA = "plasma.engineering.software-pr.broker-proposal.v1"
STATUS = "OFFLINE_MOCK_PR_ONLY_NO_GITHUB_ACTION"
TARGET = pilot.TARGET


def fail(code: str) -> None:
    raise core.ContractDenied(code)


def expected_patch() -> bytes:
    return "".join(difflib.unified_diff(
        pilot.BASE.decode().splitlines(keepends=True),
        pilot.EXPECTED.decode().splitlines(keepends=True),
        fromfile="a/" + TARGET, tofile="b/" + TARGET,
    )).encode()


def verify_handoff(order: dict, policy: dict, receipt: object,
                   patch: bytes) -> dict:
    plan = pilot.admit(order, policy)
    if type(receipt) is not dict or set(receipt) != {
            "schema_version", "status", "source", "work_order_sha256",
            "reviewed_main_sha", "work_order_id", "revision", "base_sha256",
            "changed_files", "candidate_sha256", "patch_sha256",
            "trusted_fixture_test", "model_exit", "real_codex_executed",
            "owner_approval_verified", "hardware_access_verified",
            "os_sandbox_isolation_verified", "credential_isolation_verified",
            "github_claim_created", "github_pr_created",
            "publisher_enabled", "runtime_enabled", "gate2_merge_required"}:
        fail("BROKER_RECEIPT_FIELDS_DENIED")
    if (receipt["schema_version"] != pilot.SCHEMA
            or receipt["status"] != pilot.ACCEPTED
            or receipt["source"] != "SYNTHETIC_FIXTURE_NOT_REPOSITORY_CHECKOUT"
            or receipt["work_order_sha256"] != plan["work_order_sha256"]
            or receipt["reviewed_main_sha"] != plan["reviewed_main_sha"]
            or receipt["work_order_id"] != plan["work_order_id"]
            or receipt["revision"] != plan["revision"]
            or receipt["changed_files"] != [TARGET]
            or receipt["base_sha256"] != pilot.sha256(pilot.BASE)
            or receipt["candidate_sha256"] != pilot.sha256(pilot.EXPECTED)
            or type(receipt["model_exit"]) is not int or receipt["model_exit"] != 0
            or receipt["trusted_fixture_test"] != "PASS"
            or receipt["gate2_merge_required"] is not True):
        fail("BROKER_CANDIDATE_PROVENANCE_DENIED")
    for field in ("real_codex_executed", "owner_approval_verified",
                  "hardware_access_verified", "os_sandbox_isolation_verified",
                  "credential_isolation_verified", "github_claim_created",
                  "github_pr_created", "publisher_enabled", "runtime_enabled"):
        if receipt[field] is not False:
            fail("BROKER_PRIVILEGE_ESCALATION_DENIED")
    if (type(patch) is not bytes or patch != expected_patch()
            or receipt["patch_sha256"] != hashlib.sha256(patch).hexdigest()):
        fail("BROKER_PATCH_MISMATCH")
    return {
        "schema_version": SCHEMA,
        "status": STATUS,
        "repository": "physicslu/plasma",
        "base": "main",
        "reviewed_main_sha": plan["reviewed_main_sha"],
        "work_order_sha256": plan["work_order_sha256"],
        "head": "agent/simulated-software-pr-" + plan["work_order_sha256"][:16],
        "title": "test(dispatch): synthetic software PR candidate (NOT REAL)",
        "files": [TARGET],
        "patch_sha256": receipt["patch_sha256"],
        "trusted_gate1_owner_event_verified": False,
        "github_ref_claim_verified": False,
        "github_write_credential_present": False,
        "real_codex_executed": False,
        "publication_enabled": False,
        "actual_github_pr_created": False,
        "gate2_merge_required": True,
    }


class MockPublisher:
    """No SDK, no network and no tokens. Simulated branch+PR state machine."""

    def __init__(self) -> None:
        self.branches: dict[str, str] = {}
        self.prs: dict[str, dict] = {}

    def publish(self, proposal: dict) -> dict:
        if type(proposal) is not dict or set(proposal) != {
                "schema_version", "status", "repository", "base",
                "reviewed_main_sha", "work_order_sha256", "head",
                "title", "files", "patch_sha256",
                "trusted_gate1_owner_event_verified", "github_ref_claim_verified",
                "github_write_credential_present", "real_codex_executed",
                "publication_enabled", "actual_github_pr_created",
                "gate2_merge_required"}:
            fail("MOCK_PUBLISHER_PROPOSAL_INVALID")
        if (proposal["schema_version"] != SCHEMA or proposal["status"] != STATUS
                or proposal["repository"] != "physicslu/plasma"
                or proposal["base"] != "main"
                or proposal["files"] != [TARGET]
                or type(proposal["work_order_sha256"]) is not str
                or len(proposal["work_order_sha256"]) != 64
                or proposal["head"] != "agent/simulated-software-pr-" +
                proposal["work_order_sha256"][:16]
                or type(proposal["patch_sha256"]) is not str
                or len(proposal["patch_sha256"]) != 64
                or proposal["trusted_gate1_owner_event_verified"] is not False
                or proposal["github_ref_claim_verified"] is not False
                or proposal["github_write_credential_present"] is not False
                or proposal["real_codex_executed"] is not False
                or proposal["publication_enabled"] is not False
                or proposal["actual_github_pr_created"] is not False
                or proposal["gate2_merge_required"] is not True):
            fail("MOCK_PUBLISHER_SCOPE_DENIED")
        head = proposal["head"]
        if head in self.branches or head in self.prs:
            fail("MOCK_PUBLISHER_REPLAY_DENIED")
        # These writes affect an in-memory dictionary ONLY, not GitHub.
        self.branches[head] = proposal["reviewed_main_sha"]
        self.prs[head] = {
            "head": head, "base": "main",
            "patch_sha256": proposal["patch_sha256"],
            "state": "MOCK_OPEN_UNMERGED",
        }
        return {
            "status": "MOCK_PR_CREATED_IN_MEMORY_ONLY",
            "head": head,
            "base": "main",
            "mock_pr_count": len(self.prs),
            "github_pr_created": False,
            "gate2_merge_required": True,
        }


def simulate_mock_publisher(order: dict, policy: dict, receipt: dict,
                            patch: bytes) -> dict:
    proposal = verify_handoff(order, policy, receipt, patch)
    mock = MockPublisher()
    result = mock.publish(proposal)
    return {
        "proposal": proposal,
        "mock_receipt": result,
        "runtime_enabled": False,
        "github_pr_created": False,
        "real_codex_executed": False,
    }


def publish_bundle(order: dict, policy: dict, artifacts: Path) -> dict:
    receipt_path = artifacts / "candidate-receipt.json"
    patch_path = artifacts / "candidate.patch"
    if (artifacts.is_symlink() or receipt_path.is_symlink()
            or patch_path.is_symlink() or not receipt_path.is_file()
            or not patch_path.is_file()):
        fail("BROKER_ARTIFACT_PATH_INVALID")
    try:
        receipt = core.load_json(receipt_path)
        patch = patch_path.read_bytes()
    except (OSError, UnicodeError, ValueError) as exc:
        raise core.ContractDenied("BROKER_ARTIFACT_UNREADABLE") from exc
    result = simulate_mock_publisher(order, policy, receipt, patch)
    # Do not add any real GitHub token or branch/PR write API here.
    content = (json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path = artifacts / "mock-publisher-receipt.json"
    with path.open("xb") as writer:
        writer.write(content)
    return result
