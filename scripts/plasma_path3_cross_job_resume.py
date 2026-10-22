#!/usr/bin/env python3
"""Trusted CPU-only cross-GitHub-Job Codex session continuation experiment.

Never run directly on a device. The existing Development Dispatcher performs
owner/source/runner admission, and this module accepts one bounded fixture.
The two phases use the SAME GITHUB_RUN_ID but distinct Github Actions jobs,
persisting only in the SWPC Runner owner's private local state. No session
transcripts or authentication material are uploaded as artifacts.
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
import sys
import uuid

from plasma_path3_session_resume_probe import BROKEN_SOURCE, TEST_SOURCE

FIXTURE = "page-boundary-v1"
STATE_DIR_NAME = "plasma-path3-cross-job-resume"
MAX_JSONL = 4 * 1024 * 1024
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
DIGITS = re.compile(r"[1-9][0-9]{0,18}\Z")
FIXED_SOURCE = BROKEN_SOURCE.replace("len(data) - 1", "len(data)")


class ResumeDenied(Exception):
    """Category-only error, safe to include in a public receipt."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise ResumeDenied(code)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_json(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink() and
            path.stat().st_size <= 8192, "RESUME_MANIFEST_INVALID")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        raise ResumeDenied("RESUME_MANIFEST_INVALID") from None
    require(type(value) is dict, "RESUME_MANIFEST_INVALID")
    return value


def write_private_json(path: Path, value: dict, *, replace: bool = False) -> None:
    payload = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    require(len(payload) <= 8192, "RESUME_MANIFEST_TOO_LARGE")
    tmp = path.with_name(path.name + ".pending")
    require(not tmp.exists() and not tmp.is_symlink(),
            "RESUME_MANIFEST_PENDING_EXISTS")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(payload)
    if not replace:
        require(not path.exists() and not path.is_symlink(),
                "RESUME_MANIFEST_ALREADY_EXISTS")
    else:
        require(path.is_file() and not path.is_symlink(),
                "RESUME_MANIFEST_MISSING")
    os.replace(tmp, path)


def validate_identity(identity: dict) -> dict:
    fields = ("owner", "github_run_id", "comment_id", "runner_name",
              "trusted_sha", "source_sha", "registry_sha256",
              "work_order_sha256")
    require(type(identity) is dict and set(identity) == set(fields),
            "RESUME_IDENTITY_FIELDS_DENIED")
    require(identity["owner"] == "physicslu", "RESUME_OWNER_DENIED")
    require(type(identity["github_run_id"]) is str and
            DIGITS.fullmatch(identity["github_run_id"]) is not None,
            "RESUME_RUN_ID_DENIED")
    require(type(identity["comment_id"]) is int and identity["comment_id"] > 0,
            "RESUME_COMMENT_ID_DENIED")
    require(type(identity["runner_name"]) is str and
            identity["runner_name"] == "SWPC-plasma-codex",
            "RESUME_RUNNER_DENIED")
    require(all(type(identity[k]) is str and HEX40.fullmatch(identity[k])
                for k in ("trusted_sha", "source_sha")),
            "RESUME_SOURCE_SHA_DENIED")
    require(all(type(identity[k]) is str and HEX64.fullmatch(identity[k])
                for k in ("registry_sha256", "work_order_sha256")),
            "RESUME_WORK_ORDER_DENIED")
    return dict(identity)


def require_pinned_clean_checkout(workspace: Path, identity: dict) -> None:
    require(workspace.is_dir() and not workspace.is_symlink(),
            "RESUME_WORKSPACE_DENIED")
    try:
        head = subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL, timeout=10).strip()
        status = subprocess.check_output(
            ["git", "-C", str(workspace), "status", "--porcelain",
             "--untracked-files=all"], text=True,
            stderr=subprocess.DEVNULL, timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise ResumeDenied("RESUME_GIT_CHECK_FAILED") from None
    require(head == identity["source_sha"] and not status,
            "RESUME_SOURCE_CHANGED")


def test_exit(project: Path) -> int:
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "-q", "test_mock_page_chunks.py"],
            cwd=project, capture_output=True, timeout=30, check=False)
        return result.returncode
    except (OSError, subprocess.TimeoutExpired):
        return 124


def parse_codex_events(stdout: str) -> tuple[str, dict]:
    require(type(stdout) is str and len(stdout.encode("utf-8")) <= MAX_JSONL,
            "RESUME_JSONL_TOO_LARGE")
    thread = []
    completed = []
    for line in stdout.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            raise ResumeDenied("RESUME_JSONL_INVALID") from None
        require(type(item) is dict, "RESUME_JSONL_INVALID")
        if item.get("type") == "thread.started":
            try:
                thread.append(str(uuid.UUID(item["thread_id"])))
            except (ValueError, KeyError, TypeError, AttributeError):
                raise ResumeDenied("RESUME_THREAD_INVALID") from None
        elif item.get("type") == "turn.completed":
            usage = item.get("usage")
            keys = ("input_tokens", "cached_input_tokens", "output_tokens")
            require(type(usage) is dict and
                    all(type(usage.get(k)) is int and 0 <= usage[k] <= 2**63-1
                        for k in keys) and
                    usage["cached_input_tokens"] <= usage["input_tokens"],
                    "RESUME_USAGE_INVALID")
            completed.append({k: usage[k] for k in keys})
    require(len(thread) == len(completed) == 1,
            "RESUME_EVENTS_INCOMPLETE")
    return thread[0], completed[0]


def command_for_stage(phase: str, thread: str | None = None) -> list[str]:
    require(phase in ("new", "resume"), "RESUME_PHASE_DENIED")
    args = [
        "codex", "--ask-for-approval", "never",
        "-c", 'sandbox_mode="workspace-write"',
        "-c", "sandbox_workspace_write.network_access=false",
        "exec", "--json",
    ]
    if phase == "new":
        require(thread is None, "RESUME_UNEXPECTED_THREAD")
        args.extend(["--sandbox", "workspace-write", "-"])
    else:
        try:
            actual = str(uuid.UUID(thread))
        except (ValueError, TypeError, AttributeError):
            raise ResumeDenied("RESUME_THREAD_INVALID") from None
        args.extend(["resume", actual, "-"])
    return args


def sandbox_command(state: Path, project: Path, home: Path) -> list[str]:
    """Build an OS mount-isolated Codex exec; no devices or host project mounts."""
    wrapper = shutil.which("bwrap")
    codex = shutil.which("codex")
    require(wrapper is not None and codex is not None, "RESUME_TOOLS_UNAVAILABLE")
    require(os.geteuid() != 0, "RESUME_ROOT_DENIED")
    auth = home / ".codex" / "auth.json"
    require(auth.is_file() and not auth.is_symlink(),
            "RESUME_AUTH_UNAVAILABLE")
    codex_real = Path(codex).resolve()
    system_code = codex_real.is_relative_to(Path("/usr"))
    nvm_code = codex_real.is_relative_to(home / ".nvm")
    require(system_code or nvm_code, "RESUME_CODEX_INSTALL_UNSUPPORTED")
    require(state.parent.is_dir() and project.is_dir(),
            "RESUME_STATE_DIR_MISSING")
    args = [
        wrapper, "--die-with-parent", "--new-session",
        "--unshare-user", "--unshare-pid", "--unshare-ipc",
        "--unshare-uts", "--clearenv",
        "--ro-bind", "/usr", "/usr",
    ]
    for system_dir in ("/bin", "/sbin", "/lib", "/lib64"):
        p = Path(system_dir)
        if p.is_symlink():
            args.extend(["--symlink", os.readlink(p), system_dir])
        elif p.is_dir():
            args.extend(["--ro-bind", system_dir, system_dir])
    if nvm_code:
        args.extend(["--dir", "/home", "--dir", str(home)])
        args.extend(["--ro-bind", str(home / ".nvm"), str(home / ".nvm")])
    args.extend([
        "--dir", "/work",
        "--dir", "/codex-home",
        "--bind", str(project), "/work",
        "--bind", str(state / "codex-home"), "/codex-home",
        "--ro-bind", str(auth), "/codex-home/auth.json",
        "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
    ])
    for system_dir in ("/etc/ssl/certs", "/etc/ca-certificates"):
        if Path(system_dir).is_dir():
            args.extend(["--ro-bind", system_dir, system_dir])
    for f in ("/etc/resolv.conf", "/etc/hosts",
              "/etc/nsswitch.conf", "/etc/passwd", "/etc/group"):
        if Path(f).is_file():
            args.extend(["--ro-bind", f, f])
    args.extend([
        "--setenv", "HOME", "/codex-home",
        "--setenv", "CODEX_HOME", "/codex-home",
        "--setenv", "PATH",
        f"{codex_real.parent}:/usr/local/bin:/usr/bin:/bin",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--chdir", "/work", "--",
    ])
    return args


def new_prompt(challenge: str) -> str:
    return (
        "PLASMA owner-approved CPU-only page-boundary diagnostic across "
        "two GitHub Actions Jobs. Do not use Git, network tools, SSH, "
        "sudo or hardware. Run python3 -m unittest -q "
        "test_mock_page_chunks.py; diagnose the off-by-one failure, "
        "but DO NOT edit or create any files this turn. "
        "Remember the following one-time continuity challenge only "
        f"in this conversation, never write it to files: {challenge}\n"
        "Then stop. A second, separately scheduled GitHub Job will resume "
        "this same Codex session."
    )


RESUME_PROMPT = (
    "Continue the previous CPU-only page-boundary diagnosis. "
    "Fix only mock_page_chunks.py (not the test). "
    "Run python3 -m unittest -q test_mock_page_chunks.py until PASS. "
    "Write resume-proof.txt containing the 32-character challenge "
    "from the preceding conversation, followed by one newline. "
    "That challenge is not repeated here; do not invent it. "
    "Do not use Git, network tools, SSH, sudo or any physical hardware."
)


def default_execute(command: list[str], prompt: str, state: Path) -> tuple[str, dict]:
    outer = sandbox_command(state, state / "project", Path.home())
    try:
        r = subprocess.run(
            [*outer, *command], input=prompt, capture_output=True,
            text=True, timeout=300, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ResumeDenied("RESUME_CODEX_INVOKE_FAILED") from None
    require(r.returncode == 0, "RESUME_CODEX_NONZERO")
    return parse_codex_events(r.stdout)


def clean_fixture(project: Path, expected: str, *, proof_allowed: bool = False) -> None:
    source = project / "mock_page_chunks.py"
    test = project / "test_mock_page_chunks.py"
    require(source.is_file() and not source.is_symlink()
            and source.read_text(encoding="utf-8") == expected
            and test.is_file() and not test.is_symlink()
            and test.read_text(encoding="utf-8") == TEST_SOURCE,
            "RESUME_WORKSPACE_HASH_MISMATCH")
    permitted = {"mock_page_chunks.py", "test_mock_page_chunks.py", "__pycache__"}
    if proof_allowed:
        permitted.add("resume-proof.txt")
    require({p.name for p in project.iterdir()} <= permitted,
            "RESUME_WORKSPACE_EXTRA_FILES")


def run_stage(phase: str, *, identity: dict, workspace: Path, state_base: Path,
              execute=default_execute, nonce_factory=secrets.token_hex) -> dict:
    """Run exactly one Codex process per call, never a hidden retry."""
    ident = validate_identity(identity)
    require(phase in ("new", "resume"), "RESUME_PHASE_DENIED")
    require_pinned_clean_checkout(workspace, ident)
    require(os.geteuid() != 0, "RESUME_ROOT_DENIED")
    require(state_base.is_dir() and not state_base.is_symlink(),
            "RESUME_STATE_ROOT_DENIED")
    require((state_base.stat().st_mode & 0o077) == 0,
            "RESUME_STATE_ROOT_PERMISSIONS")
    state = state_base / ("run-" + ident["github_run_id"])
    project = state / "project"
    manifest = state / "manifest.json"
    if phase == "new":
        require(not state.exists() and not state.is_symlink(),
                "RESUME_STATE_ALREADY_EXISTS")
        state.mkdir(mode=0o700)
        project.mkdir(mode=0o700)
        (state / "codex-home").mkdir(mode=0o700)
        (state / "codex-home" / "auth.json").touch(mode=0o600)
        (project / "mock_page_chunks.py").write_text(
            BROKEN_SOURCE, encoding="utf-8")
        (project / "test_mock_page_chunks.py").write_text(
            TEST_SOURCE, encoding="utf-8")
        clean_fixture(project, BROKEN_SOURCE)
        require(test_exit(project) == 1, "RESUME_BASELINE_NOT_FAIL")
        nonce = nonce_factory(16)
        require(type(nonce) is str and
                re.fullmatch(r"[0-9a-f]{32}", nonce) is not None,
                "RESUME_CHALLENGE_INVALID")
        thread, usage = execute(command_for_stage("new"), new_prompt(nonce), state)
        clean_fixture(project, BROKEN_SOURCE)
        require(test_exit(project) == 1, "RESUME_FIRST_TURN_PREMATURE_FIX")
        result = {
            "schema": 1, "identity": ident, "status": "READY_FOR_RESUME",
            "thread_id": thread, "challenge_sha256": digest(nonce.encode()),
            "fixture_source_sha256": digest(BROKEN_SOURCE.encode()),
            "fixture_test_sha256": digest(TEST_SOURCE.encode()),
            "new_usage": usage,
        }
        write_private_json(manifest, result)
        return {
            "status": "EVIDENCE_READY_REVIEW_REQUIRED",
            "continuity_probe": FIXTURE,
            "resume_phase": "new",
            "phase_result": "READY_FOR_RESUME",
            "thread_id_sha256": digest(thread.encode()),
            "before_exit": 1, "after_exit": 1,
            "codex_usage": usage,
            "github_run_id": ident["github_run_id"],
        }
    require(state.is_dir() and not state.is_symlink() and
            (state.stat().st_mode & 0o077) == 0,
            "RESUME_STATE_MISSING")
    record = safe_json(manifest)
    require(record.get("schema") == 1
            and record.get("status") == "READY_FOR_RESUME"
            and record.get("identity") == ident,
            "RESUME_BINDING_MISMATCH")
    require(record.get("fixture_source_sha256") == digest(BROKEN_SOURCE.encode())
            and record.get("fixture_test_sha256") == digest(TEST_SOURCE.encode()),
            "RESUME_FIXTURE_MISMATCH")
    require(type(record.get("challenge_sha256")) is str
            and HEX64.fullmatch(record["challenge_sha256"]) is not None,
            "RESUME_CHALLENGE_HASH_INVALID")
    clean_fixture(project, BROKEN_SOURCE)
    require(test_exit(project) == 1, "RESUME_PRE_RESUME_NOT_FAIL")
    thread = record.get("thread_id")
    cmd = command_for_stage("resume", thread)
    record["status"] = "RESUME_STARTED"
    write_private_json(manifest, record, replace=True)  # prevents automatic retry
    resumed_thread, usage = execute(cmd, RESUME_PROMPT, state)
    require(resumed_thread == thread, "RESUME_THREAD_MISMATCH")
    clean_fixture(project, FIXED_SOURCE, proof_allowed=True)
    require(test_exit(project) == 0, "RESUME_FIX_NOT_PASS")
    proof = project / "resume-proof.txt"
    require(proof.is_file() and not proof.is_symlink()
            and re.fullmatch(rb"[0-9a-f]{32}\n", proof.read_bytes()) is not None,
            "RESUME_PROOF_INVALID")
    require(digest(proof.read_bytes()[:-1]) == record["challenge_sha256"],
            "RESUME_CONTEXT_NOT_RESTORED")
    extra = {p.name for p in project.iterdir()}
    require(extra <= {"mock_page_chunks.py", "test_mock_page_chunks.py",
                      "resume-proof.txt", "__pycache__"},
            "RESUME_WORKSPACE_EXTRA_FILES")
    record["status"] = "RESUME_VERIFIED"
    record["resume_usage"] = usage
    write_private_json(manifest, record, replace=True)
    return {
        "status": "EVIDENCE_READY_REVIEW_REQUIRED",
        "continuity_probe": FIXTURE,
        "resume_phase": "resume",
        "phase_result": "VERIFIED_PASS",
        "same_thread": True,
        "context_continuity": "VERIFIED",
        "thread_id_sha256": digest(thread.encode()),
        "before_exit": 1, "after_exit": 0,
        "codex_usage": usage,
        "github_run_id": ident["github_run_id"],
    }


def state_root_for_runner() -> Path:
    require(os.geteuid() != 0, "RESUME_ROOT_DENIED")
    home = Path.home()
    state_root = home / ".local" / "state" / STATE_DIR_NAME
    require(not state_root.is_symlink(), "RESUME_STATE_ROOT_SYMLINK")
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    require(not state_root.is_symlink()
            and (state_root.stat().st_mode & 0o077) == 0,
            "RESUME_STATE_ROOT_PERMISSIONS")
    return state_root
