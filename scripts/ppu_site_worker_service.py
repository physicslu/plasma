#!/usr/bin/env python3
"""systemd entry for plasma-site-worker.service (root; AF_UNIX only).

Fail-closed wiring of the C-3 core: two sockets (control for the Runtime
group, transport for the Package group), trusted Runtime = plasma-server
MainPID, Job lease = C-1 ``execution_lease``, seals under the StateDirectory.
Exits non-zero (systemd restarts it) if any prerequisite is missing; while it
is down the Runtime cannot open Site sessions, so Site Packages fail closed.

No versioned path lives here:

* Python = the interpreter systemd started this service with
  (``sys.executable``), i.e. the Active Python Runtime of the unit.
* OpenOCD = the engine named by the deployment-written, root-owned selection
  record ``ENGINE_SELECTION`` (install root + binary/admission SHA256 + driver
  + ABI + qualified adapter speed). It is verified at startup and pinned for
  the life of this process; a new selection takes effect only on a service
  restart (behind the deployment's Runtime quiesce). A missing / invalid /
  mismatching selection never falls back to another install: the Worker
  still serves ``status`` but every session is refused ``ENGINE_NOT_READY``.
"""
from __future__ import annotations

import grp
import hashlib
import json
import os
import re
import signal
import stat
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ppu_site_worker as worker  # noqa: E402
from ppu_site_adapter_abi5 import Abi5OpenocdAdapter  # noqa: E402

RUN = Path(os.environ.get("RUNTIME_DIRECTORY", "/run/plasma-site-worker"))
STATE = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/plasma-site-worker"))
RUNTIME_CONTROL = Path("/run/plasma-server/control.sock")
ENGINE_SELECTION = Path("/etc/plasma/site-worker-engine.json")
ENGINE_BASE = Path("/opt/plasma/programming-engines/openocd")
ENGINE_SCHEMA = "plasma.ppu.site-worker-engine.v1"
SUPPORTED_DRIVER_ABI = {"plasma_swd": frozenset({5})}
PYTHON = Path(sys.executable)


class EngineNotReady(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EngineSelection:
    openocd_root: Path
    openocd_sha256: str
    admission_sha256: str
    adapter_driver: str
    driver_abi: int
    adapter_khz: int
    record_sha256: str


def _need(ok: bool, code: str) -> None:
    if not ok:
        raise EngineNotReady(code)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _trusted_file(path: Path, *, require_root: bool) -> os.stat_result:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        raise EngineNotReady("MISSING:" + path.name) from None
    except OSError:
        raise EngineNotReady("UNREADABLE:" + path.name) from None
    _need(stat.S_ISREG(info.st_mode), "NOT_REGULAR_FILE:" + path.name)
    _need(info.st_mode & 0o022 == 0, "WRITABLE_BY_OTHERS:" + path.name)
    if require_root:
        _need(info.st_uid == 0, "NOT_ROOT_OWNED:" + path.name)
    return info


def load_engine(record: Path = ENGINE_SELECTION, *, base: Path = ENGINE_BASE,
                require_root: bool = True) -> EngineSelection:
    """Resolve and verify the deployment-selected OpenOCD engine.

    Raises EngineNotReady with an explicit code; never guesses an install
    from directory names and never falls back to another version.
    """
    _trusted_file(record, require_root=require_root)
    try:
        raw = record.read_bytes()
        data: Any = json.loads(raw)
    except (OSError, ValueError):
        raise EngineNotReady("SELECTION_UNREADABLE") from None
    _need(isinstance(data, dict) and set(data) == {
        "schema", "openocd_root", "openocd_sha256", "admission_sha256",
        "adapter_driver", "driver_abi", "adapter_khz"}, "SELECTION_FIELDS_INVALID")
    _need(data["schema"] == ENGINE_SCHEMA, "SELECTION_SCHEMA_UNSUPPORTED")
    root_raw, driver, abi, khz = (data["openocd_root"], data["adapter_driver"],
                                  data["driver_abi"], data["adapter_khz"])
    _need(type(root_raw) is str and Path(root_raw).is_absolute()
          and ".." not in Path(root_raw).parts, "SELECTION_ROOT_INVALID")
    root = Path(root_raw)
    _need(root.parent == base and not root.is_symlink() and root.is_dir(),
          "SELECTION_ROOT_NOT_INSTALLED")
    for field in ("openocd_sha256", "admission_sha256"):
        _need(type(data[field]) is str and re.fullmatch(r"[0-9a-f]{64}", data[field]) is not None,
              "SELECTION_DIGEST_INVALID")
    _need(type(driver) is str and driver in SUPPORTED_DRIVER_ABI
          and type(abi) is int and abi in SUPPORTED_DRIVER_ABI[driver],
          "SELECTION_DRIVER_ABI_UNSUPPORTED")
    _need(type(khz) is int and 0 < khz <= 100_000, "SELECTION_ADAPTER_KHZ_INVALID")
    binary = root / "bin" / "openocd"
    admission = root / "libexec" / "plasma_swd_site_admission.py"
    _trusted_file(binary, require_root=require_root)
    _trusted_file(admission, require_root=require_root)
    _need(_sha256(binary) == data["openocd_sha256"], "OPENOCD_SHA256_MISMATCH")
    _need(_sha256(admission) == data["admission_sha256"], "ADMISSION_SHA256_MISMATCH")
    _need((root / "share" / "openocd" / "scripts").is_dir(), "SCRIPTS_ROOT_MISSING")
    return EngineSelection(root, data["openocd_sha256"], data["admission_sha256"], driver,
                           abi, khz, hashlib.sha256(raw).hexdigest())


class NotReadyAdapter:
    """Serves ``status`` only; every session is refused ENGINE_NOT_READY."""
    name = "engine-not-ready"
    supported_sites: frozenset[int] = frozenset()
    operations: frozenset[str] = frozenset()

    def __init__(self, code: str) -> None:
        self.not_ready = code

    def identity(self) -> Mapping[str, Any]:
        return {"state": "ENGINE_NOT_READY"}

    def startup_sealed_sites(self) -> set[int]:
        return set()

    def run(self, *_args: Any, **_kwargs: Any) -> Mapping[str, Any]:
        raise worker.TransportDenied("ENGINE_NOT_READY")


def default_adapter(record: Path = ENGINE_SELECTION, *, python: Path = PYTHON,
                    base: Path = ENGINE_BASE, require_root: bool = True):
    try:
        engine = load_engine(record, base=base, require_root=require_root)
    except EngineNotReady as exc:
        print(f"SITE_WORKER_ENGINE_NOT_READY:{exc.code}", file=sys.stderr)
        return NotReadyAdapter(exc.code)
    return Abi5OpenocdAdapter(openocd_root=engine.openocd_root, python=python,
                              adapter_khz=engine.adapter_khz,
                              adapter_driver=engine.adapter_driver)


def build(run_dir: Path = RUN, state_dir: Path = STATE, *, adapter=None,
          runtime_pid=None, lease_verifier=None, control_gid=None, transport_gid=None):
    if os.geteuid() != 0 and adapter is None:
        raise SystemExit("SITE_WORKER_REQUIRES_ROOT")
    adapter = adapter or default_adapter()
    core = worker.SiteWorkerCore(
        adapter,
        runtime_pid=runtime_pid or worker.systemd_main_pid("plasma-server.service"),
        lease_verifier=lease_verifier or worker.runtime_lease_verifier(RUNTIME_CONTROL),
        seal_dir=state_dir / "seals")
    control = worker.SiteWorkerServer(
        core, run_dir / "control.sock", mode=0o660, role="control",
        group=grp.getgrnam("plasma").gr_gid if control_gid is None else control_gid)
    transport = worker.SiteWorkerServer(
        core, run_dir / "transport.sock", mode=0o660, role="transport",
        group=grp.getgrnam("plasma-package").gr_gid if transport_gid is None else transport_gid)
    return core, control, transport


def main() -> int:
    _core, control, transport = build()
    control.start()
    transport.start()
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    stop.wait()
    control.close()
    transport.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
