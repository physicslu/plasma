"""Offline failure injections: all enrollment, processes and PTYs are fake."""
import json
import signal
import subprocess
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import plasma_development_stage_transport as t
import plasma_path2_runtime_integration as r
import test_plasma_path2_swpc_bridge as harness_module
bridge = harness_module.bridge

SHA = 'a' * 40
TASK = {'capability':'path2-stage-contract', 'stage':'test',
        'project':'pl/projects/z2-fixed-unified-site1'}
APPROVAL = {'task_id':'z2-path2-testing', 'execution_path':'path2-cli',
            'execution_capability':'path2-stage-contract', 'pinned_sha':SHA,
            'trusted_sha':SHA, 'pr_number':0}

class FailureCodes(unittest.TestCase):
    def test_each_safe_code_survives_shared_adapter(self):
        for code in t.SAFE_FAILURE_CODES:
            with self.subTest(code=code), patch.object(t, 'execute', side_effect=t.Blocked(code)):
                with self.assertRaises(r.RuntimeDenied) as caught:
                    r.registered_hardware_stage(TASK, APPROVAL)
                self.assertEqual(caught.exception.args, (code,))

    def test_every_failure_stops_path3_before_restore(self):
        task={'execution_path':'path3-codex','capability':'codex-workspace',
              'work_order_scope':'guarded-hardware','work_order_sha256':'c'*64,
              'hardware_stages':['test','restore']}
        approval={'task_id':'path3-work-order','execution_path':'path3-codex',
                  'execution_capability':'codex-guarded-hardware',
                  'work_order_sha256':'c'*64,'pinned_sha':SHA,'trusted_sha':SHA,'pr_number':0}
        for code in t.SAFE_FAILURE_CODES:
            with self.subTest(code=code), patch.object(t,'execute',side_effect=t.Blocked(code)) as call:
                with self.assertRaises(r.RuntimeDenied) as caught:
                    r.path3_shared_hardware_stages(task,approval)
                self.assertEqual(caught.exception.args,(code,))
                call.assert_called_once_with('test',SHA)

    def test_hostile_exception_text_is_never_exported(self):
        for exc in (t.Blocked('SOURCE_SHA_INVALID\nsecret'), t.Blocked('10.0.0.1 password'),
                    t.Blocked(['SOURCE_SHA_INVALID']), t.Blocked(),
                    OSError('secret path'), ValueError('secret stdout')):
            with self.subTest(exc=type(exc)), patch.object(t,'execute',side_effect=exc):
                with self.assertRaises(r.RuntimeDenied) as caught:
                    r.registered_hardware_stage(TASK, APPROVAL)
                self.assertEqual(caught.exception.args, ('UNKNOWN',))

    def test_local_missing_enrollment_never_launches(self):
        for exc in (FileNotFoundError('secret'), ValueError('bad json'), KeyError('account')):
            with patch.object(t,'enrollment',side_effect=exc), patch.object(t.subprocess,'Popen') as launch:
                with self.assertRaisesRegex(t.Blocked,'LOCAL_ENROLLMENT_DENIED'):
                    t.execute('test',SHA)
                launch.assert_not_called()

    def test_bad_hostname_never_launches(self):
        for host in ('-option','bad host','host;id','host\nsecret',''):
            with patch.object(t.pwd,'getpwuid',return_value=Mock(pw_name=t.WORKER)), \
                 patch.object(t.os,'geteuid',return_value=1000), \
                 patch.object(t,'private_json',side_effect=[{'ssh_host':host,'ssh_username':'xilinx','ssh_password':'fake'}, {'sudo_password':'fake'}]), \
                 patch.object(t.subprocess,'Popen') as launch:
                with self.assertRaisesRegex(t.Blocked,'SSH_OR_SUDO_ROUTE_NOT_ENROLLED'):
                    t.execute('test',SHA)
                launch.assert_not_called()

    def test_transport_diagnostic_categories_are_bounded(self):
        cases = [
            (255,b'ssh: connect to host fake port 22: Connection timed out\r\n','SSH_CONNECT_TIMEOUT_OR_UNREACHABLE'),
            (255,b'ssh: connect to host fake port 22: No route to host\n','SSH_CONNECT_TIMEOUT_OR_UNREACHABLE'),
            (255,b'ssh: Could not resolve hostname fake: Name or service not known\n','SSH_CONNECT_TIMEOUT_OR_UNREACHABLE'),
            (255,b'Host key verification failed.\n','HOST_KEY_REJECTED'),
            (255,b'fake: Permission denied (password).\n','REMOTE_AUTH_OR_SUDO_FAILED'),
            (1,b'sudo: 1 incorrect password attempt\n','REMOTE_AUTH_OR_SUDO_FAILED'),
            (2,b'PATH2_APPROVED_ROOT_SOURCE_NOT_INSTALLED\n','Z2_ROOT_SOURCE_OR_IMAGE_BLOCKED'),
            (1,b'F1B_IMAGE_NOT_LOADED\n','REMOTE_EXIT_OR_PRIVILEGE_FAILED'),
            (-signal.SIGBUS,b'','CHILD_OWNERSHIP_UNCERTAIN'),
            (1,b'pl.hil.swd04.contract.SafetyError: MMIO_CHILD_UNREAPED_NO_RELOAD\n','CHILD_OWNERSHIP_UNCERTAIN'),
            (1,b'pl.hil.swd04.contract.SafetyError: MMIO child failed or SIGBUS\n','CHILD_OWNERSHIP_UNCERTAIN'),
        ]
        for rc, output, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(t.remote_failure(rc,output),expected)

    def test_exact_root_diagnostics_are_failure_classes_only(self):
        for code in t.ROOT_MANIFEST_DIAGNOSTICS:
            self.assertEqual(t.remote_failure(2,(code+'\n').encode()),
                             'Z2_ROOT_SOURCE_OR_IMAGE_BLOCKED')
            self.assertEqual(t.remote_failure(2,(code+' secret\n').encode()),
                             'REMOTE_EXIT_OR_PRIVILEGE_FAILED')
        code=b'LiveStageDenied: F1B_IMAGE_NOT_LOADED\n'
        self.assertEqual(t.remote_failure(1,code),'F1B_IMAGE_NOT_LOADED')
        self.assertEqual(t.remote_failure(1,code*2),'REMOTE_EXIT_OR_PRIVILEGE_FAILED')
        self.assertEqual(t.remote_failure(255,code),'REMOTE_EXIT_OR_PRIVILEGE_FAILED')
        harness=harness_module.BridgeContracts()
        for rc, output in ((1,code),(2,b'PATH2_APPROVED_SOURCE_HASH_MISMATCH\n')):
            with self.assertRaises(bridge.Blocked):
                harness._fake_ssh([output,harness._receipt()],exit_code=rc)

    def test_malformed_and_hostile_receipts_fail_closed(self):
        good = {'stage':'test','boot_id':'fake-test-boot','result':'IDENTITY_PASS'}
        for output in (b'hostile password 10.0.0.1',
                       (t.MARK+'{broken}\n').encode(),
                       (t.MARK+json.dumps(good)+'\n') .encode()*2,
                       (t.MARK+json.dumps(good | {'boot_id':'secret\naddress'})+'\n').encode(),
                       (t.MARK+json.dumps(good | {'result':'FAILED_RECOVERY'})+'\n').encode()):
            with self.assertRaises(t.Blocked) as caught:
                t.parse_receipt('test',SHA,output)
            self.assertIn(str(caught.exception),t.SAFE_FAILURE_CODES)

    def test_nonzero_and_sigbus_never_accept_success(self):
        harness=harness_module.BridgeContracts()
        for rc in (1,2,255,-signal.SIGBUS):
            with self.subTest(rc=rc), self.assertRaises(bridge.Blocked):
                harness._fake_ssh([harness._receipt()],exit_code=rc)

    def test_failed_restore_does_not_become_receipt(self):
        harness=harness_module.BridgeContracts()
        for result in ('FAILED_RECOVERY','UNKNOWN_MANUAL_RECOVERY','IDENTITY_PASS'):
            with self.assertRaises(bridge.Blocked):
                harness._fake_ssh([harness._receipt(result=result,stage='restore')],stage='restore')

    def test_denied_child_cleanup_is_uncertain_without_retry(self):
        proc=Mock(pid=999999)
        proc.poll.return_value=None
        with patch.object(t,'enrollment',return_value=('fake','fake','fake')), \
             patch.object(t.os,'openpty',return_value=(90,91)), \
             patch.object(t.tty,'setraw'), patch.object(t.os,'close') as close, \
             patch.object(t.subprocess,'Popen',return_value=proc), \
             patch.object(t.time,'monotonic',side_effect=[0,200]), \
             patch.object(t.os,'killpg',side_effect=PermissionError('secret')) as kill:
            with self.assertRaisesRegex(t.Blocked,'CHILD_OWNERSHIP_UNCERTAIN'):
                t.execute('test',SHA)
            kill.assert_called_once()
            self.assertEqual(close.call_count,2)

    def test_unreaped_child_overrides_timeout_and_closes_fds(self):
        proc=Mock(pid=999999)
        proc.poll.return_value=None
        proc.wait.side_effect=subprocess.TimeoutExpired('fake',2)
        with patch.object(t,'enrollment',return_value=('fake','fake','fake')), \
             patch.object(t.os,'openpty',return_value=(90,91)), \
             patch.object(t.tty,'setraw'), patch.object(t.os,'close') as close, \
             patch.object(t.subprocess,'Popen',return_value=proc), \
             patch.object(t.time,'monotonic',side_effect=[0,200]), \
             patch.object(t.os,'killpg'):
            with self.assertRaisesRegex(t.Blocked,'CHILD_OWNERSHIP_UNCERTAIN'):
                t.execute('test',SHA)
            self.assertEqual(proc.wait.call_count,2)
            self.assertEqual(close.call_count,2)

if __name__ == '__main__': unittest.main()
