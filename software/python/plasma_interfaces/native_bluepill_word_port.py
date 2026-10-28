"""SHA-pinned C Remote Bitbang loop inside the *existing* Python MMIO owner.

No new Root entry, file/device opener, Site owner, socket listener or callback
is introduced. Each bounded C call is made with the parent LinuxMMIO mutex
held and the Site lease revalidated. The mapped pointer never leaves that
private call. This is not hardware qualification or AXI fault containment.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import platform
import re
import stat
import sys

from .bluepill_remote_bitbang import SWDBitbangError
from .bluepill_z2_word_port import BLUEPILL_SWD_BASE, BluepillZ2WordPort
from .fixed_abi_mmio_port import ARMv7DMBBarrier
from .linux_mmio import MMIOError

_ERRORS = {
    1: "Native bridge not admitted or already closed",
    2: "Wrong PL image or GPIO ABI",
    3: "PL outputs not in reset-safe state",
    4: "Unsupported reset/JTAG/delay/wire command",
    5: "Trailing bytes after quit are prohibited",
    6: "Invalid native buffer or response capacity",
}


class _State(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in (
        "admitted", "closed", "poisoned", "clock", "swdio", "oe",
        "reads", "writes")]


def qualify_native_bridge_library(library: str, sha256: str) -> os.stat_result:
    """Read-only file/SHA check, safe to run before *any* MMIO device open."""
    if not isinstance(library, str) or not os.path.isabs(library):
        raise MMIOError("Absolute native bridge library required")
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise MMIOError("Exact native bridge SHA256 required")
    location = Path(library)
    try:
        metadata = location.lstat()
        if not stat.S_ISREG(metadata.st_mode) or location.is_symlink():
            raise MMIOError("Native bridge must be a regular, non-symlink file")
        if hashlib.sha256(location.read_bytes()).hexdigest() != sha256:
            raise MMIOError("Native bridge SHA256 mismatch")
    except OSError as exc:
        raise MMIOError("Cannot read native bridge artifact") from exc
    return metadata


class NativeBluepillWordPort:
    """One Site 1 RBB session; C consumes up to 4096 wire bytes per call."""

    def __init__(self, port: BluepillZ2WordPort, *, library: str,
                 sha256: str) -> None:
        if not isinstance(port, BluepillZ2WordPort):
            raise MMIOError("An already-owned Blue Pill Site 1 WordPort is required")
        metadata = qualify_native_bridge_library(library, sha256)
        location = Path(library)

        parent = port._lease._parent
        with parent._mutex:
            port._lease._guard(BLUEPILL_SWD_BASE)
            parent._check_active()
            if parent.readonly or parent._apertures[BLUEPILL_SWD_BASE].size != 4096:
                raise MMIOError("Exact writable 4KiB candidate aperture required")
            # A host compiler fence is never a hardware DMB. Non-regular
            # backends require the *existing* verified native ARMv7 barrier.
            try:
                device_info = Path(parent.device).lstat()
            except OSError as exc:
                raise MMIOError("Cannot validate MMIO device identity") from exc
            regular_file = stat.S_ISREG(device_info.st_mode)
            if not regular_file and not isinstance(port._barrier, ARMv7DMBBarrier):
                raise MMIOError("Hardware MMIO requires the verified ARMv7 barrier")

        try:
            dll = ctypes.CDLL(library)
            dll.plasma_rbb_abi_version.argtypes = []
            dll.plasma_rbb_abi_version.restype = ctypes.c_uint32
            dll.plasma_rbb_is_armv7.argtypes = []
            dll.plasma_rbb_is_armv7.restype = ctypes.c_uint32
            pointer = ctypes.POINTER(ctypes.c_uint32)
            state_ptr = ctypes.POINTER(_State)
            dll.plasma_rbb_admit.argtypes = [pointer, state_ptr]
            dll.plasma_rbb_close.argtypes = [pointer, state_ptr]
            dll.plasma_rbb_exchange.argtypes = [pointer, state_ptr,
                                                ctypes.c_void_p, ctypes.c_size_t,
                                                ctypes.c_void_p, ctypes.c_size_t,
                                                ctypes.POINTER(ctypes.c_size_t)]
            for func in (dll.plasma_rbb_admit, dll.plasma_rbb_close,
                         dll.plasma_rbb_exchange):
                func.restype = ctypes.c_int
            if dll.plasma_rbb_abi_version() != 1:
                raise MMIOError("Unsupported native bridge ABI")
            if not regular_file and (dll.plasma_rbb_is_armv7() != 1 or
                    platform.machine().lower() not in ("armv7", "armv7l", "armv7-a") or
                    sys.byteorder != "little" or ctypes.sizeof(ctypes.c_void_p) != 4):
                raise MMIOError("Native ARMv7-A little-endian 32-bit bridge required")
            # Detect replacement between integrity check and loading.
            now = location.lstat()
            stable = lambda st: (st.st_dev, st.st_ino, st.st_mode,
                                 st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            if stable(now) != stable(metadata) or hashlib.sha256(location.read_bytes()).hexdigest() != sha256:
                raise MMIOError("Native bridge artifact changed during load")
        except (OSError, AttributeError) as exc:
            raise MMIOError("Cannot load native C bridge ABI") from exc
        self._port = port
        self._dll = dll
        self._state = _State()

    @property
    def closed(self) -> bool:
        return bool(self._state.closed)

    @property
    def poisoned(self) -> bool:
        return bool(self._state.poisoned)

    def _invoke(self, method: str, *args: object) -> int:
        parent = self._port._lease._parent
        with parent._mutex:
            self._port._lease._guard(BLUEPILL_SWD_BASE)
            parent._check_active()
            # The only mapped pointer is temporary; parent and lease remain
            # alive for the entire native call. RLock also guards close/reload.
            try:
                words = parent._map_words(parent._apertures[BLUEPILL_SWD_BASE])
                first_word = ctypes.c_uint32.from_buffer(words)
            except (OSError, ValueError, BufferError) as exc:
                parent._poisoned = True
                raise MMIOError("Native MMIO mapping uncertain; no retry") from exc
            before_reads, before_writes = self._state.reads, self._state.writes
            try:
                return getattr(self._dll, method)(ctypes.byref(first_word),
                                                   ctypes.byref(self._state), *args)
            finally:
                parent._read_count += self._state.reads - before_reads
                parent._write_count += self._state.writes - before_writes
                # Do not retain the exported Python buffer (close needs it free).
                del first_word

    @staticmethod
    def _check(result: int) -> None:
        if result != 0:
            raise SWDBitbangError(_ERRORS.get(result, "Native bridge rejected operation"))

    def admit(self) -> None:
        self._check(self._invoke("plasma_rbb_admit"))

    def close(self) -> None:
        if not self.closed:
            self._check(self._invoke("plasma_rbb_close"))

    def exchange(self, commands: bytes) -> bytes:
        if type(commands) is not bytes:
            raise TypeError("Wire protocol requires bytes")
        if len(commands) > 4096:
            raise ValueError("Native C block must not exceed 4096 bytes")
        response = ctypes.create_string_buffer(max(len(commands), 1))
        input_data = ctypes.create_string_buffer(commands)
        used = ctypes.c_size_t()
        result = self._invoke("plasma_rbb_exchange", input_data, len(commands),
                              response, len(commands), ctypes.byref(used))
        self._check(result)
        return response.raw[:used.value]
