#!/usr/bin/env python3
"""Host-only negative/contract tests for the trusted Candidate relay.

NEVER runs real Codex, never dispatches SWPC and never imports candidate code
into the trusted main process. Real acceptance is a separate approved SWPC job.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_candidate_dispatcher_bridge as bridge


class CandidateBridgeContracts(unittest.TestCase):
    def task(self):
        return {
            "execution_path": "path3-codex",
            "objective": (
                "Do not use hardware. Produce 12 triangular numbers in Python, "
                "record real Exit Code and a complete test log in the workspace."
            ),
            "output_path": "scripts/experiments/plasma_auto4_branch_codex_generated.py",
            "output_format": "csv",
        }

    def event(self):
        return {
            "action": "created",
            "issue": {"number": 981},
            "comment": {
                "id": 34567,
                "user": {"login": "physicslu"},
                "body": "/plasma-dispatch run candidate-dispatcher-e2e-1083 "
                        "--pr 1083 --sha " + "b"*40 + " 981",
            },
            "sender": {"login": "physicslu"},
            "repository": {"full_name": "physicslu/plasma"},
        }

    def context(self):
        return {
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_ACTOR": "physicslu",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a"*40,
            "RUNNER_ENVIRONMENT": "self-hosted",
            "RUNNER_NAME": "SWPC-plasma-codex",
        }

    def registry(self):
        return {
            "schema_version": bridge.trusted.VERSION,
            "mode": "development",
            "tasks": {bridge.TASK_ID: self.task()},
        }

    def args(self, registry_file, workspace):
        return SimpleNamespace(
            pinned_sha="b"*40,
            trusted_sha="a"*40,
            pr_number=1083,
            registry=registry_file,
            workspace=workspace,
            registry_sha256=hashlib.sha256(registry_file.read_bytes()).hexdigest(),
        )

    def test_one_exact_task_only(self):
        bridge.valid_task(self.task(), 1083)
        for field, value in (
            ("execution_path", "path2-cli"),
            ("capability", "vivado-host-build"),
            ("output_path", "scripts/experiments/plasma_other_generated.py"),
            ("objective", "Use USB or FPGA and download firmware."),
        ):
            altered=self.task()
            altered[field]=value
            with self.subTest(field=field), self.assertRaisesRegex(
                bridge.BridgeDenied, "CANDIDATE_TASK_DENIED"
            ):
                bridge.valid_task(altered,1083)
        with self.assertRaisesRegex(bridge.BridgeDenied,"CANDIDATE_PR_DENIED"):
            bridge.valid_task(self.task(),1082)

    def test_trusted_owner_sha_registry_and_runner_gate(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            registry=root/"registry.json"
            registry.write_text(json.dumps(self.registry()))
            workspace=root/"candidate"
            workspace.mkdir()
            args=self.args(registry,workspace)
            with patch.object(bridge.os,"geteuid",return_value=1001):
                admitted=bridge.admission(self.event(),self.context(),
                                           args,self.registry(),"b"*40)
                self.assertEqual(admitted["task"]["execution_path"],"path3-codex")
                for key,value in (
                    ("GITHUB_EVENT_NAME","pull_request"),
                    ("GITHUB_ACTOR","untrusted"),
                    ("GITHUB_REF","refs/heads/agent"),
                    ("RUNNER_NAME","unknown"),
                    ("GITHUB_SHA","f"*40),
                ):
                    env={**self.context(),key:value}
                    with self.subTest(key=key),self.assertRaises(bridge.BridgeDenied):
                        bridge.admission(self.event(),env,args,self.registry(),"b"*40)
                with self.assertRaisesRegex(bridge.BridgeDenied,"CANDIDATE_SOURCE_DENIED"):
                    bridge.admission(self.event(),self.context(),args,
                                     self.registry(),"c"*40)
                original=args.registry_sha256
                args.registry_sha256="0"*64
                with self.assertRaisesRegex(bridge.BridgeDenied,"CANDIDATE_REGISTRY_DENIED"):
                    bridge.admission(self.event(),self.context(),args,
                                     self.registry(),"b"*40)
                args.registry_sha256=original
                forged=copy.deepcopy(self.event())
                forged["sender"]["login"]="attacker"
                with self.assertRaises(bridge.trusted.Denied):
                    bridge.admission(forged,self.context(),args,
                                     self.registry(),"b"*40)

    def test_candidate_sandbox_has_no_network_or_host_credentials(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/"candidate").mkdir()
            (root/"scratch").mkdir()
            with patch.object(bridge.shutil,"which",return_value="/usr/bin/bwrap"),\
                 patch.object(bridge.Path,"is_file",return_value=True):
                args=bridge.sandbox_command(
                    root/"candidate",root/"scratch",
                    trusted_sha="a"*40,pinned_sha="b"*40,
                    registry_sha256="c"*64,phase="prepare")
            joined=" ".join(args)
            for term in ("--unshare-all","--clearenv","--ro-bind","--dev /dev",
                         "--setenv HOME /tmp","/scratch/bin:/usr/bin:/bin"):
                self.assertIn(term,joined)
            self.assertNotIn("--share-net",joined)
            self.assertNotIn("--bind /home",joined)
            self.assertNotIn("--bind /dev",joined)
            self.assertNotIn("--setenv GITHUB_TOKEN",joined)
            self.assertNotIn("--setenv GH_TOKEN",joined)
            self.assertNotIn("--setenv CODEX_HOME",joined)
            self.assertNotIn("--setenv SSH_AUTH_SOCK",joined)
            self.assertIn("/work/scripts/plasma_development_dispatch.py",joined)
            with patch.object(bridge.shutil,"which",return_value=None):
                with self.assertRaisesRegex(
                    bridge.BridgeDenied,"CANDIDATE_SANDBOX_NOT_AVAILABLE"):
                    bridge.sandbox_command(root/"candidate",root/"scratch",
                        trusted_sha="a"*40,pinned_sha="b"*40,
                        registry_sha256="c"*64,phase="prepare")

    def test_real_codex_stays_in_trusted_host_and_only_one_invocation(self):
        src=(ROOT/"scripts/plasma_candidate_dispatcher_bridge.py").read_text()
        wf=(ROOT/".github/workflows/plasma-engineering-runtime-dispatch.yml").read_text()
        self.assertIn('list(CODEX_CMD), cwd=scratch / "workspace"',src)
        self.assertIn("input_bytes=prompt, timeout=240",src)
        self.assertIn("CANDIDATE_PROMPT_OUT_OF_SCOPE",src)
        self.assertIn("CANDIDATE_REPLAY_RECEIPT_DENIED",src)
        self.assertIn("os.killpg(proc.pid, signal.SIGKILL)",src)
        self.assertIn("CODEX_SHIM",src)
        self.assertIn("candidate-dispatcher-e2e-1083",wf)
        self.assertIn("trusted/scripts/plasma_candidate_dispatcher_bridge.py",wf)
        self.assertIn("trusted/scripts/plasma_development_dispatch.py execute-codex",wf)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",wf)
        self.assertNotIn("pull_request_target:",wf)

    def test_two_phase_candidate_real_codex_relay_offline_fixture(self):
        """Run the full trusted state machine with a synthetic agent only."""
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            candidate=root/"candidate"
            candidate.mkdir()
            registry=candidate/"tasks.json"
            registry.write_text(json.dumps(self.registry()))
            event=root/"event.json"
            event.write_text(json.dumps(self.event()))
            real=bridge.TASK_ID
            args=self.args(registry,candidate)
            argv=[
                "bridge.py","--event",str(event),"--registry",str(registry),
                "--workspace",str(candidate),"--trusted-sha",args.trusted_sha,
                "--pinned-sha",args.pinned_sha,"--pr-number",str(args.pr_number),
                "--registry-sha256",args.registry_sha256,
            ]
            calls=[]
            def make_cmd(_candidate,scratch,*,phase,**kwargs):
                return ["sandbox-fixture",phase,str(scratch)]
            def subprocess_fixture(cmd, *, cwd, env, input_bytes=None, timeout=45):
                calls.append((cmd[0],cmd[1] if len(cmd)>1 else "",cwd))
                if cmd[0]=="sandbox-fixture":
                    scratch=Path(cmd[2])
                    if cmd[1]=="prepare":
                        prompt=(b"PLASMA owner software test: "+
                                self.task()["objective"].encode())
                        (scratch/"prompt.bin").write_bytes(prompt)
                        evidence=scratch/"workspace/.plasma-path3-evidence"
                        evidence.mkdir()
                        return 2,json.dumps({
                            "status":"CODEX_EXECUTION_FAILED_REVIEW_REQUIRED",
                            "worker_admission":{"status":"WORKER_SOURCE_ADMITTED"}
                        }).encode(),b""
                    source=scratch/"workspace/scripts/experiments/plasma_auto4_branch_codex_generated.py"
                    csv=source.with_suffix(".csv")
                    log=source.with_suffix(".test.log")
                    payload=json.dumps({
                        "status":"EVIDENCE_READY_REVIEW_REQUIRED",
                        "codex_exit_code":0,
                        "pinned_sha":"b"*40,
                        "worker_admission":{"status":"WORKER_SOURCE_ADMITTED"},
                        "codex_log_sha256":"f"*64,
                        "source_sha256":bridge.digest(source.read_bytes()),
                        "output_sha256":bridge.digest(csv.read_bytes()),
                        "test_log_sha256":bridge.digest(log.read_bytes()),
                    }).encode()
                    return 0,payload,b""
                self.assertEqual(tuple(cmd),bridge.CODEX_CMD)
                scratch=Path(cwd)
                out=scratch/"scripts/experiments/plasma_auto4_branch_codex_generated.py"
                out.parent.mkdir(parents=True)
                out.write_text("for n in range(1,13): print(n,n*(n+1)//2)\\n")
                out.with_suffix(".csv").write_text(
                    "n,triangular\\n"+"".join(
                        f"{n},{n*(n+1)//2}\\n" for n in range(1,13)))
                out.with_suffix(".test.log").write_text("12 rows checked; exit 0\\n")
                evidence=scratch/".plasma-path3-evidence"
                evidence.mkdir()
                (evidence/"engineering-report.md").write_text("Synthetic fixture, not real Codex.\\n")
                self.assertIn(self.task()["objective"].encode(),input_bytes)
                return 0,b"HOSTED_SYNTHETIC_AGENT_ONLY",b""
            from contextlib import redirect_stdout
            from io import StringIO
            output=StringIO()
            with (patch.dict(os.environ,self.context(),clear=True),
                  patch.object(bridge.os,"geteuid",return_value=1001),
                  patch.object(bridge.subprocess,"check_output",return_value="b"*40),
                  patch.object(bridge,"sandbox_command",side_effect=make_cmd),
                  patch.object(bridge,"run_process",side_effect=subprocess_fixture),
                  patch.object(sys,"argv",argv),redirect_stdout(output)):
                rc=bridge.main()
            self.assertEqual(rc,0,output.getvalue())
            result=json.loads(output.getvalue())
            self.assertEqual(result["candidate_sha"],"b"*40)
            self.assertEqual(result["codex_exit_code"],0)
            self.assertTrue(result["agent_real_execution"])
            self.assertEqual(len(calls),3)
            self.assertEqual([x[0] for x in calls],
                             ["sandbox-fixture","codex","sandbox-fixture"])
            target=candidate/"scripts/experiments/plasma_auto4_branch_codex_generated.py"
            self.assertTrue(target.exists())
            self.assertTrue(target.with_suffix(".test.log").exists())
            self.assertTrue(target.with_suffix(".codex.log").exists())
            rows=target.with_suffix(".csv").read_text().splitlines()
            self.assertEqual(rows[-1],"12,78")

    def test_error_paths_cannot_forge_success_or_change_hardware(self):
        self.assertEqual(bridge.STAMP,
                         "plasma.candidate_dispatcher.trusted_relay.v1")
        shim=bridge.CODEX_SHIM
        self.assertIn("raise SystemExit(73)",shim)
        self.assertIn("raise SystemExit(74)",shim)
        self.assertIn("BRIDGE_PHASE",shim)
        self.assertNotIn("sudo",shim)
        self.assertNotIn("ssh",shim)
        self.assertNotIn("/dev/mem",shim)


if __name__ == "__main__":
    unittest.main(verbosity=2)
