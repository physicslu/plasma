#!/usr/bin/env python3
"""Gate 1D: read-only claim protection qualification for PLASMA engineering dispatch.

All results are policy/read-only assessments. Never creates, updates, deletes
GitHub refs, changes rulesets, uses GitHub credentials, or invokes Codex.
"""
from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
from typing import Any

REF_INCLUDE = "refs/heads/plasma-engineering-claims/**/*"
REF_PREFIX = "refs/heads/plasma-engineering-claims/"
RULE_TYPES = frozenset({"deletion", "update", "non_fast_forward"})
BLOCKED_TYPES = frozenset({"creation"})
RULESET_KEYS = frozenset({"name", "target", "enforcement", "bypass_actors",
                           "conditions", "rules"})
STATUS_BLOCKED = "NO_GO_CLAIM_PROTECTION_UNQUALIFIED"
CANARY_TYPES = ("CREATE_ALLOWED", "SECOND_CREATE_REJECTED",
                "UPDATE_REJECTED", "FORCE_UPDATE_REJECTED",
                "DELETE_REJECTED", "READBACK_PRESERVED")
CANARY_REF = "refs/heads/plasma-engineering-claims/900003/ruleset-canary-r1"


class Denied(ValueError):
    """Safe, static failure code."""


def deny(code: str) -> None:
    raise Denied(code)


def validate_proposal(proposal: object) -> dict:
    """Verify only the exact intentionally designed ruleset can be proposed.

    No creation restriction: first claim must be creatable by authorized
    creator, but must be empirically verified once this policy is applied.
    """
    if type(proposal) is not dict or set(proposal) != RULESET_KEYS:
        deny("RULESET_PROPOSAL_FIELDS_INVALID")
    if (proposal.get("name") != "Protect PLASMA engineering dispatch claims"
            or proposal.get("target") != "branch"
            or proposal.get("enforcement") != "active"
            or proposal.get("bypass_actors") != []):
        deny("RULESET_SCOPE_OR_BYPASS_DENIED")
    if proposal.get("conditions") != {"ref_name":{"include":[REF_INCLUDE],"exclude":[]}}:
        deny("RULESET_REF_SCOPE_DENIED")
    rules = proposal.get("rules")
    if type(rules) is not list or len(rules) != len(RULE_TYPES):
        deny("RULESET_RULES_INVALID")
    if any(type(r) is not dict or set(r) != {"type"} for r in rules):
        deny("RULESET_RULE_FIELDS_INVALID")
    kinds = [r["type"] for r in rules]
    if len(set(kinds)) != len(kinds) or set(kinds) != RULE_TYPES:
        deny("RULESET_RULE_TYPES_INVALID")
    if BLOCKED_TYPES & set(kinds):
        deny("RULESET_CREATION_UNINTENTIONALLY_RESTRICTED")
    return {
        "status": "PROPOSAL_SCHEMA_PASS_NOT_APPLIED",
        "rule_types": sorted(RULE_TYPES),
        "create_restriction": "NOT_CONFIGURED_BY_DESIGN",
        "live_github_ruleset": "NOT_VERIFIED",
        "runtime_enabled": False,
    }


def exact_live_ruleset(snapshot: object, proposal: dict) -> dict:
    """Read-only evidence check from a future trusted GitHub GET snapshot.

    Reject weak/missing, evaluation-only, broader rules, bypass, or
    conflicting multiple matching policies. This does not prove GitHub
    enforcement behavior or that snapshot actually came from GitHub.
    """
    validate_proposal(proposal)
    if type(snapshot) is not list:
        deny("GITHUB_RULESET_SNAPSHOT_INVALID")
    matches = []
    for candidate in snapshot:
        if type(candidate) is not dict:
            deny("GITHUB_RULESET_ENTRY_INVALID")
        cond = candidate.get("conditions")
        if type(cond) is not dict or type(cond.get("ref_name")) is not dict:
            continue
        refs = cond["ref_name"]
        inc = refs.get("include")
        exc = refs.get("exclude")
        if type(inc) is not list or type(exc) is not list:
            deny("GITHUB_RULESET_REF_FIELDS_INVALID")
        # Catch broader ~ALL and glob rules which can silently override
        # desired create/update semantics even if the dedicated rule exists.
        covers_claim = any(pattern == "~ALL" or
                           (type(pattern) is str and
                            fnmatchcase(CANARY_REF, pattern))
                           for pattern in inc)
        if not covers_claim:
            continue
        matches.append(candidate)
    if len(matches) != 1:
        return {"status": STATUS_BLOCKED, "matching_claim_rulesets": len(matches),
                "reason":"RULESET_NOT_UNIQUE_OR_MISSING", "runtime_enabled":False}
    candidate = matches[0]
    for k in RULESET_KEYS:
        if candidate.get(k) != proposal.get(k):
            return {"status": STATUS_BLOCKED, "matching_claim_rulesets": 1,
                    "reason":"RULESET_CONFIG_DRIFT", "runtime_enabled":False}
    if (type(candidate.get("id")) is not int or candidate["id"] <= 0
            or candidate.get("source") != "physicslu/plasma"
            or candidate.get("source_type") != "Repository"):
        return {"status": STATUS_BLOCKED, "matching_claim_rulesets": 1,
                "reason":"RULESET_ORIGIN_NOT_VERIFIED", "runtime_enabled":False}
    return {
        "status": "RULESET_READBACK_MATCH_NOT_LIVE_CANARY",
        "ruleset_id": candidate["id"],
        "matching_claim_rulesets": 1,
        "canary": "NOT_RUN",
        "runtime_enabled": False,
    }


def verify_canary_receipts(receipts: object) -> dict:
    """Synthetic canary protocol; must NOT substitute for trusted GitHub runs.

    Input is untrusted; even a matching receipt cannot authorize runtime.
    The future operator MUST independently attest API status, actor,
    effective rules, ref read-back, push-workflow effects and cleanup.
    """
    if type(receipts) is not list or len(receipts) != len(CANARY_TYPES):
        deny("CANARY_RECEIPTS_INCOMPLETE")
    observations = []
    for expected, item in zip(CANARY_TYPES, receipts):
        if (type(item) is not dict or set(item) != {"step", "result", "ref"}
                or item["step"] != expected or item["ref"] != CANARY_REF
                or item["result"] != "OBSERVED"):
            deny("CANARY_RECEIPTS_SEQUENCE_OR_RESULT_DENIED")
        observations.append(item["step"])
    return {
        "status": "CANARY_RECEIPT_SCHEMA_ONLY_NOT_TRUSTED",
        "step_count": len(observations),
        "live_github_attestation": "NOT_VERIFIED",
        "runtime_enabled": False,
    }


def read_json(path: Path) -> object:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1048576:
        deny("JSON_INPUT_INVALID")
    def no_duplicates(pairs: list[tuple[str,Any]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                deny("JSON_DUPLICATE_KEY")
            result[key] = value
        return result
    try:
        return json.loads(path.read_text(encoding="utf-8"),object_pairs_hook=no_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError) as ex:
        raise Denied("JSON_PARSE_DENIED") from ex


def main() -> int:
    p=argparse.ArgumentParser(description="Gate 1D offline-only claim protection qualifier")
    p.add_argument("mode",choices=("proposal","ruleset-readback","canary-receipts"))
    p.add_argument("--proposal",type=Path)
    p.add_argument("--snapshot",type=Path)
    p.add_argument("--receipts",type=Path)
    args=p.parse_args()
    try:
        if args.mode == "proposal":
            if args.proposal is None or args.snapshot is not None or args.receipts is not None:
                deny("ARGUMENTS_INVALID")
            result=validate_proposal(read_json(args.proposal))
        elif args.mode == "ruleset-readback":
            if args.proposal is None or args.snapshot is None or args.receipts is not None:
                deny("ARGUMENTS_INVALID")
            result=exact_live_ruleset(read_json(args.snapshot),read_json(args.proposal))
        else:
            if args.receipts is None or args.proposal is not None or args.snapshot is not None:
                deny("ARGUMENTS_INVALID")
            result=verify_canary_receipts(read_json(args.receipts))
        print(json.dumps(result,sort_keys=True))
        return 2 if result["status"] == STATUS_BLOCKED else 0
    except Denied as ex:
        print(json.dumps({"status":STATUS_BLOCKED,"reason":str(ex),
                          "runtime_enabled":False},sort_keys=True))
        return 2


if __name__=="__main__":
    raise SystemExit(main())
