"""Host-only contracts. Fake Vivado here never constitutes a real Build PASS."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plasma_development_dispatch as dev
import plasma_vivado_host_build as build


class LicensedF1B(unittest.TestCase):
    def test_source_authentication_compares_bytes_not_index(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            name = 'pl/projects/z2-fixed-unified-site1/create_project.tcl'
            helper = 'pl/projects/z2-swd-gpio/prepare-board-repository.sh'
            files = {name: b'fixed reviewed Tcl', helper:
                     (dev.ROOT / helper).read_bytes()}
            for path, data in files.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            def git(args, **kwargs):
                if 'rev-parse' in args:
                    raw = b'a' * 40 + b'\n'
                elif 'ls-tree' in args:
                    raw = b'\0'.join(x.encode() for x in files) + b'\0'
                else:
                    raw = files[args[-1].split(':', 1)[1]]
                return subprocess.CompletedProcess(args, 0, raw, b'')
            with patch.object(build.subprocess, 'run', side_effect=git):
                actual = build.authenticate_host_inputs(root, 'a' * 40)
                self.assertEqual(set(actual['files_sha256']), set(files))
                (root / name).write_bytes(b'edited after owner review')
                with self.assertRaisesRegex(build.BuildDenied, 'UNREVIEWED_INPUT'):
                    build.authenticate_host_inputs(root, 'a' * 40)
                (root / name).unlink()
                (root / name).symlink_to(root / helper)
                with self.assertRaisesRegex(build.BuildDenied, 'SOURCE_DENIED'):
                    build.authenticate_host_inputs(root, 'a' * 40)

    def test_license_categories_never_include_raw_identifiers(self):
        with tempfile.TemporaryDirectory() as td:
            license_path = Path(td) / 'Xilinx.lic'
            license_path.write_text('HOSTID=001122334455 SECRET_LICENSE_PAYLOAD')
            completed = [subprocess.CompletedProcess([], 0,
                         b'Invalid host SECRET_LICENSE_PAYLOAD HOSTID=001122334455', b''),
                         subprocess.CompletedProcess([], 42, b'valid license was not found', b'')]
            with patch.object(build, 'discover_vivado_license', return_value={
                    'XILINXD_LICENSE_FILE': str(license_path)}), \
                    patch.object(build.socket, 'if_nameindex', side_effect=PermissionError):
                result = build.license_snapshot(executor=lambda *a, **k: completed.pop(0))
            self.assertTrue(result['lmdiag']['invalid_host'])
            self.assertFalse(result['vivado_startup']['pass'])
            self.assertIsNone(result['matching_interface_visible'])
            self.assertNotIn('001122334455', json.dumps(result))
            self.assertNotIn('SECRET_LICENSE_PAYLOAD', json.dumps(result))

    def execute(self, *, license_ok=True, failure=False, codex_exit=0):
        root = Path(self.tmp.name)
        req = {'task_id': 'f1b-path3-codex-vivado-build', 'pr_number': 123,
               'source_sha': 'b' * 40, 'trusted_sha': 'a' * 40}
        def engineer(*args, **kwargs):
            evidence = root / '.plasma-path3-evidence'
            evidence.mkdir()
            (evidence / 'engineering-report.md').write_text('Synthetic engineer\n')
            return {'codex_exit_code': codex_exit,
                    'status': 'EVIDENCE_READY_REVIEW_REQUIRED'}
        count = []
        def engine(*args, **kwargs):
            count.append(kwargs)
            self.assertEqual(kwargs['execution_path'], 'path3-codex')
            if failure:
                raise build.BuildDenied('BUILD_VIVADO_LICENSE_REJECTED')
            return {'build_dir': f'/synthetic/fresh-{len(count)}'}
        with patch.object(dev, 'run_codex_task', side_effect=engineer), \
                patch.object(build, 'license_snapshot', return_value={
                    'vivado_startup': {'pass': license_ok}}), \
                patch.object(build, 'authenticate_host_inputs', return_value={}), \
                patch.object(build, 'run', side_effect=engine):
            receipt = dev.run_licensed_f1b_task({}, workspace=root, req=req)
        return receipt, count

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_trusted_engine_runs_twice_with_separate_evidence(self):
        receipt, calls = self.execute()
        self.assertEqual(receipt['licensed_host_build_status'], 'PASS')
        self.assertEqual(len(calls), 2)
        self.assertNotEqual(calls[0]['evidence_dir'], calls[1]['evidence_dir'])

    def test_first_engine_failure_stops_repeat(self):
        receipt, calls = self.execute(failure=True)
        self.assertEqual(len(calls), 1)
        self.assertNotEqual(receipt['licensed_host_build_status'], 'PASS')
        result = json.loads((Path(self.tmp.name) / '.plasma-path3-evidence' /
                             'licensed-host-builds.json').read_text())
        self.assertEqual(result['reason'], 'BUILD_VIVADO_LICENSE_REJECTED')

    def test_failed_license_does_not_launch_build(self):
        receipt, calls = self.execute(license_ok=False)
        self.assertEqual(calls, [])
        self.assertEqual(receipt['status'], 'HOST_BUILD_FAILED_REVIEW_REQUIRED')

    def test_failed_codex_does_not_launch_build(self):
        _, calls = self.execute(codex_exit=2)
        self.assertEqual(calls, [])

    def test_generic_work_order_cannot_select_host_executor(self):
        with self.assertRaisesRegex(dev.Denied, 'SOURCE_BINDING'):
            dev.run_licensed_f1b_task({}, workspace=Path(self.tmp.name), req={
                'task_id': 'path3-work-order', 'pr_number': 0,
                'source_sha': 'a' * 40, 'trusted_sha': 'a' * 40})


if __name__ == '__main__':
    unittest.main()
