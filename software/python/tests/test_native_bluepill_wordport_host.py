"""Protocol A/B and fail-closed C WordPort tests. Regular files only.

Protocol A: direct Remote Bitbang byte transcripts against synthetic MMIO.
Protocol B: stream fragmentation/EOF/budget on one private local UNIX socket.
Neither protocol claims SWD DPIDR or FPGA/ARMv7 hardware qualification.
"""
from __future__ import annotations

from contextlib import ExitStack
import ctypes
import hashlib
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
import unittest

from plasma_interfaces.bluepill_remote_bitbang import (
    RemoteBitbangSWD, SWDBitbangError, serve_connection, serve_local_unix_once,
)
from plasma_interfaces.bluepill_z2_word_port import (
    BLUEPILL_SWD_BASE as BASE, BluepillZ2WordPort, bluepill_z2_aperture,
)
from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOError, MMIOClosed
from plasma_interfaces.native_bluepill_word_port import NativeBluepillWordPort

REPO = Path(__file__).resolve().parents[3]
BUILDER = REPO / "scripts/build-native-bluepill-wordport.sh"


class NativeBridgeHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build_dir = tempfile.TemporaryDirectory(prefix="plasma-native-build-")
        cls.library = Path(cls.build_dir.name) / "libplasma_wordport.so"
        subprocess.run(["bash", str(BUILDER), "host", str(cls.library)],
                       check=True, capture_output=True, timeout=30)
        cls.sha = hashlib.sha256(cls.library.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.build_dir.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="plasma-native-mmio-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.device = self.root / "sparse-regular-file"
        with self.device.open("wb") as f:
            f.truncate(BASE + 4096)
        self.word(0x00, 0x50425357)
        self.word(0x04, 0x00010000)
        self.word(0x0C, 0x09)  # safe pin identity + sampled input high
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.mmio = self.stack.enter_context(
            LinuxMMIO((bluepill_z2_aperture(),), device=str(self.device),
                      owner_lock=str(self.root / "owner.lock")))
        self.lease = self.stack.enter_context(self.mmio.claim_site(1, BASE))
        self.callback_count = 0

    def word(self, offset, value):
        with self.device.open("r+b") as handle:
            handle.seek(BASE + offset)
            handle.write(value.to_bytes(4, "little"))

    def read(self, offset):
        with self.device.open("rb") as handle:
            handle.seek(BASE + offset)
            return int.from_bytes(handle.read(4), "little")

    def bridge(self, *, library=None, sha=None):
        def forbidden_callback():
            self.callback_count += 1
            raise AssertionError("Python per-bit barrier callback was invoked")
        return NativeBluepillWordPort(
            BluepillZ2WordPort(self.lease, host_test_barrier=forbidden_callback),
            library=str(library or self.library), sha256=sha or self.sha)

    def test_protocol_a_ordered_commands_readback_and_quit(self):
        b = self.bridge()
        with self.assertRaises(SWDBitbangError):
            b.exchange(b"d")  # no access before admission
        self.assertEqual(self.mmio.stats().read32, 0)
        b.admit()
        self.assertEqual(b.exchange(b"Odefgc"), b"1")
        self.assertEqual(self.read(8), 7)
        self.assertEqual(b.exchange(b"oQ"), b"")
        self.assertEqual(self.read(8), 2)
        self.assertTrue(b.closed)
        self.assertEqual((self.mmio.stats().read32, self.mmio.stats().write32),
                         (4, 7))
        self.assertEqual(self.callback_count, 0)
        with self.assertRaises(SWDBitbangError):
            b.admit()

    def test_protocol_a_deassert_only_and_sample_zero(self):
        self.word(12, 8)
        b = self.bridge()
        b.admit()
        self.assertEqual(b.exchange(b"rBbc"), b"0")
        self.assertEqual(self.mmio.stats().write32, 0)
        b.close()
        self.assertEqual(self.read(8), 2)

    def test_protocol_a_sample_followed_by_quit_in_same_native_batch(self):
        b = self.bridge()
        b.admit()
        self.assertEqual(b.exchange(b"cQ"), b"1")
        self.assertTrue(b.closed)
        self.assertEqual(self.read(8), 2)

    def test_protocol_a_strict_chunk_bound_and_host_artifact_not_armv7(self):
        binary = ctypes.CDLL(str(self.library))
        binary.plasma_rbb_is_armv7.restype = ctypes.c_uint32
        self.assertEqual(binary.plasma_rbb_is_armv7(), 0)
        b = self.bridge()
        b.admit()
        with self.assertRaises(ValueError):
            b.exchange(b"d" * 4097)
        self.assertEqual(self.mmio.stats().write32, 0)
        b.close()

    def test_protocol_a_rejects_abi_and_unsafe_initial_pins_without_writes(self):
        for offset, value in ((0, 0), (4, 2), (12, 7)):
            with self.subTest(offset=offset):
                old = self.read(offset)
                self.word(offset, value)
                b = self.bridge()
                with self.assertRaises(SWDBitbangError):
                    b.admit()
                self.assertTrue(b.poisoned)
                b.close()  # poisoned state MUST NOT touch the drive register
                self.assertEqual(self.mmio.stats().write32, 0)
                self.word(offset, old)

    def test_protocol_a_rejects_reset_jtag_unknown_and_quit_tail(self):
        for payload in (b"s", b"R", b"0", b"Z", b"x", b"QO", b"QQ"):
            with self.subTest(payload=payload):
                b = self.bridge()
                b.admit()
                with self.assertRaises(SWDBitbangError):
                    b.exchange(b"O" + payload)
                self.assertTrue(b.closed)
                self.assertEqual(self.read(8), 2)

    def test_protocol_a_released_lease_and_poisoned_mmio_fail_closed(self):
        b = self.bridge()
        b.admit()
        self.lease.close()
        with self.assertRaises(MMIOClosed):
            b.exchange(b"d")
        # No direct C access after lease release. Mapped page stays owned by
        # LinuxMMIO until Python's existing context manager closes it.
        self.assertEqual(self.mmio.stats().write32, 0)

    def test_protocol_a_parent_poison_prevents_native_access(self):
        b = self.bridge()
        b.admit()
        self.mmio._poisoned = True  # injected host-only uncertain bus state
        with self.assertRaisesRegex(MMIOError, "poisoned"):
            b.exchange(b"d")
        self.assertEqual(self.mmio.stats().write32, 0)

    def test_native_sha_symlink_wrong_type_and_no_implicit_admission(self):
        with self.assertRaisesRegex(MMIOError, "SHA256 mismatch"):
            self.bridge(sha="0" * 64)
        alias = self.root / "alias.so"
        alias.symlink_to(self.library)
        with self.assertRaisesRegex(MMIOError, "non-symlink"):
            self.bridge(library=alias)
        with self.assertRaisesRegex(MMIOError, "already-owned"):
            NativeBluepillWordPort(object(), library=str(self.library), sha256=self.sha)
        self.assertEqual(self.mmio.stats().read32, 0)

    def test_protocol_b_local_unix_fragmented_stream(self):
        b = self.bridge()
        private = self.root / "private"
        private.mkdir(mode=0o700)
        location = private / "rbb.sock"
        results = []

        def client():
            try:
                deadline = time.monotonic() + 2
                while True:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    try:
                        sock.connect(str(location))
                        break
                    except (FileNotFoundError, ConnectionRefusedError):
                        sock.close()
                        if time.monotonic() > deadline:
                            raise
                        time.sleep(.005)
                with sock:
                    sock.settimeout(2)
                    sock.sendall(b"O")
                    sock.sendall(b"d")
                    sock.sendall(b"c")
                    results.append(sock.recv(1))
                    sock.sendall(b"oQ")
            except BaseException as exc:
                results.append(exc)

        thread = threading.Thread(target=client)
        thread.start()
        try:
            count = serve_local_unix_once(location, b, idle_timeout_s=2)
        finally:
            thread.join(timeout=3)
        self.assertEqual(results, [b"1"])
        self.assertEqual(count, 5)
        self.assertFalse(location.exists())
        self.assertEqual(self.read(8), 2)
        self.assertEqual(self.callback_count, 0)

    def test_protocol_b_eof_and_budget_fail_closed(self):
        for data, limit in ((b"O", 20), (b"Odddd", 2)):
            with self.subTest(data=data):
                server, client = socket.socketpair()
                b = self.bridge()
                try:
                    client.sendall(data)
                    client.close()
                    with self.assertRaises(SWDBitbangError):
                        serve_connection(server, b, command_limit=limit)
                    self.assertEqual(self.read(8), 2)
                    self.assertTrue(b.closed)
                finally:
                    server.close()
                    client.close()

    def test_protocol_b_timeout_unlinks_only_owned_socket(self):
        private = self.root / "private"
        private.mkdir(mode=0o700)
        location = private / "idle.sock"
        with self.assertRaises(socket.timeout):
            serve_local_unix_once(location, self.bridge(), idle_timeout_s=0.05)
        self.assertFalse(location.exists())

    def test_protected_session_keeps_root_guards_before_native_data_path(self):
        script = (REPO / "scripts/bluepill-wordport-session.py").read_text()
        self.assertLess(script.index("qualify_native_bridge_library(args.native"),
                        script.index("with port.exclusive()"))
        self.assertLess(script.index("validate_checkpoint(record"),
                        script.index("bridge = NativeBluepillWordPort("))
        for required in ("root.trusted_local()", "root.native_runtime_preflight()",
                         "root.live_program_session_report(", "mmio.claim_site(1, BASE)",
                         "serve_local_unix_once(args.socket, bridge, idle_timeout_s=60,",
                         "signal.alarm(600)"):
            self.assertIn(required, script)
        self.assertIn("['fuser', '-s', device]", script)
        self.assertLess(script.index("root.live_program_session_report("),
                        script.index("bridge = NativeBluepillWordPort("))
        self.assertNotIn("bridge = RemoteBitbangSWD(", script)

    def test_bounded_native_throughput_smoke(self):
        b = self.bridge()
        b.admit()
        block = b"de" * 2048
        start = time.perf_counter()
        for _ in range(25):
            self.assertEqual(b.exchange(block), b"")
        native_elapsed = time.perf_counter() - start
        self.assertEqual(self.mmio.stats().write32, 102400)
        self.assertGreater(native_elapsed, 0)
        b.close()
        # Reference only: same file/MMIO lease, but Python's per-bit callback
        # and locks. A host-file ratio does NOT predict physical SWCLK speed.
        ref = RemoteBitbangSWD(
            BluepillZ2WordPort(self.lease, host_test_barrier=lambda: None), base=BASE)
        ref.admit()
        start = time.perf_counter()
        for _ in range(25):
            self.assertEqual(ref.exchange(block), b"")
        reference_elapsed = time.perf_counter() - start
        ref.close()
        print(f"HOST_ONLY_SYNTHETIC_102400_WRITES native_s={native_elapsed:.6f} "
              f"python_s={reference_elapsed:.6f} "
              f"ratio={reference_elapsed/native_elapsed:.2f}x")
        self.assertEqual(self.callback_count, 0)


if __name__ == "__main__":
    unittest.main()
