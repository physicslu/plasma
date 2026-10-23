#!/usr/bin/env python3
"""Synthetic cross-Job checks, no SWPC, real model, or physical hardware."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_path3_cross_job_resume as flow
import plasma_development_dispatch as dev

SID = "0190deaf-babe-47cd-9e00-a1b2c3d4e5f6"
NONCE = "c" * 32
SHA = "b" * 40


class ResumeTwoJobOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "checkout"
        self.repo.mkdir()
        (self.repo / "AGENTS.md").write_text("host-only synthetic fixture\n")
        self.private = Path(self.tmp.name) / "runner-private"
        self.binding = {
            "github_run_id": "123456",
            "runner": "SWPC-plasma-codex", "uid": os.geteuid(),
            "source_sha": SHA, "trusted_sha": "a" * 40,
            "work_order_sha256": "d" * 64,
            "workspace_sha256": "e" * 64,
        }
        self.req = {"task_id": "path3-work-order",
                    "session_resume": "page-boundary-off-by-one",
                    "pr_number": 987, "source_sha": SHA,
                    "trusted_sha": "a" * 40, "work_order_sha256": "d" * 64}
        self.calls = []
        self.mismatch = False
        self.missing_proof = False

    def fake_git(self, _repo):
        scratch = self.repo / flow.probe.ROOT_FOLDER
        rows = (["?? " + flow.probe.ROOT_FOLDER + "/" + p.relative_to(scratch).as_posix()
                 for p in scratch.rglob("*") if p.is_file()]
                if scratch.exists() else [])
        return SHA, rows

    def fake_test(self, scratch):
        text = (scratch / flow.probe.SOURCE_NAME).read_text()
        return 1 if "len(data) - 1" in text else 0

    def fake_command(self, _root, _private, sid):
        return ["HOSTED_FAKE_CODEX", "new" if sid is None else "resume", sid or "-"]

    def fake_codex(self, args, **kw):
        self.calls.append(args[1])
        root = Path(kw["cwd"])
        if args[1] == "new":
            self.assertIn(NONCE, kw["input"])
            self.assertNotIn("No SWPC", kw["input"])
            self.assertIn("isolated CPU-only workspace", kw["input"])
            self.assertNotIn("resume", args)
        else:
            self.assertEqual(args[2], SID)
            self.assertNotIn(NONCE, kw["input"])
            self.assertNotIn("No network, Git writes, SWPC", kw["input"])
            source = root / flow.probe.SOURCE_NAME
            source.write_text(source.read_text().replace(
                "len(data) - 1", "len(data)"))
            if not self.missing_proof:
                (root / flow.probe.PROOF_NAME).write_text(NONCE + "\n")
        sid = ("a190deaf-babe-47cd-9e00-a1b2c3d4e5f6"
               if args[1] == "resume" and self.mismatch else SID)
        events = [
            {"type": "thread.started", "thread_id": sid},
            {"type": "turn.completed", "usage": {
                "input_tokens": 120, "cached_input_tokens": 80,
                "output_tokens": 21}},
        ]
        return subprocess.CompletedProcess(args, 0,
            "".join(json.dumps(e) + "\n" for e in events), "")

    def phase(self, stage):
        with patch.object(flow, "runner_binding", return_value=dict(self.binding)), \
             patch.object(flow.probe, "git_state", side_effect=self.fake_git), \
             patch.object(flow.probe, "test_result", side_effect=self.fake_test):
            return flow.execute(
                stage, self.req, self.repo, env={},
                state_root=self.private, executor=self.fake_codex,
                command_builder=self.fake_command,
                test_runner=lambda _workspace, scratch: self.fake_test(scratch),
                nonce_factory=lambda: NONCE)

    def clean_second_checkout(self):
        # A second GH Actions Job with checkout clean:true resets untracked
        # source; only the private runner state is preserved.
        scratch = self.repo / flow.probe.ROOT_FOLDER
        if scratch.exists():
            shutil.rmtree(scratch)

    def test_new_expected_fail_then_separate_resume_pass(self):
        first = self.phase("new")
        self.assertEqual(first["status"], "NEW_EXPECTED_TEST_FAIL")
        self.assertEqual(first["test_after"], 1)
        self.assertEqual(self.calls, ["new"])
        private = self.private / "123456.json"
        self.assertTrue(private.is_file())
        self.assertEqual(private.stat().st_mode & 0o777, 0o600)
        self.assertIn(SID, private.read_text())
        self.assertNotIn(SID, json.dumps(first))
        self.assertNotIn(NONCE, private.read_text())
        self.clean_second_checkout()
        second = self.phase("resume")
        self.assertEqual(second["status"], "RESUME_FIX_PASS")
        self.assertTrue(second["same_thread"])
        self.assertEqual(second["continuity"], "VERIFIED")
        self.assertEqual(second["test_after"], 0)
        self.assertEqual(self.calls, ["new", "resume"])
        self.assertNotIn(SID, json.dumps(second))
        self.assertNotIn(NONCE, json.dumps(second))
        self.assertFalse(private.exists())
        self.assertTrue((self.private / "123456.consumed").exists())

    def test_missing_session_and_replays_rejected(self):
        with self.assertRaises(flow.ResumeDenied):
            self.phase("resume")
        self.assertEqual(self.calls, [])
        self.phase("new")
        with self.assertRaises(flow.ResumeDenied):
            self.phase("new")
        self.clean_second_checkout()
        self.phase("resume")
        self.clean_second_checkout()
        with self.assertRaises(flow.ResumeDenied):
            self.phase("resume")
        self.assertEqual(self.calls, ["new", "resume"])

    def test_negative_changed_sha_work_order_runner_workspace(self):
        self.phase("new")
        self.clean_second_checkout()
        for key in ("trusted_sha", "source_sha", "work_order_sha256",
                    "runner", "uid", "workspace_sha256"):
            with self.subTest(field=key):
                original = self.binding[key]
                self.binding[key] = "f" * 40 if key.endswith("_sha") else (
                    "f" * 64 if key.endswith("sha256") else
                    999 if key == "uid" else "wrong-runner")
                with self.assertRaisesRegex(flow.ResumeDenied,
                                            "RESUME_BINDING_MISMATCH"):
                    self.phase("resume")
                self.binding[key] = original
        self.assertEqual(self.calls, ["new"])

    def test_thread_mismatch_never_passes(self):
        self.phase("new")
        self.clean_second_checkout()
        self.mismatch = True
        with self.assertRaisesRegex(flow.ResumeDenied, "RESUME_THREAD_MISMATCH"):
            self.phase("resume")
        self.assertEqual(self.calls, ["new", "resume"])

    def test_missing_first_turn_challenge_never_passes(self):
        self.phase("new")
        self.clean_second_checkout()
        self.missing_proof = True
        with self.assertRaisesRegex(flow.ResumeDenied,
                                    "RESUME_CHALLENGE_NOT_RECOVERED"):
            self.phase("resume")
        self.assertEqual(self.calls, ["new", "resume"])

    def test_real_runner_and_source_pin_guards(self):
        context = {"GITHUB_JOB": "development-codex", "GITHUB_RUN_ID": "123456",
                   "GITHUB_RUN_ATTEMPT": "1",
                   "RUNNER_NAME": "SWPC-plasma-codex",
                   "RUNNER_ENVIRONMENT": "self-hosted"}
        with patch.object(flow.os, "geteuid", return_value=1000), \
             patch.object(flow.probe, "git_state", return_value=(SHA, [])):
            bound = flow.runner_binding("new", self.req, self.repo, context)
            self.assertEqual(bound["github_run_id"], "123456")
            for key, bad in (("GITHUB_JOB", "other"),
                             ("GITHUB_RUN_ATTEMPT", "2"),
                             ("RUNNER_NAME", "other"),
                             ("RUNNER_ENVIRONMENT", "github-hosted")):
                with self.subTest(key=key):
                    with self.assertRaises(flow.ResumeDenied):
                        flow.runner_binding("new", self.req, self.repo,
                                            context | {key: bad})
            with self.assertRaises(flow.ResumeDenied):
                flow.runner_binding("new", self.req, self.repo,
                                    context | {"GITHUB_RUN_ID": "abc"})

    def test_bwrap_and_private_auth_required(self):
        with patch.object(flow.shutil, "which", return_value=None):
            with self.assertRaisesRegex(flow.ResumeDenied,
                                        "RESUME_BWRAP_OR_CODEX_UNAVAILABLE"):
                flow.isolated_command(self.repo, self.private, None)
            with self.assertRaisesRegex(flow.ResumeDenied,
                                        "RESUME_TEST_BWRAP_UNAVAILABLE"):
                flow.isolated_unittest(self.repo, self.repo / flow.probe.ROOT_FOLDER)

    def test_model_namespace_keeps_git_and_candidate_checkout_read_only(self):
        scratch = self.repo / flow.probe.ROOT_FOLDER
        scratch.mkdir()
        isolated = self.private / "123456"
        isolated.mkdir(parents=True)
        auth_home = Path(self.tmp.name) / "safe-auth-home"
        auth_file = auth_home / ".codex" / "auth.json"
        auth_file.parent.mkdir(parents=True)
        auth_file.write_text("{}")
        with patch.object(flow.Path, "home", return_value=auth_home), \
             patch.object(flow.shutil, "which",
                          side_effect=lambda name: "/usr/bin/" + name):
            command = flow.isolated_command(self.repo, isolated, None)
        ro = ["--ro-bind", str(self.repo), "/work"]
        writable_scratch = ["--bind", str(scratch),
                            "/work/" + flow.probe.ROOT_FOLDER]
        ro_idx = command.index("--ro-bind", command.index("--ro-bind") + 1)
        self.assertIn(ro, [command[i:i + 3]
                            for i in range(len(command) - 2)])
        self.assertIn(writable_scratch,
                      [command[i:i + 3] for i in range(len(command) - 2)])
        self.assertNotIn(["--bind", str(self.repo), "/work"],
                         [command[i:i + 3] for i in range(len(command) - 2)])
        self.assertIn("--dev", command)
        self.assertIn("/usr/bin/codex", command)
        self.assertNotIn("--unshare-net", command)  # Real Codex model API
        self.assertEqual(command[-2:], ["workspace-write", "-"])
        with patch.object(flow.Path, "home", return_value=auth_home), \
             patch.object(flow.shutil, "which",
                          side_effect=lambda name: "/usr/bin/" + name):
            broken = self.repo / flow.probe.ROOT_FOLDER
            shutil.rmtree(broken)
            with self.assertRaisesRegex(flow.ResumeDenied,
                                        "RESUME_SCRATCH_DENIED"):
                flow.isolated_command(self.repo, isolated, None)

    def test_model_install_outside_readonly_mount_denied(self):
        # Never bind an arbitrary user home to enable a non-system CLI.
        scratch = self.repo / flow.probe.ROOT_FOLDER
        scratch.mkdir()
        isolated = self.private / "123456"
        isolated.mkdir(parents=True)
        with patch.object(flow.shutil, "which",
                          side_effect=lambda name:
                              str(Path(self.tmp.name) / "unmounted" / name)):
            with self.assertRaisesRegex(flow.ResumeDenied,
                                        "RESUME_CODEX_INSTALL_UNMOUNTED"):
                flow.isolated_command(self.repo, isolated, None)

    def test_sandboxed_test_does_not_inherit_runner_tokens(self):
        seen = {}
        def fake_run(args, **kw):
            seen["args"] = args
            seen["env"] = kw["env"]
            return subprocess.CompletedProcess(args, 0, b"", b"Ran 2 tests in 0.0s\nOK\n")
        with patch.object(flow.shutil, "which", return_value="/usr/bin/bwrap"), \
             patch.object(flow.subprocess, "run", side_effect=fake_run), \
             patch.dict(os.environ, {"GH_TOKEN": "sensitive-fixture",
                                     "PYTHONPATH": "/untrusted"}, clear=False):
            result = flow.isolated_unittest(self.repo, self.repo)
        self.assertEqual(result, 0)
        self.assertNotIn("GH_TOKEN", seen["env"])
        self.assertNotIn("PYTHONPATH", seen["env"])
        self.assertIn("--unshare-net", seen["args"])
        self.assertIn("--dev", seen["args"])
        self.assertIn(["--ro-bind", str(self.repo), "/work"],
                      [seen["args"][i:i + 3]
                       for i in range(len(seen["args"]) - 2)])
        self.assertNotIn(["--bind", str(self.repo), "/work"],
                         [seen["args"][i:i + 3]
                          for i in range(len(seen["args"]) - 2)])

    def test_resume_work_order_schema_rejects_scope_expansion(self):
        order = {
            "schema": dev.WORK_ORDER_SCHEMA,
            "objective": "CPU-only Page-boundary diagnosis with no hardware use.",
            "acceptance": "Only a second Actions Job can resume and fix the unchanged test.",
            "execution_path": "path3-codex",
            "capability": "codex-workspace",
            "scope": "host-only",
            "session_resume": "page-boundary-off-by-one",
            "pr_number": 1134,
            "source_sha": SHA,
        }
        def parse(payload):
            event = {"comment": {"body": dev.WORK_ORDER_PREFIX +
                                          json.dumps(payload)}}
            return dev.parse_dynamic_work_order(event)
        self.assertEqual(parse(order)["session_resume"],
                         "page-boundary-off-by-one")
        for key, value in (("scope", "guarded-hardware"),
                           ("session_resume", "any-session"),
                           ("pr_number", 0),
                           ("capability", "cpu-only")):
            with self.subTest(key=key), self.assertRaises(dev.Denied):
                parse(order | {key: value})
        with self.assertRaises(dev.Denied):
            parse(order | {"hardware_stages": ["flash"]})

    def test_only_existing_workflow_and_runner(self):
        wf = (ROOT / ".github/workflows/plasma-engineering-runtime-dispatch.yml").read_text()
        self.assertIn("development-codex-resume:", wf)
        self.assertEqual(wf.count(
            "runs-on: [self-hosted, linux, x64, plasma-codex]"), 3)
        self.assertIn("needs: [development-authorize, development-codex]", wf)
        self.assertNotIn("plasma-path3-crossjob.yml", wf)


if __name__ == "__main__":
    unittest.main()
