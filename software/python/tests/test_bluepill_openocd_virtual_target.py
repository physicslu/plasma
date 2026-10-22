"""Host-only: real pinned upstream OpenOCD -> UNIX socket -> PS bridge ->
word-port model of SWD GPIO PL -> independent virtual SWDv1 DPIDR target.

This is not a device-connected HIL test or a claim of production readiness.
"""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time

import pytest

from plasma_interfaces.bluepill_remote_bitbang import (
    RemoteBitbangSWD, serve_local_unix_once,
)

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pl/verification/models"))
from virtual_swd_target import VirtualSWDTarget  # noqa: E402

BASE = 0x40008000


class VirtualWordPort:
    """Model GPIO reads/writes; no FPGA device, socket privilege or real IC."""

    def __init__(self):
        self.target = VirtualSWDTarget()
        self.drive = 0b010  # SWCLK low, SWDIO high, Hi-Z
        self.target_drive = False
        self.target_value = 1
        self.writes = 0
        self.barriers = 0

    def read32(self, address):
        if address == BASE:
            return RemoteBitbangSWD.MAGIC
        if address == BASE + 4:
            return RemoteBitbangSWD.VERSION
        if address == BASE + 12:
            if self.target_drive:
                swdio = self.target_value
            elif self.drive & 4:
                swdio = (self.drive >> 1) & 1
            else:
                swdio = 1  # modeled external pullup
            return (swdio | ((self.drive & 1) << 1) |
                    (self.drive & 4) | ((self.drive & 2) << 2))
        raise OSError("Non-Site AXI read")

    def write32(self, address, value):
        if address != BASE + 8 or type(value) is not int or not 0 <= value <= 7:
            raise OSError("Non-Site AXI write")
        if not self.drive & 1 and value & 1:
            self.target_drive, self.target_value = self.target.rising(
                bool(value & 4), bool(value & 2)
            )
        self.drive = value
        self.writes += 1

    def write_barrier(self):
        self.barriers += 1


def test_real_upstream_openocd_remote_bitbang_reads_virtual_dpidr():
    candidate = os.environ.get("PLASMA_BLUEPILL_OPENOCD")
    if not candidate:
        pytest.skip("Only run with explicitly built, pinned upstream OpenOCD binary")
    binary = Path(candidate).resolve()
    assert binary.is_file()
    with tempfile.TemporaryDirectory(prefix="plasma-bb-") as root:
        location = Path(root) / "site1.sock"
        port = VirtualWordPort()
        bridge = RemoteBitbangSWD(port, base=BASE)
        errors = []

        def serve():
            try:
                serve_local_unix_once(location, bridge, idle_timeout_s=12)
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        deadline = time.monotonic() + 5
        while not location.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert location.is_socket(), f"private bridge listener unavailable: {errors}"

        args = [
            str(binary),
            "-c", "adapter driver remote_bitbang",
            "-c", f"remote_bitbang host {location}",
            "-c", "remote_bitbang port 0",
            "-c", "transport select swd",
            "-c", "swd newdap blue cpu -expected-id 0x2ba01477",
            "-c", "dap create blue.dap -tap blue.cpu",
            "-c", "init",
            "-c", "shutdown",
        ]
        result = subprocess.run(args, capture_output=True, text=True, timeout=20)
        thread.join(timeout=13)
        stdout = result.stdout + result.stderr
        diagnostics = (
            f"return={result.returncode}, writes={port.writes}, "
            f"barriers={port.barriers}, target_state={port.target.state}, "
            f"target_connected={port.target.connected}, "
            f"target_resets={port.target.resets}, "
            f"wire_count={len(port.target.wire)}, "
            f"headers={port.target.headers[-20:]}, "
            f"recent_events={port.target.events[-25:]}, "
            f"recent_wire={port.target.wire[-30:]}, "
            f"bridge_errors={errors!r}\\n"
        )
        assert result.returncode == 0, diagnostics + stdout[-6000:]
        assert port.target.connected, (
            "The virtual target never received a valid DPIDR SWD transfer\n"
            + stdout[-4000:]
        )
        assert port.writes > 0 and port.barriers >= port.writes
        assert not location.exists()
        assert not errors, repr(errors)
