"""Host-only checkpoint rejection; no SSH, MMIO or physical target."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

PATH = Path(__file__).resolve().parents[1] / 'bluepill-wordport-session.py'
spec = importlib.util.spec_from_file_location('bluepill_session', PATH)
session = importlib.util.module_from_spec(spec)
spec.loader.exec_module(session)


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.manifest = SimpleNamespace(
            firmware_name='candidate.bin', image_id='bluepill',
            firmware_sha256='b' * 64, axi_base=0x40008000,
            axi_bytes=4096, abi_version=0x10000,
            identity_words=((0, 0x50425357, 0xffffffff),
                            (4, 0x10000, 0xffffffff),
                            (12, 8, 0xfffffffe)))
        self.record = dict(schema='plasma.fpga.image-deployment.v3',
                           status='IMAGE', boot_id='boot', image='candidate.bin',
                           image_id='bluepill', manifest_sha256='a' * 64,
                           firmware_sha256='b' * 64, test_count=1)

    def validate(self):
        session.validate_checkpoint(self.record, self.manifest,
                                    boot_id='boot', manifest_sha='a' * 64)

    def test_held_tested_exact_image(self):
        self.validate()

    def test_stale_unknown_golden_or_untested_rejected(self):
        for key, bad in [('schema', 'old'), ('status', 'RECOVERY'),
                         ('status', 'UNKNOWN'), ('status', 'TEST_IN_FLIGHT'),
                         ('boot_id', 'other-boot'), ('image', 'base.bin'),
                         ('image_id', 'other-image'), ('manifest_sha256', 'c'*64),
                         ('firmware_sha256', 'd'*64), ('test_count', 0),
                         ('test_count', True)]:
            with self.subTest(key=key, value=bad):
                original = self.record[key]
                self.record[key] = bad
                with self.assertRaisesRegex(RuntimeError, 'HELD_TESTED'):
                    self.validate()
                self.record[key] = original

    def test_other_aperture_or_abi_rejected(self):
        for key, bad in [('axi_base', 0x40000000), ('axi_bytes', 65536),
                         ('abi_version', 2), ('identity_words', ())]:
            with self.subTest(key=key):
                original = getattr(self.manifest, key)
                setattr(self.manifest, key, bad)
                with self.assertRaisesRegex(RuntimeError, 'BLUEPILL_IMAGE_ABI'):
                    self.validate()
                setattr(self.manifest, key, original)

    def test_deadline_fails_closed(self):
        with self.assertRaises(TimeoutError):
            session.deadline_expired(None, None)


if __name__ == '__main__':
    unittest.main()
