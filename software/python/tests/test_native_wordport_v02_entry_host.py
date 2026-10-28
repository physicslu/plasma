"""Host-only contract checks for the v0.2 Path 2 / direct Z2 entrypoint.

No SSH, device nodes, OpenOCD or Flash operations are executed here.
"""
import importlib.util
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/plasma_native_wordport_v02.py"
spec = importlib.util.spec_from_file_location("plasma_native_wordport_v02", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class NativeV02HostOnly(unittest.TestCase):
    def render(self, operation):
        return module.make_tcl(
            Path("/run/plasma-test-only/swd.sock"),
            Path("/home/xilinx/firmware-v02.bin"),
            Path("/home/xilinx/private-readback.bin"),
            operation,
        )

    def test_program_one_erase_and_write_no_automatic_reset(self):
        tcl = self.render("program-v02")
        self.assertEqual(tcl.count("flash erase_address "), 1)
        self.assertEqual(tcl.count("flash write_image "), 1)
        self.assertIn("0x08000000 0xF800", tcl)
        self.assertIn("verify_image /home/xilinx/firmware-v02.bin 0x08000000 bin", tcl)
        self.assertIn("dump_image /home/xilinx/private-readback.bin 0x08000000 62800", tcl)
        self.assertNotIn("reset run", tcl)
        self.assertNotIn("resume", tcl)
        self.assertNotIn("flash mass_erase", tcl)
        self.assertIn("PLASMA_V02_COMPLETED_NO_RESET", tcl)

    def test_diagnostics_on_each_error_and_nonzero_exit(self):
        tcl = self.render("program-v02")
        for stage in ("ERASE", "PROGRAM", "VERIFY", "READBACK"):
            self.assertIn("plasma_diag " + stage, tcl)
        self.assertEqual(tcl.count("shutdown error"), 4)
        for cmd in (
            "mdw 0xE000EDF0 1",
            "mdw 0x2000003C 2",
            "mdw 0x20000040 8",
            "mdw 0x4002200C 1",
            "mdw 0x40022010 1",
            "mdw 0xE000ED28 1",
            "mdw 0xE000ED2C 1",
            "reg pc", "reg xPSR",
        ):
            self.assertIn(cmd, tcl)
        self.assertLess(tcl.index("PLASMA_DIAG_PREHALT"), tcl.index("PLASMA_DIAG_NOW_HALT"))
        self.assertLess(tcl.index("PLASMA_DIAG_NOW_HALT"), tcl.index("reg pc"))

    def test_post_session_reconnect_is_read_only_but_halt_changes_cpu(self):
        tcl = self.render("diagnose-after")
        self.assertIn("REATTACH_NOT_FAILURE_INSTANT", tcl)
        self.assertNotIn("flash write_image ", tcl)
        self.assertNotIn("flash erase_address ", tcl)
        self.assertNotIn("reset run", tcl)
        self.assertIn("PLASMA_DIAG_NOW_HALT", tcl)

    def test_invalid_operation_and_path_preflight(self):
        with self.assertRaises(ValueError):
            self.render("mass-erase")
        for unsafe in ("a/relative.bin", "/tmp/../wrong.bin", "/tmp/bad name.bin"):
            with self.subTest(unsafe=unsafe), self.assertRaises(module.NotRun):
                module.file_at(unsafe)
        self.assertEqual(module.V02_BYTES, 62800)
        self.assertEqual(module.ERASE_BYTES, 62 * 1024)
        self.assertEqual(len(module.V02_SHA), 64)
        self.assertEqual(len(module.NATIVE_SHA), 64)

    def test_no_implicit_hardware_or_credential_use(self):
        text = SCRIPT.read_text()
        self.assertIn('if __name__ == "__main__"', text)
        self.assertIn('args.role == "swpc"', text)
        self.assertIn("check_source(args.source_sha256)", text)
        self.assertIn("sudo -S -p ''", text)
        self.assertIn("--owner-attested", text)
        self.assertIn('stat.S_IMODE(login.stat().st_mode) != 0o600', text)
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("PLASMA_DIAG_BEGIN", text)
        self.assertNotIn("restore_golden(", text)
        self.assertNotIn("subprocess.run([\"git\"", text)


class NativeV02DynamicTcl(unittest.TestCase):
    """Actually execute generated Tcl in tclsh with an in-memory OpenOCD stub.

    This is Host-only OpenOCD *command simulation*, not OpenOCD firmware execution.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="plasma-v02-tcl-fault-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.simulator = self.directory / "mock-openocd.tcl"
        self.simulator.write_text(r"""
proc echo {args} {puts "OCD_ECHO [join $args { }]"}
proc gdb_port {args} {}
proc tcl_port {args} {}
proc telnet_port {args} {}
proc adapter {args} {}
proc remote_bitbang {args} {}
proc transport {args} {}
proc find {name} {return "/dev/null"}
proc init {} {puts "MOCK_INIT"}
proc flash {op args} {
    puts "MOCK_FLASH $op"
    if {$op eq "write_image"} {error "timeout waiting for algorithm"}
}
proc verify_image {args} {puts "MOCK_VERIFY"}
proc dump_image {args} {puts "MOCK_DUMP"}
proc mdw {address count} {
    puts "MOCK_MDW $address $count"
    if {$::env(INJECT_MDW_ERROR) eq "1" && $address eq "0x4002200C"} {
        error "INJECTED_FLASH_SR_READ_ERROR"
    }
}
proc halt {} {puts "MOCK_HALT"}
proc reg {name} {puts "MOCK_REG $name"}
proc debug_reason {} {puts "MOCK_DEBUG_REASON"}
proc shutdown {args} {
    puts "MOCK_SHUTDOWN [join $args ,]"
    if {[lsearch -exact $args error] >= 0} {exit 17}
    exit 0
}
source [lindex $argv 0]
""")

    def run_tcl(self, mdw_fail=False):
        import os
        config = self.directory / "generated.tcl"
        config.write_text(module.make_tcl(
            self.directory / "mock.sock",
            self.directory / "v02.bin",
            self.directory / "readback.bin", "program-v02"))
        environment = dict(os.environ, INJECT_MDW_ERROR="1" if mdw_fail else "0")
        return subprocess.run(["tclsh", str(self.simulator), str(config)],
                              env=environment, capture_output=True,
                              text=True, timeout=10)

    def test_loader_timeout_executes_same_session_snapshot_and_fails(self):
        r = self.run_tcl()
        self.assertEqual(r.returncode, 17, r.stderr)
        text = r.stdout
        self.assertEqual(text.count("MOCK_FLASH erase_address"), 1)
        self.assertEqual(text.count("MOCK_FLASH write_image"), 1)
        self.assertNotIn("MOCK_VERIFY", text)
        self.assertNotIn("MOCK_DUMP", text)
        self.assertIn("timeout waiting for algorithm", text)
        self.assertIn("PLASMA_DIAG_BEGIN PROGRAM", text)
        self.assertIn("MOCK_MDW 0x20000040 8", text)
        self.assertIn("MOCK_MDW 0x4002200C 1", text)
        self.assertIn("MOCK_MDW 0x40022010 1", text)
        self.assertIn("MOCK_REG pc", text)
        self.assertIn("MOCK_REG xPSR", text)
        self.assertIn("MOCK_SHUTDOWN error", text)
        self.assertNotIn("MOCK_RESET", text)
        self.assertLess(text.index("MOCK_MDW 0xE000EDF0"),
                        text.index("MOCK_HALT", text.index("PLASMA_DIAG_BEGIN")))
        self.assertLess(text.index("MOCK_MDW 0x4002200C"),
                        text.index("MOCK_REG pc"))

    def test_mdw_failure_does_not_abort_other_diagnostics_or_mask_timeout(self):
        r = self.run_tcl(mdw_fail=True)
        self.assertEqual(r.returncode, 17, r.stderr)
        self.assertIn("PLASMA_DIAG_READ_FAIL INJECTED_FLASH_SR_READ_ERROR", r.stdout)
        self.assertIn("MOCK_MDW 0x40022010 1", r.stdout)
        self.assertIn("MOCK_REG xPSR", r.stdout)
        self.assertIn("PLASMA_DIAG_END PROGRAM", r.stdout)
        self.assertEqual(r.stdout.count("MOCK_FLASH write_image"), 1)
        self.assertIn("MOCK_SHUTDOWN error", r.stdout)


class NativeV02DynamicSession(unittest.TestCase):
    """Mock Python process/socket lifecycle without touching /run or any device."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="plasma-v02-session-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.bundle = self.directory / "bundle"
        self.bundle.mkdir()
        self.sockets = self.directory / "sockets"
        self.sockets.mkdir()
        self.barrier = self.directory / "mock-barrier.so"
        self.barrier.write_bytes(b"regular-file-host-test-only")
        self.runner = NativeV02DynamicTcl()
        self.runner.setUp()
        self.addCleanup(self.runner.tearDown) if hasattr(self.runner, "tearDown") else None
        self.addCleanup(self.runner.tmp.cleanup)

    def test_failure_reaps_bridge_and_socket_and_preserves_receipt(self):
        self._check_process_failure(timeout=False)

    def test_hard_timeout_reaps_bridge_and_preserves_partial_logs(self):
        self._check_process_failure(timeout=True)

    def _check_process_failure(self, timeout):
        opened = []
        real_run = subprocess.run
        real_popen = subprocess.Popen

        class FakeBridge:
            def __init__(self, argv):
                location = Path(argv[argv.index("--socket") + 1])
                self.location = location
                self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.listener.bind(str(location))
                self.returncode = None
                self.terminated = False

            def poll(self):
                return self.returncode

            def terminate(self):
                self.terminated = True
                self.listener.close()
                self.location.unlink()
                self.returncode = 0

            def communicate(self, timeout):
                return ('{"result":"BRIDGE_CLOSED"}', "")

        def fake_popen(argv, **kwargs):
            b = FakeBridge(argv)
            opened.append(b)
            return b

        def fake_run(argv, **kwargs):
            self.assertEqual(argv[0], module.OPENOCD)
            if timeout:
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"],
                                                output=b"mock partial stdout\n",
                                                stderr=b"mock partial stderr\n")
            config_path = Path(argv[argv.index("-f") + 1])
            # The mock Bridge Popen must not intercept the real, local Tcl interpreter.
            with patch.object(module.subprocess, "Popen", real_popen):
                return real_run(["tclsh", str(self.runner.simulator), str(config_path)],
                                env=dict(__import__("os").environ, INJECT_MDW_ERROR="1"),
                                capture_output=True, text=True, timeout=10)

        a = SimpleNamespace(operation="program-v02")
        out = io.StringIO()
        with patch.object(module, "BUNDLE", self.bundle), \
             patch.object(module, "z2_preflight",
                          return_value=(self.directory / "v02.bin",
                                        self.directory / "mock-native.so",
                                        self.barrier, "mock-boot", "0" * 40)), \
             patch.object(module.subprocess, "Popen", side_effect=fake_popen), \
             patch.object(module.subprocess, "run", side_effect=fake_run), \
             redirect_stdout(out):
            status = module.on_z2(a, socket_base=self.sockets)

        self.assertEqual(status, 1)
        self.assertEqual(len(opened), 1, "must not start another bridge")
        self.assertTrue(opened[0].terminated)
        self.assertFalse(opened[0].location.exists())
        self.assertEqual(list(self.sockets.iterdir()), [])
        receipt_file = next(self.bundle.glob(".work/native-v02-path2/run-*/receipt.json"))
        receipt = json.loads(receipt_file.read_text())
        log = (receipt_file.parent / "openocd.log").read_text()
        self.assertEqual(receipt["result"], "FAIL")
        self.assertTrue(receipt["socket_released"])
        self.assertTrue(receipt["no_reset_no_retry"])
        self.assertEqual(receipt["bridge_exit"], 0)
        self.assertFalse((receipt_file.parent / "readback-v02.bin").exists())
        if timeout:
            self.assertIn("OPENOCD_570S_TIMEOUT", receipt["error"])
            self.assertIn("mock partial stdout", log)
            self.assertIn("mock partial stderr", log)
            self.assertEqual(receipt["diagnostic"], "NOT_CAPTURED")
        else:
            self.assertEqual(receipt["openocd_exit"], 17)
            self.assertEqual(receipt["diagnostic"], "POST_ERROR_SAME_SESSION")
            self.assertIn("PLASMA_DIAG_END PROGRAM", log)
            self.assertIn("PLASMA_DIAG_READ_FAIL", log)
            self.assertEqual(log.count("MOCK_FLASH write_image"), 1)


class NativeV02PreflightHostOnly(unittest.TestCase):
    """Exercise the preflight routing without hardware, subprocesses, or sockets."""

    def test_preflight_only_reports_checked_facts_and_does_not_start_bridge(self):
        args = SimpleNamespace(operation="preflight", owner_attested=False)
        captured = io.StringIO()
        with patch.object(module, "z2_preflight", return_value=(
                Path("/fake/verified-image.bin"), Path("/fake/native.so"),
                Path("/fake/barrier.so"), "mock-current-boot", "a" * 40)), \
             patch.object(module.subprocess, "Popen", side_effect=AssertionError(
                "preflight must never spawn bridge")), \
             patch.object(module.subprocess, "run", side_effect=AssertionError(
                "preflight must never run OpenOCD")), \
             redirect_stdout(captured):
            status = module.on_z2(args)
        self.assertEqual(status, 0)
        report = json.loads(captured.getvalue())
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["operation"], "preflight")
        self.assertEqual(report["hw_action"], "NONE")
        self.assertTrue(report["no_erase_program_halt_reset"])
        self.assertEqual(report["electrical"], "NOT_VERIFIED_OWNER_MUST_CHECK")
        for check in ("openocd_executable_and_scripts", "mmio_devices_idle",
                      "openocd_and_swd_owner_idle",
                      "held_tested_image_manifest_and_golden_sha256",
                      "reviewed_script_sha256"):
            self.assertEqual(report["checks"][check], "PASS")

    def test_preflight_error_is_fail_closed_no_subprocess_or_false_pass(self):
        args = SimpleNamespace(operation="preflight", owner_attested=False)
        with patch.object(module, "z2_preflight",
                          side_effect=module.NotRun(69, "MMIO_BUSY_OR_UNKNOWN")), \
             patch.object(module.subprocess, "Popen", side_effect=AssertionError(
                "blocked preflight must never spawn bridge")), \
             self.assertRaises(module.NotRun) as error:
            module.on_z2(args)
        self.assertEqual(error.exception.status, 69)
        self.assertEqual(str(error.exception), "MMIO_BUSY_OR_UNKNOWN")

    def test_cli_preflight_does_not_require_electrical_attestation(self):
        args = ["program", "--role", "z2", "--operation", "preflight",
                "--firmware", "/fake/fw-v02.bin", "--source-sha256", "a" * 64]
        with patch("sys.argv", args), \
             patch.object(module, "on_z2", return_value=0) as on_z2:
            self.assertEqual(module.main(), 0)
            self.assertEqual(on_z2.call_args.args[0].operation, "preflight")
            self.assertFalse(on_z2.call_args.args[0].owner_attested)

    def test_hardware_modes_still_require_owner_attestation(self):
        with patch.object(module.os, "geteuid", return_value=0), \
             patch.object(module, "check_source"), \
             patch.object(module, "Z2_ENTRY", SCRIPT):
            for op in ("program-v02", "diagnose-after"):
                args = SimpleNamespace(operation=op, owner_attested=False)
                with self.subTest(operation=op), self.assertRaises(module.NotRun) as raised:
                    module.z2_preflight(args)
                self.assertEqual(raised.exception.status, 77)
                self.assertEqual(str(raised.exception), "OWNER_ATTESTATION_REQUIRED_FOR_HARDWARE")

    def test_source_contract_explicit_preflight_and_no_program_tcl(self):
        text = SCRIPT.read_text()
        self.assertIn('"preflight", "program-v02", "diagnose-after"', text)
        self.assertIn('if args.operation == "preflight":', text)
        self.assertIn('"hw_action": "NONE"', text)
        self.assertIn('"no_erase_program_halt_reset": True', text)
        self.assertIn('if args.operation != "preflight" and not args.owner_attested', text)
        self.assertIn('if args.owner_attested:\n        command.append("--owner-attested")', text)


if __name__ == "__main__":
    unittest.main()
