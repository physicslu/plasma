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


class ExtendedAdmission(unittest.TestCase):
    def evidence(self, **changes):
        from dataclasses import replace
        good = f1b.AdmissionEvidence(
            reviewed_source=f1b.SOURCE, boot_id='synthetic-boot',
            provenance_boot_id='synthetic-boot', original_sha=f1b.BASE_SHA,
            original_hwh_sha=f1b.BASE_HWH_SHA, root_owned_source=True,
            protected_recovery=True, bootgen_receipt_verified=True, root_route=True, complete_proc_visibility=True,
            kernel_driver_excluded=True, hardware_owner_excluded=True,
            axi_idle_isolated=True, child_reaped=True)
        return replace(good, **changes)

    def test_each_missing_admission_fact_denies(self):
        from dataclasses import fields
        f1b.admit(self.evidence(), maps='', fds=[])
        for field in fields(f1b.AdmissionEvidence):
            value = False if field.type == 'bool' else ''
            with self.subTest(field=field.name), self.assertRaises(ValueError):
                f1b.admit(self.evidence(**{field.name: value}), maps='', fds=[])
        with self.assertRaises(ValueError):
            f1b.admit(self.evidence(provenance_boot_id='old-boot'), maps='', fds=[])

    def test_retained_fds(self):
        for node in ('/dev/mem', '/dev/mem (deleted)', '/dev/uio1',
                     '/dev/xdevcfg', '/dev/fpga0', 'UNKNOWN', ''):
            with self.subTest(node=node), self.assertRaises(ValueError):
                f1b.admit(self.evidence(), maps='', fds=[node])

    def test_partial_bin(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'candidate.bin'
            p.write_bytes(b'partial')
            with patch.object(f1b, 'verify_file'), patch.object(
                    f1b.staging, 'bit_payload', return_value=bytes.fromhex('aa995566')):
                with self.assertRaisesRegex(ValueError, 'payload mismatch'):
                    f1b.verify_conversion(p, p)

    def test_child_sigbus_timeout_unreaped(self):
        for code, reaped, timeout in ((-7, True, False), (0, False, False),
                                      (0, True, True), (None, True, False)):
            with self.subTest(code=code), self.assertRaises(ValueError):
                f1b.child_result(code, reaped=reaped, timed_out=timeout)
        f1b.child_result(0, reaped=True, timed_out=False)

    def test_restore_verification_failure_no_second_write(self):
        state, events = Admission().sequence('verify')
        self.assertEqual(events.count('load'), 1)
        self.assertEqual(events.count('restore'), 1)
        self.assertEqual(state['restoration_verified'], 'FAIL_OR_UNKNOWN')

    def test_axi_hang_or_unreaped_suppresses_restore(self):
        for fact in ('axi_idle_isolated', 'child_reaped'):
            events = []
            def identity():
                raise TimeoutError('synthetic AXI hang')
            state = f1b.offline_sequence(
                preflight=lambda: None, load=lambda: events.append('load'),
                identity=identity,
                restore_guard=lambda: f1b.admit(self.evidence(**{fact: False}), maps='', fds=[]),
                restore=lambda: events.append('restore'), verify_restore=lambda: None)
            self.assertEqual(events, ['load'])
            self.assertEqual(state['restore'], 'FAIL_OR_UNKNOWN')


class SupervisorAdapter(unittest.TestCase):
    def test_lock_intent_and_fresh_restore_admission(self):
        events = []
        def observe():
            events.append('observe')
            return ExtendedAdmission().evidence(), '', []
        from contextlib import nullcontext
        with patch.object(f1b, 'exclusive_session', return_value=nullcontext()) as lock:
            state = f1b.supervised_sequence(
                lock_path=Path('/synthetic/lock'), observe=observe,
                record_intent=lambda: events.append('intent'),
                load=lambda: events.append('load'), identity=lambda: events.append('identity'),
                restore=lambda: events.append('restore'),
                verify_restore=lambda: events.append('verify'))
        lock.assert_called_once()
        self.assertEqual(events, ['observe', 'intent', 'load', 'identity',
                                  'observe', 'restore', 'verify'])
        self.assertEqual(state['restoration_verified'], 'PASS')

    def test_intent_failure_never_writes(self):
        from contextlib import nullcontext
        writes = []
        def intent():
            raise OSError('receipt cannot be persisted')
        with patch.object(f1b, 'exclusive_session', return_value=nullcontext()):
            state = f1b.supervised_sequence(
                lock_path=Path('/synthetic/lock'),
                observe=lambda: (ExtendedAdmission().evidence(), '', []),
                record_intent=intent, load=lambda: writes.append('load'),
                identity=lambda: None, restore=lambda: writes.append('restore'),
                verify_restore=lambda: None)
        self.assertEqual(writes, [])
        self.assertEqual(state['preflight'], 'NOT_RUN')


class RetiredPath3PrefetchOffline(unittest.TestCase):
    def test_legacy_prefetch_is_absent_but_content_integrity_remains(self):
        """Delete the Path 3 prefetch without weakening protected Path 2 checks."""
        import hashlib
        workflow = Path('.github/workflows/plasma-engineering-runtime-dispatch.yml').read_text()
        self.assertNotIn('plasma-f1b-pinned', workflow)
        self.assertNotIn('Prefetch exact F1-B BIT/HWH', workflow)
        self.assertNotIn('PLASMA_FPGA_PATH3_APPROVED', workflow)

        with tempfile.TemporaryDirectory() as d:
            payload = b'synthetic-bit-content'
            bit = Path(d) / 'candidate.bit'
            bit.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            self.assertEqual(f1b.verify_file(bit, digest, size=len(payload)), payload)
            with self.assertRaisesRegex(ValueError, 'artifact hash rejected'):
                f1b.verify_file(bit, '0' * 64)
            with self.assertRaisesRegex(ValueError, 'artifact size rejected'):
                f1b.verify_file(bit, digest, size=len(payload) + 1)
            with self.assertRaises(FileNotFoundError):
                f1b.verify_file(Path(d) / 'missing.bit', digest)


if __name__ == '__main__':
    unittest.main(verbosity=2)


def test_noop_is_not_test_pass():
    events = []
    state = f1b.offline_sequence(
        preflight=lambda: None, load=lambda: None, identity=lambda: None,
        restore_guard=lambda: None, restore=lambda: events.append('restore'),
        verify_restore=lambda: None)
    assert state['test'] == 'NOT_RUN'
    assert state['hil02'] == 'NOT_APPLICABLE'
    assert state['overall'] != 'PASS_SOFTWARE_OFFLINE'
    assert events == ['restore']


def test_three_matching_reads_are_offline_only():
    seen = []
    def read(address):
        seen.append(address)
        return f1b.IDENTITY[address - f1b.BASE]
    state = f1b.offline_sequence(
        preflight=lambda: None, load=lambda: None,
        identity=lambda: f1b.read_identity(read), restore_guard=lambda: None,
        restore=lambda: None, verify_restore=lambda: None)
    assert seen == [0x40000000, 0x40000004, 0x40004000]
    assert state['test'] == 'PASS'
    assert state['hil02'] == 'NOT_APPLICABLE'
    assert state['overall'] == 'PASS_SOFTWARE_OFFLINE'
    assert state['execution'] == 'software-offline'


def test_f1b_profile_pins_one_aperture_and_firmware():
    assert f1b.PROFILE.apertures == (('identity', 0x40000000, 0x10000),)
    assert f1b.PROFILE.bin_sha256 == f1b.BIN_SHA
    assert f1b.PROFILE.recovery_sha256 == f1b.BASE_SHA
    assert dict(f1b.PROFILE.identity_words) == f1b.IDENTITY


def test_identity_child_uses_readonly_native_backend(tmp_path):
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    backend = MagicMock()
    backend.__enter__.return_value = backend
    backend.read32.side_effect = lambda address: f1b.IDENTITY[address - f1b.BASE]
    backend.stats.return_value = SimpleNamespace(read32=3, write32=0)
    with patch('plasma_interfaces.linux_mmio.LinuxMMIO', return_value=backend) as factory, \
         patch('pl.hil.swd04.native_qualify.check_runtime'):
        f1b.identity_child(tmp_path / 'identity.json')
    assert factory.call_args.kwargs == {'readonly': True}
    aperture = factory.call_args.args[0][0]
    assert aperture.readable == frozenset((0, 4, 0x4000))
    assert aperture.writable == frozenset()
    assert backend.read32.call_count == 3
    backend.write32.assert_not_called()


def test_missing_child_evidence_never_passes(tmp_path):
    state = {'test': 'NOT_RUN'}
    with patch.object(f1b.one_shot, 'run_child'), \
         __import__('pytest').raises(FileNotFoundError):
        f1b.identity_callback(tmp_path / 'missing.json')(state)
    assert state['test'] == 'NOT_RUN'


def test_bounded_child_timeout_reaps_before_return():
    import subprocess
    from pl.hil.swd04 import one_shot
    from unittest.mock import MagicMock
    import pytest
    proc = MagicMock(pid=123)
    proc.wait.side_effect = [subprocess.TimeoutExpired('synthetic', 35), 0]
    with patch.object(one_shot.subprocess, 'Popen', return_value=proc), \
         patch.object(one_shot.os, 'killpg') as kill, \
         pytest.raises(one_shot.c.SafetyError, match='MMIO_CHILD_TIMEOUT'):
        one_shot.run_child(['synthetic'])
    assert proc.wait.call_count == 2
    kill.assert_called_once_with(123, one_shot.signal.SIGTERM)


def test_bounded_child_sigbus_and_unreaped_are_never_pass():
    import subprocess
    import pytest
    from unittest.mock import MagicMock
    from pl.hil.swd04 import one_shot
    for returns, message in (([-7], 'SIGBUS'),
                             ([subprocess.TimeoutExpired('synthetic', 35)] * 3,
                              'UNREAPED_NO_RELOAD')):
        proc = MagicMock(pid=123)
        proc.wait.side_effect = returns
        with patch.object(one_shot.subprocess, 'Popen', return_value=proc), \
             patch.object(one_shot.os, 'killpg'), \
             pytest.raises(one_shot.c.SafetyError, match=message):
            one_shot.run_child(['synthetic'])


def test_profile_ownership_checks_full_64k():
    # Ordinary host fixtures cover a retained last-page mapping after fd close.
    import pytest
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as root:
        proc = Path(root)
        (proc/'123/fd').mkdir(parents=True)
        (proc/'123/maps').write_text(
            '10000000-10001000 r--s 4000f000 00:01 1 /dev/mem\n')
        with pytest.raises(f1b.one_shot.c.SafetyError, match='retained PL mapping'):
            f1b.development.check_users({'/dev/mem'}, proc=proc, profile=f1b.PROFILE)
