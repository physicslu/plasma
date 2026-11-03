#!/usr/bin/env python3
"""Stage C-2: non-root process executor for Python / Native C Package Actions.

This is the ``trusted_executors`` adapter for ``ppu_asset_execution`` (one
dispatch seam; no second Package Engine, shell executor or FPGA loader). It
runs ONLY the planned, identity-bound entrypoint of the Active Asset Set:

* python  -> ``<trusted python> -I -B -S <set>/payload/packages/<id>/python/main.py``
* native-c -> the single executable ``<set>/payload/packages/<id>/bin/<file>``

with no request-supplied argv, path, environment or shell. The launcher
refuses to run as root. The child runs in its own session/process group, with
a clean environment, a private 0700 work directory, stdin=/dev/null, bounded
captured output and rlimits (CPU, address space, open files, file size, no
core). Timeout and cancellation kill the WHOLE process group. A durable
journal record is written before spawn and finalized after reaping.

Not provided here (NOT_QUALIFIED): dedicated per-Package UID, network
namespace, seccomp/syscall filtering. Those need a privileged helper or a Z2
permission matrix (separate owner decision). Packages declaring Sites are
refused until the Site Transport broker exists (Stage C-3): this launcher
never opens /dev/mem, /dev/uio*, FPGA Manager or any MMIO on their behalf.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

RECEIPT_SCHEMA = "plasma.ppu.package-action-receipt.v1"
JOURNAL_SCHEMA = "plasma.ppu.package-action-journal.v1"
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
JOB_ID = re.compile(r"[0-9a-f]{32}\Z")
OUTPUT_LIMIT = 64 * 1024
TAIL_BYTES = 4096
KILL_GRACE_S = 2.0
MEMORY_LIMIT = 512 * 1024 * 1024
OPEN_FILES_LIMIT = 64
FILE_SIZE_LIMIT = 16 * 1024 * 1024
RESULTS = frozenset({"SUCCEEDED", "FAILED", "TIMEOUT", "CANCELLED"})


class PackageLaunchDenied(ValueError):
    pass


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise PackageLaunchDenied(code)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def _limits(cpu_s: int) -> Callable[[], None]:
    def apply() -> None:  # runs in the child between fork and exec
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
        resource.setrlimit(resource.RLIMIT_NOFILE, (OPEN_FILES_LIMIT, OPEN_FILES_LIMIT))
        resource.setrlimit(resource.RLIMIT_FSIZE, (FILE_SIZE_LIMIT, FILE_SIZE_LIMIT))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        os.umask(0o077)
    return apply


def _kill_group(pgid: int, sig: int) -> None:
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _output(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()[: OUTPUT_LIMIT + 1]
    except FileNotFoundError:  # e.g. the systemd entry was SIGKILLed
        raw = b""
    return {"bytes": min(len(raw), OUTPUT_LIMIT), "truncated": len(raw) > OUTPUT_LIMIT,
            "sha256": hashlib.sha256(raw[:OUTPUT_LIMIT]).hexdigest(),
            "tail": raw[:OUTPUT_LIMIT][-TAIL_BYTES:].decode("utf-8", "replace")}


class LocalProcessSpawner:
    """Default (development / Host) process primitive: same uid as the Runtime.

    Keeps the exact Stage C-2 behaviour. ``dedicated_uid`` is NOT_QUALIFIED.
    """

    launcher = "non-root-process-group"
    isolation = {"dedicated_uid": "NOT_QUALIFIED", "network": "NOT_QUALIFIED",
                 "syscall_filter": "NOT_QUALIFIED", "rlimits": "APPLIED"}

    def __init__(self, geteuid: Callable[[], int] = os.geteuid) -> None:
        self._geteuid = geteuid

    def spawn(self, *, job_id: str, package_id: str, kind: str, argv: list[str],
              entry: Path, entry_sha256: str, env: dict[str, str], work: Path,
              limit: int) -> "_LocalHandle":
        stdout_path, stderr_path = work / ".stdout", work / ".stderr"
        with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
            child = subprocess.Popen(
                argv, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                close_fds=True, start_new_session=True, preexec_fn=_limits(limit + 1),
            )
        return _LocalHandle(child, self._geteuid(), stdout_path, stderr_path)


class _LocalHandle:
    def __init__(self, child, uid, stdout_path, stderr_path):
        self.child, self.uid = child, uid
        self.pgid = child.pid
        self.stdout_path, self.stderr_path = stdout_path, stderr_path

    def poll(self):
        return self.child.poll()

    def signal_group(self, sig: int) -> None:
        _kill_group(self.pgid, sig)

    def wait(self, timeout: float | None = None):
        return self.child.wait(timeout=timeout)

    def group_alive(self) -> bool:
        return _group_alive(self.pgid)

    @property
    def returncode(self):
        return self.child.returncode

    def finish(self) -> None:
        pass


PACKAGE_UNIT = "plasma-package@{job}.service"
UNIT_SPEC_SCHEMA = "plasma.ppu.package-unit-spec.v1"


def run_systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/usr/bin/systemctl", *args], capture_output=True, text=True,
                          timeout=30, env={"PATH": "/usr/bin:/bin", "LANG": "C"})


class SystemdUnitSpawner:
    """Production process primitive: run the Package as ``plasma-package``.

    The Runtime (uid plasma) may only start / stop / kill instances of the
    fixed template ``plasma-package@<32hex>.service`` through the fixed-purpose
    root helper ``ppu_package_unit_helper.py`` (pass ``HelperSystemctl`` as
    ``systemctl``); user,
    sandbox and ExecStart (``ppu_package_entry.py``) are fixed in the unit.
    The only data passed is a job spec in the Runtime-owned spec directory.
    systemd's cgroup bounds every Package process, including setsid escapes.
    """

    launcher = "systemd-unit:plasma-package@"
    isolation = {"dedicated_uid": "CONFIGURED_NOT_QUALIFIED_ON_Z2",
                 "network": "PRIVATE_NETWORK_CONFIGURED_NOT_QUALIFIED_ON_Z2",
                 "syscall_filter": "CONFIGURED_NOT_QUALIFIED_ON_Z2",
                 "rlimits": "CONFIGURED_NOT_QUALIFIED_ON_Z2"}

    def __init__(self, *, package_uid: int,
                 spec_dir: Path = Path("/run/plasma-package-specs"),
                 output_root: Path = Path("/run/plasma-package"),
                 systemctl: Callable[..., subprocess.CompletedProcess] = run_systemctl) -> None:
        _require(type(package_uid) is int and package_uid > 0, "PACKAGE_UID_INVALID")
        self.package_uid = package_uid
        self.spec_dir = Path(spec_dir)
        self.output_root = Path(output_root)
        self.systemctl = systemctl

    def spawn(self, *, job_id: str, package_id: str, kind: str, argv: list[str],
              entry: Path, entry_sha256: str, env: dict[str, str], work: Path,
              limit: int) -> "_UnitHandle":
        _require(JOB_ID.fullmatch(job_id) is not None, "PACKAGE_LAUNCH_PLAN_INVALID")
        _require(package_id != "" and kind in ("python", "native-c"), "PACKAGE_LAUNCH_PLAN_INVALID")
        if self.package_uid == os.geteuid():
            raise PackageLaunchDenied("PACKAGE_UID_EQUALS_RUNTIME_UID")
        unit = PACKAGE_UNIT.format(job=job_id)
        spec = {"schema": UNIT_SPEC_SCHEMA, "job_id": job_id, "package_id": package_id,
                "kind": kind, "entry_path": str(entry), "entry_sha256": entry_sha256,
                "env": {k: v for k, v in env.items() if k == "PLASMA_SITE_WORKER_SOCKET"}}
        path = self.spec_dir / f"{job_id}.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(spec, stream, sort_keys=True)
        os.chmod(path, 0o644)
        started = self.systemctl("start", unit)
        handle = _UnitHandle(self, unit, job_id, path)
        if started.returncode != 0:
            handle.finish()
            raise PackageLaunchDenied("PACKAGE_UNIT_START_DENIED")
        props = handle.show()
        pid = int(props.get("MainPID", "0") or 0)
        if pid <= 1:
            handle.finish()
            raise PackageLaunchDenied("PACKAGE_UNIT_NO_MAIN_PID")
        handle.pgid = pid  # systemd makes the main process a session leader
        return handle

    def stop_leftover(self) -> list[str]:
        """Runtime restart: stop every remaining Package unit (outcome unknown)."""
        listed = self.systemctl("list-units", "--all", "--plain", "--no-legend", "plasma-package@*")
        stopped = []
        for line in listed.stdout.splitlines():
            unit = line.split()[0] if line.split() else ""
            if re.fullmatch(r"plasma-package@[0-9a-f]{32}\.service", unit):
                self.systemctl("stop", unit)
                stopped.append(unit)
        return stopped


class _UnitHandle:
    def __init__(self, spawner: SystemdUnitSpawner, unit: str, job_id: str, spec_path: Path):
        self.spawner, self.unit, self.spec_path = spawner, unit, spec_path
        self.uid = spawner.package_uid
        self.pgid = 0
        out = spawner.output_root / job_id
        self.stdout_path, self.stderr_path, self.status_path = out / "stdout", out / "stderr", out / "status.json"
        self.returncode = None

    def show(self) -> dict[str, str]:
        r = self.spawner.systemctl("show", "--property=ActiveState,SubState,MainPID,TasksCurrent", self.unit)
        return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)

    def poll(self):
        if self.returncode is not None:
            return self.returncode
        props = self.show()
        state, sub = props.get("ActiveState"), props.get("SubState")
        if state == "active" and sub == "exited":
            try:
                status = json.loads(self.status_path.read_text())
            except (OSError, ValueError):
                status = {"result": "UNKNOWN"}
            if status.get("result") == "EXITED" and type(status.get("exit_code")) is int:
                self.returncode = status["exit_code"]
            elif status.get("result") == "SIGNALED" and type(status.get("signal")) is int:
                self.returncode = -status["signal"]
            else:  # entry denied the spec, or status unreadable
                self.returncode = 126
        elif state in ("failed", "inactive"):
            self.returncode = -signal.SIGKILL
        return self.returncode

    def signal_group(self, sig: int) -> None:
        self.spawner.systemctl("kill", f"--signal={int(sig)}", "--kill-whom=all", self.unit)

    def wait(self, timeout: float | None = None):
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.unit, timeout)
            time.sleep(0.05)
        return self.returncode

    def group_alive(self) -> bool:
        props = self.show()
        tasks = props.get("TasksCurrent", "")
        if tasks.isdigit():
            return int(tasks) > 0
        return props.get("ActiveState") == "active" and props.get("SubState") == "running"

    def finish(self) -> None:
        self.spawner.systemctl("stop", self.unit)
        try:
            os.unlink(self.spec_path)
        except FileNotFoundError:
            pass


def make_package_executor(
    product_root: Path, *, python_executable: Path, state_root: Path,
    cancel_event: threading.Event | None = None,
    geteuid: Callable[[], int] = os.geteuid,
    poll_s: float = 0.05,
    site_worker: Any | None = None,
    spawner: Any | None = None,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """Return the python / native-c executor for ``dispatch_asset_execution``.

    ``state_root`` holds the durable Package Action journal (``<job_id>.json``)
    and per-job private work directories. ``cancel_event`` is the Runtime
    Job's cancellation signal. ``site_worker`` (Stage C-3) is the only way a
    Package declaring Sites can run: without it such Packages are refused
    (``PACKAGE_SITE_TRANSPORT_NOT_WIRED``). With it, a Worker session bound
    to this Job, its declared Sites and the child process group is opened
    after spawn and always closed afterwards. ``spawner`` is only the process
    primitive (default ``LocalProcessSpawner``; production
    ``SystemdUnitSpawner`` runs the Package as ``plasma-package``); identity
    validation, timeout / cancel decisions, journal and receipt stay here.
    """
    product_root = Path(product_root)
    python_executable = Path(python_executable)
    state_root = Path(state_root)
    spawner = spawner if spawner is not None else LocalProcessSpawner(geteuid)

    def execute(plan: Mapping[str, Any]) -> dict[str, Any]:
        _require(geteuid() != 0, "PACKAGE_LAUNCHER_MUST_NOT_RUN_AS_ROOT")
        _require(isinstance(plan, Mapping)
                 and plan.get("schema") == "plasma.ppu.asset-execution-plan.v1"
                 and plan.get("status") == "AUTHORIZED_NOT_EXECUTED"
                 and plan.get("package_kind") in ("python", "native-c")
                 and type(plan.get("asset_set_sha256")) is str and SHA64.fullmatch(plan["asset_set_sha256"])
                 and type(plan.get("job_id")) is str and JOB_ID.fullmatch(plan["job_id"]),
                 "PACKAGE_LAUNCH_PLAN_INVALID")
        resources, entry = plan.get("resources"), plan.get("entrypoint")
        _require(isinstance(resources, Mapping) and isinstance(entry, Mapping)
                 and type(resources.get("max_runtime_s")) is int and resources["max_runtime_s"] > 0
                 and type(entry.get("path")) is str and type(entry.get("sha256")) is str
                 and SHA64.fullmatch(entry["sha256"]),
                 "PACKAGE_LAUNCH_PLAN_INVALID")
        sites = resources.get("sites")
        _require(type(sites) is list and (sites == [] or site_worker is not None),
                 "PACKAGE_SITE_TRANSPORT_NOT_WIRED")
        package_root = f"payload/packages/{plan['package_id']}/"
        _require(entry["path"].startswith(package_root) and ".." not in entry["path"].split("/"),
                 "PACKAGE_LAUNCH_ENTRYPOINT_DENIED")
        staged = product_root / "assets" / "staged" / plan["asset_set_sha256"]
        target = staged / entry["path"]
        info = target.lstat() if os.path.lexists(target) else None
        _require(info is not None and stat.S_ISREG(info.st_mode), "PACKAGE_LAUNCH_ENTRYPOINT_DENIED")
        _require(_sha(target) == entry["sha256"], "PACKAGE_LAUNCH_ENTRYPOINT_CHANGED")
        if plan["package_kind"] == "python":
            _require(python_executable.is_absolute() and python_executable.is_file(),
                     "PACKAGE_LAUNCH_PYTHON_UNAVAILABLE")
            argv = [str(python_executable), "-I", "-B", "-S", str(target)]
        else:
            _require(info.st_mode & 0o111 != 0, "PACKAGE_LAUNCH_ENTRYPOINT_DENIED")
            argv = [str(target)]

        state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        record_path = state_root / f"{plan['job_id']}.json"
        _require(not os.path.lexists(record_path), "PACKAGE_ACTION_JOB_ALREADY_RECORDED")
        identity = {k: plan[k] for k in ("asset_set_sha256", "package_identity_sha256",
                                         "package_kind", "package_id", "job_id")}
        record = {"schema": JOURNAL_SCHEMA, **identity, "state": "running",
                  "started_epoch_s": time.time(), "uid": geteuid()}
        _atomic_json(record_path, record)
        work = Path(tempfile.mkdtemp(prefix=f"job-{plan['job_id']}-", dir=state_root))
        os.chmod(work, 0o700)
        env = {"PATH": "/usr/bin:/bin", "LANG": "C", "HOME": str(work),
               "PLASMA_JOB_ID": plan["job_id"], "PLASMA_PACKAGE_ID": plan["package_id"]}
        if sites:
            env["PLASMA_SITE_WORKER_SOCKET"] = str(site_worker.socket_path)
        session = None
        transport: dict[str, Any] = {"sites": list(sites), "session": "NOT_USED"}
        limit = resources["max_runtime_s"]
        result, exit_code, killed_signal = "FAILED", None, None
        started = time.monotonic()
        child = None
        try:
            child = spawner.spawn(job_id=plan["job_id"], package_id=plan["package_id"],
                                  kind=plan["package_kind"], argv=argv, entry=target,
                                  entry_sha256=entry["sha256"], env=env, work=work, limit=limit)
            pgid = child.pgid
            deadline = started + limit
            reason = None
            if sites:
                try:
                    session = site_worker.open_session(
                        job_id=plan["job_id"], sites=list(sites), pgid=pgid,
                        uid=child.uid, max_runtime_s=limit)
                    transport["session"] = "OPENED"
                except Exception as exc:
                    transport.update(session="DENIED", error=str(exc)[:120])
                    reason = "SITE_SESSION_DENIED"
                    child.signal_group(signal.SIGKILL)
            while child.poll() is None:
                if cancel_event is not None and cancel_event.is_set():
                    reason = "CANCELLED"
                elif time.monotonic() >= deadline:
                    reason = "TIMEOUT"
                if reason:
                    child.signal_group(signal.SIGTERM)
                    try:
                        child.wait(timeout=KILL_GRACE_S)
                    except subprocess.TimeoutExpired:
                        pass
                    break
                time.sleep(poll_s)
            # Always kill and reap the whole group: no orphaned grandchildren.
            child.signal_group(signal.SIGKILL)
            if session is not None:
                try:
                    closed = site_worker.close_session(session["session_id"])
                    transport.update(session="CLOSED", sealed_sites=closed.get("sealed_sites", []))
                except Exception as exc:
                    transport.update(session="CLOSE_FAILED", error=str(exc)[:120])
                session = None
            child.wait()
            for _ in range(int(KILL_GRACE_S / poll_s)):
                if not child.group_alive():
                    break
                time.sleep(poll_s)
            group_reaped = not child.group_alive()
            exit_code = child.returncode
            if exit_code is not None and exit_code < 0:
                killed_signal, exit_code = -exit_code, None
            result = ("FAILED" if reason == "SITE_SESSION_DENIED"
                      else reason or ("SUCCEEDED" if exit_code == 0 else "FAILED"))
            # Unknown hardware outcome: a sealed Site or an unconfirmed close.
            hardware = ("NONE" if not sites else
                        "UNKNOWN_SITE_SEALED" if transport.get("sealed_sites") else
                        "UNKNOWN_SESSION_NOT_CLOSED" if transport["session"] == "CLOSE_FAILED" else
                        "SITE_WORKER")
            receipt = {
                "schema": RECEIPT_SCHEMA, **identity, "result": result,
                "exit_code": exit_code, "signal": killed_signal,
                "duration_s": round(time.monotonic() - started, 3),
                "max_runtime_s": limit, "process_group_reaped": group_reaped,
                "stdout": _output(child.stdout_path), "stderr": _output(child.stderr_path),
                "launcher": spawner.launcher, "uid": geteuid(), "package_uid": child.uid,
                "isolation": dict(spawner.isolation),
                "site_ids": list(sites), "hardware": hardware, "site_transport": transport,
            }
            _require(group_reaped, "PACKAGE_ACTION_PROCESS_GROUP_NOT_REAPED")
            final = {**record, "state": result.lower(), "finished_epoch_s": time.time(),
                     "hardware": hardware,
                     "receipt_sha256": hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()}
            _atomic_json(record_path, final)
            return receipt
        except BaseException as exc:
            if session is not None:
                try:
                    site_worker.close_session(session["session_id"])
                except Exception:
                    pass
            _atomic_json(record_path, {**record, "state": "outcome_unknown",
                                       "error": type(exc).__name__, "finished_epoch_s": time.time()})
            raise
        finally:
            if child is not None:
                try:
                    child.finish()
                except Exception:
                    pass
            shutil.rmtree(work, ignore_errors=True)

    return execute


def interrupted_actions(state_root: Path) -> list[str]:
    """Job IDs whose journal never reached a terminal state (Runtime restart)."""
    out = []
    root = Path(state_root)
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out.append(path.stem)
            continue
        if record.get("state") in ("running", "outcome_unknown"):
            out.append(path.stem)
    return out
