#!/usr/bin/env python3
"""Manual CPU-only Path 3 NEW -> FAIL -> RESUME -> PASS probe.

RETIRED FROM PATH 3 RUNTIME — offline research only (#1181).
No GitHub dispatch, SWPC use, hardware operations or private rollout reads.
Not a production dispatcher: invoking this script requires an explicit manual
flag and a clean, isolated checkout of an exact source commit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import uuid

ROOT_FOLDER = ".plasma-path3-resume-probe"
SOURCE_NAME = "mock_page_chunks.py"
TEST_NAME = "test_mock_page_chunks.py"
PROOF_NAME = "resume-proof.txt"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_STDOUT = 4 * 1024 * 1024

BROKEN_SOURCE = """\
def split_pages(data: bytes, page_size: int = 8) -> list[bytes]:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    # Deliberate bug: exact one-byte final page is skipped.
    return [data[i:i + page_size] for i in range(0, len(data) - 1, page_size)]
"""

TEST_SOURCE = """\
import unittest
from mock_page_chunks import split_pages

class PageBoundaryTests(unittest.TestCase):
    def test_lengths(self):
        for n in (0, 1, 7, 8, 9, 15, 16, 17, 24, 25):
            with self.subTest(n=n):
                data = bytes(range(n))
                expected = [data[i:i + 8] for i in range(0, n, 8)]
                self.assertEqual(split_pages(data, 8), expected)

    def test_bad_page_size(self):
        with self.assertRaises(ValueError):
            split_pages(b"x", 0)

if __name__ == "__main__":
    unittest.main()
"""


class ProbeDenied(Exception):
    """Public category-only error; never includes raw Codex stdout."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_state(repo: Path) -> tuple[str, list[str]]:
    head = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain",
         "--untracked-files=all"], text=True
    )
    return head, status.splitlines()


def only_probe_changes(status: list[str]) -> bool:
    # No modifications outside our dedicated untracked scratch directory.
    return all(
        len(line) >= 4
        and line[:2] == "??"
        and line[3:].startswith(ROOT_FOLDER + "/")
        for line in status
    )


def cmd(resume_id: str | None) -> list[str]:
    # Do not override Codex approval, sandbox, or network policy here.
    # The invoking operator's Codex configuration remains authoritative.
    args = ["codex", "exec", "--json"]
    if resume_id is not None:
        args.extend(["resume", resume_id, "-"])
    else:
        args.append("-")
    return args


def parse_events(stdout: str) -> tuple[str, dict | None]:
    if len(stdout.encode("utf-8")) > MAX_STDOUT:
        raise ProbeDenied("JSONL_EVENT_LIMIT")
    threads: list[str] = []
    usages: list[dict] = []
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            raise ProbeDenied("JSONL_INVALID") from None
        if not isinstance(item, dict):
            raise ProbeDenied("JSONL_INVALID")
        if item.get("type") == "thread.started":
            try:
                threads.append(str(uuid.UUID(item["thread_id"])))
            except (KeyError, TypeError, ValueError, AttributeError):
                raise ProbeDenied("THREAD_ID_INVALID") from None
        if item.get("type") == "turn.completed":
            usage = item.get("usage")
            keys = ("input_tokens", "cached_input_tokens", "output_tokens")
            if (not isinstance(usage, dict)
                or any(type(usage.get(k)) is not int or usage[k] < 0
                       for k in keys)
                or usage["cached_input_tokens"] > usage["input_tokens"]):
                raise ProbeDenied("USAGE_INVALID")
            usages.append({k: usage[k] for k in keys})
    if len(threads) != 1:
        raise ProbeDenied("THREAD_ID_NOT_UNIQUE")
    if len(usages) != 1:
        raise ProbeDenied("TURN_USAGE_NOT_UNIQUE")
    return threads[0], usages[0]


def test_result(root: Path) -> int:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "unittest", "-q", TEST_NAME],
            cwd=root, capture_output=True, timeout=30, check=False,
        )
        return r.returncode
    except (OSError, subprocess.TimeoutExpired):
        return 124


def first_prompt(nonce: str) -> str:
    return (
        "PLASMA owner-approved CPU-only Session Resume diagnostic in an "
        "isolated checkout. No SWPC, hardware, network, deployment or Git writes. "
        "Run python3 -m unittest -q test_mock_page_chunks.py in this directory; "
        "identify the precise page-boundary failure. DO NOT fix anything in this "
        "first turn, and DO NOT write files. Retain this ephemeral continuity "
        "challenge in the conversation ONLY, never in a file or test log: "
        f"{nonce}\n"
        "After describing the root cause, stop. The owner will resume the same "
        "Codex session in a separate process."
    )


RESUME_PROMPT = (
    "Resume the previous CPU-only page-boundary bug diagnosis. Fix ONLY "
    "mock_page_chunks.py; leave test_mock_page_chunks.py untouched. "
    "Run python3 -m unittest -q test_mock_page_chunks.py and fix until PASS. "
    "Then create resume-proof.txt containing ONLY the ephemeral continuity "
    "challenge string you received in the previous turn, followed by a newline. "
    "The challenge is deliberately NOT repeated here and must not be invented. "
    "No network, Git writes, SWPC, FPGA, USB, target power or real IC operations."
)


def run_probe(repo: Path, expected_head: str, *,
              executor=subprocess.run, state=git_state,
              nonce_factory=lambda: secrets.token_hex(16)) -> dict:
    """Two distinct Codex processes; no retry loops or implicit resume."""
    if not SHA40.fullmatch(expected_head):
        raise ProbeDenied("EXPECTED_HEAD_INVALID")
    repo = repo.resolve(strict=True)
    if not repo.is_dir() or not (repo / "AGENTS.md").is_file():
        raise ProbeDenied("REPO_INVALID")
    current_head, status = state(repo)
    if current_head != expected_head or status:
        raise ProbeDenied("SOURCE_NOT_CLEAN_OR_PINNED")
    scratch = repo / ROOT_FOLDER
    if scratch.exists() or scratch.is_symlink():
        raise ProbeDenied("PROBE_ALREADY_EXISTS")
    scratch.mkdir(mode=0o700)
    (scratch / SOURCE_NAME).write_text(BROKEN_SOURCE, encoding="utf-8")
    (scratch / TEST_NAME).write_text(TEST_SOURCE, encoding="utf-8")
    test_hash = sha256((scratch / TEST_NAME).read_bytes())
    nonce = nonce_factory()
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ProbeDenied("CHALLENGE_INVALID")
    report = {
        "case": "page-boundary-off-by-one",
        "mode": "MANUAL_HOST_ONLY",
        "head": current_head,
        "phase1": "NOT_RUN",
        "phase2": "NOT_RUN",
        "same_thread": "NOT_VERIFIED",
        "context_continuity": "NOT_VERIFIED",
        "test_before": None,
        "test_after_first": None,
        "test_after_resume": None,
        "usage": [],
        "result": "FAIL",
        "failure_reason": None,
    }

    def invoke(command: list[str], prompt: str) -> tuple[str, dict]:
        try:
            r = executor(
                command, input=prompt, cwd=scratch, capture_output=True,
                text=True, timeout=240, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise ProbeDenied("CODEX_INVOKE_FAILED") from None
        if r.returncode != 0:
            raise ProbeDenied("CODEX_NONZERO")
        return parse_events(r.stdout)

    try:
        before = test_result(scratch)
        report["test_before"] = before
        if before == 0:
            raise ProbeDenied("BUG_FIXTURE_NOT_FAILING")
        sid, usage1 = invoke(cmd(None), first_prompt(nonce))
        report["usage"].append(usage1)
        report["phase1"] = "COMPLETE"
        report["test_after_first"] = test_result(scratch)
        if report["test_after_first"] == 0:
            raise ProbeDenied("FIRST_TURN_PREMATURE_FIX")
        if sha256((scratch / TEST_NAME).read_bytes()) != test_hash:
            raise ProbeDenied("TEST_MODIFIED")
        if (scratch / PROOF_NAME).exists():
            raise ProbeDenied("EARLY_PROOF_CREATED")
        # A stored nonce would let a fresh session fake continuity. Exclude
        # bytecode caches, then reject any new workspace file after turn 1.
        allow = {SOURCE_NAME, TEST_NAME}
        if {p.name for p in scratch.iterdir() if p.name != "__pycache__"} != allow:
            raise ProbeDenied("FIRST_TURN_EXTRA_FILES")
        if any(nonce.encode("ascii") in p.read_bytes()
               for p in (scratch / SOURCE_NAME, scratch / TEST_NAME)):
            raise ProbeDenied("CHALLENGE_LEAKED_TO_FILES")
        head1, changed1 = state(repo)
        if head1 != expected_head or not only_probe_changes(changed1):
            raise ProbeDenied("UNAUTHORIZED_WORKSPACE_CHANGE")
        sid2, usage2 = invoke(cmd(sid), RESUME_PROMPT)
        report["usage"].append(usage2)
        report["phase2"] = "COMPLETE"
        report["same_thread"] = sid == sid2
        report["test_after_resume"] = test_result(scratch)
        if sha256((scratch / TEST_NAME).read_bytes()) != test_hash:
            raise ProbeDenied("TEST_MODIFIED")
        proof = scratch / PROOF_NAME
        matched = proof.is_file() and not proof.is_symlink() and (
            proof.read_bytes() == (nonce + "\n").encode("ascii"))
        report["context_continuity"] = "VERIFIED" if matched else "NOT_VERIFIED"
        head2, changed2 = state(repo)
        if head2 != expected_head or not only_probe_changes(changed2):
            raise ProbeDenied("UNAUTHORIZED_WORKSPACE_CHANGE")
        if not report["same_thread"]:
            raise ProbeDenied("RESUMED_THREAD_MISMATCH")
        if report["test_after_resume"] != 0:
            raise ProbeDenied("BUG_NOT_FIXED")
        if not matched:
            raise ProbeDenied("CHALLENGE_NOT_RECOVERED")
        report["result"] = "PASS"
    except ProbeDenied as exc:
        report["failure_reason"] = str(exc)
    finally:
        report["thread_id_sha256"] = sha256(sid.encode()) if "sid" in locals() else None
        path = scratch / "receipt.json"
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(payload)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manual-host-only", action="store_true",
                   help="Explicit permission for two CPU-only local Codex execs")
    p.add_argument("--repo", type=Path, required=True,
                   help="Clean isolated Git checkout, never the live SWPC workspace")
    p.add_argument("--expected-head", required=True)
    args = p.parse_args()
    if not args.manual_host_only:
        p.error("No Codex runs by default; --manual-host-only is required")
    try:
        result = run_probe(args.repo, args.expected_head)
    except ProbeDenied as exc:
        print(json.dumps({"result": "FAIL", "reason": str(exc)}))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["result"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
