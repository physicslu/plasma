"""Host-only failure injections; never loads firmware or opens devices."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pl.hil import f1b


class Admission(unittest.TestCase):
    def test_exact_reads(self):
        seen = []
        def read(address):
            seen.append(address)
            return f1b.IDENTITY[address-f1b.BASE]
        self.assertEqual(f1b.read_identity(read), f1b.IDENTITY)
        self.assertEqual(seen, [f1b.BASE+x for x in f1b.IDENTITY])

    def test_wrong_abi(self):
        with self.assertRaisesRegex(ValueError, 'ABI mismatch'):
            f1b.read_identity(lambda address: 0x504C534D)

    def test_denied_offsets(self):
        for offset in (-4, 1, 0x54, 0x1000, 0x400C, 0x10000, True):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                f1b.checked_address(offset)

    def test_wrong_hash_and_missing_recovery(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'bad'; p.write_bytes(b'foreign')
            with self.assertRaises(ValueError):
                f1b.verify_file(p, f1b.BIT_SHA)
            with self.assertRaises(FileNotFoundError):
                f1b.verify_file(Path(d)/'missing-base.bin', f1b.BASE_SHA)

    def test_conversion_bytes_without_foreign_bin_pin(self):
        # Synthetic parser output exercises conversion comparison only.
        with tempfile.TemporaryDirectory() as d:
            bit, firmware = Path(d)/'test.bit', Path(d)/'test.bin'
            bit.write_bytes(b'synthetic')
            firmware.write_bytes(bytes.fromhex('665599aa00000020'))
            with patch.object(f1b, 'verify_file'), patch.object(
                    f1b.staging, 'bit_payload', return_value=bytes.fromhex('aa995566')):
                self.assertEqual(f1b.verify_conversion(bit, firmware)['size_bytes'], 8)
                firmware.write_bytes(bytes.fromhex('aa99556600000020'))
                with self.assertRaisesRegex(ValueError, 'payload mismatch'):
                    f1b.verify_conversion(bit, firmware)

    def test_retained_vma_entire_window(self):
        for offset in (0x40000000, 0x40004000, 0x4000F000):
            with self.subTest(offset=offset), self.assertRaisesRegex(ValueError, 'MMIO VMA'):
                f1b.reject_retained_maps(
                    f'10000000-10001000 r--s {offset:08x} 01:01 1 /dev/mem')
        with self.assertRaisesRegex(ValueError, 'PL device VMA'):
            f1b.reject_retained_maps('10000000-10001000 r--s 00000000 01:01 1 /dev/uio0')
        f1b.reject_retained_maps('10000000-10001000 r--s 50000000 01:01 1 /dev/mem')

    def sequence(self, failure=None, held=False):
        events = []
        def action(name):
            def call():
                events.append(name)
                if name == failure:
                    raise TimeoutError(name)
                if name == 'guard' and held:
                    raise ValueError('retained VMA/AXI health unknown')
            return call
        state = f1b.offline_sequence(
            preflight=action('preflight'), load=action('load'),
            identity=action('identity'), restore_guard=action('guard'),
            restore=action('restore'), verify_restore=action('verify'))
        return state, events

    def test_held_owner_preflight_no_load(self):
        state, events = self.sequence('preflight')
        self.assertEqual(events, ['preflight'])
        self.assertEqual(state['candidate_load'], 'NOT_RUN')

    def test_failed_or_timed_out_load_attempts_guarded_restore(self):
        state, events = self.sequence('load')
        self.assertEqual(events, ['preflight', 'load', 'guard', 'restore', 'verify'])
        self.assertEqual(state['candidate_load'], 'NOT_RUN')
        self.assertEqual(state['restoration_verified'], 'PASS')

    def test_identity_timeout_retained_vma_no_reload(self):
        state, events = self.sequence('identity', held=True)
        self.assertNotIn('restore', events)
        self.assertEqual(state['restore'], 'FAIL_OR_UNKNOWN')

    def test_clean_restoration(self):
        state, events = self.sequence()
        self.assertEqual(events, ['preflight', 'load', 'identity', 'guard', 'restore', 'verify'])
        self.assertEqual(state['restoration_verified'], 'PASS')


if __name__ == '__main__':
    unittest.main(verbosity=2)
