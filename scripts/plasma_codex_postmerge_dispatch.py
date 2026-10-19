#!/usr/bin/env python3
"""Fail-closed, ONE-PR postmerge admission for the real SWPC Codex Hello C pilot.

Only the GitHub-hosted 'authorize' job may query GitHub. Codex and its
publisher consume the reviewed main SHA after that job has succeeded.
This is not a generic dispatcher and never invokes Codex itself.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from urllib.request import Request, urlopen

REPO = "physicslu/plasma"
OWNER = "physicslu"
GATE1_PR = 1033
GATE1_HEAD = "c83c7094b5a8ae0c3204feb793f3778f73336adb"
GATE1_MERGE = "28da4602c1c7141e5c8561c9bfcf4e57aaa6235d"
ACTIVATION_PR = 0  # Assigned when THIS implementation PR is opened; fail closed.
ACTIVATION_HEAD_BRANCH = "agent/issue981-postmerge-swpc-codex-autodispatch"
MARKER = "PLASMA-AUTO-DISPATCH: issue981-c11-hello-world/gate1-pr1033/executor-codex"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
ALLOWED_FILES = frozenset({
    ".github/workflows/plasma-codex-software-mvp.yml",
    "scripts/plasma_codex_software_mvp.py",
    "scripts/tests/test_plasma_codex_software_mvp.py",
    "scripts/plasma_codex_postmerge_dispatch.py",
    "scripts/tests/test_plasma_codex_postmerge_dispatch.py",
    "docs/development/plasma-codex-software-mvp.md",
})


class Refused(Exception):
    pass


def require(ok: object, why: str) -> None:
    if ok is not True:
        raise Refused(why)


def validate(
    event: dict, env: dict[str, str], gate1: dict, activation: dict,
    associated_prs: list, changed_files: list, commit: dict,
) -> dict:
    """Pure offline validator; independent tests provide mocked GitHub objects."""
    sha = env.get("GITHUB_SHA", "")
    run = env.get("GITHUB_RUN_ID", "")
    require(ACTIVATION_PR >= 1, "ACTIVATION_PR_NOT_PINNED")
    require(
        env.get("GITHUB_EVENT_NAME") == "push"
        and env.get("GITHUB_ACTOR") == OWNER
        and env.get("GITHUB_REPOSITORY") == REPO
        and env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and SHA40.fullmatch(sha) is not None
        and re.fullmatch(r"[1-9][0-9]{0,19}", run) is not None,
        "BAD_GITHUB_CONTEXT",
    )
    require(
        type(event) is dict
        and event.get("ref") == "refs/heads/main"
        and event.get("after") == sha
        and type(event.get("repository")) is dict
        and event["repository"].get("full_name") == REPO
        and type(event.get("head_commit")) is dict
        and event["head_commit"].get("id") == sha
        and event.get("created") is False
        and event.get("deleted") is False
        and event.get("forced") is False,
        "BAD_PUSH_EVENT",
    )
    require(
        type(gate1) is dict and gate1.get("number") == GATE1_PR
        and gate1.get("state") == "closed" and gate1.get("merged") is True
        and gate1.get("merge_commit_sha") == GATE1_MERGE
        and gate1.get("head", {}).get("sha") == GATE1_HEAD
        and gate1.get("base", {}).get("ref") == "main"
        and gate1.get("user", {}).get("login") == OWNER
        and gate1.get("merged_by", {}).get("login") == OWNER
        and "executor: SWPC Codex (Mode 2)" in (gate1.get("body") or ""),
        "GATE1_CODEX_PROVENANCE_DENIED",
    )
    require(
        type(activation) is dict
        and activation.get("number") == ACTIVATION_PR
        and activation.get("state") == "closed"
        and activation.get("merged") is True
        and activation.get("merge_commit_sha") == sha
        and activation.get("base", {}).get("ref") == "main"
        and activation.get("head", {}).get("ref") == ACTIVATION_HEAD_BRANCH
        and activation.get("user", {}).get("login") == OWNER
        and activation.get("merged_by", {}).get("login") == OWNER
        and (activation.get("body") or "").splitlines().count(MARKER) == 1,
        "ACTIVATION_MERGE_PROVENANCE_DENIED",
    )
    require(
        type(associated_prs) is list and len(associated_prs) == 1
        and associated_prs[0].get("number") == ACTIVATION_PR
        and associated_prs[0].get("merge_commit_sha") == sha,
        "MERGED_COMMIT_NOT_EXACT_PR",
    )
    require(
        type(commit) is dict
        and commit.get("sha") == sha
        and type(commit.get("parents")) is list
        and len(commit["parents"]) == 1
        and SHA40.fullmatch(commit["parents"][0].get("sha", "")) is not None,
        "SQUASH_COMMIT_REQUIRED",
    )
    require(
        type(changed_files) is list and 2 <= len(changed_files) <= len(ALLOWED_FILES)
        and activation.get("changed_files") == len(changed_files),
        "PR_FILE_COUNT_DENIED",
    )
    paths = [x.get("filename") for x in changed_files if type(x) is dict]
    require(
        len(paths) == len(changed_files)
        and len(paths) == len(set(paths))
        and set(paths).issubset(ALLOWED_FILES)
        and ".github/workflows/plasma-codex-software-mvp.yml" in paths
        and "scripts/plasma_codex_postmerge_dispatch.py" in paths
        and all(x.get("status") in ("added", "modified") for x in changed_files),
        "PR_FILE_SCOPE_DENIED",
    )
    return {
        "status": "PASS", "executor": "swpc-codex",
        "work_order": "issue981-c11-hello-world",
        "gate1_pr": GATE1_PR, "activation_pr": ACTIVATION_PR,
        "merge_sha": sha, "run_id": int(run),
        "live_model_executed": False, "provenance_verified": True,
    }


def request_json(endpoint: str, token: str) -> object:
    req = Request(
        "https://api.github.com/repos/" + REPO + endpoint,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(req, timeout=12) as resp:
        raw = resp.read(256 * 1024 + 1)
    require(len(raw) <= 256 * 1024, "RESPONSE_TOO_LARGE")
    return json.loads(raw)


def run(event_path: Path, env: dict[str, str]) -> dict:
    require(
        event_path.is_file() and not event_path.is_symlink()
        and event_path.stat().st_size < 131072,
        "EVENT_FILE_DENIED",
    )
    event = json.loads(event_path.read_text(encoding="utf-8"))
    sha = env.get("GITHUB_SHA", "")
    # Fast local rejection BEFORE querying any remotely supplied metadata.
    require(
        ACTIVATION_PR >= 1
        and env.get("GITHUB_EVENT_NAME") == "push"
        and env.get("GITHUB_REPOSITORY") == REPO
        and env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_ACTOR") == OWNER
        and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and SHA40.fullmatch(sha) is not None
        and type(event) is dict and event.get("after") == sha,
        "FAST_EVENT_DENIED",
    )
    token = env.get("GH_TOKEN", "")
    require(bool(token), "HOSTED_READ_TOKEN_REQUIRED")
    gate1 = request_json(f"/pulls/{GATE1_PR}", token)
    activation = request_json(f"/pulls/{ACTIVATION_PR}", token)
    associated = request_json(f"/commits/{sha}/pulls?per_page=10", token)
    files = request_json(f"/pulls/{ACTIVATION_PR}/files?per_page=100", token)
    commit = request_json(f"/commits/{sha}", token)
    return validate(event, env, gate1, activation, associated, files, commit)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--event", type=Path, required=True)
    args = p.parse_args()
    try:
        verdict = run(args.event, dict(os.environ))
        print(json.dumps(verdict, sort_keys=True))
        return 0
    except (Refused, OSError, ValueError, KeyError, TypeError) as exc:
        why = str(exc) if isinstance(exc, Refused) else "PROVENANCE_IO_OR_FORMAT_DENIED"
        print(json.dumps({"status": "NO_GO", "reason": why, "model_executed": False}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
