#!/usr/bin/env python3
"""Negative provenance / replay / unrelated merge checks. No GitHub or SWPC."""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_codex_postmerge_dispatch as adm


class PostmergeGateTests(unittest.TestCase):
    SHA = "f" * 40
    PARENT = "e" * 40

    def fixtures(self):
        env = {
            "GITHUB_EVENT_NAME": "push",
            "GITHUB_ACTOR": "physicslu",
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": self.SHA,
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_RUN_ID": "39199999999",
        }
        event = {
            "ref": "refs/heads/main", "after": self.SHA,
            "head_commit": {"id": self.SHA},
            "repository": {"full_name": "physicslu/plasma"},
            "created": False, "deleted": False, "forced": False,
        }
        gate1 = {
            "number": 1033, "state": "closed", "merged": True,
            "merge_commit_sha": adm.GATE1_MERGE,
            "head": {"sha": adm.GATE1_HEAD},
            "base": {"ref": "main"},
            "user": {"login": "physicslu"},
            "merged_by": {"login": "physicslu"},
            "body": "Owner-approved Gate 1 — executor: SWPC Codex (Mode 2)",
        }
        activation = {
            "number": adm.ACTIVATION_PR, "state": "closed", "merged": True,
            "merge_commit_sha": self.SHA,
            "base": {"ref": "main"},
            "head": {"ref": adm.ACTIVATION_HEAD_BRANCH},
            "user": {"login": "physicslu"},
            "merged_by": {"login": "physicslu"},
            "body": "This activates a fixed one-shot job.\n" + adm.MARKER + "\n",
            "changed_files": 2,
        }
        associated = [{"number": adm.ACTIVATION_PR,
                       "merge_commit_sha": self.SHA}]
        files = [
            {"filename": ".github/workflows/plasma-codex-software-mvp.yml",
             "status": "modified"},
            {"filename": "scripts/plasma_codex_postmerge_dispatch.py",
             "status": "added"},
        ]
        commit = {"sha": self.SHA, "parents": [{"sha": self.PARENT}]}
        return [event, env, gate1, activation, associated, files, commit]

    def good(self, parts):
        return adm.validate(*parts)

    def test_exact_owner_gate1_and_gate2_merge_only(self):
        result = self.good(self.fixtures())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["executor"], "swpc-codex")
        self.assertEqual(result["gate1_pr"], 1033)
        self.assertEqual(result["activation_pr"], adm.ACTIVATION_PR)
        self.assertFalse(result["live_model_executed"])

    def test_gate1_actor_is_not_inferred_from_other_or_chatgpt_task(self):
        for bad in ("Gate 1 — executor: ChatGPT", "", "executor: hosted Codex"):
            x = self.fixtures()
            x[2]["body"] = bad
            with self.subTest(bad=bad), self.assertRaises(adm.Refused):
                self.good(x)

    def test_unauthorized_main_push_and_other_pr_never_dispatch(self):
        variations = [
            (1, "GITHUB_EVENT_NAME", "pull_request"),
            (1, "GITHUB_ACTOR", "another-user"),
            (1, "GITHUB_REF", "refs/heads/feature"),
            (1, "GITHUB_RUN_ATTEMPT", "2"),
            (1, "GITHUB_REPOSITORY", "other/repository"),
            (1, "GITHUB_SHA", "b" * 40),
            (3, "number", 1081),
            (3, "merge_commit_sha", "a" * 40),
            (3, "merged", False),
            (3, "state", "open"),
            (3, "changed_files", 99),
        ]
        for index, key, val in variations:
            x = self.fixtures()
            x[index][key] = val
            with self.subTest(index=index,key=key),self.assertRaises(adm.Refused):
                self.good(x)

    def test_untrusted_actor_and_approval_provenance_fail_closed(self):
        for index, key, val in (
            (2, "head", {"sha": "b"*40}),
            (2, "merge_commit_sha", "c"*40),
            (2, "merged_by", {"login": "attacker"}),
            (3, "merged_by", {"login": "attacker"}),
            (3, "user", {"login": "attacker"}),
            (3, "base", {"ref": "not-main"}),
            (3, "head", {"ref": "not-approved"}),
            (3, "body", "activation without marker"),
            (3, "body", adm.MARKER + "\n" + adm.MARKER),
        ):
            x = self.fixtures()
            x[index][key] = val
            with self.subTest(index=index,key=key),self.assertRaises(adm.Refused):
                self.good(x)

    def test_commit_association_and_squash_are_required(self):
        for mutator in (
            lambda x: x[4].append({"number": 2000,"merge_commit_sha": self.SHA}),
            lambda x: x[4][0].update({"number": 999}),
            lambda x: x[4][0].update({"merge_commit_sha": "a"*40}),
            lambda x: x[6].update({"parents": [{"sha":"e"*40},{"sha":"d"*40}]}),
            lambda x: x[6].update({"sha": "c"*40}),
        ):
            x = self.fixtures()
            mutator(x)
            with self.assertRaises(adm.Refused):
                self.good(x)

    def test_file_scope_rejects_hardware_and_model_auth_changes(self):
        for bad in ("examples/hello-world/main.c", ".github/workflows/z2-ps-release.yml",
                    "scripts/evil.sh", "AGENTS.md", "secrets/token.txt"):
            x = self.fixtures()
            x[5][1]["filename"] = bad
            with self.subTest(file=bad), self.assertRaises(adm.Refused):
                self.good(x)
        x = self.fixtures()
        x[5][1]["status"] = "removed"
        with self.assertRaises(adm.Refused):
            self.good(x)

    def test_push_event_replay_force_delete_and_branch_are_denied(self):
        for key, val in (
            ("ref", "refs/heads/another"), ("after", "a"*40),
            ("forced", True), ("created", True), ("deleted", True),
            ("head_commit", {"id": "a"*40}),
        ):
            x = self.fixtures()
            x[0][key] = val
            with self.subTest(key=key), self.assertRaises(adm.Refused):
                self.good(x)

    def test_contract_wiring_offline_only_and_no_comment_trigger(self):
        wf=(ROOT/".github/workflows/plasma-codex-software-mvp.yml").read_text()
        self.assertNotIn("issue_comment:",wf)
        self.assertNotIn("workflow_dispatch:",wf)
        self.assertIn("github.event_name == 'push'",wf)
        self.assertIn("needs: contract",wf)
        self.assertIn("plasma_codex_postmerge_dispatch.py --event",wf)
        self.assertIn("needs.authorize.outputs.approved_sha == github.sha",wf)
        self.assertIn("test \"$APPROVED_SHA\" = \"$GITHUB_SHA\"",wf)
        self.assertIn("runs-on: [self-hosted, linux, x64, plasma-codex]",wf)
        self.assertIn("needs: [authorize, codex]",wf)
        self.assertIn("pull-requests: write",wf)
        self.assertIn("persist-credentials: false",wf)
        self.assertNotIn("OPENAI_API_KEY",wf)
        self.assertEqual(wf.count("runs-on: [self-hosted, linux, x64, plasma-codex]"),1)
        self.assertEqual(wf.count("runs-on: ubuntu-24.04"),3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
