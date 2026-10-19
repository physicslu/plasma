#!/usr/bin/env python3
"""Host-only tests for reusable Development Mode issue-comment dispatch."""
from __future__ import annotations

import copy
import hashlib
import json
import os
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
        self.assertIn("outputs.execution_capability == 'cpu-only'", guard)
        self.assertIn("needs.development-claim.result == 'skipped'", guard)
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
            with patch.object(dev.shutil, "which", return_value=sys.executable):
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
                with patch.object(dev,"run_task",return_value={"status":"PASS"}) as mock:
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
        for prompt in ("", "x\nmalicious", "a"*801):
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
            self.assertIn("No Z2, FPGA, USB",calls[0][1]["input"].decode())
            self.assertIn("independently check",calls[0][1]["input"].decode())
            self.assertNotIn("shell",calls[0][1])
            self.assertTrue(target.with_suffix(".codex.log").is_file())

    def test_codex_failure_preserves_session_log(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)
            target=work/self.task["output_path"]
            target.parent.mkdir(parents=True)
            class Failure:
                returncode=5
                stdout=b"attempt failed"
                stderr=b"problem detail"
            with self.assertRaisesRegex(dev.Denied,"CODEX_CLI_NONZERO"):
                dev.run_codex_task(self.task,workspace=work,
                                   executor=lambda *args,**kwargs:Failure())
            log=target.with_suffix(".codex.log").read_text()
            self.assertIn("attempt failed",log)
            self.assertIn("problem detail",log)

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

    def test_host_build_approved_pr_head_and_no_replays(self):
        ctx=self.context()
        for attempt in ("2","0","","abc"):
            with self.subTest(attempt=attempt),self.assertRaisesRegex(
                dev.Denied,"HOST_BUILD_RERUN_DENIED"
            ):
                dev.authorize(self.event(),ctx | {"GITHUB_RUN_ATTEMPT":attempt},
                              self.registry)
        fixture=DevelopmentBranchDispatchContracts()
        branch_event=fixture.branch_event(
            task="fixed-site1-vivado-host-build",pr=1100,sha="b"*40)
        plan=dev.authorize(branch_event,ctx,self.registry,
                           pr_info=fixture.valid_pr())
        self.assertEqual(plan["pr_number"],1100)
        self.assertEqual(plan["pinned_sha"],"b"*40)
        self.assertEqual(plan["trusted_sha"],"a"*40)
        self.assertEqual(plan["execution_capability"],"vivado-host-build")
        for attempt in ("2", "0"):
            with self.subTest(attempt=attempt),self.assertRaisesRegex(
                dev.Denied,"HOST_BUILD_RERUN_DENIED"):
                dev.authorize(branch_event,
                              ctx | {"GITHUB_RUN_ATTEMPT":attempt},
                              self.registry,pr_info=fixture.valid_pr())
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
        self.assertIn("execution_capability == 'vivado-host-build'",guard)
        self.assertIn("outputs.task_id == 'fixed-site1-vivado-host-build'",guard)
        self.assertNotIn("outputs.pr_number == '0'",guard)
        self.assertIn("github.run_attempt == 1",guard)
        self.assertIn("execution_capability == 'cpu-only'",guard)
        self.assertIn("execution_capability == 'z2-cpu-only'",guard)
        self.assertIn("needs.development-claim.result == 'success'",guard)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",wf)
        self.assertIn("== 'vivado-host-build' && 50 || 5",wf)
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
            {"RUNNER_NAME":"some-runner"},
            {"GITHUB_RUN_ATTEMPT":"2"},
            {"GITHUB_SHA":"b"*40},
            {"GITHUB_EVENT_NAME":"pull_request"},
            {"GITHUB_REF":"refs/heads/feature"},
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



if __name__ == "__main__":
    unittest.main()
