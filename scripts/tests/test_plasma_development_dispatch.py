#!/usr/bin/env python3
"""Host-only tests for reusable Development Mode issue-comment dispatch."""
from __future__ import annotations

import copy
import errno
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import plasma_development_dispatch as dev

WORKFLOW=ROOT/".github/workflows/plasma-engineering-runtime-dispatch.yml"
REGISTRY=ROOT/"specs/engineering-dispatch/development-tasks-v1.json"


class DevelopmentPath2Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=json.loads(REGISTRY.read_text())
        cls.task=dev.task_by_id(cls.registry,"nine-nine-path2")

    def event(self):
        return {
            "action":"created","issue":{"number":981},
            "comment":{"id":31921,"user":{"login":"physicslu"},
                       "body":"/plasma-dispatch run nine-nine-path2 981"},
            "sender":{"login":"physicslu"},
            "repository":{"full_name":"physicslu/plasma"},
        }

    def context(self):
        return {
            "GITHUB_EVENT_NAME":"issue_comment",
            "GITHUB_ACTOR":"physicslu",
            "GITHUB_REPOSITORY":"physicslu/plasma",
            "GITHUB_REF":"refs/heads/main",
            "GITHUB_SHA":"a"*40,
        }

    def test_owner_issue_comment_authorizes_one_pinned_task(self):
        plan=dev.authorize(self.event(),self.context(),self.registry)
        self.assertEqual(plan["task_id"],"nine-nine-path2")
        self.assertEqual(plan["execution_path"],"path2-cli")
        self.assertEqual(plan["pinned_sha"],"a"*40)
        self.assertEqual(plan["status"],"AUTHORIZED_DEV_TASK")

    def test_real_reference_runs_as_bounded_process_in_hosted_ci(self):
        # This tests the registry and output contract, NOT SWPC execution.
        receipt=dev.run_task(self.task)
        self.assertEqual(receipt["status"],"PASS")
        self.assertEqual(receipt["rows"],81)
        self.assertEqual(receipt["exit_code"],0)
        self.assertEqual(receipt["stdout_bytes"],576)
        self.assertEqual(receipt["first_row"],"1,1,1")
        self.assertEqual(receipt["last_row"],"9,9,81")
        self.assertEqual(receipt["stdout_sha256"],
                         "142d9b788a5902e98048690e75e9d91ac8e22334c592f7e2e5a93e8bc878bc5d")

    def test_untrusted_event_and_newline_command_denied(self):
        event=self.event()
        ctx=self.context()
        for key,bad in (
            ("GITHUB_EVENT_NAME","pull_request"),
            ("GITHUB_ACTOR","attacker"),
            ("GITHUB_REPOSITORY","fork/plasma"),
            ("GITHUB_REF","refs/heads/dev"),
            ("GITHUB_SHA","main"),
        ):
            with self.subTest(key=key):
                tampered=dict(ctx)
                tampered[key]=bad
                with self.assertRaises(dev.Denied):
                    dev.authorize(event,tampered,self.registry)
        changes=[
            ("action","edited"),("issue.number",12),
            ("issue.pull_request",{"url":"example.invalid"}),
            ("sender.login","attacker"),("comment.user.login","attacker"),
            ("repository.full_name","fork/plasma"),
            ("comment.body","/plasma-dispatch run nine-nine-path2 981\n"),
            ("comment.body","/plasma-dispatch run nine-nine-path2 981; echo BAD"),
            ("comment.body","/plasma-dispatch run unknown-task 981"),
            ("comment.id",True),
        ]
        for key,bad in changes:
            with self.subTest(key=key):
                tampered=copy.deepcopy(event)
                obj=tampered
                path=key.split(".")
                for p in path[:-1]:
                    obj=obj[p]
                obj[path[-1]]=bad
                with self.assertRaises(dev.Denied):
                    dev.authorize(tampered,ctx,self.registry)

    def test_registry_refuses_arbitrary_commands_and_paths(self):
        for path in ("/tmp/run.py","scripts/experiments/../unsafe.py",
                     "scripts/experiments/hello.sh",
                     "scripts/experiments/a.py; sudo",
                     "scripts/plasma_engineering_runtime_v1.py"):
            task=copy.deepcopy(self.registry)
            task["tasks"]["nine-nine-path2"]["script"]=path
            with self.subTest(path=path),self.assertRaises(dev.Denied):
                dev.task_by_id(task,"nine-nine-path2")
        for args in (["-c"],["a;id"],["../passwd"],["foo bar"],[""]):
            task=copy.deepcopy(self.registry)
            task["tasks"]["nine-nine-path2"]["argv"]=args
            with self.subTest(args=args),self.assertRaises(dev.Denied):
                dev.task_by_id(task,"nine-nine-path2")
        task=copy.deepcopy(self.registry)
        task["tasks"]["nine-nine-path2"]["execution_path"]="path3-codex"
        with self.assertRaises(dev.Denied):
            dev.task_by_id(task,"nine-nine-path2")
        task=copy.deepcopy(self.registry)
        task["tasks"]["nine-nine-path2"]["expected_stdout_sha256"]="0"*64
        with self.assertRaisesRegex(dev.Denied,"OUTPUT_SHA256_MISMATCH"):
            dev.run_task(dev.task_by_id(task,"nine-nine-path2"))

    def test_worker_checks_identity_before_script_execution(self):
        # Never touches any device or starts Codex in this test.
        with tempfile.TemporaryDirectory() as tmp:
            event_path=Path(tmp)/"event.json"
            event_path.write_text(json.dumps(self.event()))
            env=self.context() | {
                "RUNNER_NAME":"untrusted",
                "RUNNER_ENVIRONMENT":"self-hosted",
                "GITHUB_RUN_ID":"123",
            }
            args=["execute","--event",str(event_path),
                  "--pinned-sha","a"*40]
            with patch.object(sys,"argv",["dispatch.py",*args]),patch.dict(os.environ,env):
                self.assertEqual(dev.main(),2)

    def test_one_existing_shared_runner_and_no_per_task_workflow(self):
        wf=WORKFLOW.read_text()
        self.assertIn("issue_comment:",wf)
        self.assertIn("github.actor == 'physicslu'",wf)
        self.assertIn("github.event.issue.number == 981",wf)
        self.assertIn("development-authorize:",wf)
        self.assertIn("development-execute:",wf)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",wf)
        self.assertIn("needs: development-authorize",wf)
        self.assertIn("persist-credentials: false",wf)
        self.assertIn("github.event_name == 'issue_comment'",wf)
        self.assertNotIn("run: sudo ",wf)
        self.assertNotIn("plasma-path2-nine-nine.yml",wf)
        self.assertEqual(self.registry["mode"],"development")


class DevelopmentBranchDispatchContracts(DevelopmentPath2Contracts):
    """Hosted-only positive and adversarial PR branch admission contracts."""

    def branch_event(self, task="nine-nine-path2", pr=1100, sha="b"*40):
        e=self.event()
        e["comment"]["body"]=(
            f"/plasma-dispatch run {task} --pr {pr} --sha {sha} 981"
        )
        return e

    def valid_pr(self, pr=1100, sha="b"*40):
        return {
            "number":pr, "state":"open", "merged_at":None,
            "user":{"login":"physicslu"},
            "base":{"ref":"main","repo":{"full_name":"physicslu/plasma"}},
            "head":{"ref":"feature/example-software",
                    "sha":sha,
                    "repo":{"full_name":"physicslu/plasma"}},
        }

    def test_valid_pr_head_is_routed_without_merging_to_main(self):
        event=self.branch_event()
        request=dev.request(event,self.context())
        self.assertEqual(request["pr_number"],1100)
        self.assertEqual(request["source_sha"],"b"*40)
        self.assertEqual(request["trusted_sha"],"a"*40)
        plan=dev.authorize(event,self.context(),self.registry,
                           pr_info=self.valid_pr())
        self.assertEqual(plan["status"],"AUTHORIZED_DEV_TASK")
        self.assertEqual(plan["execution_path"],"path2-cli")
        self.assertEqual(plan["pinned_sha"],"b"*40)
        self.assertEqual(plan["trusted_sha"],"a"*40)
        event=self.branch_event(task="nine-nine-path3")
        plan=dev.authorize(event,self.context(),self.registry,
                           pr_info=self.valid_pr())
        self.assertEqual(plan["execution_path"],"path3-codex")

    def test_branch_rejects_bad_pr_head_owner_repo_base_state(self):
        event=self.branch_event()
        for label, mutate in (
            ("wrong head",lambda p:p["head"].update(sha="c"*40)),
            ("fork head",lambda p:p["head"]["repo"].update(full_name="other/plasma")),
            ("wrong base",lambda p:p["base"].update(ref="release")),
            ("fork base",lambda p:p["base"]["repo"].update(full_name="other/plasma")),
            ("not owner",lambda p:p["user"].update(login="other")),
            ("bad branch",lambda p:p["head"].update(ref="main")),
            ("not open",lambda p:p.update(state="closed")),
            ("merged",lambda p:p.update(merged_at="2026-10-19")),
            ("wrong number",lambda p:p.update(number=99)),
        ):
            pr=self.valid_pr()
            mutate(pr)
            with self.subTest(label=label),self.assertRaises(dev.Denied):
                dev.authorize(event,self.context(),self.registry,pr_info=pr)
        with self.assertRaisesRegex(dev.Denied,"PR_METADATA_DENIED"):
            dev.authorize(event,self.context(),self.registry)

    def test_branch_rejects_command_injection_non_exact_sha_and_untrusted_actor(self):
        for command in (
            "/plasma-dispatch run nine-nine-path2 --pr 1100 --sha abc 981",
            "/plasma-dispatch run nine-nine-path2 --pr 01100 --sha "+"b"*40+" 981",
            "/plasma-dispatch run nine-nine-path2 --pr 1100 --sha "+"b"*40+" 981\n",
            "/plasma-dispatch run nine-nine-path2 --pr 1100 --sha "+"b"*40+" 981;id",
            "/plasma-dispatch run nine-nine-path2 --pr 1100 --sha "+"b"*40+" 981 && true",
            "/plasma-dispatch run nine-nine-path2 --pr 1100 --sha "+"b"*40+" 982",
        ):
            event=self.event()
            event["comment"]["body"]=command
            with self.subTest(command=command),self.assertRaises(dev.Denied):
                dev.request(event,self.context())
        for field in ("GITHUB_ACTOR","GITHUB_REF","GITHUB_REPOSITORY"):
            ctx=self.context()
            ctx[field]="untrusted"
            with self.subTest(field=field),self.assertRaises(dev.Denied):
                dev.request(self.branch_event(),ctx)

    def test_generic_cpu_only_route_has_no_test_specific_task_allowlist(self):
        wf = WORKFLOW.read_text()
        guard = wf.split("  development-execute:", 1)[1].split(
            "  development-codex:", 1
        )[0].split("    if: >-", 1)[1].split("    runs-on:", 1)[0]
        self.assertIn("needs.development-authorize.result == 'success'", guard)
        self.assertIn("outputs.execution_path == 'path2-cli'", guard)
        self.assertIn('"cpu-only"', guard)
        self.assertNotIn("needs.development-claim.result == 'skipped'", guard)
        self.assertNotIn("'nine-nine-path2'", guard)
        self.assertNotIn("'auto4-premerge-path2'", guard)
        self.assertNotIn("'1055'", guard)
        self.assertNotIn("'b19fd8f6c9806e99678d8c5c71fc0f8634379ac3'", guard)
        self.assertIn("execution_capability: ${{ steps.approve.outputs.execution_capability }}", wf)
        self.assertIn("--execution-capability \"$EXECUTION_CAPABILITY\"", wf)

    def test_a2_hardware_claim_route_is_still_restricted(self):
        wf = WORKFLOW.read_text()
        guard = wf.split("  development-execute:", 1)[1].split(
            "  development-codex:", 1
        )[0].split("    if: >-", 1)[1].split("    runs-on:", 1)[0]
        self.assertIn("outputs.execution_capability == 'z2-cpu-only'", guard)
        self.assertIn("outputs.task_id == 'hil-a2-cpu-only'", guard)
        self.assertIn("needs.development-claim.result == 'success'", guard)
        self.assertIn("needs.development-claim.outputs.claim_ref ==", guard)
        self.assertIn("needs.development-claim.outputs.work_order_sha256 ==", guard)
        self.assertIn("github.run_attempt == 1", guard)
        self.assertIn("github.event.issue.number == 981", wf)
        self.assertIn("github.actor == 'physicslu'", wf)
        self.assertIn("needs.development-authorize.outputs.task_id == 'hil-a2-cpu-only'", wf)

    def test_task_names_do_not_set_cpu_capability_and_hardware_is_denied(self):
        base = copy.deepcopy(self.registry["tasks"]["nine-nine-path2"])
        for name in ("my-project-smoke", "eeprom-algorithm-unit", "maths-only"):
            reg = {
                "schema_version": dev.VERSION,
                "mode": "development",
                "tasks": {name: dict(base)},
            }
            self.assertEqual(dev.task_by_id(reg, name)["capability"], "cpu-only")
            self.assertEqual(
                dev.authorize(
                    self.branch_event(task=name), self.context(),
                    reg, pr_info=self.valid_pr()
                )["execution_capability"], "cpu-only"
            )
        for cap in ("z2-cpu-only", "usb", "hardware", "network", ""):
            bad = dict(base, capability=cap)
            with self.subTest(cap=cap), self.assertRaisesRegex(
                dev.Denied, "DEV_CAPABILITY_DENIED"
            ):
                dev.task_by_id({
                    "schema_version": dev.VERSION,
                    "mode": "development", "tasks": {"cpu-generic": bad},
                }, "cpu-generic")
        for field, bad in (("verification", "nine-nine-table-v1"),
                           ("verification", "unchecked")):
            bad_task = dict(base, **{field: bad})
            with self.subTest(verification=bad), self.assertRaisesRegex(
                dev.Denied, "TASK_VERIFICATION_DENIED"
            ):
                dev.task_by_id({
                    "schema_version": dev.VERSION,
                    "mode": "development", "tasks": {"cpu-generic": bad_task},
                }, "cpu-generic")
        legacy = dict(base)
        del legacy["capability"]
        self.assertIs(dev.task_by_id({
            "schema_version": dev.VERSION,
            "mode": "development", "tasks": {"legacy-cpu": legacy},
        }, "legacy-cpu"), legacy)

    def test_candidate_dispatcher_premerge_task_is_exact_cpu_only_sandbox(self):
        task=dev.task_by_id(self.registry,"candidate-dispatcher-premerge-sandbox")
        self.assertEqual(task["execution_path"],"path2-cli")
        self.assertEqual(task["capability"],"cpu-only")
        self.assertEqual(task["argv"],[])
        self.assertEqual(
            task["script"],
            "scripts/experiments/plasma_candidate_dispatcher_branch_smoke.py")
        source=(ROOT/task["script"]).read_text()
        self.assertIn('ROOT = Path("/work")',source)
        self.assertIn("WORKTREE_MUST_BE_READ_ONLY",source)
        self.assertIn("HOST_SYSFS_MOUNT_DENIED",source)
        self.assertIn("HOST_UDEV_MOUNT_DENIED",source)
        self.assertEqual(
            task["expected_stdout_sha256"],
            hashlib.sha256(
                b"CANDIDATE_DISPATCHER_PREMERGE_SWPC_BWRAP_STUB_PASS\n"
            ).hexdigest())

    def test_candidate_premerge_sandbox_rejects_host_credential_and_device_leaks(self):
        import importlib.util
        file=ROOT/"scripts/experiments/plasma_candidate_dispatcher_branch_smoke.py"
        spec=importlib.util.spec_from_file_location("plasma_cpu_sandbox_guard",file)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        clean={"HOME":"/tmp", "PATH":"/usr/bin:/bin", "PYTHONNOUSERSITE":"1"}
        module.check_isolation(environ=clean, exists=lambda path: False)
        for leaked in ("GITHUB_TOKEN","OPENAI_API_KEY","SSH_AUTH_SOCK","CODEX_HOME",
                       "AWS_SECRET_ACCESS_KEY","PLASMA_Z2_AUTH"):
            with self.subTest(env=leaked), self.assertRaisesRegex(
                AssertionError,"HOST_CREDENTIAL_ENV_EXPOSED"
            ):
                module.check_isolation(
                    environ={**clean,leaked:"sensitive"},exists=lambda path:False)
        for exposed in ("/home","/root","/dev/mem","/dev/uio0",
                        "/dev/ttyUSB0","/dev/bus/usb","/dev/serial"):
            with self.subTest(path=exposed), self.assertRaisesRegex(
                AssertionError,"HOST_PATH_EXPOSED"
            ):
                module.check_isolation(
                    environ=clean,exists=lambda path,p=exposed:path==p)
        for p,reason in (("/sys","HOST_SYSFS_MOUNT_DENIED"),
                         ("/run/udev","HOST_UDEV_MOUNT_DENIED")):
            with self.subTest(path=p),self.assertRaisesRegex(AssertionError,reason):
                module.check_isolation(
                    environ=clean,exists=lambda path,expected=p:path==expected)

    def test_cpu_only_sandbox_fails_closed_without_bwrap(self):
        task = copy.deepcopy(self.registry["tasks"]["nine-nine-path2"])
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            script = workspace / task["script"]
            script.parent.mkdir(parents=True)
            script.write_text("print('ok')\\n")
            with patch.object(dev.shutil, "which", return_value=None):
                with self.assertRaisesRegex(
                    dev.Denied, "CPU_ONLY_SANDBOX_UNAVAILABLE"
                ):
                    dev.run_task(task, workspace=workspace, sandbox=True)

    def test_cpu_only_sandbox_blocks_network_and_host_devices(self):
        task = copy.deepcopy(self.registry["tasks"]["nine-nine-path2"])
        stdout = (ROOT / task["script"]).read_bytes()
        # The stub preserves the ordinary SHA receipt while inspecting the
        # real argv. This is an offline sandbox-contract test, not SWPC proof.
        captured = []
        class Child:
            returncode = 0
            stdout = (ROOT / task["script"]).read_text()[:0].encode()
            stderr = b""
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td)
            script = workspace / task["script"]
            script.parent.mkdir(parents=True)
            script.write_text("print('sandbox-test')\\n")
            expected = b"sandbox-test\\n"
            task["expected_stdout_sha256"] = hashlib.sha256(expected).hexdigest()
            def fake_executor(command, **kwargs):
                captured.append((command, kwargs))
                return type("Child", (), {
                    "returncode": 0, "stdout": expected, "stderr": b"",
                })()
            # The synthetic executor never launches the wrapper; use a file
            # present on hosted CI as its path for this argv contract test.
            with patch.object(dev.shutil, "which", return_value="/usr/bin/python3"), \
                    patch.object(dev.sys, "executable", "/usr/bin/python3"):
                receipt = dev.run_task(
                    task, workspace=workspace,
                    executor=fake_executor, sandbox=True,
                )
            self.assertEqual(receipt["status"], "PASS")
            command, kwargs = captured[0]
            self.assertIn("--unshare-all", command)
            self.assertIn("--clearenv", command)
            self.assertIn("--die-with-parent", command)
            self.assertIn("--dev", command)
            self.assertIn("--ro-bind", command)
            self.assertIn("-I", command)
            self.assertIn("-S", command)
            self.assertNotIn("--share-net", command)
            self.assertNotIn("--bind", command)
            self.assertEqual(kwargs["timeout"], 40)

    def test_sha_only_candidate_cli_preserves_real_stdout_not_fixed_9x9(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            script=work/"scripts/experiments/plasma_branch_smoke.py"
            script.parent.mkdir(parents=True)
            script.write_text("print('branch-only-test')\n")
            output=b"branch-only-test\n"
            task={
                "script":"scripts/experiments/plasma_branch_smoke.py",
                "argv":[],
                "verification":"sha256-only",
                "expected_stdout_sha256":hashlib.sha256(output).hexdigest(),
            }
            receipt=dev.run_task(task,workspace=work,evidence_dir=work)
            self.assertEqual(receipt["status"],"PASS")
            self.assertEqual(receipt["stdout_sha256"],
                             task["expected_stdout_sha256"])
            self.assertEqual(
                (work/"plasma-path2-stdout.txt").read_bytes(),output)
            self.assertEqual(
                (work/"plasma-path2-stderr.txt").read_bytes(),b"")

    def test_relative_candidate_workspace_executes_single_prefix_and_captures_stdout(self):
        # Mirrors the live SWPC Path 2 call: --workspace candidate.
        # The earlier implementation produced candidate/candidate/scripts/...
        # after switching cwd and exited 2; this must execute real Python.
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "candidate"
            script = workspace / "scripts/experiments/plasma_auto4_relative_probe.py"
            script.parent.mkdir(parents=True)
            script.write_text("print('relative-workspace-pass')\n", encoding="utf-8")
            expected = b"relative-workspace-pass\n"
            task = {
                "script": "scripts/experiments/plasma_auto4_relative_probe.py",
                "argv": [],
                "verification": "sha256-only",
                "expected_stdout_sha256": hashlib.sha256(expected).hexdigest(),
            }
            previous = Path.cwd()
            try:
                os.chdir(td)
                receipt = dev.run_task(
                    task, workspace=Path("candidate"), evidence_dir=Path("candidate"),
                )
            finally:
                os.chdir(previous)
            self.assertEqual(receipt["status"], "PASS")
            self.assertEqual(receipt["exit_code"], 0)
            self.assertEqual((workspace / "plasma-path2-stdout.txt").read_bytes(),
                             expected)
            self.assertEqual((workspace / "plasma-path2-stderr.txt").read_bytes(), b"")

    def test_candidate_script_cannot_escape_through_parent_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "candidate"
            outside = Path(td) / "outside"
            outside.mkdir()
            (outside / "escape.py").write_text("print('outside')\n", encoding="utf-8")
            (workspace / "scripts").mkdir(parents=True)
            (workspace / "scripts/experiments").symlink_to(
                outside, target_is_directory=True,
            )
            task = {
                "script": "scripts/experiments/escape.py",
                "argv": [],
                "expected_stdout_sha256": "0" * 64,
            }
            with self.assertRaisesRegex(dev.Denied, "SCRIPT_NOT_FOUND"):
                dev.run_task(task, workspace=workspace)

    def test_worker_requires_authorization_digest_and_matching_pr(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            reg=work/"registry.json"
            reg.write_text(json.dumps(self.registry))
            eventfile=work/"event.json"
            eventfile.write_text(json.dumps(self.branch_event()))
            env=self.context() | {
                "RUNNER_NAME":"SWPC-plasma-codex",
                "RUNNER_ENVIRONMENT":"self-hosted",
            }
            args=["execute","--event",str(eventfile),
                  "--registry",str(reg),"--workspace",str(work),
                  "--trusted-sha","a"*40,"--pinned-sha","b"*40,
                  "--pr-number","1100",
                  "--registry-sha256",hashlib.sha256(reg.read_bytes()).hexdigest()]
            from io import StringIO
            from contextlib import redirect_stdout
            with patch.dict(os.environ,env):
                with patch.object(dev,"live_pr_metadata", return_value=None), patch.object(dev,"run_task",return_value={"status":"PASS"}) as mock:
                    with redirect_stdout(StringIO()) as out:
                        self.assertEqual(self._call_main(args),0)
                    self.assertEqual(json.loads(out.getvalue())["pinned_sha"],"b"*40)
                    mock.assert_called_once()
                for index,incorrect in (
                    (args.index("--pr-number")+1,"1200"),
                    (args.index("--pinned-sha")+1,"c"*40),
                    (args.index("--trusted-sha")+1,"d"*40),
                    (args.index("--registry-sha256")+1,"0"*64),
                ):
                    tampered=list(args)
                    tampered[index]=incorrect
                    with self.subTest(index=index), redirect_stdout(StringIO()) as out:
                        self.assertEqual(self._call_main(tampered),2)
                        self.assertEqual(json.loads(out.getvalue())["status"],
                                         "NOT_RUN_OR_FAIL")

    @staticmethod
    def _call_main(args):
        with patch.object(sys,"argv",["dispatch.py",*args]):
            return dev.main()

    def test_codex_can_repair_existing_source_and_return_text_evidence(self):
        task=dict(self.registry["tasks"]["nine-nine-path3"])
        task["output_format"]="text"
        del task["expected_stdout_sha256"]  # New task: output is not known yet.
        dev.task_by_id({**self.registry,"tasks":{"branch-codex":task}},
                       "branch-codex")
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            source=work/task["output_path"]
            source.parent.mkdir(parents=True)
            source.write_text("print('wrong')\n")
            class Result:
                returncode=0
                stdout=b"fake Codex independently repaired and tested"
                stderr=b""
            def fake_codex(command, **kwargs):
                self.assertIn("ACTUAL complete output as text",
                              kwargs["input"].decode())
                self.assertNotIn("9 x 9 results",
                                 kwargs["input"].decode())
                source.write_text("print('corrected')\n")
                source.with_suffix(".txt").write_text("corrected\n")
                source.with_suffix(".test.log").write_text(
                    "python3 -B generated.py\n1 positive PASS\nexit=0\n")
                return Result()
            receipt=dev.run_codex_task(task,workspace=work,
                                       executor=fake_codex)
            self.assertEqual(receipt["status"],"EVIDENCE_READY_REVIEW_REQUIRED")
            self.assertTrue(receipt["output_path"].endswith(".txt"))
            self.assertEqual(source.read_text(),"print('corrected')\n")
            self.assertIn("corrected",source.with_suffix(".txt").read_text())

    def test_one_trusted_main_dispatcher_two_checkouts_no_task_workflow(self):
        wf=WORKFLOW.read_text()
        self.assertIn("path: trusted",wf)
        self.assertIn("path: candidate",wf)
        self.assertIn("gh api \"repos/physicslu/plasma/pulls/$PR_NUMBER\"",wf)
        self.assertIn("trusted/scripts/plasma_development_dispatch.py",wf)
        self.assertIn("candidate/specs/engineering-dispatch/development-tasks-v1.json",wf)
        self.assertIn("needs.development-authorize.outputs.pinned_sha",wf)
        self.assertIn("runner.temp",wf)
        self.assertIn("plasma-path2-stdout.txt",wf)
        self.assertIn("candidate/scripts/experiments/plasma_*_generated.csv",wf)
        self.assertIn("candidate/scripts/experiments/plasma_*_generated.txt",wf)
        self.assertIn("plasma-path3-source.patch",wf)
        self.assertNotIn("plasma-path3-nine-nine.yml",wf)
        self.assertIn("github.event_name == 'issue_comment'",wf)


class DevelopmentPath3Contracts(DevelopmentPath2Contracts):
    @classmethod
    def setUpClass(cls):
        cls.registry=json.loads(REGISTRY.read_text())
        cls.task=dev.task_by_id(cls.registry,"nine-nine-path3")

    def event(self):
        value=super().event()
        value["comment"]["body"]="/plasma-dispatch run nine-nine-path3 981"
        return value

    def test_owner_issue_comment_authorizes_one_pinned_task(self):
        plan=dev.authorize(self.event(),self.context(),self.registry)
        self.assertEqual(plan["task_id"],"nine-nine-path3")
        self.assertEqual(plan["execution_path"],"path3-codex")
        self.assertEqual(plan["pinned_sha"],"a"*40)

    def test_real_reference_runs_as_bounded_process_in_hosted_ci(self):
        self.assertEqual(self.task["execution_path"], "path3-codex")
        self.assertIn("independently check all 81", self.task["objective"])
        self.assertNotIn("print(", self.task["objective"])
        self.assertEqual(self.task["expected_stdout_sha256"],
                         "142d9b788a5902e98048690e75e9d91ac8e22334c592f7e2e5a93e8bc878bc5d")

    def test_registry_refuses_arbitrary_commands_and_paths(self):
        for path in ("/tmp/payload.py",
                     "scripts/experiments/../../../tmp/evil.py",
                     "scripts/experiments/plasma_x_generated.sh",
                     "scripts/experiments/x.py"):
            task=copy.deepcopy(self.registry)
            task["tasks"]["nine-nine-path3"]["output_path"]=path
            with self.subTest(path=path), self.assertRaises(dev.Denied):
                dev.task_by_id(task,"nine-nine-path3")
        for prompt in ("", "x\x00malicious", "a"*8193):
            task=copy.deepcopy(self.registry)
            task["tasks"]["nine-nine-path3"]["objective"]=prompt
            with self.assertRaises(dev.Denied):
                dev.task_by_id(task,"nine-nine-path3")
        task=copy.deepcopy(self.registry)
        task["tasks"]["nine-nine-path3"]["argv"]=["sudo"]
        with self.assertRaisesRegex(dev.Denied,"TASK_FIELDS_DENIED"):
            dev.task_by_id(task,"nine-nine-path3")

    def test_fake_codex_returns_unreviewed_evidence_without_local_reexecution(self):
        # Fake agent deliberately emits an incorrect multiplication; runner
        # only collects evidence and must NOT certify PASS or execute Python.
        program='print("a,b,product")\nprint("1,1,999")\n'
        csv='a,b,product\n1,1,999\n'
        report='python3 generated.py > generated.csv\nFAIL: 1/81\nexit=0\n'
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            target=work/self.task["output_path"]
            target.parent.mkdir(parents=True)
            calls=[]
            class Result:
                returncode=0
                stdout=b"fake Codex CLI session"
                stderr=b""
            def fake_codex(command, **kwargs):
                calls.append((command,kwargs))
                target.write_text(program)
                target.with_suffix(".csv").write_text(csv)
                target.with_suffix(".test.log").write_text(report)
                return Result()
            receipt=dev.run_codex_task(self.task,workspace=work,executor=fake_codex)
            self.assertEqual(receipt["status"],"EVIDENCE_READY_REVIEW_REQUIRED")
            self.assertEqual(receipt["codex_exit_code"],0)
            self.assertEqual(receipt["acceptance"],
                             "CHATGPT_REVIEW_OF_REAL_OUTPUT_AND_TEST_LOG")
            self.assertEqual(receipt["output_sha256"],
                             hashlib.sha256(csv.encode()).hexdigest())
            self.assertEqual(receipt["test_log_sha256"],
                             hashlib.sha256(report.encode()).hexdigest())
            self.assertNotIn("rows",receipt)
            self.assertNotIn("PASS",receipt["status"])
            self.assertEqual(len(calls),1)  # No second Python subprocess.
            self.assertEqual(calls[0][0][0],"codex")
            self.assertIn("workspace-write",calls[0][0])
            self.assertNotIn("Do not program or access physical FPGA",calls[0][1]["input"].decode())
            self.assertIn("Record actual commands",calls[0][1]["input"].decode())
            self.assertNotIn("shell",calls[0][1])
            self.assertTrue((work/".plasma-path3-evidence/codex.log").is_file())

    def test_codex_failure_preserves_session_log(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            target=work/self.task["output_path"]
            target.parent.mkdir(parents=True)
            class Failure:
                returncode=5
                stdout=b"attempt failed"
                stderr=b"problem detail"
            receipt=dev.run_codex_task(self.task,workspace=work,
                                       executor=lambda *args,**kwargs:Failure())
            self.assertEqual(receipt["status"],"CODEX_EXECUTION_FAILED_REVIEW_REQUIRED")
            self.assertEqual(receipt["failure_reason"],"CODEX_CLI_NONZERO")
            self.assertEqual(receipt["codex_exit_code"],5)
            self.assertFalse(receipt["evidence_complete"])
            self.assertNotIn("PASS",receipt["status"])
            log=(work/".plasma-path3-evidence/codex.log").read_text()
            self.assertIn("attempt failed",log)
            self.assertIn("problem detail",log)
            self.assertEqual(receipt["codex_log_sha256"],
                             hashlib.sha256(log.encode()).hexdigest())

    def test_guarded_hardware_report_completeness_is_metadata(self):
        task = self.task | {"work_order_scope": "guarded-hardware"}
        with tempfile.TemporaryDirectory() as td:
            class Incomplete:
                returncode = 0
                stdout = b""
                stderr = b""
            receipt = dev.run_codex_task(
                task, workspace=Path(td),
                executor=lambda *args, **kwargs: Incomplete())
            self.assertEqual(receipt["status"], "EVIDENCE_READY_REVIEW_REQUIRED")
            self.assertNotIn("failure_reason", receipt)
            self.assertFalse(receipt["evidence_complete"])

    def test_codex_zero_exit_keeps_host_only_incomplete_evidence_as_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            class Incomplete:
                returncode=0
                stdout=b"output without reviewed evidence"
                stderr=b""
            receipt=dev.run_codex_task(
                self.task,workspace=Path(td),
                executor=lambda *args,**kwargs:Incomplete())
            self.assertEqual(receipt["status"], "EVIDENCE_READY_REVIEW_REQUIRED")
            self.assertNotIn("failure_reason", receipt)
            self.assertEqual(receipt["codex_exit_code"],0)
            self.assertFalse(receipt["evidence_complete"])
            self.assertTrue((Path(td)/".plasma-path3-evidence/codex.log").exists())

    def test_codex_failure_retains_partial_report_and_never_auto_retries(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            calls=[]
            class Failed:
                returncode=7
                stdout=b"compile FAIL, retry within Codex failed"
                stderr=b""
            def executor(command,**kwargs):
                calls.append(command)
                (root/".plasma-path3-evidence/engineering-report.md").write_text(
                    "Attempt 1 FAIL, fixed; attempt 2 FAIL. Real execution NOT_RUN.\n")
                self.assertIn("without another user approval",
                              kwargs["input"].decode())
                self.assertIn("unsafe hardware writes",kwargs["input"].decode())
                return Failed()
            receipt=dev.run_codex_task(self.task,workspace=root,
                                       executor=executor)
            self.assertEqual(len(calls),1)  # One Codex job, NO supervisor retries.
            self.assertEqual(receipt["codex_exit_code"],7)
            self.assertTrue(receipt["evidence_complete"])
            self.assertEqual(receipt["status"],"CODEX_EXECUTION_FAILED_REVIEW_REQUIRED")
            self.assertIn("engineering_report_sha256",receipt)

    def test_worker_admission_rechecks_three_sha_boundaries(self):
        class Args:
            action="execute-codex"
            trusted_sha="a"*40
            pinned_sha="a"*40
            pr_number=0
            execution_capability=None

        with tempfile.TemporaryDirectory() as td:
            args=Args()
            args.workspace=Path(td)
            args.registry=Path(td)/"tasks.json"
            args.registry.write_text(json.dumps(self.registry))
            args.registry_sha256=hashlib.sha256(args.registry.read_bytes()).hexdigest()
            req={"trusted_sha":"a"*40,"source_sha":"a"*40,
                 "pr_number":0,"task_id":"nine-nine-path3"}
            env={"RUNNER_ENVIRONMENT":"self-hosted",
                 "RUNNER_NAME":"SWPC-plasma-codex"}
            with patch.dict(os.environ,env), patch.object(os,"geteuid",return_value=1000):
                result=dev.worker_admission(req,args,self.registry)
                self.assertEqual(result["status"],"WORKER_SOURCE_ADMITTED")
                self.assertEqual(result["trusted_sha"],"a"*40)
                self.assertEqual(result["pinned_sha"],"a"*40)
                self.assertEqual(result["registry_sha256"],args.registry_sha256)
                for attr,bad,reason in (
                    ("trusted_sha","f"*40,"AUTHORIZED_SOURCE_MISMATCH"),
                    ("pinned_sha","f"*40,"AUTHORIZED_SOURCE_MISMATCH"),
                    ("registry_sha256","0"*64,"AUTHORIZED_REGISTRY_MISMATCH"),
                    ("execution_capability","cpu-only","CAPABILITY_ROUTE_MISMATCH"),
                ):
                    original=getattr(args,attr)
                    setattr(args,attr,bad)
                    with self.subTest(attr=attr),self.assertRaisesRegex(dev.Denied,reason):
                        dev.worker_admission(req,args,self.registry)
                    setattr(args,attr,original)
                with patch.dict(os.environ,{"RUNNER_NAME":"OTHER"}):
                    self.assertEqual(dev.worker_admission(req,args,self.registry)["status"],
                                     "WORKER_SOURCE_ADMITTED")
                with patch.object(os,"geteuid",return_value=0):
                    with self.assertRaisesRegex(dev.Denied,"SWPC_RUNNER_DENIED"):
                        dev.worker_admission(req,args,self.registry)

    def test_main_failure_receipt_exits_nonzero_after_worker_admission(self):
        from contextlib import redirect_stdout
        from io import StringIO
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)/"candidate"
            work.mkdir()
            event_file=Path(td)/"event.json"
            event_file.write_text(json.dumps(self.event()))
            registry=Path(td)/"tasks.json"
            registry.write_text(json.dumps(self.registry))
            digest=hashlib.sha256(registry.read_bytes()).hexdigest()
            argv=["execute-codex","--event",str(event_file),
                  "--registry",str(registry),"--workspace",str(work),
                  "--trusted-sha","a"*40,"--pinned-sha","a"*40,
                  "--pr-number","0","--registry-sha256",digest]
            env={**self.context(),
                 "RUNNER_ENVIRONMENT":"self-hosted",
                 "RUNNER_NAME":"SWPC-plasma-codex"}
            failures=[
                ({"status":"CODEX_EXECUTION_FAILED_REVIEW_REQUIRED",
                  "codex_exit_code":7},2),
                ({"status":"CODEX_EVIDENCE_INCOMPLETE_REVIEW_REQUIRED",
                  "codex_exit_code":0},2),
                ({"status":"EVIDENCE_READY_REVIEW_REQUIRED",
                  "codex_exit_code":0},0),
            ]
            with patch.dict(os.environ,env),patch.object(os,"geteuid",return_value=1000):
                for receipt,expected_exit in failures:
                    with self.subTest(receipt=receipt),patch.object(
                            dev,"run_codex_task",return_value=receipt) as agent:
                        with redirect_stdout(StringIO()) as output:
                            with patch.object(sys,"argv",["dispatch.py",*argv]):
                                rc=dev.main()
                        self.assertEqual(rc,expected_exit)
                        result=json.loads(output.getvalue())
                        self.assertEqual(result["status"],receipt["status"])
                        self.assertEqual(result["worker_admission"]["status"],
                                         "WORKER_SOURCE_ADMITTED")
                        agent.assert_called_once()
                bad=list(argv)
                bad[bad.index("--registry-sha256")+1]="0"*64
                with patch.object(dev,"run_codex_task") as agent:
                    with redirect_stdout(StringIO()) as output:
                        with patch.object(sys,"argv",["dispatch.py",*bad]):
                            rc=dev.main()
                    self.assertEqual(rc,2)
                    self.assertEqual(json.loads(output.getvalue())["reason"],
                                     "AUTHORIZED_REGISTRY_MISMATCH")
                    agent.assert_not_called()

    def test_hidden_codex_and_test_logs_are_archived_without_broad_hidden_upload(self):
        workflow=WORKFLOW.read_text()
        codex_job=workflow.split("  development-codex:",1)[1].split(
            "\n  authorize:",1)[0]
        self.assertIn("Collect Path 3 evidence even when Codex",codex_job)
        self.assertIn("tar -C candidate -czf",codex_job)
        self.assertIn("-- .plasma-path3-evidence",codex_job)
        self.assertIn("plasma-path3-engineering-evidence.tar.gz.sha256",codex_job)
        self.assertIn("PATH3_EVIDENCE_SYMLINK_DENIED",codex_job)
        self.assertNotIn("include-hidden-files: true",codex_job)
        # Simulate the exact GNU tar packaging command on temporary files,
        # without dispatching an Action or executing a Codex/host process.
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            candidate=root/"candidate"
            hidden=candidate/".plasma-path3-evidence"
            hidden.mkdir(parents=True)
            (hidden/"codex.log").write_text("Codex exit 0\n")
            (hidden/"triangular.test.log").write_text("12 rows PASS\n")
            archive=root/"evidence.tar.gz"
            proc=subprocess.run(
                ["tar","-C",str(candidate),"-czf",str(archive),
                 "--",".plasma-path3-evidence"],
                capture_output=True,check=False)
            self.assertEqual(proc.returncode,0,proc.stderr)
            with tarfile.open(archive,"r:gz") as t:
                names=set(t.getnames())
                self.assertIn(".plasma-path3-evidence/codex.log",names)
                self.assertIn(".plasma-path3-evidence/triangular.test.log",names)
                self.assertEqual(t.extractfile(
                    ".plasma-path3-evidence/codex.log").read(),
                    b"Codex exit 0\n")

    def test_workflow_has_unconditional_evidence_step_and_keeps_job_failure(self):
        wf=WORKFLOW.read_text()
        job=wf.split("  development-codex:",1)[1].split("\n  authorize:",1)[0]
        self.assertIn("Collect Path 3 evidence even when Codex",job)
        self.assertIn("if: always()",job)
        self.assertIn("git -C candidate diff --binary HEAD",job)
        self.assertIn("git -C candidate ls-files --others --exclude-standard -z",job)
        self.assertIn("plasma-path3-source.patch.sha256",job)
        self.assertLess(job.index("Collect Path 3 evidence even when"),
                        job.index("actions/upload-artifact@"))
        self.assertEqual(job.count("scripts/plasma_development_dispatch.py execute-codex"),1)
        self.assertNotIn("continue-on-error: true",job)
        self.assertNotIn("|| true",job)

    def test_development_path3_supports_vivado_and_full_source_edits(self):
        # Stub-only contract: no Vivado or physical device is invoked by CI.
        task={
            "execution_path":"path3-codex",
            "objective":"Complete actual Vivado 2026.1 F1-B Host-only implementation, "
                        "record all errors/fixes and real BIT HWH timing DRC evidence.",
        }
        dev.task_by_id({
            "schema_version":dev.VERSION, "mode":"development",
            "tasks":{"f1b-vivado-development":task},
        },"f1b-vivado-development")
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            rtl=work/"pl/rtl/host_fixture.sv"
            rtl.parent.mkdir(parents=True)
            rtl.write_text("module placeholder; endmodule\n")
            calls=[]
            class Result:
                returncode=0
                stdout=b"host-build trial logged by stub"
                stderr=b""
            def fake_codex(command, **kwargs):
                calls.append((command,kwargs))
                rtl.write_text("module host_fixture; endmodule\n")
                evidence=work/".plasma-path3-evidence"
                (evidence/"engineering-report.md").write_text(
                    "Actual host-only build log (stub fixture; NOT_RUN).\n"
                    "Root cause and fix entries required in real execution.\n")
                return Result()
            receipt=dev.run_codex_task(task,workspace=work,
                                       executor=fake_codex,
                                       task_id="f1b-path3-codex-vivado-build")
            self.assertEqual(receipt["status"],"EVIDENCE_READY_REVIEW_REQUIRED")
            self.assertNotIn("source_path",receipt)
            self.assertIn("engineering_report_sha256",receipt)
            self.assertIn("module host_fixture",rtl.read_text())
            args,kwargs=calls[0]
            self.assertEqual(kwargs["timeout"],None)
            self.assertIn("workspace-write",args)
            self.assertIn("sandbox_workspace_write.network_access=false",args)
            self.assertIn("Vivado 2026.1",kwargs["input"].decode())
            self.assertIn("trusted dispatcher will execute",kwargs["input"].decode())
            self.assertIn("twice in fresh output directories",kwargs["input"].decode())
            self.assertIn("plasma-fpga-build-diagnostics.json",kwargs["input"].decode())
            self.assertNotIn("--path3-engineering-host-only",kwargs["input"].decode())
            self.assertNotIn("run every Vivado build",kwargs["input"].decode())
            self.assertIn("RTL/Tcl/Python",kwargs["input"].decode())
            self.assertNotIn("Do not program or access physical FPGA",
                          kwargs["input"].decode())
            self.assertNotIn("Create or modify ONLY",kwargs["input"].decode())
        workflow=WORKFLOW.read_text()
        codex_job=workflow.split("  development-codex:",1)[1]
        self.assertIn("timeout-minutes: 360",codex_job)
        self.assertIn("git -C candidate diff --binary",codex_job)
        self.assertIn("plasma-path3-new-files.tar.gz",codex_job)
        self.assertIn("candidate/.plasma-path3-evidence/**",codex_job)
        self.assertNotIn("CODEX_UNAPPROVED_WORKSPACE_CHANGE",codex_job)

    def test_one_existing_shared_runner_and_no_per_task_workflow(self):
        wf=WORKFLOW.read_text()
        self.assertIn("development-codex:",wf)
        self.assertIn("needs: development-authorize",wf)
        self.assertIn("needs.development-authorize.outputs.execution_path == 'path3-codex'",wf)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",wf)
        self.assertIn("scripts/plasma_development_dispatch.py execute-codex",wf)
        self.assertIn("persist-credentials: false",wf)
        self.assertNotIn("plasma-path3-nine-nine.yml",wf)
        self.assertIn("candidate/scripts/experiments/plasma_*_generated.csv",wf)
        self.assertIn("candidate/scripts/experiments/plasma_*_generated.test.log",wf)
        self.assertIn("candidate/scripts/experiments/plasma_*_generated.codex.log",wf)
        self.assertNotIn("bounded validator runs it",wf)




class DevelopmentVivadoHostBuildContracts(unittest.TestCase):
    """Offline-only Path 2 host-build policy tests; never invokes Vivado."""

    @classmethod
    def setUpClass(cls):
        cls.registry=json.loads(REGISTRY.read_text())
        cls.task=dev.task_by_id(cls.registry,"fixed-site1-vivado-host-build")

    def event(self):
        e=DevelopmentPath2Contracts().event()
        e["comment"]["body"]="/plasma-dispatch run fixed-site1-vivado-host-build 981"
        return e

    def context(self):
        return DevelopmentPath2Contracts().context() | {"GITHUB_RUN_ATTEMPT":"1"}

    def test_path2_is_not_synonymous_with_cpu_only(self):
        task=self.task
        self.assertEqual(task["execution_path"],"path2-cli")
        self.assertEqual(task["capability"],"vivado-host-build")
        approved=dev.authorize(self.event(),self.context(),self.registry)
        self.assertEqual(approved["execution_capability"],"vivado-host-build")
        self.assertEqual(approved["pr_number"],0)
        self.assertEqual(approved["pinned_sha"],approved["trusted_sha"])
        # Existing CPU-only path and original bwrap isolation remain intact.
        cpu=dev.task_by_id(self.registry,"nine-nine-path2")
        self.assertEqual(cpu["capability"],"cpu-only")

    def test_host_build_approved_pr_head_allows_reruns(self):
        ctx=self.context()
        for attempt in ("2", "3"):
            plan = dev.authorize(self.event(), ctx | {"GITHUB_RUN_ATTEMPT": attempt},
                                 self.registry)
            self.assertEqual(plan["execution_capability"], "vivado-host-build")
        fixture=DevelopmentBranchDispatchContracts()
        branch_event=fixture.branch_event(
            task="fixed-site1-vivado-host-build",pr=1100,sha="b"*40)
        plan=dev.authorize(branch_event,ctx,self.registry,
                           pr_info=fixture.valid_pr())
        self.assertEqual(plan["pr_number"],1100)
        self.assertEqual(plan["pinned_sha"],"b"*40)
        self.assertEqual(plan["trusted_sha"],"a"*40)
        self.assertEqual(plan["execution_capability"],"vivado-host-build")
        for attempt in ("2", "3"):
            repeated = dev.authorize(branch_event,
                                     ctx | {"GITHUB_RUN_ATTEMPT": attempt},
                                     self.registry, pr_info=fixture.valid_pr())
            self.assertEqual(repeated["pinned_sha"], "b" * 40)
        for change in ("sha","repo","owner","base","state"):
            pr=fixture.valid_pr()
            if change=="sha": pr["head"]["sha"]="c"*40
            elif change=="repo": pr["head"]["repo"]["full_name"]="other/plasma"
            elif change=="owner": pr["user"]["login"]="other"
            elif change=="base": pr["base"]["ref"]="not-main"
            elif change=="state": pr["state"]="closed"
            with self.subTest(change=change),self.assertRaises(dev.Denied):
                dev.authorize(branch_event,ctx,self.registry,pr_info=pr)
        with self.assertRaisesRegex(dev.Denied,"PR_METADATA_DENIED"):
            dev.authorize(branch_event,ctx,self.registry)
        with self.assertRaisesRegex(dev.Denied,"HOST_BUILD_SOURCE_BINDING_DENIED"):
            dev.authorize(fixture.branch_event(
                task="fixed-site1-vivado-host-build",sha="a"*40),
                ctx,self.registry,pr_info=fixture.valid_pr(sha="a"*40))

    def test_host_build_schema_rejects_arbitrary_cli_and_capabilities(self):
        task=dict(self.task)
        for key,value in (
            ("project","../../scripts"),
            ("project","/tmp/my-project"),
            ("project","pl/projects/../danger"),
            ("toolchain","2025.2"),
            ("board_repo_sha","bad"),
            ("capability","host-root"),
        ):
            with self.subTest(field=key,bad=value),self.assertRaises(dev.Denied):
                bad=dict(task,**{key:value})
                reg={**self.registry,"tasks":{"fixed-site1-vivado-host-build":bad}}
                dev.task_by_id(reg,"fixed-site1-vivado-host-build")
        with self.assertRaises(dev.Denied):
            reg={**self.registry,"tasks":{"fixed-site1-vivado-host-build":
                                         dict(task,argv=["--program-fpga"])}}
            dev.task_by_id(reg,"fixed-site1-vivado-host-build")

    def test_runner_guard_allows_approved_pr_host_build_without_new_runner(self):
        wf=WORKFLOW.read_text()
        guard=wf.split("  development-execute:",1)[1].split(
            "  development-codex:",1)[0].split(
            "    if: >-",1)[1].split("    runs-on:",1)[0]
        self.assertIn('"vivado-host-build"',guard)
        self.assertNotIn("outputs.task_id == 'fixed-site1-vivado-host-build'",guard)
        self.assertNotIn("outputs.pr_number == '0'",guard)
        self.assertIn("github.run_attempt == 1",guard)
        self.assertIn('"cpu-only"',guard)
        self.assertIn("execution_capability == 'z2-cpu-only'",guard)
        self.assertIn("needs.development-claim.result == 'success'",guard)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",wf)
        self.assertIn("== 'vivado-host-build' && 50 ||",wf)
        self.assertIn("== 'z2-path2-full-hil' && 10 || 5",wf)
        self.assertNotIn("runs-on: [self-hosted, linux, x64, vivado]",wf)

    def test_host_build_source_preflight_is_pure_and_strict(self):
        import plasma_vivado_host_build as build
        approval=dev.authorize(self.event(),self.context(),self.registry)
        env={
            "GITHUB_REPOSITORY":"physicslu/plasma",
            "RUNNER_NAME":"SWPC-plasma-codex",
            "RUNNER_ENVIRONMENT":"self-hosted",
            "GITHUB_EVENT_NAME":"issue_comment",
            "GITHUB_REF":"refs/heads/main",
            "GITHUB_RUN_ATTEMPT":"1",
            "GITHUB_SHA":approval["trusted_sha"],
        }
        # This uses only local tracked source. No SWPC or Vivado call.
        p=build.preflight(self.task,workspace=ROOT,approval=approval,env=env)
        self.assertEqual(p["toolchain"],"2026.1")
        self.assertIn("z2-fixed-unified-site1",p["project"])
        self.assertEqual(p["board_sha"],self.task["board_repo_sha"])
        for changed in (
            {"GITHUB_SHA":"b"*40},
        ):
            with self.subTest(change=changed),self.assertRaises(build.BuildDenied):
                build.preflight(self.task,workspace=ROOT,approval=approval,
                                env=env|changed)
        with self.assertRaises(build.BuildDenied):
            build.preflight(self.task,workspace=ROOT,
                            approval=dict(approval,pr_number=1059),env=env)
        fixture=DevelopmentBranchDispatchContracts()
        candidate=dev.authorize(
            fixture.branch_event(task="fixed-site1-vivado-host-build",
                                 pr=1100,sha="b"*40),
            self.context(),self.registry,pr_info=fixture.valid_pr())
        accepted=build.preflight(self.task,workspace=ROOT,
                                 approval=candidate,env=env)
        self.assertEqual(accepted["source_sha"],"b"*40)
        with self.assertRaises(build.BuildDenied):
            build.preflight(self.task,workspace=ROOT,
                            approval=dict(candidate,pinned_sha="a"*40),env=env)
        with self.assertRaises(build.BuildDenied):
            build.preflight(dict(self.task,project="pl/projects/../bad"),
                            workspace=ROOT,approval=approval,env=env)

    def test_host_build_exec_requires_authorization_before_any_process(self):
        task=self.task
        with patch("plasma_vivado_host_build.run") as dangerous:
            with self.assertRaisesRegex(dev.Denied,"HOST_BUILD_APPROVAL_REQUIRED"):
                dev.run_task(task,workspace=ROOT,approval=None,sandbox=False)
            dangerous.assert_not_called()
        with patch("plasma_vivado_host_build.run") as builder:
            dev.run_task(task,workspace=ROOT,
                         approval={"task_id":"fixed-site1-vivado-host-build",
                                   "execution_path":"path2-cli",
                                   "execution_capability":"vivado-host-build",
                                   "pr_number":0,
                                   "pinned_sha":"a"*40,"trusted_sha":"a"*40},
                         sandbox=False)
            builder.assert_called_once()
        # An approved PR must not silently fall back to the trusted main
        # driver when its own fixed candidate driver is missing.
        with tempfile.TemporaryDirectory() as td:
            candidate = Path(td) / "candidate"
            candidate.mkdir()
            with patch("plasma_vivado_host_build.run") as builder:
                with self.assertRaisesRegex(
                    dev.Denied, "HOST_BUILD_CANDIDATE_DRIVER_DENIED"
                ):
                    dev.run_task(task, workspace=candidate,
                                 approval={
                                     "task_id":"fixed-site1-vivado-host-build",
                                     "execution_path":"path2-cli",
                                     "execution_capability":"vivado-host-build",
                                     "pr_number":1063,
                                     "pinned_sha":"b"*40,
                                     "trusted_sha":"a"*40},
                                 sandbox=False)
                builder.assert_not_called()
        for invalid in (
            {"task_id":"wrong"},
            {"pr_number":1063,"pinned_sha":"a"*40,"trusted_sha":"a"*40},
            {"pr_number":0,"pinned_sha":"b"*40,"trusted_sha":"a"*40},
        ):
            base={"task_id":"fixed-site1-vivado-host-build",
                  "execution_path":"path2-cli",
                  "execution_capability":"vivado-host-build",
                  "pr_number":0,
                  "pinned_sha":"a"*40,"trusted_sha":"a"*40}
            with self.subTest(invalid=invalid),patch(
                "plasma_vivado_host_build.run") as builder:
                with self.assertRaisesRegex(dev.Denied,
                                            "HOST_BUILD_APPROVAL_REQUIRED"):
                    dev.run_task(task,workspace=ROOT,approval=base|invalid,
                                 sandbox=False)
                builder.assert_not_called()

    def test_candidate_vivado_driver_is_reviewed_and_not_trusted_main(self):
        # Host-only unit fixture. Do not start Vivado or access SWPC/hardware.
        import plasma_vivado_host_build as trusted_build
        task=self.task
        approval={
            "task_id":"fixed-site1-vivado-host-build",
            "execution_path":"path2-cli",
            "execution_capability":"vivado-host-build",
            "pr_number":1064,"pinned_sha":"b"*40,"trusted_sha":"a"*40,
        }
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)/"candidate"
            scripts=work/"scripts"
            scripts.mkdir(parents=True)
            driver=scripts/"plasma_vivado_host_build.py"
            driver.write_text(
                "def run(task, *, workspace, approval, evidence_dir=None, "
                "executor=None):\n"
                "    return {'status':'CANDIDATE_DRIVER_TEST_ONLY'}\n",
                encoding="utf-8")
            with patch.object(trusted_build,"run") as main_driver:
                result=dev.run_task(task,workspace=work,approval=approval)
                self.assertEqual(result["status"],"CANDIDATE_DRIVER_TEST_ONLY")
                main_driver.assert_not_called()
            # PR driver is not admissible if absent or a symlink escape.
            driver.unlink()
            with self.assertRaisesRegex(
                dev.Denied,"HOST_BUILD_CANDIDATE_DRIVER_DENIED"
            ):
                dev.run_task(task,workspace=work,approval=approval)
            outside=Path(td)/"unreviewed.py"
            outside.write_text("raise RuntimeError('must not import')\n")
            driver.symlink_to(outside)
            with self.assertRaisesRegex(
                dev.Denied,"HOST_BUILD_CANDIDATE_DRIVER_DENIED"
            ):
                dev.run_task(task,workspace=work,approval=approval)
            driver.unlink()
            driver.write_text("x"*65537)
            with self.assertRaisesRegex(
                dev.Denied,"HOST_BUILD_CANDIDATE_DRIVER_DENIED"
            ):
                dev.run_task(task,workspace=work,approval=approval)

    def test_workflow_transports_authorized_pr_identity_to_existing_runner(self):
        wf=WORKFLOW.read_text()
        self.assertIn("pr_info_base64: ${{ steps.approve.outputs.pr_info_base64 }}",wf)
        self.assertIn("PR_INFO_BASE64: ${{ needs.development-authorize.outputs.pr_info_base64 }}",wf)
        self.assertIn('pr_info_args+=(--pr-info "$RUNNER_TEMP/plasma-dev-pr.json")',wf)
        self.assertIn('"${pr_info_args[@]}"',wf)
        self.assertIn("ref: ${{ needs.development-authorize.outputs.trusted_sha }}",wf)
        self.assertIn("ref: ${{ needs.development-authorize.outputs.pinned_sha }}",wf)
        self.assertIn("python3 trusted/scripts/plasma_development_dispatch.py execute",wf)
        dispatch=(ROOT/"scripts/plasma_development_dispatch.py").read_text()
        self.assertIn("authorize(event, os.environ, registry, pr_info=pr)",dispatch)
        self.assertNotIn("sudo ",wf)

    def test_sanitize_real_swpc_build_failure_codes(self):
        import plasma_vivado_host_build as build
        self.assertEqual(
            dev.safe_error_reason(build.BuildDenied("BUILD_BOARD_REPO_MISSING")),
            "BUILD_BOARD_REPO_MISSING",
        )
        self.assertEqual(
            dev.safe_error_reason(build.BuildDenied("BUILD_BOARD_SHA_MISMATCH")),
            "BUILD_BOARD_SHA_MISMATCH",
        )
        self.assertEqual(dev.safe_error_reason(dev.Denied("OWNER_DENIED")),
                         "OWNER_DENIED")
        for exc in (ValueError("/home/private/ssh/id_rsa"),
                    OSError("/etc/private/secret"),
                    build.BuildDenied("unsafe secret: /home/user")):
            with self.subTest(error=str(exc)):
                self.assertEqual(dev.safe_error_reason(exc), "EXECUTION_ERROR")

    def test_vivado_invokes_original_board_prepare_with_pinned_source(self):
        import plasma_vivado_host_build as build
        with tempfile.TemporaryDirectory() as td:
            board=Path(td)/"pynq-board"
            board.mkdir()
            calls=[]
            class Ready:
                returncode=0
                stdout=(str(board)+"\n").encode()
                stderr=b""
            def runner(command,**kwargs):
                calls.append((command,kwargs))
                return Ready()
            selected=build.resolve_board_repository(
                self.task,workspace=ROOT,executor=runner,
                env={"HOME":"/nonexistent"})
            self.assertEqual(selected,board)
            self.assertEqual(len(calls),1)
            command,kwargs=calls[0]
            self.assertEqual(command[0],"/usr/bin/bash")
            self.assertTrue(command[1].endswith(
                "/pl/projects/z2-swd-gpio/prepare-board-repository.sh"))
            self.assertEqual(kwargs["timeout"],180)
            self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"],"0")
            script=(ROOT/"pl/projects/z2-swd-gpio/prepare-board-repository.sh").read_text()
            self.assertIn('source_commit="'+self.task["board_repo_sha"]+'"',script)
            self.assertIn("git clone --quiet",script)
            self.assertIn('status --porcelain --untracked-files=no',script)
            self.assertIn("board.xml preset.xml part0_pins.xml",script)

    def test_vivado_explicit_board_repo_preserves_override(self):
        import plasma_vivado_host_build as build
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"board"
            p.mkdir()
            def forbidden(*args,**kwargs):
                self.fail("PREPARE_MUST_NOT_EXECUTE_WHEN_EXPLICIT_PATH_EXISTS")
            actual=build.resolve_board_repository(
                self.task,workspace=ROOT,executor=forbidden,
                env={"PLASMA_BOARD_REPO":str(p)})
            self.assertEqual(actual,p)
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_BOARD_REPO_PATH_DENIED"):
                build.resolve_board_repository(
                    self.task,workspace=ROOT,executor=forbidden,
                    env={"PLASMA_BOARD_REPO":str(p)+"/../board"})
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_BOARD_REPO_MISSING"):
                build.resolve_board_repository(
                    self.task,workspace=ROOT,executor=forbidden,
                    env={"PLASMA_BOARD_REPO":str(p/"missing")})

    def test_vivado_board_prepare_fails_closed_before_build(self):
        import plasma_vivado_host_build as build
        with tempfile.TemporaryDirectory() as td:
            board=Path(td)/"board"
            board.mkdir()
            class Fail:
                returncode=2
                stdout=b""
                stderr=b"BOARD_REPO_FAIL: pinned revision unavailable"
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_BOARD_PREPARE_FAILED"):
                build.resolve_board_repository(
                    self.task,workspace=ROOT,executor=lambda *a,**k:Fail(),
                    env={})
            class BadOutput:
                returncode=0
                stdout=b"not-an-absolute-path\n"
                stderr=b""
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_BOARD_REPO_PATH_DENIED"):
                build.resolve_board_repository(
                    self.task,workspace=ROOT,executor=lambda *a,**k:BadOutput(),
                    env={})
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_BOARD_PREPARE_PIN_MISMATCH"):
                build.resolve_board_repository(
                    {**self.task,"board_repo_sha":"f"*40},
                    workspace=ROOT,executor=lambda *a,**k:self.fail(
                        "MUST_NOT_RUN_WRONG_BOARD_REVISION"),env={})
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_BOARD_PREPARE_SCRIPT_MISSING"):
                build.resolve_board_repository(
                    self.task,workspace=Path(td),
                    executor=lambda *a,**k:self.fail(
                        "MUST_NOT_RUN_MISSING_BOARD_PREPARE"),env={})

    def test_vivado_uses_existing_candidate_local_build_root(self):
        import plasma_vivado_host_build as build
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "candidate"
            output = work / "pl/build"
            output.mkdir(parents=True)
            folder = build.prepare_host_build_dir(work)
            self.assertEqual(folder.parent, output)
            self.assertTrue(folder.name.startswith("fixed-f1-"))
            self.assertTrue((folder / "reports").is_dir())
            self.assertFalse(str(folder).startswith("/storage/projects/plasma/"))
            self.assertTrue(folder.resolve().is_relative_to(work.resolve()))
            # Never follow a candidate symlink into arbitrary host folders.
            import shutil
            shutil.rmtree(output)
            outside = Path(td) / "outside"
            outside.mkdir()
            output.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(build.BuildDenied,
                                        "BUILD_OUTPUT_ROOT_MISSING"):
                build.prepare_host_build_dir(work)

    def test_vivado_output_errors_are_actionable_and_path_sanitized(self):
        import plasma_vivado_host_build as build
        with tempfile.TemporaryDirectory() as td:
            work = Path(td) / "candidate"
            (work / "pl/build").mkdir(parents=True)
            for number, reason in (
                (errno.EACCES, "BUILD_OUTPUT_PERMISSION_DENIED"),
                (errno.EPERM, "BUILD_OUTPUT_PERMISSION_DENIED"),
                (errno.EROFS, "BUILD_OUTPUT_READ_ONLY"),
                (errno.ENOSPC, "BUILD_OUTPUT_NO_SPACE"),
                (errno.EIO, "BUILD_OUTPUT_CREATE_FAILED"),
            ):
                exc = OSError(number, "private path should stay hidden")
                with self.subTest(errno=number),patch.object(
                        build.tempfile, "mkdtemp", side_effect=exc):
                    with self.assertRaisesRegex(build.BuildDenied, reason) as ctx:
                        build.prepare_host_build_dir(work)
                    self.assertEqual(dev.safe_error_reason(ctx.exception), reason)
                    self.assertNotIn("private path", str(ctx.exception))

    def test_vivado_board_helper_launch_and_timeout_codes(self):
        import plasma_vivado_host_build as build
        for exc, reason in (
            (FileNotFoundError(errno.ENOENT, "missing bash"),
             "BUILD_BOARD_PREPARE_LAUNCH_FAILED"),
            (PermissionError(errno.EACCES, "private helper"),
             "BUILD_BOARD_PREPARE_LAUNCH_FAILED"),
            (subprocess.TimeoutExpired("mock-board-helper", 180),
             "BUILD_BOARD_PREPARE_TIMEOUT"),
        ):
            def stub(*args, **kwargs):
                raise exc
            with self.subTest(reason=reason,type=type(exc).__name__):
                with self.assertRaisesRegex(build.BuildDenied, reason) as ctx:
                    build.resolve_board_repository(
                        self.task, workspace=ROOT,
                        executor=stub,env={"HOME": "/nonexistent"})
                self.assertEqual(dev.safe_error_reason(ctx.exception), reason)

    def test_vivado_preparation_has_no_new_workflow_or_runner(self):
        src=(ROOT/"scripts/plasma_vivado_host_build.py").read_text()
        self.assertIn("resolve_board_repository(task, workspace=workspace",src)
        self.assertIn('"GIT_TERMINAL_PROMPT": "0"',src)
        self.assertIn('actual_board_sha == plan["board_sha"]',src)
        self.assertIn('BUILD_BOARD_REPO_DIRTY',src)
        self.assertNotIn("git clone",src)
        self.assertIn("BUILD_BOARD_PREPARE_FAILED",src)
        self.assertEqual(self.task["capability"],"vivado-host-build")
        wf=WORKFLOW.read_text()
        self.assertIn("  development-execute:",wf)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",wf)





class GenericWorkOrderContracts(unittest.TestCase):
    """Offline: one Work Order format, both Paths; no device/Runner access."""

    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads(REGISTRY.read_text())

    def _order(self, path="path3-codex", **kwargs):
        order = {
            "schema": dev.WORK_ORDER_SCHEMA,
            "execution_path": path,
            "capability": "codex-workspace" if path == "path3-codex"
                          else "cpu-only",
            "objective": "Perform the owner approved bounded engineering task.",
            "acceptance": "Record actual test commands and observed results.",
        }
        if path == "path2-cli":
            order["scope"] = "host-only"
            baseline = dev.task_by_id(self.registry, "nine-nine-path2")
            order.update({key: baseline[key] for key in (
                "script", "argv", "expected_stdout_sha256")})
        order.update(kwargs)
        return order

    def _event(self, order):
        return {
            "action": "created", "issue": {"number": 981},
            "comment": {"id": 246801, "user": {"login": "physicslu"},
                        "body": dev.WORK_ORDER_PREFIX +
                        json.dumps(order, ensure_ascii=False)},
            "sender": {"login": "physicslu"},
            "repository": {"full_name": "physicslu/plasma"},
        }

    def _context(self):
        return {
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_ACTOR": "physicslu",
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ATTEMPT": "1",
        }

    def test_both_paths_share_one_dynamic_protocol_no_registry_entry(self):
        self.assertNotIn("path2-work-order", self.registry["tasks"])
        self.assertNotIn("path3-work-order", self.registry["tasks"])
        for path, expected in (("path2-cli", "path2-work-order"),
                               ("path3-codex", "path3-work-order")):
            order = self._order(path)
            event = self._event(order)
            req = dev.request(event, self._context())
            self.assertEqual(req["task_id"], expected)
            self.assertEqual(req["work_order_sha256"],
                             dev.work_order_digest(order))
            approval = dev.authorize(event, self._context(), self.registry)
            self.assertEqual(approval["task_id"], expected)
            self.assertEqual(approval["execution_path"], path)
            self.assertEqual(approval["pinned_sha"], "a" * 40)
            self.assertEqual(approval["work_order_sha256"],
                             req["work_order_sha256"])
            task = dev.task_for_request(self.registry, req, event)
            self.assertEqual(task["objective"], order["objective"])
            self.assertEqual(task["acceptance"], order["acceptance"])

    def test_path2_cpu_only_uses_existing_checked_script(self):
        event = self._event(self._order("path2-cli"))
        req = dev.request(event, self._context())
        task = dev.task_for_request(self.registry, req, event)
        self.assertEqual(task["capability"], "cpu-only")
        result = dev.run_task(task)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["rows"], 81)
        with patch.object(dev.shutil, "which", return_value=None):
            with self.assertRaisesRegex(dev.Denied, "CPU_ONLY_SANDBOX_UNAVAILABLE"):
                dev.run_task(task, sandbox=True)

    def test_exact_stage_guard_accepts_only_digest_pinned_stage(self):
        import plasma_path2_runtime_integration as runtime
        stage_order = self._order(
            "path2-cli", capability="path2-stage-contract",
            scope="guarded-hardware",
            project="pl/projects/z2-fixed-unified-site1",
            stage="test")
        for field in ("script", "argv", "expected_stdout_sha256"):
            stage_order.pop(field, None)
        event = self._event(stage_order)
        req = dev.request(event, self._context())
        approval = dev.authorize(event, self._context(), self.registry)
        task = dev.task_for_request(self.registry, req, event)
        self.assertEqual(runtime.stage_contract(task, approval), "test")
        with self.assertRaisesRegex(runtime.RuntimeDenied, "WORK_ORDER_DENIED"):
            runtime.stage_contract(task, approval |
                                   {"work_order_sha256": "0" * 64})
        with self.assertRaisesRegex(runtime.RuntimeDenied, "WORK_ORDER_DENIED"):
            runtime.stage_contract(task | {"stage": "download"}, approval)

    def test_work_order_tamper_and_replay_denied_before_execution(self):
        order = self._order()
        event = self._event(order)
        req = dev.request(event, self._context())
        changed = copy.deepcopy(event)
        changed["comment"]["body"] = dev.WORK_ORDER_PREFIX + json.dumps(
            order | {"objective": "Changed objective after authorization."})
        with self.assertRaisesRegex(dev.Denied, "DIGEST_MISMATCH"):
            dev.task_for_request(self.registry, req, changed)
        repeated = dev.authorize(event, self._context() |
                                 {"GITHUB_RUN_ATTEMPT": "2"}, self.registry)
        self.assertEqual(repeated["work_order_sha256"], req["work_order_sha256"])
        class Args:
            action = "execute-codex"
            trusted_sha = "a" * 40
            pinned_sha = "a" * 40
            pr_number = 0
            execution_capability = "codex-workspace"
            work_order_sha256 = "0" * 64
        with tempfile.TemporaryDirectory() as td:
            args = Args()
            args.workspace = Path(td)
            args.registry = Path(td) / "tasks.json"
            args.registry.write_text(json.dumps(self.registry))
            args.registry_sha256 = hashlib.sha256(
                args.registry.read_bytes()).hexdigest()
            with patch.dict(os.environ, {
                "RUNNER_ENVIRONMENT": "self-hosted",
                "RUNNER_NAME": "SWPC-plasma-codex",
                "GITHUB_RUN_ATTEMPT": "1",
            }), patch.object(dev.os, "geteuid", return_value=1000):
                with self.assertRaisesRegex(dev.Denied, "WORKER_BINDING_DENIED"):
                    dev.worker_admission(req, args, self.registry, event)

    def test_reject_arbitrary_shell_and_path3_unbounded_hardware(self):
        bad_orders = [
            self._order("path2-cli", script="/bin/sh"),
            self._order("path2-cli", argv=["-c", "rm"]),
            self._order("path2-cli", capability="vivado-host-build"),
            self._order("path3-codex", scope="guarded-hardware"),
            self._order("path3-codex", capability="path2-stage-contract"),
            self._order("path3-codex", hardware_stages=["download"]),
            self._order("path2-cli", stage="restore"),
        ]
        for order in bad_orders:
            with self.subTest(order=order), self.assertRaises(dev.Denied):
                dev.request(self._event(order), self._context())
        duplicate = self._event(self._order())
        duplicate["comment"]["body"] = dev.WORK_ORDER_PREFIX + (
            '{"schema":"a","schema":"b"}')
        with self.assertRaises(dev.Denied):
            dev.request(duplicate, self._context())
        forged = self._event(self._order())
        forged["sender"]["login"] = "attacker"
        with self.assertRaisesRegex(dev.Denied, "EVENT_OWNER_DENIED"):
            dev.request(forged, self._context())

    def test_goal_order_has_no_mode_builder_or_stage_list(self):
        order = self._order(pr_number=1234, source_sha="b" * 40)
        event = self._event(order)
        pr = {
            "number": 1234, "state": "open", "merged_at": None,
            "user": {"login": "physicslu"},
            "head": {"ref": "agent/candidate", "sha": "b" * 40,
                     "repo": {"full_name": "physicslu/plasma"}},
            "base": {"ref": "main", "repo": {"full_name": "physicslu/plasma"}},
        }
        approval = dev.authorize(event, self._context(), self.registry, pr_info=pr)
        self.assertEqual(approval["execution_capability"], "codex-workspace")
        task = dev.task_for_request(self.registry,
                                   dev.request(event, self._context()), event)
        self.assertNotIn("work_order_scope", task)
        self.assertNotIn("hardware_stages", task)
        with self.assertRaisesRegex(dev.Denied, "PR_HEAD_SHA_MISMATCH"):
            dev.authorize(event, self._context(), self.registry,
                          pr_info=pr | {"head": pr["head"] | {"sha": "c" * 40}})

    def test_deleted_automatic_hardware_progression_is_absent(self):
        import plasma_path2_runtime_integration as integration
        self.assertFalse(hasattr(integration, "path3_shared_hardware_stages"))
        execute = WORKFLOW.read_text().split("  development-execute:", 1)[1].split(
            "  development-codex:", 1)[0]
        self.assertNotIn("codex-guarded-hardware", execute)
        job = WORKFLOW.read_text().split("  development-codex:", 1)[1].split(
            "  authorize:", 1)[0]
        self.assertNotIn("Prefetch exact F1-B", job)
        self.assertNotIn("PLASMA_FPGA_PATH3_APPROVED", job)

    def test_existing_workflow_and_two_runner_routes(self):
        content = WORKFLOW.read_text()
        self.assertIn("'/plasma-dispatch work-order 981'", content)
        self.assertIn('"path2-stage-contract"', content)
        self.assertIn('work-order-sha256 "$WORK_ORDER_SHA256"', content)
        self.assertEqual(content.count(
            "runs-on: [self-hosted, linux, x64, plasma-codex]"), 2)
        self.assertIn("needs.development-authorize.outputs.execution_path == 'path3-codex'",
                      content)
        self.assertIn('--execution-capability "$EXECUTION_CAPABILITY"', content)

    def test_path3_prompt_preserves_privilege_boundary_and_one_invocation(self):
        order = self._order()
        event = self._event(order)
        task = dev.task_for_request(
            self.registry, dev.request(event, self._context()), event)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            calls = []
            captured_commands = []
            class Fake:
                returncode = 0
                stdout = b"offline agent output"
                stderr = b""
            def run(command, **kw):
                captured_commands.append(command)
                calls.append(kw["input"].decode())
                (root / ".plasma-path3-evidence" /
                 "engineering-report.md").write_text("Host-only test evidence.\n")
                return Fake()
            result = dev.run_codex_task(
                task, workspace=root, executor=run,
                task_id="path3-work-order")
            self.assertEqual(result["status"], "EVIDENCE_READY_REVIEW_REQUIRED")
            self.assertEqual(len(calls), 1)
            self.assertIn("existing trusted root executor", calls[0])
            self.assertNotIn("Authorized Z2 stages in order", calls[0])
            self.assertNotIn("Authorized scope:", calls[0])
            self.assertIn("sandbox_workspace_write.network_access=false", captured_commands[0])
            self.assertIn("Acceptance criteria", calls[0])
            self.assertIn("Owner Work Order SHA256", calls[0])


if __name__ == "__main__":
    unittest.main()
