"""Host-only A/B tests: never contact SWPC, Z2, FPGA, USB or DUT."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "plasma_swd_ab_path2.py"
spec = importlib.util.spec_from_file_location("plasma_swd_ab_path2", SOURCE)
ab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ab)


class ABPath2Test(unittest.TestCase):
    def test_100_attempts_are_balanced(self):
        runs = [p for start in (0, 20, 40, 60, 80)
                for p in ab.sequence(start, 20)]
        self.assertEqual([n for n, _ in runs], list(range(1, 101)))
        self.assertEqual([v for _, v in runs].count("v0.1"), 50)
        self.assertEqual([v for _, v in runs].count("v0.2"), 50)
        self.assertEqual([v for _, v in runs[:4]],
                         ["v0.1", "v0.2", "v0.2", "v0.1"])

    def test_invalid_batches_rejected(self):
        for start, count in [(-1, 20), (1, 20), (0, 0), (0, 21),
                             (90, 20), (80, 10), (100, 20)]:
            with self.subTest(start=start, count=count):
                with self.assertRaises(ValueError):
                    ab.sequence(start, count)

    def test_region_keeps_final_two_pages(self):
        self.assertEqual(ab.ERASE_BYTES, 62 * 1024)
        self.assertEqual(65536 - ab.ERASE_BYTES, 2048)
        for v in ab.EXPECTED.values():
            self.assertLessEqual(v["bytes"], ab.ERASE_BYTES)

    def test_readback_hash_includes_erased_tail(self):
        data = b"\x01\x02"
        expected = hashlib.sha256(data + b"\xff" * (63488 - 2)).hexdigest()
        self.assertEqual(ab.expected_region_sha(data), expected)
        self.assertNotEqual(ab.expected_region_sha(data), hashlib.sha256(data).hexdigest())
        with self.assertRaises(ValueError):
            ab.expected_region_sha(b"\x00" * (63488 + 1))

    def test_firmware_hash_and_size_are_enforced(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "candidate.bin"
            file.write_bytes(b"\x00" * 18768)
            with self.assertRaisesRegex(ab.NotRun, "FIRMWARE_SIZE_OR_SHA_MISMATCH"):
                ab.firmware(file, "v0.1")
            with self.assertRaisesRegex(ab.NotRun, "FIRMWARE_NOT_AVAILABLE"):
                ab.firmware(Path(folder) / "missing", "v0.2")

    def test_remote_template_renders_and_compiles(self):
        cfg = {"mode": "flash", "site": 2, "speed_khz": 5000,
               "firmware": "/root/.plasma-bluepill-ab/example/fw-v01.bin",
               "image_id": "z2-independent-swd-v5-d0add58c"}
        source = ab.make_remote(cfg)
        self.assertNotIn("@CONFIG_B64@", source)
        self.assertIn("flash erase_address 0x08000000 0xf800", source)
        self.assertIn("adapter speed 5000", source)
        self.assertIn("reset halt", source)
        self.assertIn("reset run", source)
        self.assertIn("dump_image", source)
        self.assertNotIn("fpga_load", source)
        compile(source, "ab_flow_tpl.py", "exec")

    def test_remote_receipt_denial_is_failure_not_not_run(self):
        helper = mock.Mock()
        helper.password_ssh_z2.return_value = (1, "denied")
        with self.assertRaisesRegex(RuntimeError, "OPERATION_COMMAND_FAILED"):
            ab.remote_call(helper, {}, Path("/not-used"), "reviewed code")
        helper.password_ssh_z2.return_value = (0, "no Z2JSON receipt")
        with self.assertRaisesRegex(RuntimeError, "OPERATION_RECEIPT_MISSING"):
            ab.remote_call(helper, {}, Path("/not-used"), "reviewed code")

    def test_staging_failure_does_not_become_not_run(self):
        helper = mock.Mock()
        helper.password_ssh_z2.return_value = (1, "denied")
        with self.assertRaises(RuntimeError):
            ab.remote_stage(helper, {}, Path("/unused"), "reviewed code")

    def test_cdc_wrong_version_or_timeout_fails(self):
        with mock.patch.object(ab, "cdc_port", return_value="/dev/ttyACM0"), \
                mock.patch.object(ab.subprocess, "run", return_value=mock.Mock(
                    returncode=1, stdout="HB version=0.1", stderr="wrong version")):
            out = ab.cdc_check("v0.2", 12)
        self.assertEqual(out["result"], "FAIL")

    def test_expected_sha_is_content_not_filename(self):
        self.assertNotEqual(ab.EXPECTED["v0.1"]["sha256"],
                            ab.EXPECTED["v0.2"]["sha256"])
        self.assertNotEqual(ab.EXPECTED["v0.1"]["bytes"],
                            ab.EXPECTED["v0.2"]["bytes"])

    def test_build_fallback_does_not_download_or_install_dependencies(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ab.NotRun, "BUILD_DEPENDENCIES_MISSING"):
                ab.build_v02_from_locked_source(Path(folder), Path(folder))


if __name__ == "__main__":
    unittest.main()
