#!/usr/bin/env python3
"""systemd entry for plasma-site-worker.service (root; AF_UNIX only).

Fail-closed wiring of the C-3 core: two sockets (control for the Runtime
group, transport for the Package group), trusted Runtime = plasma-server
MainPID, Job lease = C-1 ``execution_lease``, seals under the StateDirectory.
Exits non-zero (systemd restarts it) if any prerequisite is missing; while it
is down the Runtime cannot open Site sessions, so Site Packages fail closed.
"""
from __future__ import annotations

import grp
import os
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ppu_site_worker as worker  # noqa: E402
from ppu_site_adapter_abi5 import Abi5OpenocdAdapter  # noqa: E402

RUN = Path(os.environ.get("RUNTIME_DIRECTORY", "/run/plasma-site-worker"))
STATE = Path(os.environ.get("STATE_DIRECTORY", "/var/lib/plasma-site-worker"))
RUNTIME_CONTROL = Path("/run/plasma-server/control.sock")
OPENOCD_ROOT = Path("/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154-plasma-swd-954344c5717a")
PYTHON = Path("/opt/plasma/python/3.12.13/bin/python3")


def build(run_dir: Path = RUN, state_dir: Path = STATE, *, adapter=None,
          runtime_pid=None, lease_verifier=None, control_gid=None, transport_gid=None):
    if os.geteuid() != 0 and adapter is None:
        raise SystemExit("SITE_WORKER_REQUIRES_ROOT")
    adapter = adapter or Abi5OpenocdAdapter(openocd_root=OPENOCD_ROOT, python=PYTHON)
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
