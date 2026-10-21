#!/usr/bin/env python3
"""SWPC bridge: offline-only negative contract checks, no SSH or device."""
from __future__ import annotations

from contextlib import ExitStack
import errno
import json
import os
import subprocess

from importlib.machinery import SourceFileLoader
from importlib.util import spec_from_loader, module_from_spec
from pathlib import Path
from types import SimpleNamespace
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "scripts/swpc/z2-path2-f1b-bridge"
loader = SourceFileLoader("path2_swpc_fixed_bridge_test", str(FILE))
spec = spec_from_loader(loader.name, loader)
bridge = module_from_spec(spec)
loader.exec_module(bridge)


class BridgeContracts(unittest.TestCase):
    def test_stage_allowlist_blocks_any_remote_call(self):
        for stage in ("full", "build", "reset", "download;id", "", "--help"):
            with self.subTest(stage=stage), patch.object(
                    bridge, "approved_sha") as approve, patch.object(
                    bridge, "enrollment") as creds:
                with self.assertRaisesRegex(bridge.Blocked,
                                            "STAGE_NOT_ALLOWLISTED"):
                    bridge.execute(stage, "a" * 40)
                approve.assert_not_called()
                creds.assert_not_called()

    def test_exact_reviewed_sha_checked_before_reading_secrets(self):
        with patch.object(bridge, "approved_sha",
                          side_effect=bridge.Blocked("SOURCE_NOT_APPROVED")):
            with patch.object(bridge, "enrollment") as creds:
                with self.assertRaisesRegex(bridge.Blocked,
                                            "SOURCE_NOT_APPROVED"):
                    bridge.execute("download", "a" * 40)
                creds.assert_not_called()

    def test_root_owned_0644_approval_readable_by_unprivileged_worker(self):
        # A hosted non-root test cannot chown(2). Simulate only st_uid=0,
        # while reading a real 0644 file as the current unprivileged user.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "approved"
            p.write_text("a" * 40 + "\n")
            p.chmod(0o644)
            actual_lstat = Path.lstat

            def root_owned_lstat(path):
                observed = actual_lstat(path)
                if path == p:
                    return SimpleNamespace(
                        st_mode=observed.st_mode, st_uid=0,
                        st_size=observed.st_size)
                return observed

            with patch.object(Path, "lstat", root_owned_lstat), patch.object(
                    bridge, "APPROVAL", p):
                bridge.approved_sha("a" * 40)
                with self.assertRaisesRegex(
                        bridge.Blocked, "SWPC_APPROVED_SOURCE_SHA_MISMATCH"):
                    bridge.approved_sha("b" * 40)

    def test_approval_denies_bad_ownership_type_mode_and_size(self):
        rejected = (
            ("root_only_unreadable", stat.S_IFREG | 0o600, 0, 41),
            ("group_writable", stat.S_IFREG | 0o664, 0, 41),
            ("world_writable", stat.S_IFREG | 0o666, 0, 41),
            ("worker_owned", stat.S_IFREG | 0o644, 1000, 41),
            ("symlink", stat.S_IFLNK | 0o644, 0, 41),
            ("oversized", stat.S_IFREG | 0o644, 0, 65),
        )
        with patch.object(bridge, "APPROVAL") as approved:
            for name, mode, uid, size in rejected:
                with self.subTest(name=name):
                    approved.lstat.return_value = SimpleNamespace(
                        st_mode=mode, st_uid=uid, st_size=size)
                    approved.read_text.reset_mock()
                    with self.assertRaisesRegex(
                            bridge.Blocked, "SWPC_APPROVED_SOURCE_NOT_INSTALLED"):
                        bridge.approved_sha("a" * 40)
                    approved.read_text.assert_not_called()
            with self.assertRaisesRegex(bridge.Blocked, "SOURCE_SHA_INVALID"):
                bridge.approved_sha("not-a-sha")

    def test_transport_has_only_fixed_target_and_root_stage_command(self):
        s = FILE.read_text()
        self.assertIn('STAGES = ("download", "test", "restore")', s)
        self.assertIn('ROOT_ENTRY = "/usr/local/libexec/plasma/z2-path2-f1b-root-entry"', s)
        self.assertIn('"StrictHostKeyChecking=yes"', s)
        self.assertIn('"SOURCE_SHA_INVALID"', s)
        self.assertNotIn("shell=True", s)
        self.assertNotIn("eval(", s)
        self.assertIn("REMOTE_EXIT_OR_PRIVILEGE_FAILED", s)


    @staticmethod
    def _receipt(result="LOADED_AND_HELD", stage="download"):
        return (bridge.MARK + json.dumps({
            "stage": stage, "result": result,
            "boot_id": "fe723a58-621e-444a-9171-0c81d35a3b0a",
        }) + "\n").encode()

    def _fake_ssh(self, chunks, *, exit_code=0, eio=False):
        """Drive actual Bridge parsing without sockets, SSH, sudo or hardware.

        poll() reports that SSH has exited *before* its buffered PTY data is
        drained, making the old read-loop race deterministic.
        """
        class CompletedSSH:
            pid = 515151
            def poll(self):
                return exit_code
            def wait(self, timeout=None):
                return exit_code

        stream = list(chunks)
        writes = []

        def read(_fd, _count):
            if stream:
                return stream.pop(0)
            if eio:
                raise OSError(errno.EIO, "closed PTY")
            return b""

        def write(_fd, data):
            writes.append(data)
            return len(data)

        with ExitStack() as stack:
            def replace(obj, attr, **kwargs):
                return stack.enter_context(patch.object(obj, attr, **kwargs))

            replace(bridge, "approved_sha")
            replace(bridge, "enrollment",
                    return_value=("z2.example", "fake-ssh", "fake-sudo"))
            popen = replace(bridge.subprocess, "Popen",
                            return_value=CompletedSSH())
            replace(bridge.os, "openpty", return_value=(910, 911))
            replace(bridge.os, "read", side_effect=read)
            replace(bridge.os, "write", side_effect=write)
            replace(bridge.os, "close")
            replace(bridge.select, "select",
                    return_value=([910], [], []))
            replace(bridge.tty, "setraw")
            try:
                outcome = bridge.execute("download", "a" * 40)
            finally:
                args = popen.call_args.args[0]
                self.assertEqual(args[0], "/usr/bin/ssh")
                self.assertIn("StrictHostKeyChecking=yes", args)
                self.assertIn("xilinx@z2.example", args)
        return outcome, writes

    def test_prompt_and_receipt_same_line_after_ssh_exit(self):
        # Exact failure shape: sudo -p omits newline; the receipt follows
        # directly after the sudo prompt, potentially in later PTY reads.
        outcome, writes = self._fake_ssh([
            b"xilinx@z2.example's password:",
            bridge.PROMPT.encode(),
            self._receipt(),
        ], eio=True)
        self.assertEqual(outcome["result"], "LOADED_AND_HELD")
        self.assertEqual(outcome["stage"], "download")
        self.assertTrue(outcome["real_z2"])
        self.assertEqual(writes, [b"fake-ssh\n", b"fake-sudo\n"])

    def test_root_receipt_accepted_without_cached_sudo_prompt(self):
        # A cached or NOPASSWD sudo may legitimately omit the password
        # prompt; success still requires SSH authentication and exact receipt.
        outcome, writes = self._fake_ssh([
            b"xilinx@z2.example's password:",
            b"\n" + self._receipt(),
        ])
        self.assertEqual(outcome["result"], "LOADED_AND_HELD")
        self.assertEqual(writes, [b"fake-ssh\n"])

    def test_root_receipt_with_separate_sudo_prompt_line(self):
        outcome, writes = self._fake_ssh([
            b"password:", bridge.PROMPT.encode() + b"\n",
            self._receipt(),
        ])
        self.assertEqual(outcome["stage"], "download")
        self.assertEqual(len(writes), 1)  # sudo prompt did not end tail

    def test_reject_duplicate_wrong_and_missing_root_receipts(self):
        receipt = self._receipt()
        for payload in (
            b"\n" + receipt + receipt,
            b"\n" + self._receipt(result="UNVERIFIED"),
            b"\n" + self._receipt(stage="test"),
            b"\n" + bridge.MARK.encode() + b"not-json\n",
            b"\nno root receipt\n",
        ):
            with self.subTest(payload=payload[:60]), self.assertRaises(
                    (bridge.Blocked, ValueError, json.JSONDecodeError)):
                self._fake_ssh([
                    b"xilinx@z2.example's password:", payload,
                ])

    def test_reject_nonzero_ssh_exit_despite_success_marker(self):
        with self.assertRaisesRegex(
                bridge.Blocked, "REMOTE_EXIT_OR_PRIVILEGE_FAILED"):
            self._fake_ssh([
                b"xilinx@z2.example's password:",
                b"\n" + self._receipt(),
            ], exit_code=1)

    def test_reject_missing_ssh_password_prompt_even_with_receipt(self):
        with self.assertRaisesRegex(
                bridge.Blocked, "REMOTE_EXIT_OR_PRIVILEGE_FAILED"):
            self._fake_ssh([b"\n" + self._receipt()])

    def test_reject_unexpected_pty_error(self):
        with self.assertRaises(OSError) as raised:
            class Done:
                pid = 4141
                def poll(self):
                    return 0
                def wait(self, timeout=None):
                    return 0

            with ExitStack() as stack:
                def patcher(obj, attr, **kw):
                    return stack.enter_context(patch.object(obj, attr, **kw))
                patcher(bridge, "approved_sha")
                patcher(bridge, "enrollment",
                        return_value=("z2.example", "fake-ssh", "fake-sudo"))
                patcher(bridge.subprocess, "Popen", return_value=Done())
                patcher(bridge.os, "openpty", return_value=(910, 911))
                patcher(bridge.os, "close")
                patcher(bridge.select, "select",
                        return_value=([910], [], []))
                patcher(bridge.tty, "setraw")
                patcher(bridge.os, "read",
                        side_effect=OSError(errno.EPERM, "unexpected"))
                bridge.execute("download", "a" * 40)
        self.assertEqual(raised.exception.errno, errno.EPERM)



class MonitorDispatcherBridgeIntegration(unittest.TestCase):
    """Real monitor subprocess -> Dispatcher -> runtime -> mocked Bridge SSH.

    GitHub-hosted, synthetic data only. Never opens SSH, sudo or a device.
    The fixed Bridge entry is mocked after the route is checked.
    """

    def test_synthetic_success_and_fail_closed_through_monitor(self):
        import plasma_engineering_monitor as monitor

        child = r'''
import errno
import json
import os
import subprocess
import sys
from contextlib import ExitStack
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest.mock import patch

root = Path(os.environ["PLASMA_INTEGRATION_ROOT"])
sys.path.insert(0, str(root / "scripts"))
import plasma_development_dispatch as dispatcher
import plasma_path2_runtime_integration as runtime

path = root / "scripts/swpc/z2-path2-f1b-bridge"
loader = SourceFileLoader("offline_path2_integrated_bridge", str(path))
spec = spec_from_loader(loader.name, loader)
bridge = module_from_spec(spec)
loader.exec_module(bridge)

approval = {
    "execution_path": "path2-cli",
    "execution_capability": "path2-stage-contract",
    "task_id": "z2-path2-download",
    "pinned_sha": "a" * 40,
    "trusted_sha": "a" * 40,
    "pr_number": 0,
    "auto_download_after_build_success": False,
    "auto_test_after_download_success": False,
}
task = {
    "execution_path": "path2-cli",
    "capability": "path2-stage-contract",
    "project": "pl/projects/z2-fixed-unified-site1",
    "stage": "download",
}
case = os.environ["PLASMA_INTEGRATION_CASE"]
output = Path(os.environ["PLASMA_INTEGRATION_OUTPUT"])
state = {
    "stage": "download",
    "boot_id": "synthetic-boot-only",
    "result": "LOADED_AND_HELD",
}
payload = (bridge.MARK + json.dumps(state) + "\n").encode()
chunks = [
    b"z2.example's password:",
    bridge.PROMPT.encode(),
    payload,
]

class OfflineSSH:
    pid = 77777777
    def poll(self):
        return 1 if case == "failure" else 0
    def wait(self, timeout=None):
        return self.poll()

def offline_read(_fd, _count):
    if chunks:
        return chunks.pop(0)
    raise OSError(errno.EIO, "synthetic PTY EOF")

def fake_bridge_executor(command, **kwargs):
    assert command == [
        str(runtime.ROOT_STAGE_BRIDGE), "download", "a" * 40,
    ], "UNEXPECTED_BRIDGE_COMMAND"
    assert kwargs["check"] is False
    assert kwargs["env"] == {"PATH": "/usr/bin:/bin"}
    with ExitStack() as stack:
        def p(obj, attr, **patch_kw):
            return stack.enter_context(patch.object(obj, attr, **patch_kw))
        p(bridge, "approved_sha")
        p(bridge, "enrollment",
          return_value=("z2.example", "fake-ssh", "fake-sudo"))
        ssh = p(bridge.subprocess, "Popen", return_value=OfflineSSH())
        p(bridge.os, "openpty", return_value=(910, 911))
        p(bridge.os, "read", side_effect=offline_read)
        p(bridge.os, "write", side_effect=lambda _fd, data: len(data))
        p(bridge.os, "close")
        p(bridge.select, "select", return_value=([910], [], []))
        p(bridge.tty, "setraw")
        try:
            result = bridge.execute("download", "a" * 40)
            assert ssh.call_args.args[0][0] == "/usr/bin/ssh"
            return subprocess.CompletedProcess(command, 0,
                json.dumps(result).encode(), b"")
        except bridge.Blocked:
            return subprocess.CompletedProcess(command, 2, b"",
                b"PATH2_SWPC_BRIDGE_BLOCKED_OR_UNKNOWN")

original = runtime.registered_hardware_stage
def execute_mocked(task_arg, approval_arg):
    return original(task_arg, approval_arg, executor=fake_bridge_executor)

with patch.object(runtime, "_trusted_root_bridge"), patch.object(
        runtime, "registered_hardware_stage", side_effect=execute_mocked):
    try:
        receipt = dispatcher.run_task(task, approval=approval, workspace=root)
        output.write_text(json.dumps(receipt), encoding="utf-8")
        print(json.dumps(receipt), flush=True)
    except Exception as exc:
        reason = dispatcher.safe_error_reason(exc)
        output.write_text(json.dumps({"reason": reason}), encoding="utf-8")
        sys.exit(2)
'''
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            monitor_dir = temp / "monitor"
            monitor_dir.mkdir()
            evidence = temp / "evidence.json"
            for case, expected_rc in (("success", 0), ("failure", 2)):
                with self.subTest(case=case), patch.dict(os.environ, {
                    "PLASMA_INTEGRATION_ROOT": str(ROOT),
                    "PLASMA_INTEGRATION_CASE": case,
                    "PLASMA_INTEGRATION_OUTPUT": str(evidence),
                    "GITHUB_RUN_ID": "99900001",
                    "PLASMA_MONITOR_TASK": "z2-path2-download",
                }):
                    rc = monitor.run_job(
                        "path2", [sys.executable, "-c", child],
                        directory=monitor_dir)
                self.assertEqual(rc, expected_rc)
                record = json.loads(evidence.read_text())
                state = json.loads((monitor_dir / "path2.json").read_text())
                self.assertEqual(state["exit_code"], expected_rc)
                self.assertEqual(state["status"], "IDLE")
                if case == "success":
                    self.assertEqual(record["result"], "LOADED_AND_HELD")
                    self.assertTrue(record["real_z2"])  # synthetic fixture
                    self.assertFalse(record["auto_next_stage"])
                    self.assertEqual(state["last_result"], "PASS")
                else:
                    self.assertEqual(record["reason"],
                                     "PATH2_BRIDGE_STAGE_FAILED_OR_UNKNOWN")
                    self.assertEqual(state["last_result"], "FAIL")


if __name__ == "__main__":
    unittest.main()
