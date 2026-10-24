#!/usr/bin/env python3
"""Exact owner-triggered C11 SW task on the unified SWPC HIL worker.

Uses the existing SWPC-plasma-codex identity and its ChatGPT CLI login,
without GitHub write tokens or API secrets on the worker. A separate hosted
Publisher verifies the model-generated single-file patch. All live execution
requires an explicit owner-created Issue #981 command on main; legacy
PR #1034 postmerge auto activation is archived and must NOT be replayed.
The SW command is not permission for Z2/LA/USB hardware operations.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

OWNER = "physicslu"
REPO = "physicslu/plasma"
ISSUE = 981
COMMAND = "/plasma-codex hello-c 981"
# One exact real-Codex C11 development task; only the model generates this file.
TARGET = "examples/hello-world/main.c"
EXPECTED_STDOUT = b"Hello, World!\\n".replace(b"\\n", b"\n")
STDOUT_SHA256 = hashlib.sha256(EXPECTED_STDOUT).hexdigest()
SHA40 = re.compile(r"[a-f0-9]{40}\Z")
STATUS_LIMIT = 20
MAX_PATCH = 16 * 1024

class Refused(Exception):
    pass

def fail(code: str) -> None:
    raise Refused(code)

def git(*args: str, input: bytes | None = None) -> bytes:
    return subprocess.run(["git", *args], input=input, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=True).stdout

def load_event(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 131072:
        fail("EVENT_NOT_REGULAR")
    with path.open(encoding="utf-8") as stream:
        x = json.load(stream)
    if type(x) is not dict:
        fail("EVENT_NOT_OBJECT")
    return x

def authorize(event: dict, environ: dict[str, str], sha: str) -> dict:
    # Unified HIL only admits an explicit owner-created Issue comment.
    # The historical PR #1034 one-shot push may not be replayed by a new merge.
    # Require the same context again on the worker and hosted publisher.
    if (environ.get("GITHUB_EVENT_NAME") != "issue_comment"
            or environ.get("GITHUB_ACTOR") != OWNER
            or environ.get("GITHUB_REPOSITORY") != REPO
            or environ.get("GITHUB_REF") != "refs/heads/main"
            or environ.get("GITHUB_SHA") != sha
            or not SHA40.fullmatch(sha)
            or environ.get("GITHUB_RUN_ATTEMPT") != "1"):
        fail("UNTRUSTED_GITHUB_CONTEXT")
    if (event.get("action") != "created"
            or type(event.get("issue")) is not dict
            or event["issue"].get("number") != ISSUE
            or "pull_request" in event["issue"]
            or type(event.get("comment")) is not dict
            or type(event["comment"].get("user")) is not dict
            or event["comment"].get("body") != COMMAND
            or event["comment"]["user"].get("login") != OWNER
            or type(event.get("sender")) is not dict
            or event["sender"].get("login") != OWNER
            or type(event.get("repository")) is not dict
            or event["repository"].get("full_name") != REPO
            or type(event["comment"].get("id")) is not int):
        fail("UNAUTHORIZED_OWNER_COMMAND")
    run = environ.get("GITHUB_RUN_ID", "")
    if not re.fullmatch(r"[1-9][0-9]{0,19}", run):
        fail("UNTRUSTED_RUN_ID")
    # The owner command is a fixed Codex-executor selection; never fall back
    # silently to ChatGPT, a hosted model, or a hardware capability.
    return {"repository": REPO, "issue": ISSUE, "command": COMMAND,
            "executor": "codex", "source_sha": sha, "comment_id": event["comment"]["id"],
            "run_id": int(run), "run_attempt": 1}

def inventory() -> list[str]:
    """Only the one new C source may be edited; no tracked modifications."""
    raw = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    entries = raw.split(b"\0")
    found = []
    for entry in filter(None, entries):
        try:
            text = entry.decode("utf-8", errors="strict")
        except UnicodeError:
            fail("INVALID_UTF8_PATH")
        if len(text) < 4 or text[:2] != "??":
            fail("TRACKED_MODIFICATION_OR_RENAME_DENIED")
        p = text[3:]
        if p != TARGET or p in found:
            fail("UNAUTHORIZED_PATH")
        found.append(p)
    if found != [TARGET]:
        fail("NO_SINGLE_CHANGE")
    path = Path(TARGET)
    if (path.is_symlink() or not path.is_file() or path.stat().st_size > 8192
            or not path.read_bytes().endswith(b"\n")
            or b"\x00" in path.read_bytes()):
        fail("UNSAFE_OUTPUT")
    validate_c_source(path.read_bytes())
    return found


# Deliberately constrained grammar for the FIRST physical SWPC software-write
# acceptance: no untrusted C may access filesystem, network, OS APIs or DUTs.
# The model still authors the file; tests never publish a ChatGPT-authored C file.
HELLO_C11 = re.compile(
    rb'\A[ \t\r\n]*\#include[ \t]*<stdio\.h>[ \t\r\n]+'
    rb'int[ \t]+main[ \t]*\([ \t]*void[ \t]*\)[ \t\r\n]*\{[ \t\r\n]*'
    rb'(?:puts[ \t]*\([ \t]*"Hello, World!"[ \t]*\)'
    rb'|printf[ \t]*\([ \t]*"Hello, World!\\n"[ \t]*\))'
    rb'[ \t]*;[ \t\r\n]*return[ \t]+0[ \t]*;[ \t\r\n]*\}[ \t\r\n]*\Z'
)

def validate_c_source(source: bytes) -> None:
    if len(source) > 4096 or not HELLO_C11.fullmatch(source):
        fail("HELLO_C_SOURCE_OUTSIDE_TINY_ALLOWLIST")

def compile_and_execute_hello() -> None:
    # Called by the SWPC Worker only after byte-exact static admission.
    validate_c_source(Path(TARGET).read_bytes())
    with tempfile.TemporaryDirectory(prefix="plasma-hello-c-") as tmp:
        binary = str(Path(tmp) / "hello")
        compiled = subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-O0", "-o", binary, TARGET],
            capture_output=True, timeout=45, check=False)
        if compiled.returncode != 0 or compiled.stderr or compiled.stdout:
            fail("HELLO_C11_COMPILE_FAILED")
        executed = subprocess.run([binary], capture_output=True, timeout=3,
                                  check=False, cwd=tmp)
        if (executed.returncode != 0 or executed.stdout != EXPECTED_STDOUT
                or executed.stderr != b""):
            fail("HELLO_C_OUTPUT_MISMATCH")

def create_bundle(output: Path, event: dict, env: dict[str,str]) -> dict:
    base = git("rev-parse", "HEAD").decode().strip()
    receipt = authorize(event, env, base)
    paths = inventory()
    compile_and_execute_hello()
    git("add", "-N", "--", TARGET)
    patch = git("diff", "--binary", "--", TARGET)
    if not 40 < len(patch) <= MAX_PATCH:
        fail("PATCH_SIZE_DENIED")
    if not patch.startswith(("diff --git a/"+TARGET+" b/"+TARGET+"\n").encode()):
        fail("PATCH_HEADER_DENIED")
    # 'git apply' parses patch; output file is still untrusted.
    output.mkdir(parents=True, exist_ok=False)
    (output/"candidate.patch").write_bytes(patch)
    receipt.update({"allowed_paths": paths, "patch_sha256": hashlib.sha256(patch).hexdigest(),
                    "codex_executed": True, "model_exit_code": 0,
                    "tests_passed": True, "runtime_dispatcher_enabled": False,
                    "task": "c11-hello-world", "stdout_sha256": STDOUT_SHA256})
    (output/"receipt.json").write_text(json.dumps(receipt,sort_keys=True,indent=2)+"\n")
    return receipt

def verify_bundle(root: Path, event: dict, env: dict[str,str]) -> dict:
    base = git("rev-parse","HEAD").decode().strip()
    expected = authorize(event, env, base)
    if (root.is_symlink() or not root.is_dir()
            or set(x.name for x in root.iterdir()) != {"candidate.patch","receipt.json"}):
        fail("ARTIFACT_SET_DENIED")
    patch_path = root/"candidate.patch"
    receipt_path = root/"receipt.json"
    if (patch_path.is_symlink() or receipt_path.is_symlink()
            or not patch_path.is_file() or not receipt_path.is_file()
            or patch_path.stat().st_size > MAX_PATCH
            or receipt_path.stat().st_size > 4096):
        fail("ARTIFACT_FILE_DENIED")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (type(receipt) is not dict or
            set(receipt) != set(expected) | {"allowed_paths","patch_sha256",
                "codex_executed","model_exit_code","tests_passed","runtime_dispatcher_enabled",
                "task","stdout_sha256"}
            or any(receipt.get(k) != v for k,v in expected.items())
            or receipt["allowed_paths"] != [TARGET]
            or receipt["codex_executed"] is not True
            or receipt["model_exit_code"] != 0
            or receipt["tests_passed"] is not True
            or receipt["runtime_dispatcher_enabled"] is not False
            or receipt["task"] != "c11-hello-world"
            or receipt["stdout_sha256"] != STDOUT_SHA256):
        fail("RECEIPT_INVALID")
    patch = patch_path.read_bytes()
    if (not patch or hashlib.sha256(patch).hexdigest()!=receipt["patch_sha256"]
            or not patch.startswith(("diff --git a/"+TARGET+" b/"+TARGET+"\n").encode())):
        fail("PATCH_HASH_OR_SCOPE_DENIED")
    # Publisher never runs any code from the model output.
    git("apply","--check","--cached",input=patch)
    git("apply","--cached",input=patch)
    names = git("diff","--cached","--name-only","-z").split(b"\0")
    if [n for n in names if n] != [TARGET.encode()]:
        fail("PUBLISH_PATH_DENIED")
    # Publisher verifies C grammar without executing untrusted candidate code.
    validate_c_source(git("show", ":" + TARGET))
    status = git("ls-files","--stage","--",TARGET).decode()
    if not status.startswith("100644 "):
        fail("PUBLISH_MODE_DENIED")
    # Require a new file, not deletion or modification to existing source.
    if git("ls-tree", "HEAD", "--", TARGET) != b"":
        fail("PUBLISH_EXISTING_FILE_DENIED")
    return receipt

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("authorize","bundle","publish"))
    parser.add_argument("--event",required=True,type=Path)
    parser.add_argument("--artifact-dir",type=Path)
    args=parser.parse_args()
    try:
        event=load_event(args.event)
        base=git("rev-parse","HEAD").decode().strip()
        if args.mode=="authorize":
            receipt=authorize(event,os.environ,base)
        elif args.mode=="bundle":
            if args.artifact_dir is None: fail("ARTIFACT_MISSING")
            receipt=create_bundle(args.artifact_dir,event,os.environ)
        else:
            if args.artifact_dir is None: fail("ARTIFACT_MISSING")
            receipt=verify_bundle(args.artifact_dir,event,os.environ)
        print(json.dumps({"status":"PASS","mode":args.mode,
                          "source_sha":receipt["source_sha"],
                          "run_id":receipt["run_id"]},sort_keys=True))
        return 0
    except (Refused,OSError,subprocess.CalledProcessError,subprocess.TimeoutExpired,
            ValueError,UnicodeError,json.JSONDecodeError) as ex:
        reason=str(ex) if isinstance(ex,Refused) else "MVP_IO_OR_GIT_FAILURE"
        print(json.dumps({"status":"NO_GO","reason":reason,"mode":args.mode},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())
