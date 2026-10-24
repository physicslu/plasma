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
    @staticmethod
    def minimal_c_fixture() -> str:
        # Local ephemeral test fixture; never published as a target program.
        return ('#include <stdio.h>\\n\\n'
                'int main(void)\\n'
                '{\\n'
                '    puts("Hello, World!");\\n'
                '    return 0;\\n'
                '}\\n').replace('\\n', '\n')

    def test_denies_other_c_source_and_malicious_side_effects(self):
        for bad in (
            b'#include <stdlib.h>\\nint main(void){system("id"); return 0;}',
            b'#include <stdio.h>\\nint main(void){printf("Wrong\\\\n");return 0;}',
            b'#include <stdio.h>\\nint main(void){puts("Hello, World!");system("id");return 0;}',
            b'#include <stdio.h>\\nint main(void){puts("Hello, World!");return 0;} /* nope */',
            b'#include <stdio.h>\\nint main(void){puts("Hello, World!");return 0;}\\n#define ESCALATE 1',
        ):
            with self.subTest(src=bad), self.assertRaises(mvp.Refused):
                mvp.validate_c_source(bad)

    def test_exact_c11_program_and_stdout_contract(self):
        src=self.minimal_c_fixture().encode()
        mvp.validate_c_source(src)
        self.assertEqual(mvp.EXPECTED_STDOUT, b"Hello, World!\\n".replace(b"\\n",b"\n"))
        self.assertEqual(mvp.TARGET,"examples/hello-world/main.c")
        self.assertEqual(mvp.COMMAND,"/plasma-codex hello-c 981")

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

    def test_all_automatic_push_events_denied(self):
        sha="b"*40
        env=self.env(sha)
        env["GITHUB_EVENT_NAME"]="push"
        event={"ref":"refs/heads/main", "after":sha,
               "head_commit":{"id":sha},
               "repository":{"full_name":"physicslu/plasma"},
               "forced":False,"created":False,"deleted":False}
        with self.assertRaises(mvp.Refused):
            mvp.authorize(event,env,sha)
        for change in (
            {"GITHUB_RUN_ATTEMPT":"2"},
            {"GITHUB_ACTOR":"somebody-else"},
            {"GITHUB_REF":"refs/heads/not-main"},
            {"GITHUB_SHA":"0"*40},
        ):
            bad_env={**env,**change}
            with self.subTest(change=change),self.assertRaises(mvp.Refused):
                mvp.authorize(event,bad_env,sha)
        with self.assertRaises(mvp.Refused):
            mvp.authorize({**event,"forced":True},env,sha)

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
                # CI-only disposable fixture; the deliverable main.c is
                # intentionally NOT authored in the repository by ChatGPT.
                path.write_text(self.minimal_c_fixture())
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
        self.assertIn("codex --ask-for-approval never",worker)
        self.assertIn("exec --sandbox workspace-write",worker)
        self.assertIn("sandbox_workspace_write.network_access=false",worker)
        self.assertIn("grep -Eq '^(sudo|docker|adm|dialout|gpio|i2c|video|plasma-hil)$'",worker)
        self.assertNotIn("for device in /dev/mem",worker)
        self.assertNotIn("NO_GO: software Codex can access a hardware device",worker)
        self.assertIn("for group in plasma-codex-io plasma-monitor; do",worker)
        self.assertIn('grep -Fxq "$group"',worker)
        self.assertIn('test -z "$(git status --porcelain)"',worker)
        self.assertIn("SSH_AUTH_SOCK",worker)
        self.assertNotIn("OPENAI_API_KEY",worker)
        self.assertNotIn("GH_TOKEN",worker)
        self.assertNotIn("contents: write",worker)
        self.assertNotIn("npm install",worker)
        self.assertIn("runs-on: ubuntu-24.04",publisher)
        self.assertIn("needs: [authorize, codex]",publisher)
        self.assertIn("pull-requests: write",publisher)
        self.assertIn("contents: write",publisher)
        self.assertIn("GH_TOKEN:",publisher)
        self.assertNotIn("codex --",publisher)
        self.assertIn("runs-on: ubuntu-24.04",authorize)
        # Historical SW uses the SAME one-operator Issue dispatch pattern as LA.
        self.assertIn("issue_comment:",wf)
        self.assertIn("types: [created]",wf)
        self.assertIn(mvp.COMMAND,wf)
        self.assertIn("github.event_name == 'issue_comment'",authorize)
        self.assertIn("github.actor == 'physicslu'",authorize)
        self.assertIn("github.event.issue.number == 981",authorize)
        self.assertIn("!github.event.issue.pull_request",authorize)
        self.assertIn("github.event.comment.body == '/plasma-codex hello-c 981'",authorize)
        self.assertNotIn("needs: contract",authorize)
        self.assertNotIn("plasma_codex_postmerge_dispatch.py --event",wf)
        self.assertNotIn("github.event_name == 'push'",authorize)
        self.assertIn("needs.authorize.outputs.approved_sha == github.sha",wf)
        self.assertNotIn("workflow_dispatch:",wf)
        self.assertNotIn("codex --dangerously-bypass",wf)

    def test_retained_hil_reuses_existing_runner_for_sw_and_la(self):
        sw = (ROOT/".github/workflows/plasma-codex-software-mvp.yml").read_text()
        cases = (
            (".github/workflows/plasma-codex-software-mvp.yml",
             "/plasma-codex hello-c 981", "codex"),
            (".github/workflows/plasma-codex-la2016-direct.yml",
             "/plasma-codex la2016-direct 981", "loopback"),
        )
        for path, exact_owner_command, job in cases:
            with self.subTest(path=path):
                wf=(ROOT/path).read_text()
                self.assertEqual(wf.count("runs-on: [self-hosted, linux, x64, plasma-codex]"),1)
                worker=wf.split("\n  "+job+":\n",1)[1]
                self.assertIn("    needs: authorize\n",wf)
                self.assertTrue(
                    "needs.authorize.result == 'success'" in worker or
                    "needs.authorize.outputs.approved_sha == github.sha" in worker
                )
                self.assertIn("test \"$(id -un)\" = plasma-codex",worker)
                self.assertIn("test \"$RUNNER_NAME\" = SWPC-plasma-codex",worker)
                self.assertIn("github.actor == 'physicslu'",wf)
                self.assertIn("github.event.issue.number == 981",wf)
                self.assertIn("github.event.comment.body == '"+exact_owner_command+"'",wf)
                self.assertIn("!github.event.issue.pull_request",wf)
                self.assertIn("persist-credentials: false",worker)
        self.assertNotIn("gh pr merge",sw)
        self.assertNotIn("sudo bash",sw)
        self.assertNotIn("uhubctl ",sw)

    def test_unified_hil_does_not_authorize_hardware_from_pr_or_main_push(self):
        for path in (
            ".github/workflows/plasma-codex-software-mvp.yml",
            ".github/workflows/plasma-codex-la2016-direct.yml",
        ):
            with self.subTest(path=path):
                wf=(ROOT/path).read_text()
                self.assertIn("  pull_request:\n",wf)
                self.assertIn("  push:\n",wf)
                self.assertIn("    runs-on: ubuntu-24.04",wf)
                self.assertIn("    if: >-\n      github.event_name == 'issue_comment'",wf)
                self.assertNotIn("workflow_dispatch:\n",wf)
                self.assertNotIn("pull_request_target:\n",wf)
        sw=(ROOT/".github/workflows/plasma-codex-software-mvp.yml").read_text()
        auth=sw.split("\n  authorize:\n",1)[1].split("\n  codex:\n",1)[0]
        self.assertNotIn("github.event_name == 'push'",auth)
        self.assertIn("    if: ${{ github.event_name == 'push' || github.event_name == 'pull_request' }}".replace(chr(92)+ "$"+"{{", "$"+"{{"),sw)
        self.assertIn("test -z \"${SSH_AUTH_SOCK:-}\"".replace(chr(92)+ "$", "$"),sw)
        self.assertIn("network_access=false",sw)
        self.assertIn("Do not use external programs, sudo, SSH, networks, Z2/FPGA/USB/LA,",sw)
        self.assertIn("no API secret",sw)


if __name__=="__main__":
    unittest.main(verbosity=2)
