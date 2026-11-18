#!/usr/bin/env python3
"""Fixed ExecStart of ``plasma-package@<job_id>.service`` (runs as plasma-package).

The unit file (root-owned) fixes the user, sandbox and this entry; the only
variable input is the 32-hex instance name. The job spec is written by the
Runtime into the Runtime-owned, world-readable spec directory and is
re-validated here: the entry must be a regular, non-symlinked file inside an
installed Asset Set and must still match the planned SHA-256. argv is fixed
(no request arguments, no shell). The Package runs as a child; this entry
records its exit status so the unit stays ``active (exited)`` and the
Runtime can collect output before stopping the unit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import stat
import sys
from pathlib import Path

SPEC_SCHEMA = "plasma.ppu.package-unit-spec.v1"
SPEC_DIR = Path(os.environ.get("PLASMA_PACKAGE_SPEC_DIR", "/run/plasma-package-specs"))
STAGED_ROOT = Path(os.environ.get("PLASMA_PACKAGE_STAGED_ROOT", "/opt/plasma/assets/staged"))
JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
PKG_ID = re.compile(r"[a-z][a-z0-9_.-]{0,63}\Z")
ALLOWED_ENV = {"PLASMA_SITE_WORKER_SOCKET"}


class EntryDenied(Exception):
    pass


def need(ok: bool, code: str) -> None:
    if not ok:
        raise EntryDenied(code)


def load_spec(job_id: str) -> dict:
    need(JOB_ID.fullmatch(job_id) is not None, "ENTRY_JOB_ID_INVALID")
    path = SPEC_DIR / f"{job_id}.json"
    info = os.lstat(path)
    need(stat.S_ISREG(info.st_mode) and info.st_mode & 0o022 == 0 and info.st_size <= 8192,
         "ENTRY_SPEC_UNTRUSTED")
    spec = json.loads(path.read_text(encoding="utf-8"))
    need(isinstance(spec, dict) and set(spec) == {"schema", "job_id", "package_id", "kind",
                                                  "entry_path", "entry_sha256", "env"}
         and spec["schema"] == SPEC_SCHEMA and spec["job_id"] == job_id
         and type(spec["package_id"]) is str and PKG_ID.fullmatch(spec["package_id"])
         and spec["kind"] in ("python", "native-c")
         and type(spec["entry_sha256"]) is str and SHA64.fullmatch(spec["entry_sha256"])
         and isinstance(spec["env"], dict) and set(spec["env"]) <= ALLOWED_ENV
         and all(type(v) is str and v.startswith("/") for v in spec["env"].values()),
         "ENTRY_SPEC_INVALID")
    return spec


def resolve_entry(spec: dict) -> Path:
    entry = Path(spec["entry_path"])
    need(entry.is_absolute() and ".." not in entry.parts, "ENTRY_PATH_DENIED")
    rel = entry.relative_to(STAGED_ROOT) if entry.is_relative_to(STAGED_ROOT) else None
    need(rel is not None and len(rel.parts) >= 5 and SHA64.fullmatch(rel.parts[0]) is not None
         and rel.parts[1:4] == ("payload", "packages", spec["package_id"]), "ENTRY_PATH_DENIED")
    need(os.path.realpath(entry) == str(entry), "ENTRY_PATH_DENIED")   # no symlink component
    info = os.lstat(entry)
    need(stat.S_ISREG(info.st_mode), "ENTRY_PATH_DENIED")
    if spec["kind"] == "python":
        need(rel.parts[4:] == ("python", "main.py"), "ENTRY_PATH_DENIED")
    else:
        need(rel.parts[4] == "bin" and len(rel.parts) == 6 and info.st_mode & 0o111, "ENTRY_PATH_DENIED")
    digest = hashlib.sha256(entry.read_bytes()).hexdigest()
    need(digest == spec["entry_sha256"], "ENTRY_CHANGED")
    return entry


def main(argv: list[str]) -> int:
    out_dir = Path(os.environ.get("RUNTIME_DIRECTORY", ""))
    if len(argv) != 1 or not out_dir.is_absolute() or not out_dir.is_dir():
        return 64
    status_path = out_dir / "status.json"

    def finish(payload: dict) -> int:
        tmp = out_dir / "status.json.tmp"
        tmp.write_text(json.dumps(payload))
        os.replace(tmp, status_path)
        return 0

    try:
        need(os.geteuid() != 0, "ENTRY_MUST_NOT_RUN_AS_ROOT")
        spec = load_spec(argv[0])
        entry = resolve_entry(spec)
    except (EntryDenied, OSError, ValueError) as exc:
        return finish({"result": "DENIED", "code": str(exc) if isinstance(exc, EntryDenied)
                       else type(exc).__name__})
    work = out_dir / "work"
    work.mkdir(mode=0o700, exist_ok=True)
    child_argv = ([sys.executable, "-I", "-B", "-S", str(entry)] if spec["kind"] == "python"
                  else [str(entry)])
    env = {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": str(work),
           "PLASMA_JOB_ID": spec["job_id"], "PLASMA_PACKAGE_ID": spec["package_id"], **spec["env"]}
    # The Runtime's SIGTERM targets the Package; this entry survives to record it.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    stdout = os.open(out_dir / "stdout", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    stderr = os.open(out_dir / "stderr", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    pid = os.fork()
    if pid == 0:  # Package child
        try:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.chdir(work)
            devnull = os.open(os.devnull, os.O_RDONLY)
            os.dup2(devnull, 0)
            os.dup2(stdout, 1)
            os.dup2(stderr, 2)
            os.closerange(3, 65536)
            os.execve(child_argv[0], child_argv, env)
        finally:
            os._exit(127)
    os.close(stdout)
    os.close(stderr)
    _, status = os.waitpid(pid, 0)
    if os.WIFEXITED(status):
        return finish({"result": "EXITED", "exit_code": os.WEXITSTATUS(status), "signal": None})
    return finish({"result": "SIGNALED", "exit_code": None, "signal": os.WTERMSIG(status)})


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
