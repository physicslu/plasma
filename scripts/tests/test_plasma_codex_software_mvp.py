#!/usr/bin/env python3
"""Real Git/patch handoff unit tests; intentionally NO fake model or live GitHub."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/"scripts"))
import plasma_codex_software_mvp as mvp

def command(*args: str) -> str:
    return subprocess.check_output(["git",*args],stderr=subprocess.DEVNULL,text=True).strip()

class MVPTests(unittest.TestCase):
    def event(self) -> dict:
        return {"action":"created","issue":{"number":981},
                "comment":{"id":123,"body":mvp.COMMAND,
                           "user":{"login":"physicslu"}},
                "sender":{"login":"physicslu"},
                "repository":{"full_name":"physicslu/plasma"}}

    def env(self, sha: str) -> dict:
        return {"GITHUB_EVENT_NAME":"issue_comment",
                "GITHUB_ACTOR":"physicslu",
                "GITHUB_REPOSITORY":"physicslu/plasma",
                "GITHUB_REF":"refs/heads/main",
                "GITHUB_SHA":sha,
                "GITHUB_RUN_ATTEMPT":"1",
                "GITHUB_RUN_ID":"40012345"}

    def test_exact_owner_pass(self):
        r=mvp.authorize(self.event(),self.env("a"*40),"a"*40)
        self.assertEqual(r["comment_id"],123)
        self.assertEqual(r["executor"],"codex")

    def test_other_actor_rejected(self):
        env=self.env("a"*40);env["GITHUB_ACTOR"]="attacker"
        with self.assertRaises(mvp.Refused):
            mvp.authorize(self.event(),env,"a"*40)

    def test_altered_message_rejected(self):
        for suffix in ("\n"," --force"," extra"):
            e=self.event();e["comment"]["body"]+=suffix
            with self.subTest(suffix=suffix),self.assertRaises(mvp.Refused):
                mvp.authorize(e,self.env("a"*40),"a"*40)

    def test_replay_attempt_rejected(self):
        e=self.env("a"*40);e["GITHUB_RUN_ATTEMPT"]="2"
        with self.assertRaises(mvp.Refused):
            mvp.authorize(self.event(),e,"a"*40)

    def test_wrong_issue_or_pull_request_rejected(self):
        for kind in ("wrong","pr"):
            e=self.event()
            if kind=="wrong":e["issue"]["number"]=982
            else:e["issue"]["pull_request"]={}
            with self.subTest(kind=kind),self.assertRaises(mvp.Refused):
                mvp.authorize(e,self.env("a"*40),"a"*40)

    def test_real_git_patch_handoff_and_tamper_rejection(self):
        saved=Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            try:
                os.chdir(root)
                command("init","-q")
                command("-c","user.name=Test","-c","user.email=test@example.invalid",
                        "commit","--allow-empty","-qm","base")
                sha=command("rev-parse","HEAD")
                env=self.env(sha);event=self.event()
                path=Path(mvp.TARGET);path.parent.mkdir(parents=True)
                path.write_text("# Codex MVP\n\nVerified manual operator guide.\n")
                bundle=mvp.create_bundle(root/"bundle",event,env)
                self.assertEqual(bundle["source_sha"],sha)
                self.assertTrue((root/"bundle/candidate.patch").is_file())
                command("reset","-q")
                path.unlink()
                trusted=mvp.verify_bundle(root/"bundle",event,env)
                self.assertEqual(trusted["patch_sha256"],bundle["patch_sha256"])
                self.assertEqual(command("diff","--cached","--name-only"),mvp.TARGET)
                command("reset","-q")
                altered=json.loads((root/"bundle/receipt.json").read_text())
                altered["model_exit_code"]=99
                (root/"bundle/receipt.json").write_text(json.dumps(altered))
                with self.assertRaises(mvp.Refused):
                    mvp.verify_bundle(root/"bundle",event,env)
            finally:
                os.chdir(saved)

    def test_injected_extra_file_rejected(self):
        saved=Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            try:
                os.chdir(root)
                command("init","-q")
                command("-c","user.name=Test","-c","user.email=test@example.invalid",
                        "commit","--allow-empty","-qm","base")
                dest=Path(mvp.TARGET);dest.parent.mkdir(parents=True)
                dest.write_text("valid\n")
                extra=Path("scripts/rogue.py");extra.parent.mkdir()
                extra.write_text("print('rogue')\n")
                with self.assertRaises(mvp.Refused):
                    mvp.inventory()
            finally:
                os.chdir(saved)

    def test_swpc_codex_and_hosted_publisher_are_separate(self):
        wf=(ROOT/".github/workflows/plasma-codex-software-mvp.yml").read_text()
        self.assertEqual(wf.count("runs-on: [self-hosted, linux, x64, plasma-codex]"),1)
        self.assertEqual(wf.count("runs-on: ubuntu-24.04"),3)
        authorize=wf.split("\n  authorize:",1)[1].split("\n  codex:",1)[0]
        worker=wf.split("\n  codex:",1)[1].split("\n  publisher:",1)[0]
        publisher=wf.split("\n  publisher:",1)[1]
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",worker)
        self.assertIn("test \"$RUNNER_NAME\" = SWPC-plasma-codex",worker)
        self.assertIn("test \"$(hostname)\" = SWPC",worker)
        self.assertIn("test \"$(id -un)\" = plasma-codex",worker)
        self.assertIn("persist-credentials: false",worker)
        self.assertIn("needs: authorize",worker)
        self.assertIn("codex --ask-for-approval never exec",worker)
        self.assertIn("sandbox_workspace_write.network_access=false",worker)
        self.assertIn("grep -Eq '^(sudo|docker|adm|dialout|gpio|i2c|video|plasma-hil)$'",worker)
        self.assertIn("/dev/uio*",worker)
        self.assertIn("SSH_AUTH_SOCK",worker)
        self.assertNotIn("OPENAI_API_KEY",worker)
        self.assertNotIn("GH_TOKEN",worker)
        self.assertNotIn("contents: write",worker)
        self.assertNotIn("npm install",worker)
        self.assertIn("runs-on: ubuntu-24.04",publisher)
        self.assertIn("needs: codex",publisher)
        self.assertIn("pull-requests: write",publisher)
        self.assertIn("contents: write",publisher)
        self.assertIn("GH_TOKEN:",publisher)
        self.assertNotIn("codex --",publisher)
        self.assertIn("runs-on: ubuntu-24.04",authorize)
        self.assertIn(mvp.COMMAND,wf)
        self.assertNotIn("workflow_dispatch:",wf)
        self.assertNotIn("codex --dangerously-bypass",wf)

if __name__=="__main__":
    unittest.main(verbosity=2)
