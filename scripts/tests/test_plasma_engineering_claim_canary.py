#!/usr/bin/env python3
"""Issue #981 claim canary OFFLINE negative tests; no GitHub write or real token."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_engineering_claim_canary as canary
import plasma_engineering_dispatch_gate1d as gate
RULE = ROOT / "specs/engineering-dispatch/claim-protection-ruleset-v1.json"
WF = ROOT / ".github/workflows/plasma-engineering-claim-canary.yml"
CI = ROOT / ".github/workflows/plasma-engineering-claim-canary-contract.yml"
HEAD, OTHER = "1" * 40, "2" * 40

class FakeGithub:
    def __init__(self):
        self.sha = None
        self.calls = []
        self.update_allowed = False
        self.force_allowed = False
        self.delete_allowed = False

    def __call__(self, method, path, payload):
        self.calls.append((method, path, payload))
        if (method, path) == ("GET", "/git/ref/" + canary.SHORT_REF):
            return (404, None) if self.sha is None else (
                200, {"ref": canary.REF, "object": {"sha": self.sha}})
        if (method, path) == ("POST", "/git/refs"):
            if self.sha is not None: return 422, None
            self.sha = payload["sha"]
            return 201, {"ref": canary.REF, "object": {"sha": self.sha}}
        if (method, path) == ("PATCH", "/git/refs/" + canary.SHORT_REF):
            allowed = self.force_allowed if payload["force"] else self.update_allowed
            if allowed:
                self.sha = payload["sha"]
                return 200, {"ref": canary.REF, "object": {"sha": self.sha}}
            return 403, None
        if (method, path) == ("DELETE", "/git/refs/" + canary.SHORT_REF):
            if self.delete_allowed:
                self.sha = None
                return 204, None
            return 403, None
        raise AssertionError("Unexpected mock transport call")

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proposal = json.loads(RULE.read_text())

    def event(self):
        return {"action": "created", "issue": {"number": 981},
                "comment": {"id": 123, "body": canary.COMMAND,
                            "user": {"login": "physicslu"}},
                "sender": {"login": "physicslu"},
                "repository": {"full_name": "physicslu/plasma"}}

    def env(self):
        return {"GITHUB_EVENT_NAME": "issue_comment",
                "GITHUB_ACTOR": "physicslu",
                "GITHUB_REPOSITORY": "physicslu/plasma",
                "GITHUB_REF": "refs/heads/main",
                "GITHUB_SHA": HEAD, "GITHUB_RUN_ID": "123",
                "GITHUB_RUN_ATTEMPT": "1"}

    def test_owner_exact_event_pass(self):
        r = canary.require_event(self.event(), self.env(), HEAD)
        self.assertEqual(r["ref"], canary.REF)
        self.assertEqual(r["comment_id"], 123)

    def test_forged_context_denied(self):
        for key, value in (
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_ACTOR", "attacker"),
            ("GITHUB_REPOSITORY", "attacker/repo"),
            ("GITHUB_REF", "refs/heads/dev"),
            ("GITHUB_SHA", OTHER),
            ("GITHUB_RUN_ID", "not-a-number"),
            ("GITHUB_RUN_ATTEMPT", "0"),
        ):
            bad = self.env(); bad[key] = value
            with self.subTest(key=key), self.assertRaises(canary.Stop):
                canary.require_event(self.event(), bad, HEAD)

    def test_comment_altered_or_non_owner_denied(self):
        for key in ("body", "owner", "sender", "issue", "pr", "action"):
            event = self.event()
            if key == "body": event["comment"]["body"] += "\n"
            if key == "owner": event["comment"]["user"]["login"] = "attacker"
            if key == "sender": event["sender"]["login"] = "attacker"
            if key == "issue": event["issue"]["number"] = 982
            if key == "pr": event["issue"]["pull_request"] = {}
            if key == "action": event["action"] = "edited"
            with self.subTest(key=key), self.assertRaises(canary.Stop):
                canary.require_event(event, self.env(), HEAD)

    def test_six_step_canary_and_permanent_ref(self):
        fake = FakeGithub(); trace = []
        result = canary.run_probes(fake, HEAD, OTHER, trace.append)
        self.assertEqual(result["step_count"], 6)
        self.assertEqual(fake.sha, HEAD)
        self.assertEqual(len(trace), 6)
        self.assertEqual([x["step"] for x in result["observations"]], list(gate.CANARY_TYPES))
        self.assertFalse(result["runtime_enabled"])
        self.assertFalse(result["token_identity_fully_qualified"])

    def test_replay_denied_without_second_write(self):
        fake = FakeGithub()
        canary.run_probes(fake, HEAD, OTHER)
        n = len(fake.calls)
        with self.assertRaisesRegex(canary.Stop, "CANARY_REF_ALREADY_PRESENT_OR_UNKNOWN"):
            canary.run_probes(fake, HEAD, OTHER)
        self.assertEqual(len(fake.calls), n + 1)
        self.assertEqual(fake.calls[-1][0], "GET")

    def test_mutable_update_fail_closed(self):
        for flag in ("update_allowed", "force_allowed"):
            fake = FakeGithub(); setattr(fake, flag, True)
            with self.subTest(flag=flag), self.assertRaisesRegex(
                    canary.Stop, "CANARY_UPDATE_PROTECTION_NOT_PROVEN"):
                canary.run_probes(fake, HEAD, OTHER)

    def test_mutable_delete_fail_closed(self):
        fake = FakeGithub(); fake.delete_allowed = True
        with self.assertRaisesRegex(canary.Stop, "CANARY_DELETE_PROTECTION_NOT_PROVEN"):
            canary.run_probes(fake, HEAD, OTHER)

    def test_create_failure_is_not_retried(self):
        calls = []
        def transport(method, path, payload):
            if method == "POST":
                calls.append(path)
                return 500, None
            return 404, None
        with self.assertRaisesRegex(canary.Stop, "CANARY_CREATE_NOT_CONFIRMED_NO_RETRY"):
            canary.run_probes(transport, HEAD, OTHER)
        self.assertEqual(len(calls), 1)

    def test_create_201_wrong_echo_denied(self):
        def transport(method, path, payload):
            return (404, None) if method == "GET" else (
                201, {"ref": canary.REF, "object": {"sha": OTHER}})
        with self.assertRaises(canary.Stop):
            canary.run_probes(transport, HEAD, OTHER)

    def test_distinct_sha_required(self):
        with self.assertRaisesRegex(canary.Stop, "CANARY_DISTINCT_COMMIT_REQUIRED"):
            canary.run_probes(FakeGithub(), HEAD, HEAD)

    def test_ref_readback_mismatch_denied(self):
        fake = FakeGithub(); fake.sha = OTHER
        with self.assertRaisesRegex(canary.Stop, "CANARY_REF_READBACK_MISMATCH"):
            canary.ref_readback(fake, HEAD)

    def test_ruleset_drift_denied(self):
        good = dict(self.proposal, id=canary.RULESET_ID,
                    source="physicslu/plasma", source_type="Repository")
        self.assertEqual(canary.confirmed_rulesets([good], self.proposal)["ruleset_id"],
                         canary.RULESET_ID)
        for bad in ([], [good, good],
                    [dict(good, enforcement="evaluate")],
                    [dict(good, bypass_actors=[{"actor_id": 1}])]):
            with self.subTest(bad=bad), self.assertRaises(canary.Stop):
                canary.confirmed_rulesets(bad, self.proposal)

    def test_ruleset_identity_and_unknown_overlap_denied(self):
        good = dict(self.proposal, id=canary.RULESET_ID,
                    source="physicslu/plasma", source_type="Repository")
        def transport(method, path, payload):
            if path == "/rulesets?includes_parents=true":
                return 200, [{"id": 20964250}, {"id": canary.RULESET_ID}]
            return 200, good
        canary.live_ruleset_preflight(transport, self.proposal)
        def unknown(method, path, payload):
            if path == "/rulesets?includes_parents=true":
                return 200, [{"id": 999999}, {"id": canary.RULESET_ID}]
            return transport(method, path, payload)
        with self.assertRaises(canary.Stop):
            canary.live_ruleset_preflight(unknown, self.proposal)

    def test_api_allowlist_and_payload_denied(self):
        with self.assertRaisesRegex(canary.Stop, "CANARY_API_ENDPOINT_DENIED"):
            canary.request("fake-token-over-sixteen", "DELETE", "/git/refs/heads/main")
        with self.assertRaisesRegex(canary.Stop, "CANARY_CREATE_PAYLOAD_DENIED"):
            canary.request("fake-token-over-sixteen", "POST", "/git/refs",
                           {"ref": "refs/heads/main", "sha": HEAD})
        with self.assertRaisesRegex(canary.Stop, "CANARY_TOKEN_MISSING"):
            canary.request("", "GET", "/rulesets?includes_parents=true")

    def test_api_token_not_in_url(self):
        class FakeResponse:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return None
            def read(self, size): return b'[]'
        with patch("urllib.request.urlopen", return_value=FakeResponse()) as invoke:
            code, val = canary.request("fake-token-over-sixteen", "GET",
                                       "/rulesets?includes_parents=true")
            self.assertEqual(code, 200)
            self.assertEqual(val, [])
            self.assertNotIn("fake-token", invoke.call_args.args[0].full_url)

    def test_report_does_not_attest_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "report.json"
            canary.safe_report(file, {"ref": canary.REF}, [], "NO_GO")
            doc = json.loads(file.read_text())
            self.assertIs(doc["runtime_enabled"], False)
            self.assertIs(doc["codex_executed"], False)

    def test_workflow_no_accidental_live_dispatch(self):
        workflow, contract = WF.read_text(), CI.read_text()
        self.assertIn("github.actor == 'physicslu'", workflow)
        self.assertIn(canary.COMMAND, workflow)
        self.assertIn("needs: authorize", workflow)
        self.assertIn("contents: write", workflow)
        self.assertIn("persist-credentials: false", workflow)
        self.assertIn("runs-on: ubuntu-24.04", workflow)
        self.assertIn("issue_comment:", workflow)
        self.assertIn("github.event_name != 'issue_comment'", workflow)
        self.assertIn("contents: read", contract)
        self.assertNotIn("issue_comment:", contract)
        for file in (workflow, contract):
            for forbidden in ("self-hosted", "sudo ", "workflow_dispatch:",
                              "codex exec", "pull-requests: write"):
                with self.subTest(forbidden=forbidden):
                    self.assertNotIn(forbidden, file)

if __name__ == "__main__":
    unittest.main(verbosity=2)
