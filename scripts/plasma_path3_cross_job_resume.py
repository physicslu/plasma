#!/usr/bin/env python3
"""CPU-only, two-GitHub-Job Codex resume. Trusted Dispatcher admission required.

Private raw thread state never enters workflow artifacts. This is intentionally
specific to the already-reviewed page-boundary fixture, not a generic resume API.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess

import plasma_path3_session_resume_probe as probe

JOBS = {"new": "development-codex", "resume": "development-codex-resume"}
STATE_DIR = ".local/state/plasma-path3-crossjob"
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")

class ResumeDenied(ValueError):
    """Constant diagnostic only; never expose raw Session, home, or prompt."""

def require(ok, reason):
    if not ok:
        raise ResumeDenied(reason)

def hash_data(data):
    return hashlib.sha256(data).hexdigest()

def runner_binding(phase, req, workspace, env):
    require(phase in JOBS and env.get("GITHUB_JOB") == JOBS[phase],
            "RESUME_PHASE_JOB_DENIED")
    require(env.get("GITHUB_RUN_ATTEMPT") == "1" and
            env.get("RUNNER_NAME") == "SWPC-plasma-codex" and
            env.get("RUNNER_ENVIRONMENT") == "self-hosted" and
            os.geteuid() != 0, "RESUME_RUNNER_DENIED")
    rid = env.get("GITHUB_RUN_ID", "")
    require(type(rid) is str and RUN_ID.fullmatch(rid) is not None,
            "RESUME_RUN_ID_DENIED")
    require(req.get("task_id") == "path3-work-order" and
            req.get("session_resume") == "page-boundary-off-by-one" and
            req.get("pr_number", 0) > 0, "RESUME_WORK_ORDER_DENIED")
    for key in ("trusted_sha", "source_sha"):
        require(type(req.get(key)) is str and
                probe.SHA40.fullmatch(req[key]) is not None,
                "RESUME_SHA_DENIED")
    require(type(req.get("work_order_sha256")) is str and
            SHA256.fullmatch(req["work_order_sha256"]) is not None,
            "RESUME_WORK_ORDER_DIGEST_DENIED")
    workspace = workspace.resolve(strict=True)
    require(workspace.is_dir() and (workspace / "AGENTS.md").is_file(),
            "RESUME_WORKSPACE_DENIED")
    head, status = probe.git_state(workspace)
    require(head == req["source_sha"] and not status,
            "RESUME_PINNED_WORKTREE_DENIED")
    return {"github_run_id": rid, "runner": env["RUNNER_NAME"],
            "uid": os.geteuid(), "source_sha": head,
            "trusted_sha": req["trusted_sha"],
            "work_order_sha256": req["work_order_sha256"],
            "workspace_sha256": hash_data(str(workspace).encode())}

def isolated_command(workspace, private_root, session):
    """Explicit bwrap mounts: no host hardware /dev, /sys, /run, or home.

    Network is needed by Codex for its model connection. This is NOT an
    egress firewall; the CLI sandbox independently disables tool networking.
    """
    wrap, codex = shutil.which("bwrap"), shutil.which("codex")
    require(bool(wrap and codex), "RESUME_BWRAP_OR_CODEX_UNAVAILABLE")
    auth = Path.home() / ".codex" / "auth.json"
    require(auth.is_file() and not auth.is_symlink(),
            "RESUME_AUTH_FILE_UNAVAILABLE")
    ch = private_root / "codex-home"
    ch.mkdir(mode=0o700, exist_ok=True)
    require(ch.is_dir() and not ch.is_symlink(), "RESUME_CODEX_HOME_DENIED")
    mounts = []
    for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc", "/opt"):
        if Path(path).exists():
            mounts += ["--ro-bind", path, path]
    args = [wrap, "--die-with-parent", "--new-session", "--unshare-pid",
            "--unshare-ipc", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp", *mounts, "--dir", "/home",
            "--dir", "/home/plasma",
            "--bind", str(ch), "/home/plasma/.codex",
            "--ro-bind", str(auth), "/home/plasma/.codex/auth.json",
            "--bind", str(workspace), "/work",
            "--setenv", "HOME", "/home/plasma",
            "--setenv", "CODEX_HOME", "/home/plasma/.codex",
            "--chdir", "/work/" + probe.ROOT_FOLDER,
            "--", "codex", "--ask-for-approval", "never",
            "-c", 'sandbox_mode="workspace-write"',
            "-c", "sandbox_workspace_write.network_access=false",
            "exec", "--json"]
    if session is None:
        args += ["--sandbox", "workspace-write", "-"]
    else:
        args += ["resume", session, "-"]
    return args

def isolated_unittest(workspace, scratch):
    """NEVER execute model-edited Python directly on the SWPC host.

    The child gets no physical host devices, unrelated home, /sys, /run, or
    network. The trusted outer worker only interprets bounded exit evidence.
    """
    bwrap = shutil.which("bwrap")
    require(bool(bwrap), "RESUME_TEST_BWRAP_UNAVAILABLE")
    mounts = []
    for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc"):
        if Path(path).exists():
            mounts += ["--ro-bind", path, path]
    command = [bwrap, "--die-with-parent", "--new-session",
               "--unshare-pid", "--unshare-ipc", "--unshare-net",
               "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
               *mounts, "--bind", str(workspace), "/work",
               "--chdir", "/work/" + probe.ROOT_FOLDER,
               "--", "python3", "-m", "unittest", "-q", probe.TEST_NAME]
    try:
        proc = subprocess.run(command, cwd=scratch,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ResumeDenied("RESUME_ISOLATED_TEST_FAILED") from None
    # A failed Python interpreter or sandbox is NOT a legitimate test FAIL.
    stderr = proc.stderr[:65536]
    if proc.returncode == 0 and b"OK" in stderr:
        return 0
    if (proc.returncode == 1 and b"FAIL:" in stderr and
            b"test_lengths" in stderr):
        return 1
    raise ResumeDenied("RESUME_ISOLATED_TEST_UNVERIFIED")


def execute(phase, req, workspace, *, env=None, state_root=None,
            executor=subprocess.run, command_builder=isolated_command,
            test_runner=isolated_unittest,
            nonce_factory=lambda: secrets.token_hex(16)):
    env = dict(os.environ if env is None else env)
    bound = runner_binding(phase, req, workspace, env)
    workspace = workspace.resolve(strict=True)
    # Default private path is controlled by the trusted worker, not Work Order.
    private = state_root or Path.home() / STATE_DIR
    require(private.is_absolute() and not private.is_symlink(),
            "RESUME_PRIVATE_PATH_DENIED")
    if phase == "new":
        private.mkdir(parents=True, mode=0o700, exist_ok=True)
    require(private.is_dir() and not private.is_symlink() and
            private.stat().st_uid == os.geteuid() and
            private.stat().st_mode & 0o077 == 0,
            "RESUME_PRIVATE_PERMISSIONS_DENIED")
    state_file = private / (bound["github_run_id"] + ".json")
    consumed = private / (bound["github_run_id"] + ".consumed")
    scratch = workspace / probe.ROOT_FOLDER
    require(not scratch.exists() and not scratch.is_symlink(),
            "RESUME_PROBE_ALREADY_EXISTS")
    if phase == "new":
        require(not state_file.exists() and not consumed.exists(),
                "RESUME_REPLAY_DENIED")
        nonce = nonce_factory()
        require(type(nonce) is str and re.fullmatch("[a-f0-9]{32}", nonce),
                "RESUME_CHALLENGE_INVALID")
        thread = None
        prompt = probe.first_prompt(nonce)
    else:
        require(not consumed.exists() and state_file.is_file() and
                not state_file.is_symlink() and
                state_file.stat().st_uid == os.geteuid() and
                state_file.stat().st_mode & 0o077 == 0 and
                state_file.stat().st_size <= 8192,
                "RESUME_STATE_UNAVAILABLE")
        previous = json.loads(state_file.read_text())
        require(type(previous) is dict and
                all(previous.get(k) == v for k, v in bound.items()) and
                previous.get("phase") == "new" and
                previous.get("test_before") != 0 and
                previous.get("test_after") != 0 and
                previous.get("test_sha256") ==
                    hash_data(probe.TEST_SOURCE.encode()),
                "RESUME_BINDING_MISMATCH")
        thread = probe.parse_events(
            json.dumps({"type": "thread.started",
                        "thread_id": previous.get("thread_id")}) + "\n" +
            json.dumps({"type": "turn.completed",
                        "usage": {"input_tokens": 0,
                                  "cached_input_tokens": 0,
                                  "output_tokens": 0}}) + "\n")[0]
        prompt = probe.RESUME_PROMPT
        # One-shot consume BEFORE Codex starts. Never silently retry/new.
        os.replace(state_file, consumed)
    scratch.mkdir(mode=0o700)
    (scratch / probe.SOURCE_NAME).write_text(probe.BROKEN_SOURCE)
    (scratch / probe.TEST_NAME).write_text(probe.TEST_SOURCE)
    before = test_runner(workspace, scratch)
    require(before == 1, "RESUME_FIXTURE_NOT_FAILING")
    command = command_builder(workspace, private, thread)
    try:
        proc = executor(command, input=prompt, cwd=scratch,
                        capture_output=True, text=True, timeout=240,
                        check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ResumeDenied("RESUME_CODEX_INVOKE_FAILED") from None
    require(proc.returncode == 0, "RESUME_CODEX_NONZERO")
    sid, tokens = probe.parse_events(proc.stdout)
    after = test_runner(workspace, scratch)
    require(hash_data((scratch / probe.TEST_NAME).read_bytes()) ==
            hash_data(probe.TEST_SOURCE.encode()), "RESUME_TEST_MODIFIED")
    head, changed = probe.git_state(workspace)
    require(head == bound["source_sha"] and
            probe.only_probe_changes(changed),
            "RESUME_UNAUTHORIZED_WORKSPACE_CHANGE")
    public = {"status": None, "phase": phase, "mode": "CROSS_JOB_CPU_ONLY",
              "runner": bound["runner"], "github_run_id": bound["github_run_id"],
              "source_sha": bound["source_sha"],
              "trusted_sha": bound["trusted_sha"],
              "work_order_sha256": bound["work_order_sha256"],
              "workspace_sha256": bound["workspace_sha256"],
              "thread_id_sha256": hash_data(sid.encode()),
              "test_before": before, "test_after": after, "usage": tokens}
    if phase == "new":
        require(after == 1, "RESUME_FIRST_TURN_PREMATURE_FIX")
        require(not (scratch / probe.PROOF_NAME).exists(),
                "RESUME_FIRST_TURN_PROOF_WRITTEN")
        state = {**bound, "phase": "new", "thread_id": sid,
                 "challenge_sha256": hash_data(nonce.encode()),
                 "test_sha256": hash_data(probe.TEST_SOURCE.encode()),
                 "test_before": before, "test_after": after,
                 "usage_new": tokens}
        raw = (json.dumps(state, sort_keys=True) + "\n").encode()
        require(len(raw) <= 8192, "RESUME_PRIVATE_STATE_TOO_LARGE")
        fd = os.open(state_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        public["status"] = "NEW_EXPECTED_TEST_FAIL"
    else:
        require(sid == thread, "RESUME_THREAD_MISMATCH")
        require(after == 0, "RESUME_TEST_NOT_PASSING")
        proof = scratch / probe.PROOF_NAME
        require(proof.is_file() and not proof.is_symlink() and
                proof.read_bytes().endswith(b"\n") and
                hash_data(proof.read_bytes()[:-1]) ==
                  previous["challenge_sha256"], "RESUME_CHALLENGE_NOT_RECOVERED")
        public.update(status="RESUME_FIX_PASS", same_thread=True,
                      continuity="VERIFIED", usage_new=previous["usage_new"])
    return public
