#!/usr/bin/env python3
"""SWPC Development Mode Path 2/3 operator-only, non-authorizing tmux monitor.

GitHub Actions remains the executor and evidence authority. This module only
publishes short-lived progress in the existing plasma-monitor group directory.
It never authorizes, dispatches, retries or cancels a task.
"""
from __future__ import annotations

import argparse
import datetime as dt
import grp
import json
import os
from pathlib import Path
import pwd
import re
import select
import shutil
import socket
import stat
import subprocess
import sys
import termios
import time
import tty
import unicodedata

BASE = Path("/run/plasma-codex")
MONITOR = BASE / "engineering-monitor"
RUNNER = "SWPC-plasma-codex"
WORKER = "plasma-codex"
GROUP = "plasma-monitor"
PATHS = ("path2", "path3")
CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
RUN_ID = re.compile(r"[0-9]{1,20}\Z")
TASK_ID = re.compile(r"[a-z][a-z0-9-]{2,63}\Z")
PR_NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,7})\Z")


def _valid_dir(path: Path, uid: int, gid: int) -> bool:
    try:
        s = path.lstat()
    except OSError:
        return False
    return (stat.S_ISDIR(s.st_mode) and s.st_uid == uid and
            s.st_gid == gid and stat.S_IMODE(s.st_mode) == 0o2770)


def runtime_directory() -> Path | None:
    """Fail monitoring closed, NOT the engineering job, on missing access."""
    try:
        uid = pwd.getpwnam(WORKER).pw_uid
        gid = grp.getgrnam(GROUP).gr_gid
        if (socket.gethostname() != "SWPC" or
            os.environ.get("RUNNER_NAME") != RUNNER or
            os.environ.get("RUNNER_ENVIRONMENT") != "self-hosted" or
            os.geteuid() != uid or os.geteuid() == 0 or
            not _valid_dir(BASE, uid, gid)):
            return None
        if not MONITOR.exists():
            MONITOR.mkdir(mode=0o2770)
            MONITOR.chmod(0o2770)
        if not _valid_dir(MONITOR, uid, gid):
            return None
        return MONITOR
    except (OSError, KeyError):
        return None


def _write_state(directory: Path, path: str, data: dict) -> None:
    """Atomic, group-readable snapshots; never follow a preexisting symlink."""
    name = directory / (path + ".json")
    tmp = directory / (".%s.%d.json" % (path, os.getpid()))
    raw = (json.dumps(data, sort_keys=True) + "\n").encode()
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o660)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), 0o660)
            f.write(raw)
        if name.is_symlink():
            raise OSError("monitor snapshot symlink denied")
        os.replace(tmp, name)
    finally:
        if tmp.exists():
            tmp.unlink()


def _proc_start(pid: int) -> str:
    try:
        # /proc/[pid]/stat fields after the final ')': field 22 is index 19.
        fields = Path("/proc/%d/stat" % pid).read_text().rsplit(")", 1)[1].split()
        return fields[19]
    except (OSError, IndexError):
        return ""


def _alive(state: dict) -> bool:
    try:
        pid = state["pid"]
        return (type(pid) is int and pid > 0 and
                bool(state.get("proc_start")) and
                _proc_start(pid) == state["proc_start"])
    except (KeyError, TypeError, ValueError):
        return False


def _append(log: Path, message: str) -> None:
    fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW)
    try:
        os.write(fd, (message + "\n").encode())
    finally:
        os.close(fd)


def _monitor_time_mark(now: dt.datetime | None = None) -> str:
    """Timestamp for monitor-only Path 3 log; never part of Codex evidence."""
    stamp = dt.datetime.now().astimezone() if now is None else now
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("time marker requires a timezone-aware timestamp")
    return "[MONITOR TIME MARK] " + stamp.isoformat(timespec="seconds")


def run_job(path: str, command: list[str], directory: Path | None = None) -> int:
    if path not in PATHS or not command:
        raise ValueError("invalid path/command")
    # The caller must be the already-authorized trusted workflow. Monitoring
    # unavailability must never silently mutate the work-order semantics.
    directory = runtime_directory() if directory is None else directory
    live = directory is not None
    log = directory / (path + ".log") if live else None
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    task = os.environ.get("PLASMA_MONITOR_TASK", "")
    if not RUN_ID.fullmatch(run_id):
        run_id = "unknown"
    if not TASK_ID.fullmatch(task):
        task = "unknown"
    pr_number = os.environ.get("PR_NUMBER", "")
    if not PR_NUMBER.fullmatch(pr_number):
        pr_number = "-"
    state = {
        "path": path, "status": "RUNNING", "run_id": run_id,
        "task": task, "pr_number": pr_number,
        "pid": os.getpid(), "proc_start": _proc_start(os.getpid()),
        "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    }
    if live:
        try:
            fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o660)
            with os.fdopen(fd, "wb") as f:
                os.fchmod(f.fileno(), 0o660)
                f.write(("Job %s %s RUNNING (Run %s)\n" % (path, task, run_id)).encode())
            _write_state(directory, path, state)
        except OSError as exc:
            print("MONITOR_UNAVAILABLE: %s" % type(exc).__name__, file=sys.stderr)
            live = False
    env = os.environ.copy()
    if live and path == "path3":
        env["PLASMA_ENGINEERING_MONITOR_LIVE_LOG"] = str(log)
    else:
        env.pop("PLASMA_ENGINEERING_MONITOR_LIVE_LOG", None)
    result = "UNKNOWN"
    rc = 1
    try:
        # No shell or task-specific workflow. Child keeps the exact trusted
        # command, permission boundary, worktree, receipt and exit status.
        proc = subprocess.Popen(command, env=env)
        last_heartbeat = time.monotonic()
        last_time_mark = last_heartbeat
        while proc.poll() is None:
            time.sleep(1)
            now_monotonic = time.monotonic()
            if live and now_monotonic - last_heartbeat >= 15:
                _append(log, "RUNNING | elapsed %ds | Run %s" %
                        (int(now_monotonic - last_heartbeat), run_id))
                last_heartbeat = now_monotonic
            if live and path == "path3" and now_monotonic - last_time_mark >= 60:
                # A synthetic marker goes ONLY to the disposable monitor log.
                # This must not appear in Codex stdout/stderr or GitHub evidence.
                try:
                    _append(log, "\n" + _monitor_time_mark())
                except OSError as exc:
                    print("MONITOR_TIME_MARK_FAILED: %s" %
                          type(exc).__name__, file=sys.stderr)
                last_time_mark = now_monotonic
        rc = proc.wait()
        result = "PASS" if rc == 0 else "FAIL"
        return rc
    finally:
        if live:
            try:
                _append(log, "%s | exit=%s | Run %s" % (result, rc, run_id))
                _write_state(directory, path, {
                    **state, "status": "IDLE", "last_result": result,
                    "exit_code": rc,
                    "finished": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                })
            except OSError as exc:
                print("MONITOR_WRITE_FAILED: %s" % type(exc).__name__, file=sys.stderr)


def _clip_columns(line: str, width: int) -> str:
    """Keep one log line inside one terminal row (including CJK wide glyphs)."""
    if width <= 0:
        return ""
    used = 0
    chars = []
    for char in CONTROL.sub("", line).replace("\t", "    "):
        cell_width = (0 if unicodedata.combining(char) else
                      2 if unicodedata.east_asian_width(char) in ("W", "F")
                      else 1)
        if used + cell_width > width:
            break
        chars.append(char)
        used += cell_width
    return "".join(chars)


def _read_state(directory: Path, path: str) -> dict:
    state_file = directory / (path + ".json")
    try:
        if not state_file.is_symlink() and state_file.stat().st_size < 8192:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, UnicodeError, ValueError, TypeError):
        pass
    return {}


def _clear_point(directory: Path, path: str) -> tuple[int, int, int, str | None] | None:
    """Remember the end of the current log without mutating it or job evidence."""
    log_file = directory / (path + ".log")
    try:
        if log_file.is_symlink():
            return None
        st = log_file.stat()
        if not stat.S_ISREG(st.st_mode):
            return None
        return (st.st_dev, st.st_ino, st.st_size,
                _read_state(directory, path).get("started"))
    except OSError:
        return None


def _tmux_prefix_hint() -> str:
    """Display the real tmux prefix; never change any session bindings."""
    if not os.environ.get("TMUX"):
        return "Ctrl+B"  # tmux default; also used in non-tmux unit tests.
    try:
        proc = subprocess.run(
            ["tmux", "show-options", "-gv", "prefix"],
            capture_output=True, text=True, timeout=1, check=False)
        if proc.returncode == 0:
            match = re.fullmatch(r"C-([a-zA-Z])", proc.stdout.strip())
            if match:
                return "Ctrl+" + match.group(1).upper()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "Prefix"  # Avoid claiming the wrong shortcut on custom setups.


def _poll_key(fd: int) -> str | None:
    """Read at most one key without blocking the monitor refresh loop."""
    try:
        if select.select([fd], [], [], 0)[0]:
            return os.read(fd, 1).decode("ascii", errors="ignore")
    except (OSError, ValueError):
        pass
    return None


def render_snapshot(directory: Path, path: str, *,
                    width: int | None = None,
                    height: int | None = None,
                    now: dt.datetime | None = None,
                    clear_from: tuple[int, int, int, str | None] | None = None,
                    prefix: str = "Ctrl+B") -> str:
    if path not in PATHS:
        raise ValueError("unknown path")
    name = "PATH 2 | SWPC CLI" if path == "path2" else "PATH 3 | SWPC Codex"
    log_file = directory / (path + ".log")
    state = _read_state(directory, path)
    status = state.get("status", "IDLE")
    if status == "RUNNING" and not _alive(state):
        status = "IDLE (interrupted/unknown)"
    if status not in ("IDLE", "RUNNING", "IDLE (interrupted/unknown)"):
        status = "UNKNOWN"
    lines = [name,
             "KEYS: C Clear | %s 1/2 Switch" % prefix,
             "      %s D Detach" % prefix,
             "=" * 35, "STATUS: " + status,
             "RUN: %s  TASK: %s" % (state.get("run_id", "-"), state.get("task", "-"))]
    pr_number = state.get("pr_number")
    if (type(pr_number) is str and PR_NUMBER.fullmatch(pr_number) and
            pr_number != "0"):
        lines.append("PR: #" + pr_number)
    if status == "RUNNING":
        started = state.get("started", "")
        try:
            elapsed = max(0, int((dt.datetime.now(dt.timezone.utc) -
                    dt.datetime.fromisoformat(started)).total_seconds()))
            lines.append("ELAPSED: %ds" % elapsed)
        except (TypeError, ValueError):
            pass
    else:
        lines.append("LAST: %s  EXIT: %s" %
                     (state.get("last_result", "NOT_RUN"), state.get("exit_code", "-")))
    if path == "path3":
        clock = dt.datetime.now().astimezone() if now is None else now
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError("status clock requires a timezone-aware timestamp")
        # Minute precision keeps the fixed clock legible without 1 Hz redraw.
        lines.append("NOW: " + clock.isoformat(timespec="minutes"))
    lines.extend(["", "RECENT OUTPUT", "-" * 35])
    if height is not None and height <= len(lines) + 1:
        # Give the newest log line precedence over a decorative separator
        # on short terminals (the header now includes shortcut guidance).
        lines.pop()
    try:
        if log_file.is_symlink() or not stat.S_ISREG(log_file.stat().st_mode):
            raise OSError("invalid log")
        with log_file.open("rb") as f:
            st = os.fstat(f.fileno())
            start = max(0, st.st_size - 32768)
            if clear_from is not None:
                dev, ino, offset, run_start = clear_from
                if ((st.st_dev, st.st_ino, state.get("started")) ==
                        (dev, ino, run_start) and st.st_size >= offset):
                    start = max(start, offset)
                # A new job/log or truncated log is new content, not old history.
            f.seek(start)
            log_lines = f.read().decode("utf-8", errors="replace").splitlines()[-30:]
    except OSError:
        log_lines = ["(no local output yet)"]
    if height is not None:
        # Reserve the bottom row to prevent tmux scrolling on a repaint.
        visible_log_rows = max(0, height - 1 - len(lines))
        log_lines = log_lines[-visible_log_rows:] if visible_log_rows else []
    lines.extend(log_lines)
    if height is not None:
        lines = lines[:max(0, height - 1)]
    if width is not None:
        # Leave one physical cell unused to avoid terminal autowrap.
        lines = [_clip_columns(str(line), max(0, width - 1)) for line in lines]
    return CONTROL.sub("", "\n".join(str(x) for x in lines))


def view_loop(path: str, *, directory: Path = MONITOR, output=None,
              get_size=None, sleep=None, get_now=None, get_key=None) -> None:
    """Repaint changed frames and allow operator-only, display-only C clear."""
    if output is None:
        output = sys.stdout
    if get_size is None:
        get_size = shutil.get_terminal_size
    if sleep is None:
        sleep = time.sleep
    if get_now is None:
        get_now = lambda: dt.datetime.now().astimezone()

    saved_tty = None
    fd = None
    if get_key is None:
        get_key = lambda: None
        if sys.stdin.isatty():
            try:
                fd = sys.stdin.fileno()
                saved_tty = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                get_key = lambda: _poll_key(fd)
            except OSError:
                saved_tty = None

    prefix = _tmux_prefix_hint()
    previous = None
    previous_size = None
    clear_from = None
    try:
        while True:
            if get_key() in ("c", "C"):
                clear_from = _clear_point(directory, path)
                previous = None  # Force repaint, even if status is unchanged.
            width, height = get_size()
            size = (width, height)
            frame = render_snapshot(
                directory, path, width=width, height=height,
                now=get_now() if path == "path3" else None,
                clear_from=clear_from, prefix=prefix)
            if frame != previous or size != previous_size:
                # Only repaint this tmux pane, not global terminal scrollback.
                # Clear old cells BEFORE painting shorter replacement lines.
                output.write("\033[H\033[J" + frame)
                output.flush()
                previous = frame
                previous_size = size
            sleep(1)
    finally:
        if saved_tty is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, saved_tty)


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="action", required=True)
    for action in ("run", "view"):
        q = sub.add_parser(action)
        q.add_argument("path", choices=PATHS)
        if action == "run":
            q.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args()
    if args.action == "run":
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        return run_job(args.path, command)
    try:
        view_loop(args.path)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
