"""Host-only contract checks for the v0.2 Path 2 / direct Z2 entrypoint.

No SSH, device nodes, OpenOCD or Flash operations are executed here.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
