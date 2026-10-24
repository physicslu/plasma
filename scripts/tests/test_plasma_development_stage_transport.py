"""Host-only trusted transport regressions. Fake secrets/processes only."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plasma_development_stage_transport as t
import plasma_path2_runtime_integration as r
import plasma_development_dispatch as d

SHA = 'a' * 40
PROJECT = 'pl/projects/z2-fixed-unified-site1'

class Contracts(unittest.TestCase):
    def test_no_installed_host_dependency_or_candidate_import(self):
        source = Path(t.__file__).read_text() + Path(r.__file__).read_text()
        for forbidden in ('/usr/local/libexec/plasma/z2-path2-f1b-bridge',
                          'z2-path2-f1b.approved-sha', 'importlib', 'exec_module'):
            self.assertNotIn(forbidden, source)
        self.assertEqual(t.ROOT_ENTRY, '/usr/local/libexec/plasma/z2-path2-root-entry')
        self.assertEqual(t.MARK, 'PLASMA_PATH2_STAGE=')
        self.assertNotIn('F1B_IMAGE_NOT_LOADED', source)
        self.assertIn('StrictHostKeyChecking=yes', source)
        self.assertIn('GlobalKnownHostsFile=/dev/null', source)

    def test_private_file_missing_mode_and_symlink(self):
        with tempfile.TemporaryDirectory() as td, patch.object(t.pwd, 'getpwnam',
                return_value=Mock(pw_uid=os.geteuid())):
            root = Path(td); root.chmod(0o700)
            path = root / 'credential'
            with self.assertRaises(OSError): t.private_json(path)
            path.write_text('{"fake":"secret"}'); path.chmod(0o600)
            self.assertEqual(t.private_json(path), {'fake':'secret'})
            path.chmod(0o644)
            with self.assertRaises(t.Blocked): t.private_json(path)
            path.unlink(); path.symlink_to(root / 'missing')
            with self.assertRaises(t.Blocked): t.private_json(path)

    def test_invalid_credentials_never_launch_remote(self):
        with patch.object(t.pwd, 'getpwuid', return_value=Mock(pw_name=t.WORKER)), \
             patch.object(t.os, 'geteuid', return_value=1000), \
             patch.object(t, 'private_json', return_value={}), \
             patch.object(t.subprocess, 'Popen') as launch:
            with self.assertRaisesRegex(t.Blocked, 'NOT_ENROLLED'):
                t.execute('test', SHA, PROJECT)
            launch.assert_not_called()

    def _expect_login(self, record, *, key_lookup=0):
        """Patch one worker-owned login and known_hosts, never an SSH session."""
        fake_login = Mock()
        fake_keys = Mock()
        fake_keys.lstat.return_value = Mock(st_mode=0o100600, st_uid=1000)
        return fake_login, fake_keys, [
            patch.object(t, 'LOGIN', fake_login),
            patch.object(t, 'KNOWN_HOSTS', fake_keys),
            patch.object(t, 'private_json', return_value=record),
            patch.object(t.pwd, 'getpwuid', return_value=Mock(pw_name=t.WORKER)),
            patch.object(t.os, 'geteuid', return_value=1000),
            patch.object(t.subprocess, 'run', return_value=Mock(returncode=key_lookup)),
        ]

    def test_only_path3_login_credentials_are_consumed(self):
        record = {'ssh_host': 'z2.example', 'ssh_username': 'xilinx',
                  'ssh_password': 'test-login'}
        login, keys, patches = self._expect_login(record)
        with patches[0], patches[1], patches[2] as reader, \
             patches[3], patches[4], patches[5]:
            self.assertEqual(t.enrollment(),
                             ('z2.example', 'test-login', 'test-login'))
            reader.assert_called_once_with(login)

    def test_optional_sudo_secret_also_comes_from_only_login(self):
        record = {'ssh_host': 'z2.example', 'ssh_username': 'xilinx',
                  'ssh_password': 'test-login', 'sudo_password': 'different-sudo'}
        login, keys, patches = self._expect_login(record)
        with patches[0], patches[1], patches[2] as reader, \
             patches[3], patches[4], patches[5]:
            self.assertEqual(t.enrollment(),
                             ('z2.example', 'test-login', 'different-sudo'))
            reader.assert_called_once_with(login)

    def test_missing_or_malformed_login_never_attempts_remote(self):
        for record in ({}, {'ssh_host':'z2.example'},
                       {'ssh_host':'z2.example', 'ssh_username':'xilinx',
                        'ssh_password':'fake', 'extra':'not-allowed'},
                       {'ssh_host':'z2.example', 'ssh_username':'xilinx',
                        'ssh_password':'fake', 'sudo_password':''}):
            with self.subTest(record=sorted(record)), \
                 patch.object(t, 'private_json', return_value=record), \
                 patch.object(t.pwd, 'getpwuid', return_value=Mock(pw_name=t.WORKER)), \
                 patch.object(t.os, 'geteuid', return_value=1000), \
                 patch.object(t.subprocess, 'Popen') as remote:
                with self.assertRaises(t.Blocked):
                    t.execute('test', SHA, PROJECT)
                remote.assert_not_called()
        with patch.object(t, 'private_json', side_effect=FileNotFoundError), \
             patch.object(t.pwd, 'getpwuid', return_value=Mock(pw_name=t.WORKER)), \
             patch.object(t.os, 'geteuid', return_value=1000), \
             patch.object(t.subprocess, 'Popen') as remote:
            with self.assertRaisesRegex(t.Blocked, 'LOCAL_ENROLLMENT_DENIED'):
                t.execute('test', SHA, PROJECT)
            remote.assert_not_called()

    def test_host_key_missing_or_mismatch_never_launches_ssh(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); root.chmod(0o700)
            login = root / 'login'; keys = root / 'known_hosts'
            login.write_text(json.dumps({'ssh_host':'fake.example', 'ssh_username':'xilinx', 'ssh_password':'fake'}))
            keys.write_text('fake.example ssh-ed25519 FAKE-TEST-KEY\n')
            for file in (login,keys): file.chmod(0o600)
            with patch.object(t,'LOGIN',login), patch.object(t,'KNOWN_HOSTS',keys), \
                 patch.object(t.pwd,'getpwnam',return_value=Mock(pw_uid=os.geteuid())), \
                 patch.object(t.pwd,'getpwuid',return_value=Mock(pw_name=t.WORKER)), \
                 patch.object(t.os,'geteuid',return_value=os.geteuid() or 1000), \
                 patch.object(t.subprocess,'run',return_value=Mock(returncode=1)), \
                 patch.object(t.subprocess,'Popen') as remote:
                with self.assertRaises(t.Blocked): t.execute('test',SHA,PROJECT)
                remote.assert_not_called()

    def test_candidate_python_is_not_loaded_for_stage(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); (root/'scripts').mkdir()
            (root/'scripts/plasma_development_stage_transport.py').write_text(
                'raise AssertionError("CANDIDATE_EXECUTED")')
            approval = {'task_id':'z2-path2-testing','execution_path':'path2-cli',
                        'execution_capability':'path2-stage-contract',
                        'pinned_sha':SHA,'trusted_sha':SHA,'pr_number':0}
            task = {'capability':'path2-stage-contract','stage':'test',
                    'project':'pl/projects/z2-fixed-unified-site1'}
            payload = {'stage':'test','source_sha':SHA,'project':PROJECT,'real_z2':True,
                       'boot_id':'fake-test-boot','result':'IDENTITY_PASS'}
            with patch.object(t,'execute',return_value=payload) as call:
                d.run_task(task, workspace=root, approval=approval)
                call.assert_called_once_with('test', SHA, PROJECT)

    def test_live_pr_changed_head_owner_repo_base_rejected(self):
        req = {'pr_number':123, 'source_sha':SHA}
        good = {'number':123, 'state':'open', 'merged_at':None,
                'user':{'login':'physicslu'},
                'head':{'sha':SHA,'ref':'agent/change','repo':{'full_name':d.REPO}},
                'base':{'ref':'main','repo':{'full_name':d.REPO}}}
        with patch.object(d.subprocess, 'run', return_value=Mock(stdout=json.dumps(good).encode())):
            self.assertEqual(d.live_pr_metadata(req), good)
        for section, key, value in [('head','sha','b'*40), ('user','login','other'),
                                     ('base','ref','dev'), ('head','repo',{'full_name':'fork/repo'})]:
            bad = copy.deepcopy(good); bad[section][key] = value
            with patch.object(d.subprocess, 'run', return_value=Mock(stdout=json.dumps(bad).encode())):
                with self.assertRaises(d.Denied): d.live_pr_metadata(req)
        with patch.object(d.subprocess, 'run') as call:
            self.assertIsNone(d.live_pr_metadata({'pr_number':0}))
            call.assert_not_called()

    def test_single_path2_test_has_no_implicit_download_restore(self):
        approval = {'task_id':'z2-path2-testing','execution_path':'path2-cli',
                    'execution_capability':'path2-stage-contract','pinned_sha':SHA,
                    'trusted_sha':SHA,'pr_number':0,
                    'auto_download_after_build_success':True,
                    'auto_test_after_download_success':True}
        task = {'capability':'path2-stage-contract','stage':'test',
                'project':'pl/projects/z2-fixed-unified-site1'}
        receipt = {'stage':'test','source_sha':SHA,'project':PROJECT,'real_z2':True,
                   'boot_id':'fake-test-boot','result':'IDENTITY_PASS'}
        with patch.object(t,'execute',return_value=receipt) as call:
            result = r.registered_hardware_stage(task,approval)
            self.assertFalse(result['auto_next_stage'])
            call.assert_called_once_with('test',SHA,PROJECT)
        with patch.object(t,'execute') as call:
            with self.assertRaises(r.RuntimeDenied):
                r.registered_hardware_stage(task | {'stage':'restore'},approval)
            call.assert_not_called()

    def test_timeout_kills_and_reaps(self):
        proc = Mock(pid=999999)
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired('fake',2), 0]
        with patch.object(t,'enrollment',return_value=('fake.example','fake-password','fake-sudo')), \
             patch.object(t.os,'openpty',return_value=(90,91)), \
             patch.object(t.tty,'setraw'), patch.object(t.os,'close'), \
             patch.object(t.subprocess,'Popen',return_value=proc), \
             patch.object(t.time,'monotonic',side_effect=[0,200]), \
             patch.object(t.os,'killpg') as kill:
            with self.assertRaisesRegex(t.Blocked,'REMOTE_TIMEOUT'):
                t.execute('test', SHA, PROJECT)
            self.assertEqual(kill.call_count,2)
            self.assertEqual(proc.wait.call_count,2)


    def test_generic_root_entry_is_pinned_and_syntax_valid(self):
        path = Path(__file__).resolve().parents[1] / 'z2/plasma-path2-root-entry'
        code = path.read_text()
        self.assertNotIn('plasma-path2-f1b-site1-approved', code)
        self.assertNotIn('pl.hil.path2_f1b_minimal_stage', code)
        self.assertNotIn('PLASMA_DEV_RISK_ACK', code)
        self.assertIn('.plasma-path2-profile', code)
        self.assertIn('PATH2_APPROVED_PROFILE_MISMATCH', code)
        self.assertIn('sha256sum --check --status', code)
        self.assertIn('find "$root" -type f -print0', code)
        self.assertIn('PATH2_UNPINNED_BYTECODE_DENIED', code)
        self.assertIn('PYTHONDONTWRITEBYTECODE=1', code)
        self.assertIn('"$python" -B -m "$module" "$stage"', code)
        self.assertIn('PATH2_SOURCE_WRITABLE_BY_OTHERS', code)
        self.assertIn("PATH2_REQUIRED_SOURCE_NOT_PINNED", code)
        self.assertIn('find "$root" -type l', code)
        self.assertIn('find "$root" -type d', code)
        self.assertIn('exec /usr/bin/env -i', code)
        subprocess.run(['/usr/bin/bash', '-n', str(path)], check=True)
        for args in [[], ['download'], ['test', '../escape', SHA],
                     ['test', PROJECT, 'bad'], ['arbitrary', PROJECT, SHA]]:
            result = subprocess.run(['/usr/bin/bash', str(path), *args],
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)

    def test_project_pinned_receipt_and_no_duplicate(self):
        receipt = {'stage': 'test', 'project': PROJECT,
                   'boot_id': 'test-boot-id', 'result': 'IDENTITY_PASS'}
        encoded = (t.MARK + json.dumps(receipt) + chr(10)).encode()
        self.assertEqual(t.parse_receipt(
            'test', SHA, encoded, PROJECT)['project'], PROJECT)
        with self.assertRaisesRegex(t.Blocked, 'REMOTE_RESULT_NOT_VERIFIED'):
            t.parse_receipt('test', SHA, encoded, 'pl/projects/z2-bluepill-rbb')
        with self.assertRaises(t.Blocked):
            t.parse_receipt('test', SHA, encoded + encoded, PROJECT)

    def test_project_specific_target_failure_is_never_generic_authority(self):
        # A particular project may report its own error, but Stage Transport
        # must not treat a project's stderr as a privileged root receipt.
        failed = b"LiveStageDenied: F1B_IMAGE_NOT_LOADED" + bytes([10])
        self.assertEqual(t.remote_failure(1, failed),
                         'REMOTE_EXIT_OR_PRIVILEGE_FAILED')
        self.assertEqual(t.remote_failure(2, failed),
                         'REMOTE_EXIT_OR_PRIVILEGE_FAILED')

    def test_bad_project_never_attempts_ssh(self):
        with patch.object(t, 'enrollment') as enrollment:
            with self.assertRaisesRegex(t.Blocked, 'PROJECT_NOT_ALLOWLISTED'):
                t.execute('test', SHA, '../unreviewed')
            enrollment.assert_not_called()

if __name__ == '__main__': unittest.main()
