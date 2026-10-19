#!/usr/bin/env python3
"""All tests are offline; no SWPC, Codex, device handle or hardware access."""
from __future__ import annotations

from pathlib import Path
import os
import stat
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_codex_device_permission_diagnostic as diag


class DiagnosticContracts(unittest.TestCase):
    def test_exact_glob_paths_match_failed_worker(self):
        self.assertEqual(diag.TARGET_RUN, 39190291831)
        self.assertEqual(diag.PATTERNS, (
            "/dev/mem", "/dev/uio*", "/dev/ttyUSB*", "/dev/ttyACM*",
            "/dev/hidraw*", "/dev/gpiochip*", "/dev/bus/usb/*/*",
        ))
        self.assertEqual(len(diag.PATTERNS), 7)

    def test_readable_alone_reproduces_original_no_go_without_open(self):
        fake_stat = types.SimpleNamespace(st_mode=stat.S_IFCHR | 0o640, st_uid=0, st_gid=20)
        seen = []
        def pretend_access(path, mode, *, effective_ids):
            seen.append((path,mode,effective_ids))
            return mode == os.R_OK
        with patch.object(diag.os, "stat", return_value=fake_stat), \
             patch.object(diag.pwd, "getpwuid", return_value=types.SimpleNamespace(pw_name="root")), \
             patch.object(diag.grp, "getgrgid", return_value=types.SimpleNamespace(gr_name="dialout")), \
             patch("builtins.open", side_effect=AssertionError("DEVICE_OPEN_FORBIDDEN")):
            node = diag.metadata("/dev/fake", access=pretend_access)
        self.assertTrue(node["readable"])
        self.assertFalse(node["writable"])
        self.assertTrue(node["triggers_original_no_go"])
        self.assertEqual(node["kind"], "char_device")
        self.assertEqual(node["mode"], "0640")
        self.assertEqual(seen, [("/dev/fake",os.R_OK,True),("/dev/fake",os.W_OK,True)])

    def test_writable_alone_reproduces_no_go(self):
        fake_stat = types.SimpleNamespace(st_mode=stat.S_IFCHR | 0o222, st_uid=1, st_gid=1)
        with patch.object(diag.os, "stat", return_value=fake_stat), \
             patch.object(diag.pwd,"getpwuid",return_value=types.SimpleNamespace(pw_name="owner")), \
             patch.object(diag.grp,"getgrgid",return_value=types.SimpleNamespace(gr_name="group")):
            node = diag.metadata("/dev/fake",access=lambda p,m,*,effective_ids:m==os.W_OK)
        self.assertTrue(node["writable"])
        self.assertFalse(node["readable"])
        self.assertTrue(node["triggers_original_no_go"])

    def test_effective_ids_missing_must_fail_closed(self):
        fake_stat=types.SimpleNamespace(st_mode=stat.S_IFCHR | 0o600,st_uid=0,st_gid=0)
        with patch.object(diag.os,"stat",return_value=fake_stat):
            with self.assertRaisesRegex(RuntimeError,"EFFECTIVE_ACCESS_UNAVAILABLE"):
                diag.metadata("/dev/fake",access=lambda path,mode:True)

    def test_collect_identifies_first_trigger_and_all_matches(self):
        original = diag.metadata
        def stub(path):
            return {
                "path":path,"kind":"char_device","mode":"0660",
                "uid":0,"gid":0,"user":"root","group":"root",
                "readable":path != "/dev/denied",
                "writable":False,
                "triggers_original_no_go":path != "/dev/denied",
            }
        with patch.object(diag,"metadata",side_effect=stub), \
             patch.object(diag.os,"uname",return_value=types.SimpleNamespace(nodename="SWPC")), \
             patch.object(diag.pwd,"getpwuid",return_value=types.SimpleNamespace(pw_name="plasma-codex")), \
             patch.object(diag.os,"getgroups",return_value=[]), \
             patch.object(diag.os,"getegid",return_value=10), \
             patch.object(diag.grp,"getgrgid",return_value=types.SimpleNamespace(gr_name="plasma-codex")):
            result=diag.collect(paths=["/dev/denied","/dev/first","/dev/second"],
                                acl=lambda p: {"status":"NOT_CHECKED"})
        self.assertEqual(result["status"],"NO_GO_REPRODUCED")
        self.assertEqual(result["first_trigger"],"/dev/first")
        self.assertEqual(len(result["nodes"]),3)
        self.assertNotIn("acl",result["nodes"][0])
        self.assertEqual(result["nodes"][1]["acl"]["status"],"NOT_CHECKED")
        self.assertEqual(result["notes"][0].startswith("No device files were opened."),True)

    def test_collect_does_not_claim_hardware_isolated_when_no_match(self):
        with patch.object(diag.os,"uname",return_value=types.SimpleNamespace(nodename="SWPC")), \
             patch.object(diag.pwd,"getpwuid",return_value=types.SimpleNamespace(pw_name="plasma-codex")), \
             patch.object(diag.os,"getgroups",return_value=[]), \
             patch.object(diag.os,"getegid",return_value=0), \
             patch.object(diag.grp,"getgrgid",return_value=types.SimpleNamespace(gr_name="none")):
            result=diag.collect(paths=[])
        self.assertEqual(result["status"],"NO_GO_NOT_REPRODUCED")
        self.assertIsNone(result["first_trigger"])
        self.assertIn("not proven",result["notes"][2])

    def test_too_many_nodes_is_no_go(self):
        with patch.object(diag.os,"uname",return_value=types.SimpleNamespace(nodename="SWPC")), \
             patch.object(diag.pwd,"getpwuid",return_value=types.SimpleNamespace(pw_name="plasma-codex")), \
             patch.object(diag.os,"getgroups",return_value=[]), \
             patch.object(diag.os,"getegid",return_value=0), \
             patch.object(diag.grp,"getgrgid",return_value=types.SimpleNamespace(gr_name="none")):
            result=diag.collect(paths=["/dev/not-checked"]*129)
        self.assertEqual(result["status"],"NO_GO_TOO_MANY_NODES")

    def test_acl_probe_is_only_getfacl_metadata(self):
        output=types.SimpleNamespace(returncode=0,stdout=b"user::rw-\ngroup::r--\nmask::r--\nother::---\n")
        with patch.object(diag.subprocess,"run",return_value=output) as called:
            acl=diag.acl_metadata("/dev/hidraw0")
        self.assertEqual(acl["status"],"OBSERVED")
        self.assertEqual(len(acl["entries"]),4)
        argv=called.call_args.args[0]
        self.assertEqual(argv,["getfacl","-cp","--","/dev/hidraw0"])
        self.assertNotIn("udevadm",repr(argv))
        self.assertNotIn("sudo",repr(argv))

    def test_identity_rejects_wrong_actor_runner_or_event(self):
        env={
            "GITHUB_EVENT_NAME":"workflow_dispatch",
            "GITHUB_REPOSITORY":"physicslu/plasma",
            "GITHUB_ACTOR":"physicslu",
            "GITHUB_REF":"refs/heads/main",
            "GITHUB_RUN_ATTEMPT":"1",
            "RUNNER_ENVIRONMENT":"self-hosted",
            "RUNNER_NAME":"SWPC-plasma-codex",
            "INPUT_ORIGINAL_RUN":"39190291831",
            "INPUT_CONFIRM_READ_ONLY":"true",
        }
        def check(changes):
            with patch.dict(diag.os.environ,{**env,**changes},clear=True), \
                 patch.object(diag.os,"uname",return_value=types.SimpleNamespace(nodename="SWPC")), \
                 patch.object(diag.os,"geteuid",return_value=1000), \
                 patch.object(diag.pwd,"getpwuid",return_value=types.SimpleNamespace(pw_name="plasma-codex")):
                diag.enforce_github_identity()
        check({})
        for bad in (
            {"GITHUB_ACTOR":"attacker"},
            {"GITHUB_EVENT_NAME":"push"},
            {"GITHUB_REF":"refs/heads/feature"},
            {"GITHUB_RUN_ATTEMPT":"2"},
            {"RUNNER_NAME":"SWPC-plasma-ci"},
            {"INPUT_ORIGINAL_RUN":"39190291830"},
            {"INPUT_CONFIRM_READ_ONLY":"false"},
        ):
            with self.subTest(bad=bad),self.assertRaises(RuntimeError):
                check(bad)

    def test_workflow_does_not_trigger_swpc_on_pr_or_merge(self):
        wf=(ROOT/".github/workflows/plasma-codex-device-permission-diagnostic.yml").read_text()
        self.assertIn("workflow_dispatch:",wf)
        self.assertIn('test "$CONFIRM_READ_ONLY" = true',wf)
        self.assertIn("github.actor == 'physicslu'",wf)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",wf)
        self.assertIn("needs: authorize",wf)
        self.assertIn("persist-credentials: false",wf)
        self.assertIn("scripts/tests/test_plasma_codex_device_permission_diagnostic.py",wf)
        self.assertIn("scripts/plasma_codex_device_permission_diagnostic.py --output",wf)
        self.assertNotIn("codex exec",wf)
        self.assertNotIn("codex --",wf)
        self.assertNotIn("sudo ",wf)
        self.assertNotIn("udevadm",wf)
        self.assertNotIn("OPENAI_API_KEY",wf)
        self.assertNotIn("contents: write",wf)
        self.assertNotIn("issue_comment:",wf)
        self.assertEqual(wf.count("runs-on: ubuntu-24.04"),2)
        self.assertEqual(wf.count("runs-on: [self-hosted, linux, x64, plasma-codex]"),1)


    def test_all_github_actions_expressions_are_evaluated_not_escaped(self):
        wf = (ROOT/".github/workflows/plasma-codex-device-permission-diagnostic.yml").read_text()
        expression = "$" + "{{"
        self.assertEqual(wf.count(expression), 10)
        self.assertNotIn(chr(92) + expression, wf)
        # Stronger than mere presence: verify all ten expressions and their sites.
        expected = (
            "    if: " + expression + " github.event_name == 'pull_request' || github.event_name == 'push' }}",
            "    if: " + expression + " github.event_name == 'workflow_dispatch' }}",
            "          REQUESTED_ORIGINAL_RUN: " + expression + " inputs.original_run }}",
            "          CONFIRM_READ_ONLY: " + expression + " inputs.confirm_read_only }}",
            "    if: " + expression + " needs.authorize.result == 'success' }}",
            "      INPUT_ORIGINAL_RUN: " + expression + " inputs.original_run }}",
            "      INPUT_CONFIRM_READ_ONLY: " + expression + " inputs.confirm_read_only }}",
            "          ref: " + expression + " github.sha }}",
            "          name: plasma-codex-device-permission-39190291831-" + expression + " github.run_id }}",
            "          path: " + expression + " runner.temp }}/plasma-codex-device-permission-39190291831.json",
        )
        self.assertEqual(len(set(expected)), 10)
        for line in expected:
            with self.subTest(line=line):
                self.assertEqual(wf.splitlines().count(line), 1)

    def test_workflow_dispatch_never_runs_offline_contract(self):
        wf=(ROOT/".github/workflows/plasma-codex-device-permission-diagnostic.yml").read_text()
        section=wf.split("\n  contract:\n",1)[1].split("\n  authorize:\n",1)[0]
        contract_if="    if: " + "$" + "{{ github.event_name == 'pull_request' || github.event_name == 'push' }}"
        self.assertEqual([s for s in section.splitlines() if s.strip().startswith("if:")],[contract_if])
        for event,expected in (
            ("pull_request",True),("push",True),
            ("workflow_dispatch",False),("issue_comment",False),
            ("workflow_run",False),
        ):
            with self.subTest(event=event):
                self.assertIs(event in ("pull_request","push"),expected)
        self.assertNotIn("runs-on: [self-hosted",section)

    def test_hosted_authorize_has_exact_manual_input_and_owner_gate(self):
        wf=(ROOT/".github/workflows/plasma-codex-device-permission-diagnostic.yml").read_text()
        section=wf.split("\n  authorize:\n",1)[1].split("\n  inspect:\n",1)[0]
        hosted_if="    if: " + "$" + "{{ github.event_name == 'workflow_dispatch' }}"
        self.assertEqual([line for line in section.splitlines() if line.strip().startswith("if:")],[hosted_if])
        # Both empty/unchecked confirmation and a non-owner dispatch now
        # produce a hosted FAIL. The SWPC job still needs hosted SUCCESS.
        self.assertIn("REQUESTED_ORIGINAL_RUN: " + "$" + "{{ inputs.original_run }}",section)
        self.assertIn("CONFIRM_READ_ONLY: " + "$" + "{{ inputs.confirm_read_only }}",section)
        for line in (
            'test "$REQUESTED_ORIGINAL_RUN" = 39190291831',
            'test "$CONFIRM_READ_ONLY" = true',
            'test "$GITHUB_EVENT_NAME" = workflow_dispatch',
            'test "$GITHUB_ACTOR" = physicslu',
            'test "$GITHUB_REPOSITORY" = physicslu/plasma',
            'test "$GITHUB_REF" = refs/heads/main',
            'test "$GITHUB_RUN_ATTEMPT" = 1',
        ):
            with self.subTest(line=line):
                self.assertIn(line,section)
        self.assertIn("runs-on: ubuntu-24.04", section)
        self.assertNotIn("self-hosted",section)

    def test_authorize_gate_rejects_wrong_dispatch_metadata_offline(self):
        expected=dict(event="workflow_dispatch",repo="physicslu/plasma",
                      actor="physicslu",ref="refs/heads/main",
                      attempt=1,original="39190291831",confirmed=True)
        def approved(c):
            return (c["event"]=="workflow_dispatch"
                    and c["repo"]=="physicslu/plasma"
                    and c["actor"]=="physicslu"
                    and c["ref"]=="refs/heads/main"
                    and c["attempt"]==1
                    and c["original"]=="39190291831"
                    and c["confirmed"] is True)
        self.assertTrue(approved(expected))
        for key,bad in (
            ("event","push"),("event","pull_request"),
            ("repo","another/plasma"),("actor","attacker"),
            ("ref","refs/heads/test"),("attempt",2),
            ("original","39190291830"),("confirmed",False),
            ("confirmed","true"),
        ):
            with self.subTest(key=key,bad=bad):
                self.assertFalse(approved({**expected,key:bad}))
        # The predicate is a model: the test above pins the exact YAML clauses.

    def test_inspect_is_only_after_hosted_authorization_and_inputs_are_bound(self):
        wf=(ROOT/".github/workflows/plasma-codex-device-permission-diagnostic.yml").read_text()
        section=wf.split("\n  inspect:\n",1)[1]
        prefix="$"+"{{"
        self.assertIn("    needs: authorize\n    if: "+prefix+" needs.authorize.result == 'success' }}",section)
        self.assertIn("      INPUT_ORIGINAL_RUN: "+prefix+" inputs.original_run }}",section)
        self.assertIn("      INPUT_CONFIRM_READ_ONLY: "+prefix+" inputs.confirm_read_only }}",section)
        self.assertIn("          ref: "+prefix+" github.sha }}",section)
        self.assertIn('test "$INPUT_ORIGINAL_RUN" = 39190291831',section)
        self.assertIn('test "$INPUT_CONFIRM_READ_ONLY" = true',section)
        self.assertIn('test "$RUNNER_NAME" = SWPC-plasma-codex',section)
        self.assertIn("        with:\n          ref: "+prefix+" github.sha }}\n          persist-credentials: false",section)
        self.assertIn("path: "+prefix+" runner.temp }}/plasma-codex-device-permission-39190291831.json",section)
        self.assertNotIn("codex exec",wf)
        self.assertNotIn("contents: write",wf)


if __name__=="__main__":
    unittest.main(verbosity=2)
