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

    def test_workflow_is_hosted_separated_and_inert_for_pr(self):
        wf=(ROOT/".github/workflows/plasma-codex-software-mvp.yml").read_text()
        self.assertIn("runs-on: ubuntu-24.04",wf)
        self.assertNotIn("self-hosted",wf)
        self.assertIn(mvp.COMMAND,wf)
        self.assertIn("needs: authorize",wf)
        self.assertIn("needs: codex",wf)
        self.assertIn("persist-credentials: false",wf)
        self.assertIn("pull-requests: write",wf)
        self.assertIn("OPENAI_API_KEY",wf)
        self.assertIn("codex --ask-for-approval never exec",wf)
        self.assertNotIn("workflow_dispatch:",wf)
        self.assertNotIn("codex --dangerously-bypass",wf)

if __name__=="__main__":
    unittest.main(verbosity=2)
