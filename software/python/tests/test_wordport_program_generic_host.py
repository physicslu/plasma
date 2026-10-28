"""Host-only checks for the firmware-agnostic Native C WordPort development path.

No Z2, SWPC, OpenOCD hardware, FPGA, USB or DUT is operated.
"""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/plasma_wordport_program.py"
spec = importlib.util.spec_from_file_location("plasma_wordport_program", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GenericImageContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="plasma-generic-image-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)

    def image(self, name, payload):
        path = self.directory / name
        path.write_bytes(payload)
        return path, hashlib.sha256(payload).hexdigest()

    def render(self, image_path, size, erased, operation="program"):
        return module.make_tcl(
            self.directory / "bridge.sock", image_path,
            self.directory / "readback-image.bin", operation,
            image_bytes=size, erase_bytes=erased,
        )

    def test_two_historical_images_are_data_not_compiled_in(self):
        # No dependency on either Blue Pill v0.1 or v0.2 build artifact.
        for size, erase in ((18768, 0x4C00), (62800, 0xF800)):
            with self.subTest(size=size):
                image, digest = self.image(f"arbitrary-{size}.bin", b"x" * size)
                source, actual, sha, erased = module.admit_image(
                    "program", str(image), digest)
                self.assertEqual((source, actual, sha, erased),
                                 (image, size, digest, erase))
                tcl = self.render(source, actual, erased)
                self.assertIn(f"flash erase_address 0x08000000 0x{erase:X}", tcl)
                self.assertIn(f"dump_image {self.directory / 'readback-image.bin'} "
                              f"0x08000000 {size}", tcl)
                self.assertEqual(tcl.count("flash erase_address "), 1)
                self.assertEqual(tcl.count("flash write_image "), 1)
                self.assertEqual(tcl.count("verify_image "), 1)
                self.assertEqual(tcl.count("dump_image "), 1)
                self.assertIn("PLASMA_PROGRAM_COMPLETED_NO_RESET", tcl)
                self.assertNotIn("reset run", tcl)

    def test_third_arbitrary_image_is_accepted_and_page_aligned(self):
        image, digest = self.image("future-build.bin", b"z" * 8194)
        source, size, sha, erase = module.admit_image("program", str(image), digest)
        self.assertEqual((size, erase, sha), (8194, 0x2400, digest))
        self.assertIn("flash erase_address 0x08000000 0x2400",
                      self.render(source, size, erase))
        self.assertNotIn("18768", SCRIPT.read_text())
        self.assertNotIn("62800", SCRIPT.read_text())
        self.assertNotIn("e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c",
                         SCRIPT.read_text())

    def test_exact_geometry_boundary_and_negative_image_inputs(self):
        last, digest = self.image("approved-62pages.bin", b"F" * 63488)
        self.assertEqual(module.admit_image("program", str(last), digest)[3], 63488)
        full, full_sha = self.image("full-64k.bin", b"F" * 65536)
        with self.assertRaises(module.NotRun) as blocked:
            module.admit_image("program", str(full), full_sha)
        self.assertEqual(str(blocked.exception), "ERASE_OUTSIDE_APPROVED_RANGE")
        cases = (
            ("empty", b"", None, "IMAGE_OUTSIDE_TARGET_FLASH"),
            ("oversize", b"A" * 65538, None, "IMAGE_OUTSIDE_TARGET_FLASH"),
            ("odd", b"B" * 1025, None, "IMAGE_PROGRAM_ALIGNMENT_UNSUPPORTED"),
            ("wrongsha", b"C" * 2048, "0" * 64, "IMAGE_SHA256_MISMATCH"),
        )
        for name, payload, expected, reason in cases:
            with self.subTest(name=name):
                image, sha = self.image(name + ".bin", payload)
                with self.assertRaises(module.NotRun) as raised:
                    module.admit_image("program", str(image), expected or sha)
                self.assertEqual(str(raised.exception), reason)
        with self.assertRaises(module.NotRun):
            module.admit_image("program", None, None)
        with self.assertRaises(module.NotRun):
            module.admit_image("program", str(last), None)
        with self.assertRaises(module.NotRun):
            module.admit_image("program", None, digest)

    def test_preflight_without_image_and_reset_never_flash(self):
        self.assertEqual(module.admit_image("preflight", None, None),
                         (None, 0, None, 0))
        self.assertEqual(module.admit_image("reset-run", None, None),
                         (None, 0, None, 0))
        for op in ("reset-run", "diagnose-after"):
            with self.subTest(operation=op):
                tcl = self.render(None, 0, 0, op)
                self.assertNotIn("flash erase_address ", tcl)
                self.assertNotIn("flash write_image ", tcl)
                self.assertNotIn("dump_image ", tcl)
                self.assertNotIn("verify_image ", tcl)
                self.assertEqual(tcl.count("reset run"), int(op == "reset-run"))

    def test_unsafe_or_unqualified_inputs_fail_before_openocd(self):
        with patch.object(module.os, "geteuid", return_value=0), \
             patch.object(module, "check_source"), \
             patch.object(module, "Z2_ENTRY", SCRIPT):
            for icpn, site in (("STM32F103CBT6", 1),
                               ("STM32F103C8T6", 2), ("NXP_MCX", 1)):
                args = SimpleNamespace(operation="program", owner_attested=True,
                    source_sha256="a" * 64, icpn=icpn, site_id=site,
                    firmware=None, image_sha256=None)
                with self.subTest(icpn=icpn, site=site):
                    with self.assertRaises(module.NotRun) as raised:
                        module.z2_preflight(args)
                    self.assertEqual(str(raised.exception),
                                     "UNQUALIFIED_TARGET_OR_SITE")

    def test_tcl_rejects_missing_or_unbounded_execution_plan(self):
        img = self.directory / "mock.bin"
        for size, erase in ((0, 1024), (65538, 66560), (1024, 999),
                            (2048, 1024), (2048, 66560),
                            (65536, 65536)):
            with self.subTest(size=size, erase=erase):
                with self.assertRaises(ValueError):
                    self.render(img, size, erase)


class GenericSessionHostOnly(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="plasma-generic-session-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.bundle = self.directory / "bundle"
        self.bundle.mkdir()
        self.sock_base = self.directory / "sockets"
        self.sock_base.mkdir()
        self.barrier = self.directory / "barrier.so"
        self.barrier.write_bytes(b"synthetic barrier")

    def test_arbitrary_image_snapshot_exact_readback_and_bridge_close(self):
        bytes_in = b"AB" * 4097
        image = self.directory / "selected-any-name.bin"
        image.write_bytes(bytes_in)
        image_sha = hashlib.sha256(bytes_in).hexdigest()
        opened = []

        class Bridge:
            def __init__(self, args):
                path = Path(args[args.index("--socket") + 1])
                self.socket = path
                self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                self.listener.bind(str(path))
                self.returncode = None
                self.terminated = False

            def poll(self):
                return self.returncode

            def communicate(self, timeout):
                self.listener.close()
                self.socket.unlink()
                self.returncode = 0
                return ('{"result":"BRIDGE_CLOSED"}\n', "")

            def terminate(self):
                self.terminated = True

        def fake_popen(args, **kwargs):
            bridge = Bridge(args)
            opened.append(bridge)
            return bridge

        def fake_run(args, **kwargs):
            self.assertEqual(args[0], module.OPENOCD)
            tcl_file = Path(args[args.index("-f") + 1])
            tcl = tcl_file.read_text()
            staged = tcl_file.parent / "program-image.bin"
            self.assertEqual(staged.read_bytes(), bytes_in)
            self.assertNotIn(str(image), tcl)
            self.assertIn(str(staged), tcl)
            self.assertIn("flash erase_address 0x08000000 0x2400", tcl)
            (tcl_file.parent / "readback-image.bin").write_bytes(staged.read_bytes())
            return subprocess.CompletedProcess(args, 0,
                stdout="PLASMA_ERASE_OK\nPLASMA_PROGRAM_OK\n"
                       "PLASMA_VERIFY_OK\nPLASMA_READBACK_OK\n"
                       "PLASMA_PROGRAM_COMPLETED_NO_RESET\n",
                stderr="")

        args = SimpleNamespace(operation="program", icpn="STM32F103C8T6",
                               site_id=1)
        output = io.StringIO()
        with patch.object(module, "BUNDLE", self.bundle), \
             patch.object(module, "z2_preflight", return_value=(
                 image, self.directory / "native.so",
                 self.barrier, "mock-boot-id", "a" * 40,
                 len(bytes_in), image_sha, 0x2400)), \
             patch.object(module.subprocess, "Popen", side_effect=fake_popen), \
             patch.object(module.subprocess, "run", side_effect=fake_run), \
             redirect_stdout(output):
            code = module.on_z2(args, socket_base=self.sock_base)
        self.assertEqual(code, 0)
        self.assertEqual(len(opened), 1)
        self.assertFalse(opened[0].terminated)
        self.assertEqual(list(self.sock_base.iterdir()), [])
        result = json.loads(output.getvalue())
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["image_sha256"], image_sha)
        self.assertEqual(result["readback_sha256"], image_sha)
        self.assertEqual(result["image_bytes"], 8194)
        self.assertEqual(result["erase_bytes"], 0x2400)
        self.assertEqual(result["electrical"], "NOT_MEASURED_DEV_MODE_NON_BLOCKING")
        self.assertTrue(result["socket_released"])
        self.assertTrue(result["no_auto_retry"])

    def test_wrong_readback_never_reports_pass(self):
        # Source contract: image bytes/SHA, Bridge close, and OpenOCD complete
        # marker are ALL required in the actual run receipt.
        source = SCRIPT.read_text()
        self.assertIn('sha(readback) == image_sha', source)
        self.assertIn('bridge.returncode == 0', source)
        self.assertIn('staged.stat().st_size != image_bytes or sha(staged) != image_sha',
                      source)
        self.assertIn('if args.owner_attested:', source)
        self.assertIn('"electrical": "NOT_MEASURED_DEV_MODE_NON_BLOCKING"', source)
        self.assertNotIn("NOT_VERIFIED_OWNER_MUST_CHECK", source)
        # Missing fixture sensors do not create physical PASS or a per-job
        # checklist: the explicit owner-approved command remains independent.
        self.assertNotIn('subprocess.run(["git"', source)


    def test_peripheral_register_and_core_qualification_are_separate(self):
        peripheral_tcl = module.make_tcl(self.directory / "bridge.sock", None,
            self.directory / "unused.bin", "register-read")
        core_tcl = module.make_tcl(self.directory / "bridge.sock", None,
            self.directory / "unused.bin", "core-register-read")
        combined_tcl = module.make_tcl(self.directory / "bridge.sock", None,
            self.directory / "unused.bin", "diagnose-after")
        for tcl in (peripheral_tcl, core_tcl, combined_tcl):
            self.assertNotIn("flash erase_address", tcl)
            self.assertNotIn("flash write_image", tcl)
            self.assertNotIn("reset run", tcl)
            self.assertIn("proc plasma_register_probe", tcl)
            self.assertIn("proc plasma_core_probe", tcl)
            self.assertIn("PLASMA_CORE_STATE_BEFORE", tcl)
            self.assertIn('if {$before eq "running"', tcl)
            self.assertIn('if {[catch {resume} reason]}', tcl)
            self.assertIn('if {$after ne $before}', tcl)
        self.assertIn("catch {plasma_register_probe}", peripheral_tcl)
        self.assertNotIn("catch {plasma_core_probe}", peripheral_tcl)
        self.assertIn("catch {plasma_core_probe}", core_tcl)
        self.assertNotIn("catch {plasma_register_probe}", core_tcl)
        self.assertIn("catch {plasma_core_probe}", combined_tcl)
        self.assertIn("catch {plasma_register_probe}", combined_tcl)
        self.assertIn('PLASMA_DIAG_END POST_SESSION', combined_tcl)

    def test_register_read_requires_real_32_bit_values_and_identity(self):
        good = ("PLASMA_REGISTER_PASS DBGMCU_IDCODE 0x20036410\n"
                "PLASMA_REGISTER_PASS SCB_CPUID 0x411FC231\n"
                "PLASMA_REGISTER_PASS FLASH_SR 0x00000020\n"
                "PLASMA_REGISTER_SUMMARY PASS\n")
        result, values = module.read_register_evidence(good)
        self.assertTrue(result)
        self.assertEqual(values["DBGMCU_IDCODE"], "0x20036410")
        self.assertEqual(values["FLASH_SR"], "0x00000020")
        negatives = (
            good.replace("PLASMA_REGISTER_PASS FLASH_SR 0x00000020\n", ""),
            good.replace("0x411FC231", "0x00000000"),
            good.replace("0x20036410", "0x00000000"),
            good.replace("0x00000020", "NOT_READ"),
            good + "PLASMA_REGISTER_PASS FLASH_SR 0x00000020\n",
            good.replace("PLASMA_REGISTER_SUMMARY PASS", "PLASMA_REGISTER_SUMMARY FAIL"),
            good + "PLASMA_REGISTER_FAIL FLASH_SR TARGET_IO_ERROR\n",
            "PLASMA_REGISTER_SUMMARY PASS\n",
        )
        for log in negatives:
            with self.subTest(log=log[-100:]):
                self.assertFalse(module.read_register_evidence(log)[0])

    def test_core_registers_require_values_and_original_running_state_restored(self):
        regs = ("PLASMA_CORE_REGISTER_PASS pc 0x08000420\n"
                "PLASMA_CORE_REGISTER_PASS sp 0x20004FF0\n"
                "PLASMA_CORE_REGISTER_PASS lr 0x08000201\n"
                "PLASMA_CORE_REGISTER_PASS xPSR 0x01000000\n")
        running = ("PLASMA_CORE_STATE_BEFORE running\n" + regs
                   + "PLASMA_CORE_RESUME_OK\n"
                   + "PLASMA_CORE_STATE_AFTER running\n"
                   + "PLASMA_CORE_SUMMARY PASS\n")
        halted = ("PLASMA_CORE_STATE_BEFORE halted\n" + regs
                  + "PLASMA_CORE_STATE_AFTER halted\n"
                  + "PLASMA_CORE_SUMMARY PASS\n")
        for log in (running, halted):
            self.assertTrue(module.read_core_evidence(log)[0])
        negatives = (
            running.replace("PLASMA_CORE_RESUME_OK\n", ""),
            running.replace("PLASMA_CORE_STATE_AFTER running", "PLASMA_CORE_STATE_AFTER halted"),
            running.replace("PLASMA_CORE_REGISTER_PASS lr 0x08000201\n", ""),
            running.replace("0x20004FF0", "UNREADABLE"),
            running.replace("PLASMA_CORE_SUMMARY PASS", "PLASMA_CORE_SUMMARY FAIL"),
            running + "PLASMA_CORE_REGISTER_FAIL pc TARGET_TIMEOUT\n",
            "PLASMA_CORE_SUMMARY PASS\n",
        )
        for log in negatives:
            with self.subTest(log=log[-100:]):
                self.assertFalse(module.read_core_evidence(log)[0])


if __name__ == "__main__":
    unittest.main()
