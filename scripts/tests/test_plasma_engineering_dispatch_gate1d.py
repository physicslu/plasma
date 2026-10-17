#!/usr/bin/env python3
"""Gate 1D security contract: NO live GitHub writes or any Codex/hardware."""
from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import plasma_engineering_dispatch_gate1d as gate

RULE=ROOT/"specs/engineering-dispatch/claim-protection-ruleset-v1.json"
WF=ROOT/".github/workflows/plasma-engineering-dispatch-gate1d-contract.yml"


class Gate1DContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.proposal=json.loads(RULE.read_text(encoding="utf-8"))

    def test_proposal_is_not_live_ruleset_and_allows_first_create(self) -> None:
        result=gate.validate_proposal(self.proposal)
        self.assertEqual(result["status"],"PROPOSAL_SCHEMA_PASS_NOT_APPLIED")
        self.assertEqual(result["create_restriction"],"NOT_CONFIGURED_BY_DESIGN")
        self.assertFalse(result["runtime_enabled"])
        self.assertEqual(set(result["rule_types"]),gate.RULE_TYPES)

    def test_restrict_creations_weak_rules_and_bypass_denied(self) -> None:
        edits=[
            lambda p:p["rules"].append({"type":"creation"}),
            lambda p:p["rules"].pop(),
            lambda p:p["rules"].append({"type":"deletion"}),
            lambda p:p.update(enforcement="evaluate"),
            lambda p:p.update(enforcement="disabled"),
            lambda p:p["bypass_actors"].append({"actor_id":1,"actor_type":"RepositoryRole","bypass_mode":"always"}),
            lambda p:p["conditions"]["ref_name"]["include"].__setitem__(0,"~DEFAULT_BRANCH"),
            lambda p:p["conditions"]["ref_name"]["exclude"].append("refs/heads/plasma-engineering-claims/**"),
            lambda p:p.update(target="tag"),
            lambda p:p.update(extra="unexpected"),
        ]
        for change in edits:
            with self.subTest(change=str(change)):
                p=copy.deepcopy(self.proposal)
                change(p)
                with self.assertRaises(gate.Denied):
                    gate.validate_proposal(p)

    def test_unprotected_main_only_readback_is_no_go(self) -> None:
        snapshot=[{
            "id":20964250,"name":"Protect Plasma main","target":"branch",
            "enforcement":"active","source":"physicslu/plasma",
            "source_type":"Repository","bypass_actors":[],
            "conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"],"exclude":[]}},
            "rules":[{"type":"deletion"},{"type":"non_fast_forward"}]
        }]
        output=gate.exact_live_ruleset(snapshot,self.proposal)
        self.assertEqual(output["status"],gate.STATUS_BLOCKED)
        self.assertEqual(output["matching_claim_rulesets"],0)
        self.assertFalse(output["runtime_enabled"])

    def test_synthetic_exact_readback_is_still_not_canary(self) -> None:
        rule=copy.deepcopy(self.proposal)
        rule.update(id=999001,source="physicslu/plasma",source_type="Repository")
        output=gate.exact_live_ruleset([rule],self.proposal)
        self.assertEqual(output["status"],"RULESET_READBACK_MATCH_NOT_LIVE_CANARY")
        self.assertEqual(output["canary"],"NOT_RUN")
        self.assertFalse(output["runtime_enabled"])

    def test_readback_unknown_origin_multiple_or_overlapping_rules_denied(self) -> None:
        exact=copy.deepcopy(self.proposal)
        exact.update(id=100,source="physicslu/plasma",source_type="Repository")
        bad=[copy.deepcopy(exact),copy.deepcopy(exact)]
        self.assertEqual(gate.exact_live_ruleset(bad,self.proposal)["status"],gate.STATUS_BLOCKED)
        for key,value in (
            ("source","other/repo"),("source_type","Organization"),
            ("enforcement","evaluate"),("bypass_actors",[{"actor_type":"RepositoryRole","actor_id":5}]),
            ("id",None),
        ):
            with self.subTest(key=key):
                p=copy.deepcopy(exact)
                p[key]=value
                self.assertEqual(gate.exact_live_ruleset([p],self.proposal)["status"],gate.STATUS_BLOCKED)

    def test_broad_ruleset_also_matching_claim_branch_forces_no_go(self) -> None:
        exact=copy.deepcopy(self.proposal)
        exact.update(id=100,source="physicslu/plasma",source_type="Repository")
        broader=copy.deepcopy(exact)
        broader["id"]=101
        broader["name"]="Global branch control"
        broader["conditions"]["ref_name"]["include"]=["~ALL"]
        r=gate.exact_live_ruleset([exact,broader],self.proposal)
        self.assertEqual(r["status"],gate.STATUS_BLOCKED)
        self.assertEqual(r["matching_claim_rulesets"],2)

    def test_canary_receipts_are_only_untrusted_schemas(self) -> None:
        valid=[{"step":k,"result":"OBSERVED","ref":gate.CANARY_REF}
               for k in gate.CANARY_TYPES]
        r=gate.verify_canary_receipts(valid)
        self.assertEqual(r["status"],"CANARY_RECEIPT_SCHEMA_ONLY_NOT_TRUSTED")
        self.assertEqual(r["step_count"],6)
        self.assertEqual(r["live_github_attestation"],"NOT_VERIFIED")
        self.assertFalse(r["runtime_enabled"])
        for bad in (
            valid[:-1],
            valid[::-1],
            [{**x,"ref":"refs/heads/main"} for x in valid],
            [{**x,"result":"ASSUMED"} for x in valid],
        ):
            with self.assertRaises(gate.Denied):
                gate.verify_canary_receipts(bad)

    def test_json_duplicate_key_and_symlink_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/"bad.json"
            p.write_text('{"a":1,"a":2}')
            with self.assertRaisesRegex(gate.Denied,"JSON_DUPLICATE_KEY"):
                gate.read_json(p)
            link=pathlib.Path(tmp)/"alias.json"
            link.symlink_to(p)
            with self.assertRaisesRegex(gate.Denied,"JSON_INPUT_INVALID"):
                gate.read_json(link)

    def test_cli_defaults_to_not_applied_and_no_go_for_unprotected(self) -> None:
        script=ROOT/"scripts/plasma_engineering_dispatch_gate1d.py"
        def run(*args):
            return subprocess.run([sys.executable,str(script),*args],
                                  capture_output=True,text=True,timeout=6)
        proposal=run("proposal","--proposal",str(RULE))
        self.assertEqual(proposal.returncode,0,proposal.stderr)
        self.assertEqual(json.loads(proposal.stdout)["status"],"PROPOSAL_SCHEMA_PASS_NOT_APPLIED")
        current_fixture=ROOT/"specs/engineering-dispatch/fixtures/rulesets-main-only-negative.json"
        blocked=run("ruleset-readback","--proposal",str(RULE),"--snapshot",str(current_fixture))
        self.assertEqual(blocked.returncode,2,blocked.stderr)
        self.assertEqual(json.loads(blocked.stdout)["status"],gate.STATUS_BLOCKED)

    def test_hosted_only_workflow_and_no_live_github_actions(self) -> None:
        text=WF.read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-24.04",text)
        self.assertIn("persist-credentials: false",text)
        self.assertIn("contents: read",text)
        for bad in ("\n  issue_comment:", "\n  workflow_dispatch:",
                    "runs-on: [self-hosted","contents: write",
                    "OPENAI_API_KEY:","GITHUB_TOKEN:"):
            self.assertNotIn(bad,text)
        src=(ROOT/"scripts/plasma_engineering_dispatch_gate1d.py").read_text()
        for bad in ("import requests","urllib.request","subprocess.run(",
                    "os.system(","delete_ref(","create_branch("):
            self.assertNotIn(bad,src)


if __name__=="__main__":
    unittest.main(verbosity=2)
