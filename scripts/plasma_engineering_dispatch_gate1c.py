#!/usr/bin/env python3
"""Gate 1C: read-only ruleset, workflow trigger and credential preflight.

No GitHub writes, dispatcher event trigger, device access, or Codex execution.
Static approval is never proof of live GitHub ruleset behavior.
"""
from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re

CLAIM_BRANCH = "plasma-engineering-claims/900002/example-r1"
CLAIM_REF_PATTERN = "refs/heads/plasma-engineering-claims/**/*"
REQUIRED_RULES = {"deletion", "update", "non_fast_forward"}
RISK_EVENTS = {"create", "push", "workflow_run"}
ON = re.compile(r"""^(?:on|"on"|'on')\s*:\s*(.*?)\s*$""")
EVENT = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*?)\s*$")
FILTER = re.compile(r"^    (branches|branches-ignore)\s*:\s*(.*?)\s*$")
NONRISK = {"pull_request", "pull_request_target", "workflow_dispatch", "issue_comment",
           "issues", "schedule", "workflow_call", "repository_dispatch", "delete",
           "release", "status", "check_run", "check_suite", "discussion", "fork",
           "push_request", "pull_request_review", "pull_request_review_comment",
           "watch", "merge_group", "deployment", "deployment_status", "gollum",
           "page_build", "branch_protection_rule", "workflow_job", "label",
           "member", "membership", "milestone", "public", "registry_package",
           "project", "project_card", "project_column"}


class Denied(ValueError):
    pass


def fail(reason: str) -> None:
    raise Denied(reason)


def ruleset_preflight(rulesets: object) -> dict:
    """Require precise active protection and zero bypass. No live assertion."""
    if type(rulesets) is not list:
        fail("RULESET_LIST_INVALID")
    eligible = 0
    for item in rulesets:
        if type(item) is not dict:
            fail("RULESET_ENTRY_INVALID")
        if item.get("enforcement") != "active" or item.get("target") != "branch":
            continue
        cond = item.get("conditions")
        if type(cond) is not dict or type(cond.get("ref_name")) is not dict:
            continue
        ref = cond["ref_name"]
        if type(ref.get("include")) is not list or type(ref.get("exclude")) is not list:
            continue
        if CLAIM_REF_PATTERN not in ref["include"] or ref["exclude"]:
            continue
        if item.get("bypass_actors") != []:
            continue
        rules = item.get("rules")
        if type(rules) is not list or any(type(r) is not dict for r in rules):
            continue
        if REQUIRED_RULES.issubset({r.get("type") for r in rules}):
            eligible += 1
    return {"status": "RULESET_CONFIG_MATCH_ONLY" if eligible else "NO_GO_CLAIM_RULESET_MISSING",
            "matching_rulesets": eligible,
            "required": sorted(REQUIRED_RULES),
            "live_create_update_delete_attestation": "NOT_RUN",
            "runtime_enabled": False}


def scalar(s: str) -> str | None:
    s = s.split(" #", 1)[0].strip()
    if not s:
        return None
    if s.startswith(("'", '"')) and s.endswith(s[0]):
        s = s[1:-1]
    if not s or any(x in s for x in ("\t", "#", "{", "}", "[", "]", "&", "|")):
        return None
    return s


def yaml_inline_list(s: str) -> list[str] | None:
    s = s.split(" #", 1)[0].strip()
    if not (s.startswith("[") and s.endswith("]")):
        return None
    pieces = s[1:-1].split(",")
    result = [scalar(p) for p in pieces]
    return None if any(v is None for v in result) else result


def triggers(content: str) -> tuple[dict[str, list[str]], list[str]]:
    """Conservative top-level YAML subset; unsupported is review-needed."""
    lines = content.splitlines()
    headers = [(i, ON.match(line)) for i, line in enumerate(lines) if ON.match(line)]
    if len(headers) != 1:
        return {}, ["ON_NOT_UNIQUE_OR_MISSING"]
    begin, on_match = headers[0]
    inline = on_match.group(1).split(" #", 1)[0].strip()
    events: dict[str, list[str]] = {}
    errors: list[str] = []
    if inline:
        if inline.startswith("["):
            names = yaml_inline_list(inline)
            if names is None:
                return {}, ["ON_INLINE_INVALID"]
            events = {n: [] for n in names}
        else:
            name = scalar(inline)
            if name is None or not re.fullmatch(r"[a-z_]+", name):
                return {}, ["ON_INLINE_INVALID"]
            events[name] = []
    else:
        current = None
        branch_kind = None
        for line in lines[begin + 1:]:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if line[0] not in " \t":
                break
            if "\t" in line[:len(line)-len(line.lstrip())]:
                errors.append("YAML_INDENT_TAB")
                continue
            em = EVENT.match(line)
            if em:
                current = em.group(1)
                branch_kind = None
                if current in events:
                    errors.append("DUPLICATE_EVENT")
                events.setdefault(current, [])
                continue
            if current != "push":
                continue
            filt = FILTER.match(line)
            if filt:
                branch_kind = filt.group(1)
                value = filt.group(2).strip()
                if value:
                    items = yaml_inline_list(value)
                    if items is None:
                        errors.append("BRANCH_INLINE_UNPARSEABLE")
                    else:
                        events["push"].extend(items if branch_kind == "branches" else ["!" + x for x in items])
                    branch_kind = None
                continue
            list_item = re.match(r"^\s{6,}-\s+(.+)$", line)
            if list_item and branch_kind:
                item = scalar(list_item.group(1))
                if item is None:
                    errors.append("BRANCH_ITEM_UNPARSEABLE")
                else:
                    events["push"].append(item if branch_kind == "branches" else "!" + item)
            elif re.match(r"^    \w[\w-]*:", line):
                branch_kind = None
        if not events:
            errors.append("ON_EMPTY")
    if any(e not in RISK_EVENTS | NONRISK for e in events):
        errors.append("UNKNOWN_EVENT")
    return events, sorted(set(errors))


def inspect_workflow(name: str, source: str) -> dict:
    events, errors = triggers(source)
    risks = []
    if "create" in events:
        risks.append("CREATE_REF_EVENT")
    if "workflow_run" in events:
        risks.append("WORKFLOW_RUN_CHAIN")
    if "push" in events:
        patterns = events["push"]
        positives = [p for p in patterns if not p.startswith("!")]
        # Do not trust paths filters as a safety gate for ref creation.
        if not patterns or not positives:
            risks.append("PUSH_UNRESTRICTED_OR_IGNORE_ONLY")
        elif any(fnmatchcase(CLAIM_BRANCH, p) for p in positives):
            risks.append("PUSH_CLAIM_BRANCH")
    if errors:
        risks.append("UNCLASSIFIED_TRIGGER")
    flags = [name for name, expr in (
        ("SELF_HOSTED", r"runs-on:\s*(?:\[[^\n]*self-hosted|self-hosted)"),
        ("CONTENTS_WRITE", r"contents:\s*write"),
        ("ACTIONS_WRITE", r"actions:\s*write"),
        ("SECRET_REFERENCE", r"secrets\.[A-Za-z_]+"),
    ) if re.search(expr, source, re.I)]
    return {"workflow": name, "events": sorted(events), "risks": sorted(set(risks)),
            "privilege_hints": flags}


def workflow_audit(directory: Path) -> dict:
    if directory.is_symlink() or not directory.is_dir():
        fail("WORKFLOW_DIRECTORY_INVALID")
    files = sorted([*directory.glob("*.yml"), *directory.glob("*.yaml")])
    if not files:
        fail("WORKFLOWS_EMPTY")
    rows = []
    for path in files:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 524288:
            rows.append({"workflow": path.name, "events": [], "risks": ["UNREADABLE_FILE"], "privilege_hints": []})
            continue
        try:
            rows.append(inspect_workflow(path.name, path.read_text(encoding="utf-8")))
        except (UnicodeError, OSError):
            rows.append({"workflow": path.name, "events": [], "risks": ["UNREADABLE_FILE"], "privilege_hints": []})
    exposed = [x for x in rows if x["risks"]]
    return {"status": "NO_GO_WORKFLOW_TRIGGER_RISK" if exposed else "STATIC_TRIGGER_SCAN_PASS",
            "scanned": len(rows), "total": len(files), "potential_exposures": len(exposed),
            "results": rows, "live_ref_creation_test": "NOT_RUN",
            "token_event_behavior_untested": True, "runtime_enabled": False}


def credential_contract(doc: object) -> dict:
    """Role separation is DESIGN ONLY; no claim about real GitHub tokens."""
    if type(doc) is not dict or set(doc) != {"schema_version", "status", "roles"}:
        fail("CREDENTIAL_DOCUMENT_INVALID")
    if doc["schema_version"] != "plasma.engineering.credentials.v1" or doc["status"] != "OFFLINE_CONTRACT_ONLY":
        fail("CREDENTIAL_VERSION_DENIED")
    roles = doc["roles"]
    if type(roles) is not dict or set(roles) != {"authorizer", "claimer", "worker", "publisher"}:
        fail("CREDENTIAL_ROLES_DENIED")
    requirements = {
        "authorizer": ({"contents": "read"}, False, False),
        "claimer": ({"contents": "write"}, True, False),
        "worker": ({"contents": "read"}, False, True),
        "publisher": ({"contents": "write", "pull-requests": "write"}, False, False),
    }
    for name, (perms, create, model) in requirements.items():
        role = roles[name]
        if type(role) is not dict or set(role) != {"permissions", "create_claim", "run_codex",
                                                   "github_write_token_to_codex",
                                                   "persist_credentials", "hosted_only"}:
            fail("CREDENTIAL_ROLE_FIELDS_DENIED")
        if (role["permissions"] != perms
            or type(role["create_claim"]) is not bool or role["create_claim"] != create
            or type(role["run_codex"]) is not bool or role["run_codex"] != model
            or role["github_write_token_to_codex"] is not False
            or role["persist_credentials"] is not False
            or role["hosted_only"] is not True):
            fail("CREDENTIAL_PRIVILEGE_BOUNDARY_DENIED")
    return {"status": "CREDENTIAL_CONTRACT_ONLY_PASS", "runtime_enabled": False,
            "live_token_isolation_test": "NOT_RUN"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate 1C offline security preflight")
    parser.add_argument("operation", choices=("audit-workflows", "check-rulesets", "check-credentials"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    try:
        if args.operation == "audit-workflows":
            if args.directory is None or args.input is not None:
                fail("ARGUMENTS_INVALID")
            report = workflow_audit(args.directory)
        else:
            if args.input is None or args.directory is not None:
                fail("ARGUMENTS_INVALID")
            if args.input.is_symlink() or not args.input.is_file() or args.input.stat().st_size > 1048576:
                fail("INPUT_NOT_REGULAR")
            data = json.loads(args.input.read_text(encoding="utf-8"))
            report = ruleset_preflight(data) if args.operation == "check-rulesets" else credential_contract(data)
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        allowed = ("STATIC_TRIGGER_SCAN_PASS", "CREDENTIAL_CONTRACT_ONLY_PASS", "RULESET_CONFIG_MATCH_ONLY")
        return 2 if args.strict and report["status"] not in allowed else 0
    except (Denied, OSError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, Denied) else "INPUT_PARSE_OR_IO_DENIED"
        print(json.dumps({"status": "NO_GO_INVALID_INPUT", "reason": reason, "runtime_enabled": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
