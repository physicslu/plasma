#!/usr/bin/env python3
"""Stage C-3 Hardware Adapter: Z2 ABI-v5 SWD via the existing PS-local OpenOCD.

Single hardware ownership is preserved: this adapter never maps MMIO, never
takes the ADR-0007 fence / Site lock and never drives SWD itself. Per
operation it composes ONLY existing, reviewed owners:

  root Site admission (plasma_swd_site_admission.py admit <site>; Root G5 live
  admission + owner electrical attestation)  ->  PS-local OpenOCD
  ``plasma_swd`` (its ps_owner takes the fence + Site lock, validates the
  admission record per MMIO word, uses the native word port and ARMv7
  barriers)  ->  revoke.

Operations (allowlist): ``probe`` = OpenOCD ``dap init`` + ``dpreg 0`` with a
fixed argv (no target, flash, erase, program or reset). Sites: 1 and 2 only
(the ABI-v5 bd976140 two-Site geometry with a real hardware baseline).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from ppu_site_worker import TransportDenied, TransportUnknown

DPIDR = re.compile(r"SWD DPIDR (0x[0-9a-fA-F]{8})")
DPREG0 = re.compile(r"PLASMA_DPREG0=(0x[0-9a-fA-F]+)")
SAFE_OFF = "SAFE_OFF_MODE_OFF_VERIFIED"
ADMIT_TIMEOUT_S = 120
OPENOCD_MAX_S = 45


class Abi5OpenocdAdapter:
    name = "z2-abi5-swd-openocd5088"
    supported_sites = frozenset({1, 2})
    operations = frozenset({"probe"})

    def __init__(self, *, openocd_root: Path, python: Path, expected_image_id: str,
                 journal: Path = Path("/var/lib/plasma-privileged/fpga-deployment-state.json"),
                 record_dir: Path = Path("/run/plasma-z2-swd05"),
                 run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 popen: Callable[..., Any] = subprocess.Popen,
                 openocd_running: Callable[[], bool] | None = None,
                 poll_s: float = 0.05) -> None:
        self.openocd_root = Path(openocd_root)
        self.python = Path(python)
        self.expected_image_id = expected_image_id
        self.journal = Path(journal)
        self.record_dir = Path(record_dir)
        self._run = run
        self._popen = popen
        self._openocd_running = openocd_running or self._pgrep_openocd
        self.poll_s = poll_s

    @property
    def openocd(self) -> Path:
        return self.openocd_root / "bin" / "openocd"

    @property
    def admission(self) -> Path:
        return self.openocd_root / "libexec" / "plasma_swd_site_admission.py"

    @staticmethod
    def _pgrep_openocd() -> bool:
        out = subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin"})
        return bool(out.stdout.split())

    def _record(self, site: int) -> Path:
        return self.record_dir / f"swd-site{site}-admission"

    # --- identity (FPGA reload detection) -------------------------------------------
    def identity(self) -> Mapping[str, Any]:
        try:
            raw = self.journal.read_bytes()
            state = json.loads(raw)
        except (OSError, ValueError):
            return {"state": "UNREADABLE"}
        return {"journal_sha256": hashlib.sha256(raw).hexdigest(),
                "status": state.get("status"), "image_id": state.get("image_id"),
                "session_id": state.get("session_id"), "boot_id": state.get("boot_id"),
                "firmware_sha256": state.get("firmware_sha256")}

    def startup_sealed_sites(self) -> set[int]:
        """A leftover admission record or any running OpenOCD is an unknown owner."""
        if self._openocd_running():
            return set(self.supported_sites)
        return {site for site in self.supported_sites if os.path.lexists(self._record(site))}

    # --- operations ---------------------------------------------------------------
    def _argv(self, site: int) -> list[str]:
        scripts = self.openocd_root / "share" / "openocd" / "scripts"
        return [str(self.openocd), "-s", str(scripts), "-d2",
                "-c", "adapter driver plasma_swd", "-c", f"plasma_swd site {site}",
                "-c", "transport select swd", "-c", "gdb port disabled",
                "-c", "tcl port disabled", "-c", "telnet port disabled",
                "-c", "swd newdap bp cpu", "-c", "dap create bp.dap -chain-position bp.cpu",
                "-c", "init", "-c", "echo PLASMA_DPREG0=[bp.dap dpreg 0]", "-c", "shutdown"]

    def _revoke(self, site: int) -> bool:
        try:
            r = self._run([str(self.python), "-I", "-B", str(self.admission), "revoke", str(site)],
                          capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0 and not os.path.lexists(self._record(site))

    def run(self, site: int, operation: str, *, deadline: float,
            cancel: threading.Event) -> Mapping[str, Any]:
        if site not in self.supported_sites or operation not in self.operations:
            raise TransportDenied("OPERATION_OR_SITE_NOT_SUPPORTED")
        ident = self.identity()
        if ident.get("status") != "IMAGE" or ident.get("image_id") != self.expected_image_id:
            raise TransportDenied("FPGA_IMAGE_NOT_EXPECTED")
        # Single hardware owner: refuse while any other OpenOCD / admission exists.
        if self._openocd_running() or os.path.lexists(self._record(site)):
            raise TransportDenied("EXTERNAL_SITE_OWNER_PRESENT")
        try:
            a = self._run([str(self.python), "-I", "-B", str(self.admission), "admit", str(site)],
                          capture_output=True, text=True, timeout=ADMIT_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired):
            # Admission writes only a root-private record; revoke and refuse.
            if not self._revoke(site):
                raise TransportUnknown("ADMISSION_OUTCOME_UNKNOWN")
            raise TransportDenied("ADMISSION_FAILED")
        if a.returncode != 0 or "SITE_ADMISSION_RECORD_ISSUED" not in a.stdout:
            if not self._revoke(site):
                raise TransportUnknown("ADMISSION_REVOKE_FAILED")
            raise TransportDenied("ADMISSION_DENIED")
        log, reason, rc = "", None, None
        try:
            child = self._popen(self._argv(site), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)
            limit = min(deadline, time.monotonic() + OPENOCD_MAX_S)
            while child.poll() is None:
                if cancel.is_set():
                    reason = "CANCELLED_DURING_OPERATION"
                elif time.monotonic() >= limit:
                    reason = "OPERATION_TIMEOUT"
                if reason:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait()
                    break
                time.sleep(self.poll_s)
            out = child.stdout.read() if child.stdout else b""
            log = out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out)
            rc = child.returncode
        finally:
            revoked = self._revoke(site)
        if reason:
            # Killed mid-transaction: SAFE_OFF not proven.
            raise TransportUnknown(reason)
        if not revoked:
            raise TransportUnknown("ADMISSION_REVOKE_FAILED")
        if SAFE_OFF not in log:
            raise TransportUnknown("SAFE_OFF_NOT_VERIFIED")
        connect, dpreg = DPIDR.findall(log), DPREG0.findall(log)
        values = {int(v, 16) for v in connect + dpreg}
        if rc == 0 and connect and dpreg and len(values) == 1:
            return {"result": "PASS", "dpidr": "0x%08x" % values.pop(), "safe_off": True}
        return {"result": "FAIL", "code": "DPIDR_NOT_READ", "openocd_rc": rc, "safe_off": True}
