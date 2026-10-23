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
import stat
import struct
import subprocess
import time
import uuid

import plasma_path3_session_resume_probe as probe

JOBS = {"new": "development-codex", "resume": "development-codex-resume"}
STATE_DIR = ".local/state/plasma-path3-crossjob"
RUN_ID = re.compile(r"[1-9][0-9]{0,19}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")

# The SWPC native binary hash is not independently available from Run
# #39941174584. Keep home-installed executables DENIED until a reviewed
# constant is pinned from authorized read-only host evidence.
NVM_NATIVE_SHA256 = None
NVM_NODE_VERSION = "v22.23.2"
CODEX_NPM_VERSION = "0.162.1"
NATIVE_TARGET = "x86_64-unknown-linux-musl"
NATIVE_MOUNT = "/plasma-native/codex"
MAX_NATIVE_BYTES = 128 * 1024 * 1024

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
            type(req.get("pr_number")) is int and
            req["pr_number"] >= 0, "RESUME_WORK_ORDER_DENIED")
    for key in ("trusted_sha", "source_sha"):
        require(type(req.get(key)) is str and
                probe.SHA40.fullmatch(req[key]) is not None,
                "RESUME_SHA_DENIED")
    if req["pr_number"] == 0:
        # One-off main-pinned deferred acceptance: never allow an arbitrary
        # candidate, a stale main SHA, or a spoofed runner event to execute.
        require(req["source_sha"] == req["trusted_sha"] ==
                env.get("GITHUB_SHA") and
                env.get("GITHUB_REF") == "refs/heads/main" and
                env.get("GITHUB_EVENT_NAME") == "issue_comment",
                "RESUME_MAIN_SHA_MISMATCH")
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


def _safe_nvm_node(path, home, *, directory=False):
    """Ensure all path components are owner/root-controlled and no symlinks."""
    require(path.is_relative_to(home), "RESUME_CODEX_SOURCE_DENIED")
    current = home
    for part in path.relative_to(home).parts:
        current = current / part
        require(not current.is_symlink(), "RESUME_CODEX_SOURCE_DENIED")
        try:
            meta = current.stat()
        except OSError:
            raise ResumeDenied("RESUME_CODEX_SOURCE_DENIED") from None
        require(meta.st_uid in (0, os.geteuid()) and
                not (meta.st_mode & 0o022) and
                (stat.S_ISDIR(meta.st_mode) if
                 current != path or directory else stat.S_ISREG(meta.st_mode)),
                "RESUME_CODEX_SOURCE_DENIED")


def _package_metadata(path, home, name):
    _safe_nvm_node(path, home)
    require(path.stat().st_size <= 65536, "RESUME_CODEX_PACKAGE_INVALID")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise ResumeDenied("RESUME_CODEX_PACKAGE_INVALID") from None
    require(type(data) is dict and data.get("name") == name and
            data.get("version") in (
                CODEX_NPM_VERSION, CODEX_NPM_VERSION + "-linux-x64"),
            "RESUME_CODEX_PACKAGE_INVALID")
    return data


def _require_standalone_x64_elf(data):
    """Reject PT_INTERP and DT_NEEDED: never import unmounted shared objects."""
    require(len(data) >= 64 and data[:6] == b"\x7fELF\x02\x01",
            "RESUME_CODEX_NATIVE_ELF_DENIED")
    etype, machine = struct.unpack_from("<HH", data, 16)
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phsize, phnum = struct.unpack_from("<HH", data, 54)
    require(etype in (2, 3) and machine == 62 and phsize == 56 and
            1 <= phnum <= 128 and
            phoff + phnum * phsize <= len(data),
            "RESUME_CODEX_NATIVE_ELF_DENIED")
    for i in range(phnum):
        kind, _, offset, _, _, length, _, _ = struct.unpack_from(
            "<IIQQQQQQ", data, phoff + i * phsize)
        require(kind != 3, "RESUME_CODEX_NATIVE_DEPENDENCY_DENIED")
        if kind == 2:
            require(offset + length <= len(data) and length % 16 == 0,
                    "RESUME_CODEX_NATIVE_ELF_DENIED")
            for j in range(offset, offset + length, 16):
                tag = struct.unpack_from("<q", data, j)[0]
                require(tag != 1, "RESUME_CODEX_NATIVE_DEPENDENCY_DENIED")
                if tag == 0:
                    break


def _nvm_native_codex(codex):
    """Fixed observed NVM + upstream npm layout; never mount its parent tree."""
    home = Path.home().resolve(strict=True)
    prefix = home / ".nvm" / "versions" / "node" / NVM_NODE_VERSION
    entry = prefix / "bin" / "codex"
    package = prefix / "lib" / "node_modules" / "@openai" / "codex"
    wrapper = package / "bin" / "codex.js"
    require(Path(codex) == entry and entry.is_symlink() and
            Path(os.path.realpath(codex)) == wrapper,
            "RESUME_CODEX_SOURCE_DENIED")
    _safe_nvm_node(wrapper, home)
    metadata = _package_metadata(package / "package.json", home,
                                 "@openai/codex")
    require(metadata.get("bin") == {"codex": "bin/codex.js"},
            "RESUME_CODEX_PACKAGE_INVALID")
    candidates = [
        package / "node_modules" / "@openai" / "codex-linux-x64",
        package.parent / "codex-linux-x64",
        package,
    ]
    found = []
    for root in candidates:
        native = root / "vendor" / NATIVE_TARGET / "bin" / "codex"
        if native.exists() or native.is_symlink():
            found.append((root, native))
    require(len(found) == 1, "RESUME_CODEX_NATIVE_AMBIGUOUS")
    root, native = found[0]
    _safe_nvm_node(native, home)
    if root != package:
        _package_metadata(root / "package.json", home,
                          "@openai/codex-linux-x64")
    require(native.stat().st_mode & 0o111 and
            native.stat().st_size <= MAX_NATIVE_BYTES,
            "RESUME_CODEX_NATIVE_ELF_DENIED")
    require(type(NVM_NATIVE_SHA256) is str and
            SHA256.fullmatch(NVM_NATIVE_SHA256) is not None,
            "RESUME_CODEX_SHA256_UNPINNED")
    raw = native.read_bytes()
    require(hash_data(raw) == NVM_NATIVE_SHA256,
            "RESUME_CODEX_SHA256_MISMATCH")
    _require_standalone_x64_elf(raw)
    require(hash_data(native.read_bytes()) == NVM_NATIVE_SHA256,
            "RESUME_CODEX_SHA256_MISMATCH")
    return native


def isolated_command(workspace, private_root, session):
    """Explicit bwrap mounts: no host hardware /dev, /sys, /run, or home.

    Network is needed by Codex for its model connection. This is NOT an
    egress firewall; the CLI sandbox independently disables tool networking.
    """
    wrap, codex = shutil.which("bwrap"), shutil.which("codex")
    require(bool(wrap and codex), "RESUME_BWRAP_OR_CODEX_UNAVAILABLE")
    codex_binary = os.path.realpath(codex)
    native_mounts = []
    if not any(codex_binary.startswith(prefix) for prefix in (
            "/usr/", "/bin/", "/sbin/", "/lib/", "/lib64/", "/opt/")):
        binary = _nvm_native_codex(codex)
        native_mounts = ["--dir", "/plasma-native",
                         "--ro-bind", str(binary), NATIVE_MOUNT]
        codex_binary = NATIVE_MOUNT
    auth = Path.home() / ".codex" / "auth.json"
    require(auth.is_file() and not auth.is_symlink(),
            "RESUME_AUTH_FILE_UNAVAILABLE")
    ch = private_root / "codex-home"
    scratch = workspace / probe.ROOT_FOLDER
    require(scratch.is_dir() and not scratch.is_symlink() and
            scratch.resolve(strict=True) ==
                workspace.resolve(strict=True) / probe.ROOT_FOLDER,
            "RESUME_SCRATCH_DENIED")
    ch.mkdir(mode=0o700, exist_ok=True)
    require(ch.is_dir() and not ch.is_symlink() and
            not (ch / "auth.json").is_symlink(),
            "RESUME_CODEX_HOME_DENIED")
    mounts = []
    for path in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc", "/opt"):
        if Path(path).exists():
            mounts += ["--ro-bind", path, path]
    args = [wrap, "--die-with-parent", "--new-session", "--unshare-pid",
            "--unshare-ipc", "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp", *mounts, *native_mounts, "--dir", "/home",
            "--dir", "/home/plasma",
            "--bind", str(ch), "/home/plasma/.codex",
            "--ro-bind", str(auth), "/home/plasma/.codex/auth.json",
            "--ro-bind", str(workspace), "/work",
            "--bind", str(scratch), "/work/" + probe.ROOT_FOLDER,
            "--setenv", "HOME", "/home/plasma",
            "--setenv", "CODEX_HOME", "/home/plasma/.codex",
            "--chdir", "/work/" + probe.ROOT_FOLDER,
            "--", codex_binary, "--ask-for-approval", "never",
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
               *mounts, "--ro-bind", str(workspace), "/work",
               "--bind", str(scratch), "/work/" + probe.ROOT_FOLDER,
               "--chdir", "/work/" + probe.ROOT_FOLDER,
               "--", "python3", "-m", "unittest", "-q", probe.TEST_NAME]
    # Do not leak Actions credentials or inherit Python import hooks into a
    # test that executes model-edited Python code in the sandbox.
    safe_env = {"PATH": "/usr/local/bin:/usr/bin:/bin",
                "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                "PYTHONNOUSERSITE": "1"}
    try:
        proc = subprocess.run(command, cwd=scratch, env=safe_env,
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
    # Codex Session storage belongs to this immutable Actions Run, not a
    # shared collection of unrelated sessions on the SWPC host.
    session_root = private / bound["github_run_id"]
    if phase == "new":
        require(not session_root.exists() and not session_root.is_symlink(),
                "RESUME_PRIVATE_RUN_EXISTS")
        session_root.mkdir(mode=0o700)
    require(session_root.is_dir() and not session_root.is_symlink() and
            session_root.stat().st_uid == os.geteuid() and
            session_root.stat().st_mode & 0o077 == 0,
            "RESUME_PRIVATE_RUN_UNSAFE")
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
        prompt = probe.first_prompt(nonce).replace(
            "No SWPC, hardware, network, deployment or Git writes.",
            "Running in SWPC's isolated CPU-only workspace. No host-device "
            "access, network tools, deployment or Git writes.")
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
                type(previous.get("created_unix")) is int and
                0 <= int(time.time()) - previous["created_unix"] <= 7200 and
                previous.get("test_before") == 1 and
                previous.get("test_after") == 1 and
                previous.get("test_sha256") ==
                    hash_data(probe.TEST_SOURCE.encode()),
                "RESUME_BINDING_MISMATCH")
        require(type(previous.get("challenge_sha256")) is str and
                SHA256.fullmatch(previous["challenge_sha256"]) is not None and
                type(previous.get("usage_new")) is dict,
                "RESUME_STATE_INCOMPLETE")
        try:
            raw_thread = previous.get("thread_id")
            thread = str(uuid.UUID(raw_thread))
            require(raw_thread == thread, "RESUME_THREAD_INVALID")
        except (TypeError, ValueError, AttributeError):
            raise ResumeDenied("RESUME_THREAD_INVALID") from None
        prompt = probe.RESUME_PROMPT.replace(
            "No network, Git writes, SWPC, FPGA, USB, target power or real IC operations.",
            "No host-device access, network tools, Git writes, FPGA, USB, "
            "target power or real IC operations.")
        # One-shot consume BEFORE Codex starts. Immediately erase the raw
        # private Thread ID from the replay tombstone, even if Codex fails.
        os.replace(state_file, consumed)
        with consumed.open("w", encoding="utf-8") as stream:
            json.dump({"consumed": True,
                       "github_run_id": bound["github_run_id"]}, stream)
            stream.write("\n")
    scratch.mkdir(mode=0o700)
    (scratch / probe.SOURCE_NAME).write_text(probe.BROKEN_SOURCE)
    (scratch / probe.TEST_NAME).write_text(probe.TEST_SOURCE)
    before = test_runner(workspace, scratch)
    require(before == 1, "RESUME_FIXTURE_NOT_FAILING")
    command = command_builder(workspace, session_root, thread)
    # Do not inherit GitHub/ACTIONS tokens, owner CLI environment or Node
    # injection variables into the model-facing subprocess.
    child_env = {"PATH": "/usr/local/bin:/usr/bin:/bin",
                 "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
                 "TERM": "dumb"}
    try:
        proc = executor(command, input=prompt, cwd=scratch,
                        env=child_env, capture_output=True, text=True,
                        timeout=240, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ResumeDenied("RESUME_CODEX_INVOKE_FAILED") from None
    require(proc.returncode == 0, "RESUME_CODEX_NONZERO")
    try:
        sid, tokens = probe.parse_events(proc.stdout)
    except probe.ProbeDenied as exc:
        raise ResumeDenied(str(exc)) from None
    after = test_runner(workspace, scratch)
    test_path = scratch / probe.TEST_NAME
    source_path = scratch / probe.SOURCE_NAME
    require(test_path.is_file() and not test_path.is_symlink() and
            source_path.is_file() and not source_path.is_symlink(),
            "RESUME_SOURCE_FILE_INVALID")
    require(hash_data(test_path.read_bytes()) ==
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
        require(hash_data(source_path.read_bytes()) ==
                hash_data(probe.BROKEN_SOURCE.encode()),
                "RESUME_FIRST_TURN_MODIFIED_SOURCE")
        require(not (scratch / probe.PROOF_NAME).exists(),
                "RESUME_FIRST_TURN_PROOF_WRITTEN")
        state = {**bound, "phase": "new", "thread_id": sid,
                 "created_unix": int(time.time()),
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
                proof.stat().st_size <= 128 and
                proof.read_bytes().endswith(b"\n") and
                hash_data(proof.read_bytes()[:-1]) ==
                  previous["challenge_sha256"], "RESUME_CHALLENGE_NOT_RECOVERED")
        public.update(status="RESUME_FIX_PASS", same_thread=True,
                      continuity="VERIFIED", usage_new=previous["usage_new"])
        # No retained model Session is needed once continuity is proven.
        # Remove only this Run's own private, owner-only Session directory.
        shutil.rmtree(session_root)
    return public
