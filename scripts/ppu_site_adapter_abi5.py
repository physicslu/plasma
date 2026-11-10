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
``reset halt`` -> ``poll off`` -> ``flash probe 0`` -> erase (image rounded up
to erase units) -> write -> verify -> full readback compare -> ``reset run``
-> ``shutdown`` for the session-bound, Runtime-resolved Flash profile
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

from ppu_site_engine import EngineSelection
from ppu_site_worker import (FlashImage, SiteWorkerDenied, TransportDenied, TransportFailed,
                             TransportUnknown)

DPIDR = re.compile(r"SWD DPIDR (0x[0-9a-fA-F]{8})")
# OpenOCD's own observation of the executed Flash range (command_print output).
ERASED = re.compile(r"erased address (0x[0-9a-fA-F]+) \(length (\d+)\)")
WROTE = re.compile(r"\bwrote (\d+) bytes\b")
VERIFIED = re.compile(r"\bverified (\d+) bytes\b")
_ERASE_CMD = re.compile(r"flash erase_address (0x[0-9a-f]{8}) (0x[0-9a-f]{8})\Z")
_WRITE_CMD = re.compile(r"flash write_image \{[^{}]+\} (0x[0-9a-f]{8}) bin\Z")
_VERIFY_CMD = re.compile(r"flash verify_image \{[^{}]+\} (0x[0-9a-f]{8}) bin\Z")
_DUMP_CMD = re.compile(r"dump_image \{[^{}]+\} (0x[0-9a-f]{8}) (0x[0-9a-f]{8})\Z")
DPREG0 = re.compile(r"PLASMA_DPREG0=(0x[0-9a-fA-F]+)")
SAFE_OFF = "SAFE_OFF_MODE_OFF_VERIFIED"
ADMIT_TIMEOUT_S = 120
OPENOCD_MAX_S = 45
CLEANUP_PROBE_MAX_S = 5


class Abi5OpenocdAdapter:
    name = "z2-abi5-swd-openocd5088"
    supported_sites = frozenset({1, 2})
    operations = frozenset({"probe", "flash_cycle"})

    def __init__(self, *, openocd_root: Path, python: Path, adapter_khz: int,
                 adapter_driver: str = "plasma_swd",
                 verified_engine: EngineSelection | None = None,
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
        # The root Worker service supplies this only after load_engine() has
        # verified the selection record and installed executable/admission SHA.
        # A directly constructed adapter has no trusted OPF Engine receipt.
        if verified_engine is not None and (
            self.openocd_root != verified_engine.openocd_root
            or adapter_khz != verified_engine.adapter_khz
            or adapter_driver != verified_engine.adapter_driver
        ):
            raise ValueError("verified engine does not match adapter")
        self.engine_selection_sha256 = (
            verified_engine.record_sha256 if verified_engine is not None else None
        )
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
    # This installed adapter is the Z2 ABI5 reference implementation. Bundle
    # declarations cannot choose its physical platform; native admission checks
    # the live PL identity and ABI on every session.
    platform = {"platform": "linux-armv7", "board": "pynq-z2",
                "fpga_part": "xc7z020clg400-1"}

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
        """Current per-Site root admission records, checked afresh by Worker."""
        return {site for site in self.supported_sites if os.path.lexists(self._record(site))}

    # --- operations ---------------------------------------------------------------
    def _base_argv(self, site: int) -> list[str]:
        return [str(self.openocd), "-s", str(self.scripts_root), "-d2",
                "-c", f"adapter driver {self.adapter_driver}",
                "-c", f"{self.adapter_driver} site {site}",
                "-c", "transport select swd", "-c", "gdb port disabled",
                "-c", "tcl port disabled", "-c", "telnet port disabled"]

    def _argv(self, site: int) -> list[str]:
        return [*self._base_argv(site),
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

        # The Job Binding address, not the bank's flash_base, is the write
        # target; FlashImage already proved the whole erase window in-bank.
        size = len(image.payload)
        erase_address, erase_length = image.erase_range
        address = f"0x{image.load_address:08x}"
        source, output = tcl_path(staged), tcl_path(readback)
        return [
            *self._base_argv(site),
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
            "-c", f"flash erase_address 0x{erase_address:08x} 0x{erase_length:08x}",
            "-c", f"flash write_image {source} {address} bin",
            "-c", f"flash verify_image {source} {address} bin",
            "-c", f"dump_image {output} {address} 0x{size:08x}",
            "-c", "reset run",
            "-c", "shutdown",
        ]

    @staticmethod
    def _executed_flash_range(argv: list[str], log: str, size: int) -> dict[str, int] | None:
        """Range evidence from what actually ran, never from the request.

        Addresses come from the exact OpenOCD commands executed; the erase
        range is additionally OpenOCD's own ``erased address`` report, and the
        written/verified byte counts must equal the Image. Any missing,
        duplicated or disagreeing observation returns None (not proven).
        """
        commands = [argv[i + 1] for i, part in enumerate(argv[:-1]) if part == "-c"]

        def one(pattern: re.Pattern[str]) -> tuple[str, ...] | None:
            found = [m.groups() for m in map(pattern.match, commands) if m]
            return found[0] if len(found) == 1 else None

        erase, write, verify, dump = (one(_ERASE_CMD), one(_WRITE_CMD),
                                      one(_VERIFY_CMD), one(_DUMP_CMD))
        erased = ERASED.findall(log)
        wrote, verified = WROTE.findall(log), VERIFIED.findall(log)
        if (erase is None or write is None or verify is None or dump is None
                or len(erased) != 1
                or wrote != [str(size)] or verified != [str(size)]):
            return None
        commanded = (int(erase[0], 16), int(erase[1], 16))
        observed = (int(erased[0][0], 16), int(erased[0][1]))
        if commanded != observed or int(dump[1], 16) != size:
            return None
        return {"erase_address": observed[0], "erase_length": observed[1],
                "write_address": int(write[0], 16), "verify_address": int(verify[0], 16),
                "readback_address": int(dump[0], 16)}

    def _revoke(self, site: int) -> bool:
        try:
            r = self._run([str(self.python), "-I", "-B", str(self.admission), "revoke", str(site)],
                          capture_output=True, text=True, timeout=60)
        except Exception:
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
            try:
                image.erase_range  # re-prove the Job window before any admission
            except SiteWorkerDenied:
                raise TransportDenied("FLASH_RANGE_INVALID") from None
            with tempfile.TemporaryDirectory(prefix="plasma-c3-flash-") as directory:
                staged = Path(directory) / "normalized-image.bin"
                readback = Path(directory) / "readback.bin"
                staged.write_bytes(image.payload)
                staged.chmod(0o600)
                argv = self._flash_argv(site, image, staged, readback)
                log, rc = self._session(
                    site, deadline=deadline, cancel=cancel,
                    argv=argv, max_duration_s=300,
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
                executed = self._executed_flash_range(argv, log, len(image.payload))
                if executed is None:
                    return {"result": "FAIL", "code": "FLASH_RANGE_NOT_OBSERVED",
                            "openocd_rc": rc, "safe_off": True}
                return {"result": "PASS", "icpn": image.icpn,
                        "target_config": image.profile.target_config,
                        "adapter_khz": self.adapter_khz,
                        "bytes_verified": len(observed),
                        "readback_sha256": observed_sha,
                        "load_address": image.load_address, **executed,
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
        log, rc = self._session(site, deadline=deadline, cancel=threading.Event(),
                                cleanup_probe=False)
        return {"result": "SAFE_OFF_VERIFIED", "openocd_rc": rc,
                "log_sha256": hashlib.sha256(log.encode()).hexdigest()}

    def _session(self, site: int, *, deadline: float, cancel: threading.Event,
                 argv: list[str] | None = None,
                 max_duration_s: float = OPENOCD_MAX_S,
                 cleanup_probe: bool = True) -> tuple[str, Any]:
        # The admission record and native ps_owner lock protect this Site.
        # A different Site's OpenOCD process does not block this Site.
        if os.path.lexists(self._record(site)):
            raise TransportDenied("EXTERNAL_SITE_OWNER_PRESENT")
        try:
            a = self._run([str(self.python), "-I", "-B", str(self.admission), "admit", str(site)],
                          capture_output=True, text=True, timeout=ADMIT_TIMEOUT_S)
        except Exception:
            # Admission writes only a root-private record; revoke and refuse.
            if not self._revoke(site):
                raise TransportUnknown("ADMISSION_OUTCOME_UNKNOWN")
            raise TransportDenied("ADMISSION_FAILED")
        if a.returncode != 0 or "SITE_ADMISSION_RECORD_ISSUED" not in a.stdout:
            if not self._revoke(site):
                raise TransportUnknown("ADMISSION_REVOKE_FAILED")
            # Expose only an explicitly structured, bounded Root denial code.
            # Arbitrary stderr, paths and exception strings stay private.
            denial = "ADMISSION_DENIED"
            receipts = [line.split("=", 1)[1] for line in a.stdout.splitlines()
                        if line.startswith("PLASMA_SWD_SITE_ADMISSION=")]
            if len(receipts) == 1 and len(receipts[0]) <= 4096:
                try:
                    payload = json.loads(receipts[0])
                except (ValueError, TypeError):
                    payload = None
                if isinstance(payload, dict) and payload.get("result") == "DENIED":
                    code = payload.get("code")
                    if type(code) is str and re.fullmatch(r"[A-Z][A-Z0-9_]{0,95}", code):
                        denial += ":" + code
            raise TransportDenied(denial)
        log, raw, reason, rc = "", b"", None, None
        child = None
        operation_error = None
        cleanup_error = False
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
        except Exception as exc:
            operation_error = type(exc).__name__
            try:
                if child is not None and child.poll() is None:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    child.wait()
                if child is not None:
                    rc = child.returncode
            except Exception:
                cleanup_error = True
        finally:
            revoked = self._revoke(site)
        try:
            self._save_openocd_evidence(site, raw, rc, reason, revoked)
        except Exception:
            raise TransportUnknown("OPENOCD_EVIDENCE_WRITE_FAILED") from None
        if not revoked:
            raise TransportUnknown("ADMISSION_REVOKE_FAILED")
        if cleanup_error:
            raise TransportUnknown("OPENOCD_CHILD_NOT_REAPED")
        if reason or operation_error:
            if not cleanup_probe:
                raise TransportUnknown(reason or "OPENOCD_EXCEPTION:" + operation_error)
            # A killed or crashed child may have been in a SWD transaction.
            # A new bounded native-owner session must prove SAFE_OFF before
            # this failure may be offered to the Runtime for retry.
            if child is None:
                raise TransportDenied("OPENOCD_START_FAILED:" + operation_error)
            try:
                self.verify_safe_off(site, deadline=time.monotonic() + CLEANUP_PROBE_MAX_S)
            except Exception as exc:
                raise TransportUnknown((reason or operation_error) + ":CLEANUP_UNVERIFIED:" +
                                       getattr(exc, "code", type(exc).__name__)) from None
            raise TransportFailed(reason or "OPENOCD_EXCEPTION:" + operation_error)
        if SAFE_OFF not in log:
            # Native ps_owner reports these before any MMIO or SWD access.
            # Another process may legitimately hold the Site lock; that is
            # current ownership, not a permanent fault in this Job's Site.
            for denied in ("PS_OWNER_SITE_LOCK_UNAVAILABLE", "PS_OWNER_PL_IMAGE_NOT_LOADED"):
                if "plasma_swd: " + denied in log:
                    raise TransportDenied(denied)
            raise TransportUnknown("SAFE_OFF_NOT_VERIFIED")
        return log, rc
