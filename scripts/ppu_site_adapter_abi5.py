#!/usr/bin/env python3
"""Stage C-3 Hardware Adapter: Z2 ABI-v5 SWD via the existing PS-local OpenOCD.

Single hardware ownership is preserved: this adapter never maps MMIO, never
takes the ADR-0007 fence / Site lock and never drives SWD itself. Per
operation it composes ONLY existing, reviewed owners:

  root Site admission (plasma_swd_site_admission.py admit <site>; Root G5 live
  admission, record schema v3, ``voltage_source: NOT_MEASURED``)  ->  PS-local
  OpenOCD ``plasma_swd`` (its ps_owner takes the fence + Site lock, requires a
  loaded PL Image on this boot, uses the native word port and ARMv7 barriers;
  it reads no admission record and no electrical attestation)  ->  revoke.

Operations (allowlist): ``probe`` = OpenOCD ``dap init`` + ``dpreg 0`` with a
fixed argv (no target, flash, erase, program or reset); ``flash_cycle`` =
``reset halt`` -> erase (image rounded up to erase units) -> write -> verify
-> full readback compare -> ``reset run`` for the session-bound, Runtime-resolved Flash profile
(target config + geometry). Sites: 1 and 2 only (the ABI-v5 two-Site
geometry with a real hardware baseline; deriving Sites from the loaded PL is a
separate Root/FPGA change).

The OpenOCD install is the deployment-selected engine (see
``ppu_site_worker_service.load_engine``), never a versioned constant here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

from ppu_site_worker import FlashImage, TransportDenied, TransportUnknown

DPIDR = re.compile(r"SWD DPIDR (0x[0-9a-fA-F]{8})")
DPREG0 = re.compile(r"PLASMA_DPREG0=(0x[0-9a-fA-F]+)")
SAFE_OFF = "SAFE_OFF_MODE_OFF_VERIFIED"
ADMIT_TIMEOUT_S = 120
OPENOCD_MAX_S = 45


class Abi5OpenocdAdapter:
    name = "z2-abi5-swd-openocd5088"
    supported_sites = frozenset({1, 2})
    operations = frozenset({"probe", "flash_cycle"})

    def __init__(self, *, openocd_root: Path, python: Path, adapter_khz: int,
                 adapter_driver: str = "plasma_swd",
                 journal: Path = Path("/var/lib/plasma-privileged/fpga-deployment-state.json"),
                 record_dir: Path = Path("/run/plasma-z2-swd05"),
                 run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                 popen: Callable[..., Any] = subprocess.Popen,
                 openocd_running: Callable[[], bool] | None = None,
                 poll_s: float = 0.05,
                 evidence_dir: Path | None = None) -> None:
        self.openocd_root = Path(openocd_root)
        self.python = Path(python)
        if type(adapter_khz) is not int or not 0 < adapter_khz <= 100_000:
            raise ValueError("adapter_khz invalid")
        if re.fullmatch(r"[a-z][a-z0-9_]{0,31}", adapter_driver) is None:
            raise ValueError("adapter_driver invalid")
        self.adapter_khz = adapter_khz
        self.adapter_driver = adapter_driver
        self.journal = Path(journal)
        self.record_dir = Path(record_dir)
        self._run = run
        self._popen = popen
        self._openocd_running = openocd_running or self._pgrep_openocd
        self.poll_s = poll_s
        # systemd StateDirectory is root-owned and writable despite ProtectSystem=strict.
        state_root = Path(os.environ.get("STATE_DIRECTORY") or "/var/lib/plasma-site-worker")
        self.evidence_dir = Path(evidence_dir) if evidence_dir is not None else state_root / "openocd-evidence"

    @property
    def openocd(self) -> Path:
        return self.openocd_root / "bin" / "openocd"

    @property
    def admission(self) -> Path:
        return self.openocd_root / "libexec" / "plasma_swd_site_admission.py"

    @property
    def scripts_root(self) -> Path:
        return self.openocd_root / "share" / "openocd" / "scripts"

    # --- identity (FPGA reload detection; change detection, not a version pin) ---
    def identity(self) -> Mapping[str, Any]:
        try:
            raw = self.journal.read_bytes()
            state = json.loads(raw)
        except (OSError, ValueError):
            return {"state": "UNREADABLE"}
        if not isinstance(state, dict):
            return {"state": "UNREADABLE"}
        return {"journal_sha256": hashlib.sha256(raw).hexdigest(),
                "status": state.get("status"), "image_id": state.get("image_id"),
                "session_id": state.get("session_id"), "boot_id": state.get("boot_id"),
                "firmware_sha256": state.get("firmware_sha256")}

    @staticmethod
    def _pgrep_openocd() -> bool:
        out = subprocess.run(["pgrep", "-x", "openocd"], capture_output=True, text=True,
                             env={"PATH": "/usr/bin:/bin"})
        return bool(out.stdout.split())

    def _record(self, site: int) -> Path:
        return self.record_dir / f"swd-site{site}-admission"

    def startup_sealed_sites(self) -> set[int]:
        """A leftover admission record or any running OpenOCD is an unknown owner."""
        if self._openocd_running():
            return set(self.supported_sites)
        return {site for site in self.supported_sites if os.path.lexists(self._record(site))}

    # --- operations ---------------------------------------------------------------
    def _argv(self, site: int) -> list[str]:
        return [str(self.openocd), "-s", str(self.scripts_root), "-d2",
                "-c", f"adapter driver {self.adapter_driver}",
                "-c", f"{self.adapter_driver} site {site}",
                "-c", "transport select swd", "-c", "gdb port disabled",
                "-c", "tcl port disabled", "-c", "telnet port disabled",
                "-c", "swd newdap bp cpu", "-c", "dap create bp.dap -chain-position bp.cpu",
                "-c", "init", "-c", "echo PLASMA_DPREG0=[bp.dap dpreg 0]", "-c", "shutdown"]

    def _target_config(self, image: FlashImage) -> str:
        """The bound target config must be a regular file inside this engine's
        scripts root (no symlink escape); the name was shape-checked at bind."""
        root = self.scripts_root.resolve()
        path = (root / image.profile.target_config).resolve()
        if root not in path.parents or not path.is_file():
            raise TransportDenied("TARGET_CONFIG_NOT_FOUND")
        return image.profile.target_config

    def _flash_argv(self, site: int, image: FlashImage, staged: Path, readback: Path) -> list[str]:
        """Flash sequence for the session-bound profile; no caller-supplied Tcl."""
        def tcl_path(path: Path) -> str:
            raw = path.resolve().as_posix()
            if "{" in raw or "}" in raw or any(ord(ch) < 32 for ch in raw):
                raise TransportDenied("IMAGE_PATH_INVALID")
            return "{" + raw + "}"

        profile, size = image.profile, len(image.payload)
        base = f"0x{profile.flash_base:08x}"
        source, output = tcl_path(staged), tcl_path(readback)
        return [
            str(self.openocd), "-s", str(self.scripts_root), "-d2",
            "-c", f"adapter driver {self.adapter_driver}",
            "-c", f"{self.adapter_driver} site {site}",
            "-c", "transport select swd",
            "-c", "gdb port disabled",
            "-c", "tcl port disabled",
            "-c", "telnet port disabled",
            "-f", self._target_config(image),
            # Target configs may force their own SWCLK (stm32f1x.cfg: 1000 kHz);
            # the selected engine's qualified adapter speed wins.
            "-c", f"adapter speed {self.adapter_khz}",
            "-c", "init",
            # A plain ``halt`` of running firmware leaves the stm32f1x write
            # algorithm stuck after the erase (Driver track HIL 2026-11-04,
            # runbook section 10): every Flash operation starts from reset.
            "-c", "reset halt",
            # Match the proven Site 2 A/B OpenOCD sequence: avoid background
            # target-state polling and explicitly probe bank 0 before erase.
            "-c", "poll off",
            "-c", "flash probe 0",
            "-c", f"flash erase_address {base} 0x{profile.erase_length(size):08x}",
            "-c", f"flash write_image {source} {base} bin",
            "-c", f"flash verify_image {source} {base} bin",
            "-c", f"dump_image {output} {base} 0x{size:08x}",
            "-c", "reset run",
            "-c", "shutdown",
        ]

    def _revoke(self, site: int) -> bool:
        try:
            r = self._run([str(self.python), "-I", "-B", str(self.admission), "revoke", str(site)],
                          capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0 and not os.path.lexists(self._record(site))

    def _save_openocd_evidence(self, site: int, raw: bytes, rc: int | None,
                               reason: str | None, revoked: bool) -> None:
        """Persist raw child output before any unknown-outcome error is raised.

        Never return these root-private paths or raw text to the Runtime/API.
        An untrusted directory or failed write must not produce a Flash PASS.
        """
        directory = self.evidence_dir
        directory.mkdir(mode=0o700, exist_ok=True)
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077):
            raise OSError("OPENOCD_EVIDENCE_DIR_UNTRUSTED")

        fd, filename = tempfile.mkstemp(prefix=f"site{site}-", suffix=".stdout",
                                         dir=directory)
        with os.fdopen(fd, "wb") as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())

        marker = SAFE_OFF.encode("ascii") in raw
        record = {
            "schema": "plasma.ppu.openocd-evidence.v1",
            "site": site,
            "captured_unix_ns": time.time_ns(),
            "stdout_file": Path(filename).name,
            "stdout_bytes": len(raw),
            "stdout_sha256": hashlib.sha256(raw).hexdigest(),
            "openocd_rc": rc,
            "safe_off_marker_present": marker,
            "safe_off_verified": reason is None and revoked and marker,
            "admission_revoked": revoked,
            "termination_reason": reason,
        }
        metadata = Path(filename).with_suffix(".json")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        meta_fd = os.open(metadata, flags, 0o600)
        with os.fdopen(meta_fd, "w", encoding="utf-8") as output:
            json.dump(record, output, sort_keys=True, separators=(",", ":"))
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())

    def run(self, site: int, operation: str, *, deadline: float,
            cancel: threading.Event, image: FlashImage | None = None) -> Mapping[str, Any]:
        if site not in self.supported_sites or operation not in self.operations:
            raise TransportDenied("OPERATION_OR_SITE_NOT_SUPPORTED")
        if operation == "flash_cycle":
            if (image is None
                    or not (0 < len(image.payload) <= image.profile.flash_size)
                    or hashlib.sha256(image.payload).hexdigest() != image.sha256):
                raise TransportDenied("FLASH_IMAGE_NOT_BOUND")
            with tempfile.TemporaryDirectory(prefix="plasma-c3-flash-") as directory:
                staged = Path(directory) / "normalized-image.bin"
                readback = Path(directory) / "readback.bin"
                staged.write_bytes(image.payload)
                staged.chmod(0o600)
                log, rc = self._session(
                    site, deadline=deadline, cancel=cancel,
                    argv=self._flash_argv(site, image, staged, readback),
                    max_duration_s=300,
                )
                if rc != 0:
                    return {"result": "FAIL", "code": "OPENOCD_FLASH_FAILED",
                            "openocd_rc": rc, "safe_off": True}
                if not readback.is_file():
                    return {"result": "FAIL", "code": "READBACK_MISSING",
                            "openocd_rc": rc, "safe_off": True}
                observed = readback.read_bytes()
                observed_sha = hashlib.sha256(observed).hexdigest()
                if observed != image.payload:
                    return {"result": "FAIL", "code": "READBACK_MISMATCH",
                            "openocd_rc": rc, "expected_sha256": image.sha256,
                            "readback_sha256": observed_sha, "safe_off": True}
                return {"result": "PASS", "icpn": image.icpn,
                        "target_config": image.profile.target_config,
                        "adapter_khz": self.adapter_khz,
                        "bytes_verified": len(observed),
                        "readback_sha256": observed_sha,
                        "openocd_rc": 0, "safe_off": True}
        log, rc = self._session(site, deadline=deadline, cancel=cancel)
        connect, dpreg = DPIDR.findall(log), DPREG0.findall(log)
        values = {int(v, 16) for v in connect + dpreg}
        if rc == 0 and connect and dpreg and len(values) == 1:
            return {"result": "PASS", "dpidr": "0x%08x" % values.pop(), "safe_off": True}
        return {"result": "FAIL", "code": "DPIDR_NOT_READ", "openocd_rc": rc, "safe_off": True}

    def verify_safe_off(self, site: int, *, deadline: float) -> Mapping[str, Any]:
        """Operator recovery evidence: one admitted OpenOCD session (read-only
        ``dap init``) that ends with the ps_owner SAFE_OFF verification.
        Raises TransportDenied / TransportUnknown exactly like ``run``."""
        if site not in self.supported_sites:
            raise TransportDenied("OPERATION_OR_SITE_NOT_SUPPORTED")
        log, rc = self._session(site, deadline=deadline, cancel=threading.Event())
        return {"result": "SAFE_OFF_VERIFIED", "openocd_rc": rc,
                "log_sha256": hashlib.sha256(log.encode()).hexdigest()}

    def _session(self, site: int, *, deadline: float, cancel: threading.Event,
                 argv: list[str] | None = None,
                 max_duration_s: float = OPENOCD_MAX_S) -> tuple[str, Any]:
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
        log, raw, reason, rc = "", b"", None, None
        try:
            child = self._popen(self._argv(site) if argv is None else argv,
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                start_new_session=True, close_fds=True)
            limit = min(deadline, time.monotonic() + max_duration_s)
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
            raw = out if isinstance(out, bytes) else str(out).encode("utf-8", "replace")
            log = raw.decode("utf-8", "replace")
            rc = child.returncode
        finally:
            revoked = self._revoke(site)
        try:
            self._save_openocd_evidence(site, raw, rc, reason, revoked)
        except OSError:
            raise TransportUnknown("OPENOCD_EVIDENCE_WRITE_FAILED") from None
        if reason:
            # Killed mid-transaction: SAFE_OFF not proven.
            raise TransportUnknown(reason)
        if not revoked:
            raise TransportUnknown("ADMISSION_REVOKE_FAILED")
        if SAFE_OFF not in log:
            raise TransportUnknown("SAFE_OFF_NOT_VERIFIED")
        return log, rc
