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

import plasma_engineering_activity as engineering_activity

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
WORK_ORDER_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
# Defense-in-depth: hosted Authorizer independently validates the source.
# The monitor may display only an explicitly submitted public metadata field.
MONITOR_SUMMARY = re.compile(
    r"[A-Za-z0-9\u4e00-\u9fff]"
    r"[A-Za-z0-9\u4e00-\u9fff ._()/+-]{6,78}"
    r"[A-Za-z0-9\u4e00-\u9fff)]\Z"
)
MONITOR_SENSITIVE = re.compile(
    r"\b(?:password|passwd|secret|credential|token|bearer|"
    r"private.key|api.key|authorization)\b|[a-fA-F0-9]{32,}",
    re.IGNORECASE,
)
# One layout for both paths. Terminal widths are display cells, not letters.
MAX_DISPLAY_COLUMNS = 100
MONITOR_STAGES = frozenset({
    "CPU-only CLI", "Native preflight", "Vivado host build",
    "Guarded Download", "Guarded Test", "Guarded Restore",
    "Guarded Full HIL", "Codex workspace",
})
STATIC_GUARDED_STAGES = {
    "z2-path2-download": "Guarded Download",
    "z2-path2-testing": "Guarded Test",
    "z2-path2-restore": "Guarded Restore",
    "z2-path2-full-hil": "Guarded Full HIL",
}
# Narrow receipt projection; a filesystem JSON file is NOT an independently
# authenticated verification receipt. Project known categorical DENIAL only.
RECEIPT_PERMISSION_STAGES = frozenset({
    "CLI_WRAPPER", "CLI_MANIFEST", "PLATFORM_MANIFEST", "NATIVE_BINARY",
})
RECEIPT_PERMISSION_CAUSES = frozenset({"OWNER_MISMATCH", "PEER_WRITABLE"})
MAX_RECEIPT_BYTES = 8192


def _receipt_permission_hint(raw: object, *, run_id: str, task: str,
                             work_order_sha: str, exit_code: int) -> dict | None:
    """Project only an exact known sanitized native preflight denial."""
    if (exit_code != 2 or task != "path2-work-order" or
            WORK_ORDER_SHA256.fullmatch(work_order_sha) is None or
            type(raw) is not dict):
        return None
    if not (
        raw.get("schema") == "plasma.codex.native_preflight.v1" and
        raw.get("status") == "NOT_RUN_OR_FAIL" and
        raw.get("reason") == "NATIVE_PATH_PERMISSIONS_DENIED" and
        raw.get("github_run_id") == run_id and
        raw.get("task_id") == task and
        raw.get("work_order_sha256") == work_order_sha and
        type(raw.get("denial_stage")) is str and
        raw["denial_stage"] in RECEIPT_PERMISSION_STAGES and
        type(raw.get("denial_cause")) is str and
        raw["denial_cause"] in RECEIPT_PERMISSION_CAUSES and
        raw.get("model_session") == "NOT_RUN" and
        raw.get("hardware_access") == "NOT_RUN" and
        raw.get("provenance") == "NOT_INDEPENDENTLY_VERIFIED" and
        raw.get("sha256_pin_authorized") is False
    ):
        return None
    index = raw.get("denial_component_index")
    if type(index) is not int or not 1 <= index <= 24:
        return None
    return {
        "reason": "NATIVE_PATH_PERMISSIONS_DENIED",
        "stage": raw["denial_stage"],
        "cause": raw["denial_cause"],
        "component_index": index,
    }


def _safe_stored_receipt_hint(value: object) -> dict | None:
    """Validate the monitor snapshot again; it is group-readable metadata."""
    if type(value) is not dict or set(value) != {
            "reason", "stage", "cause", "component_index"}:
        return None
    if (value["reason"] != "NATIVE_PATH_PERMISSIONS_DENIED" or
            type(value["stage"]) is not str or
            value["stage"] not in RECEIPT_PERMISSION_STAGES or
            type(value["cause"]) is not str or
            value["cause"] not in RECEIPT_PERMISSION_CAUSES or
            type(value["component_index"]) is not int or
            not 1 <= value["component_index"] <= 24):
        return None
    return value


def _read_path2_receipt_hint(*, runner_temp: object, run_id: str,
                             task: str, work_order_sha: str,
                             exit_code: int) -> dict | None:
    """Read only the fixed Runner Temp receipt, never user-supplied paths.

    No arbitrary output, filenames, stack traces or command arguments are
    copied into the Monitor. Any absence/race/error fails closed.
    """
    if (type(runner_temp) is not str or not runner_temp or
            not Path(runner_temp).is_absolute() or len(runner_temp) > 512 or
            run_id == "unknown"):
        return None
    # Exact file name is from the trusted workflow, not the Work Order.
    file_path = Path(runner_temp) / "plasma-path2-receipt.json"
    fd = -1
    try:
        fd = os.open(file_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or
                st.st_nlink != 1 or st.st_mode & 0o022 or
                not 0 < st.st_size <= MAX_RECEIPT_BYTES):
            return None
        with os.fdopen(fd, "rb", closefd=False) as stream:
            body = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(body) > MAX_RECEIPT_BYTES:
            return None
        raw = json.loads(body.decode("utf-8"))
        return _receipt_permission_hint(
            raw, run_id=run_id, task=task,
            work_order_sha=work_order_sha, exit_code=exit_code)
    except (OSError, ValueError, UnicodeError, TypeError):
        return None
    finally:
        if fd >= 0:
            os.close(fd)




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
    work_order_sha = os.environ.get("WORK_ORDER_SHA256", "")
    summary = os.environ.get("PLASMA_MONITOR_SUMMARY", "")
    summary_valid = (
        task == ("path3-work-order" if path == "path3" else "path2-work-order") and
        WORK_ORDER_SHA256.fullmatch(work_order_sha) is not None and
        type(summary) is str and MONITOR_SUMMARY.fullmatch(summary) is not None
        and MONITOR_SENSITIVE.search(summary) is None
    )
    stage = os.environ.get("PLASMA_MONITOR_STAGE", "")
    guarded = stage.startswith("Guarded ") if type(stage) is str else False
    guarded_verified = (
        (task == "path2-work-order" and
         WORK_ORDER_SHA256.fullmatch(work_order_sha) is not None) or
        STATIC_GUARDED_STAGES.get(task) == stage
    )
    if path == "path3":
        # Validated Work Order category, NOT an inferred Vivado/build phase.
        stage = ("Codex workspace" if task == "path3-work-order" and
                 WORK_ORDER_SHA256.fullmatch(work_order_sha) is not None
                 else "")
    elif (type(stage) is not str or stage not in MONITOR_STAGES or
          stage == "Codex workspace" or
          (guarded and not guarded_verified)):
        stage = ""
    state = {
        "path": path, "status": "RUNNING", "run_id": run_id,
        "task": task, "pr_number": pr_number,
        "monitor_summary": summary if summary_valid else "",
        "monitor_stage": stage,
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
    # Operator-only metadata never enters the engineering/Codex process env.
    env.pop("PLASMA_MONITOR_SUMMARY", None)
    env.pop("PLASMA_MONITOR_STAGE", None)
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
                # A verified Runner receipt is NOT asserted: expose only a
                # bounded categorical hint matching this exact run/Work Order.
                hint = (_read_path2_receipt_hint(
                    runner_temp=os.environ.get("RUNNER_TEMP", ""),
                    run_id=run_id, task=task,
                    work_order_sha=work_order_sha, exit_code=rc)
                    if path == "path2" and rc != 0 else None)
                _append(log, "%s | exit=%s | Run %s" % (result, rc, run_id))
                _write_state(directory, path, {
                    **state, "status": "IDLE", "last_result": result,
                    "exit_code": rc,
                    **({"receipt_hint": hint} if hint is not None else {}),
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
    lines = ["%s | C Clear | %s 1/2 Switch | %s D Detach" %
             (name, prefix, prefix),
             "=" * 35,
             "STATUS: %s    RUN: %s" % (status, state.get("run_id", "-")),
             "TASK: %s" % state.get("task", "-")]
    pr_number = state.get("pr_number")
    if (type(pr_number) is str and PR_NUMBER.fullmatch(pr_number) and
            pr_number != "0"):
        lines[-1] += "  PR: #" + pr_number
    if path in PATHS:
        summary = state.get("monitor_summary", "")
        if (type(summary) is str and
                MONITOR_SUMMARY.fullmatch(summary) is not None and
                MONITOR_SENSITIVE.search(summary) is None):
            lines.append("GOAL: " + summary)
        else:
            lines.append("GOAL: (operator summary not provided)")
    stage = state.get("monitor_stage", "")
    if (type(stage) is not str or stage not in MONITOR_STAGES or
        (path == "path3" and stage != "Codex workspace") or
        (path == "path2" and stage == "Codex workspace")):
        stage = ""
    lines.append("STAGE: " + (stage or "(not available)"))
    if status == "RUNNING":
        started = state.get("started", "")
        try:
            elapsed = max(0, int((dt.datetime.now(dt.timezone.utc) -
                    dt.datetime.fromisoformat(started)).total_seconds()))
            lines.append("ELAPSED: %ds" % elapsed)
        except (TypeError, ValueError):
            pass
    else:
        # The monitor wrapper's return code is NOT a verification receipt.
        lines.append("WRAPPER: %s  EXIT: %s" %
                     (state.get("last_result", "NOT_RUN"), state.get("exit_code", "-")))
        hint = _safe_stored_receipt_hint(state.get("receipt_hint"))
        if (path == "path2" and state.get("last_result") == "FAIL" and
                type(state.get("exit_code")) is int and
                state["exit_code"] == 2 and
                state.get("task") == "path2-work-order" and
                hint is not None):
            lines.append("RECEIPT: %s | %s | %s | #%d" % (
                hint["reason"], hint["stage"], hint["cause"],
                hint["component_index"]))
    if path in PATHS:
        clock = dt.datetime.now().astimezone() if now is None else now
        if clock.tzinfo is None or clock.utcoffset() is None:
            raise ValueError("status clock requires a timezone-aware timestamp")
        # Show the SWPC host-local wall clock. Do not render ISO's "T"
        # separator or UTC offset; keep minute cadence and timestamp inputs
        # timezone-aware. Evidence and monitor time marks are unchanged.
        lines.append("NOW: " + clock.strftime("%Y-%m-%d %H:%M"))
    # Activity is recomputed from the already sanitized, bounded log tail.
    # It never becomes a new job authorizer or a trusted result receipt.
    lines.append("DOING: —")
    lines.extend(["", "RECENT ACTIVITY", "-" * 35])
    if height is not None:
        # Preserve at least one latest log row plus a spare bottom row.
        # Sacrifice decoration before truncating trusted status/goal/stage.
        for decoration in ("-" * 35, ""):
            if height > len(lines) + 1:
                break
            if decoration in lines:
                lines.remove(decoration)
    # Scan more than the visible tail so a prior observed failure survives
    # subsequent successful steps. This is bounded history, not a receipt.
    # The actual task result and failure cause remain in GitHub evidence.
    history_lines = []
    try:
        if log_file.is_symlink() or not stat.S_ISREG(log_file.stat().st_mode):
            raise OSError("invalid log")
        with log_file.open("rb") as f:
            st = os.fstat(f.fileno())
            scan_start = max(0, st.st_size - 524288)
            f.seek(scan_start)
            history_lines = f.read().decode("utf-8", errors="replace").splitlines()
            log_lines = history_lines[-30:]
            if clear_from is not None:
                dev, ino, offset, run_start = clear_from
                if ((st.st_dev, st.st_ino, state.get("started")) ==
                        (dev, ino, run_start) and st.st_size >= offset):
                    f.seek(max(scan_start, offset))
                    log_lines = f.read().decode("utf-8", errors="replace").splitlines()[-30:]
    except OSError:
        log_lines = ["(no local output yet)"]
    active_items = {}
    last_step = None
    last_error = None
    last_sequence = 0
    for original in history_lines:
        event = engineering_activity.parse_public_line(original)
        if event is None or event["seq"] <= last_sequence:
            continue
        last_sequence = event["seq"]
        if event["state"] == "RUNNING":
            active_items[event["id"]] = event
        else:
            active_items.pop(event["id"], None)
            last_step = event
            if event["state"] == "FAIL":
                last_error = event

    def _step_label(event: dict) -> str:
        result = event["state"]
        if event["exit_code"] is not None:
            result += " (exit %d)" % event["exit_code"]
        return "[%s] %s %s | %s" % (
            event["source"], event["kind"], result, event["detail"])

    activity_rows = []
    visible_sequence = 0
    for original in log_lines:
        event = engineering_activity.parse_public_line(original)
        if event is None or event["seq"] <= visible_sequence:
            continue
        visible_sequence = event["seq"]
        activity_rows.append("%s %s" % (event["time"], _step_label(event)))
    if activity_rows:
        log_lines = activity_rows[-30:]
    else:
        # Invalid structured records are never echoed as raw terminal lines.
        log_lines = [
            line for line in log_lines
            if not line.startswith(engineering_activity.PREFIX)]
    if status == "RUNNING" and active_items:
        last = next(reversed(active_items.values()))
        lines[lines.index("DOING: —")] = (
            "DOING: %s | %s" % (last["kind"], last["detail"]))
    insert_at = lines.index("DOING: —") + 1 if "DOING: —" in lines else (
        next(i for i, line in enumerate(lines) if line.startswith("DOING:")) + 1)
    if last_step is not None:
        lines.insert(insert_at, "LAST STEP: " + _step_label(last_step))
        insert_at += 1
    if last_error is not None:
        lines.insert(insert_at, "LAST ERROR: " + _step_label(last_error))
    if height is not None:
        # Keep diagnostic failures ahead of optional last-step and decoration.
        # A short pane still reserves one physical row for recent output.
        while len(lines) > max(0, height - 2):
            optional = next((i for i, line in enumerate(lines)
                             if line.startswith("LAST STEP:")), None)
            if optional is not None:
                lines.pop(optional)
            elif "" in lines:
                lines.remove("")
            elif "-" * 35 in lines:
                lines.remove("-" * 35)
            elif any(line.startswith("LAST ERROR:") for line in lines):
                # Prefer the observed failure + recent output to a clock line.
                clock_index = next((i for i, line in enumerate(lines)
                                    if line.startswith("NOW:")), None)
                if clock_index is not None:
                    lines.pop(clock_index)
                else:
                    break
            else:
                break
    if height is not None:
        # Reserve the bottom row to prevent tmux scrolling on a repaint.
        visible_log_rows = max(0, height - 1 - len(lines))
        log_lines = log_lines[-visible_log_rows:] if visible_log_rows else []
    lines.extend(log_lines)
    if height is not None:
        lines = lines[:max(0, height - 1)]
    if width is not None:
        # Leave one physical cell unused to avoid terminal autowrap.
        lines = [_clip_columns(str(line),
                max(0, min(width - 1, MAX_DISPLAY_COLUMNS))) for line in lines]
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
