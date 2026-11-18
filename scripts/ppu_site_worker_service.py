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
* OpenOCD = the engine named by the root-owned selection record
  ``ENGINE_SELECTION`` (install root + binary/admission SHA256 + driver + ABI +
  qualified adapter speed), written only by ``ppu_site_engine.py select``. It is verified at startup and pinned for
  the life of this process; a new selection takes effect only on a service
  restart (behind the deployment's Runtime quiesce). A missing / invalid /
  mismatching selection never falls back to another install: the Worker
  still serves ``status`` but every session is refused ``ENGINE_NOT_READY``.
"""
from __future__ import annotations

import grp
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ppu_site_worker as worker  # noqa: E402
from ppu_site_engine import (  # noqa: E402,F401  (re-exported for callers)
    ENGINE_BASE, ENGINE_SCHEMA, ENGINE_SELECTION, EngineNotReady, EngineSelection, load_engine,
)
from ppu_site_adapter_abi5 import Abi5OpenocdAdapter  # noqa: E402

RUN = Path(os.environ.get("RUNTIME_DIRECTORY", "/run/plasma-site-worker"))
STATE = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/plasma-site-worker"))
RUNTIME_CONTROL = Path("/run/plasma-server/control.sock")
PYTHON = Path(sys.executable)

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
                              adapter_driver=engine.adapter_driver,
                              verified_engine=engine)


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
