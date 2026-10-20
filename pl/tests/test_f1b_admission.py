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


class TrustedPrefetchOffline(unittest.TestCase):
    def test_embedded_validator_synthetic_receipt_and_rejections(self):
        """Execute exact embedded validator with synthetic pins, never a network call."""
        import ast
        import hashlib
        import subprocess
        import sys
        import zipfile
        workflow = Path('.github/workflows/plasma-engineering-runtime-dispatch.yml').read_text()
        block = workflow.split("          python3 - \"$RUNNER_TEMP/plasma-f1b-pinned\" <<'PY'\n", 1)[1].split('\n          PY', 1)[0]
        source = '\n'.join(line[10:] for line in block.splitlines())
        tree = ast.parse(source)
        payloads = {'system_wrapper.bit': b'synthetic-bit', 'system.hwh': b'synthetic-hwh'}
        # Positive exercise uses explicit synthetic fixtures, not real custody evidence.
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'items' for t in node.targets):
                node.value = ast.parse(repr(tuple((n, len(b), hashlib.sha256(b).hexdigest())
                                                  for n, b in payloads.items())), mode='eval').body
        synthetic = ast.unparse(ast.fix_missing_locations(tree))
        for scenario in ('valid', 'corrupt', 'partial', 'missing'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                with zipfile.ZipFile(root/'source.zip', 'w') as archive:
                    for name, data in payloads.items():
                        if scenario == 'missing' and name == 'system.hwh':
                            continue
                        if name == 'system_wrapper.bit':
                            if scenario == 'corrupt':
                                data = b'X' * len(data)
                            if scenario == 'partial':
                                data = data[:-1]
                        archive.writestr('plasma/plasma/candidate/pl/build/f1b-deliverables/'+name, data)
                result = subprocess.run([sys.executable, '-c', synthetic, d], capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, scenario == 'valid', result.stderr)
                if scenario == 'valid':
                    for name, data in payloads.items():
                        self.assertEqual((root/name).read_bytes(), data)
        self.assertIn('GH_TOKEN: ${{ github.token }}', workflow)
        self.assertIn('F1B_ARTIFACT_IDENTITY_DENIED', source)


if __name__ == '__main__':
    unittest.main(verbosity=2)
