#!/usr/bin/env python3
"""Gate 1C full-checkout negative security contracts; hosted/offline only."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_engineering_dispatch_gate1c as gate

SPEC = ROOT / "specs/engineering-dispatch"
WORKFLOWS = ROOT / ".github/workflows"
OWN_WORKFLOW = WORKFLOWS / "plasma-engineering-dispatch-gate1c-contract.yml"


class Gate1CSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main_rule = json.loads((SPEC/"fixtures/rulesets-main-only-negative.json").read_text())
        cls.positive_rule = json.loads((SPEC/"fixtures/rulesets-claim-protected-synthetic.json").read_text())
        cls.credentials = json.loads((SPEC/"credential-boundaries-v1.json").read_text())

    def test_real_main_only_ruleset_snapshot_is_no_go(self):
        r = gate.ruleset_preflight(self.main_rule)
        self.assertEqual(r["status"], "NO_GO_CLAIM_RULESET_MISSING")
        self.assertEqual(r["matching_rulesets"], 0)
        self.assertFalse(r["runtime_enabled"])
        self.assertEqual(r["live_create_update_delete_attestation"], "NOT_RUN")

    def test_synthetic_claim_ruleset_only_matches_configuration(self):
        r = gate.ruleset_preflight(self.positive_rule)
        self.assertEqual(r["status"], "RULESET_CONFIG_MATCH_ONLY")
        self.assertFalse(r["runtime_enabled"])
        self.assertEqual(r["live_create_update_delete_attestation"], "NOT_RUN")

    def test_bypass_force_push_deletion_scope_enforcement_must_fail_closed(self):
        for changed in ("evaluate", "target", "bypass", "missing-update",
                        "default-only", "excluded"):
            with self.subTest(changed=changed):
                p=copy.deepcopy(self.positive_rule)
                item=p[0]
                if changed=="evaluate": item["enforcement"]="evaluate"
                if changed=="target": item["target"]="tag"
                if changed=="bypass": item["bypass_actors"]=[{"actor_type":"RepositoryRole","actor_id":5}]
                if changed=="missing-update": item["rules"].pop()
                if changed=="default-only": item["conditions"]["ref_name"]["include"]=["~DEFAULT_BRANCH"]
                if changed=="excluded": item["conditions"]["ref_name"]["exclude"]=["refs/heads/plasma-engineering-claims/**"]
                self.assertEqual(gate.ruleset_preflight(p)["status"],
                                 "NO_GO_CLAIM_RULESET_MISSING")

    def test_create_push_globs_and_workflow_run_are_potentially_exposed(self):
        cases=[
            ("on: create\njobs: {}\n", "CREATE_REF_EVENT"),
            ("on: [push, pull_request]\n", "PUSH_UNRESTRICTED_OR_IGNORE_ONLY"),
            ('on:\n  push:\n    branches: ["**"]\n    paths: ["release/**"]\n', "PUSH_CLAIM_BRANCH"),
            ("on:\n  push:\n    branches-ignore:\n      - main\n", "PUSH_UNRESTRICTED_OR_IGNORE_ONLY"),
            ("on:\n  push:\n    branches:\n      - 'plasma-engineering-claims/**'\n", "PUSH_CLAIM_BRANCH"),
            ("on:\n  workflow_run:\n    workflows: [CI]\n", "WORKFLOW_RUN_CHAIN"),
            ("on: {push: null}\n", "UNCLASSIFIED_TRIGGER"),
        ]
        for source,reason in cases:
            with self.subTest(reason=reason):
                self.assertIn(reason,gate.inspect_workflow("fixture.yml",source)["risks"])

    def test_main_only_and_pull_request_are_not_direct_claim_ref_exposure(self):
        cases=[
            "on:\n  pull_request:\n    branches: [main]\n  push:\n    branches: [main]\n",
            "on:\n  push:\n    branches:\n      - main\n      - 'release/*'\n",
            "on: pull_request\n",
            "on:\n  workflow_dispatch:\n",
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(gate.inspect_workflow("fixture.yml",source)["risks"],[])

    def test_privileged_workflow_hints_cannot_override_risk(self):
        source=("on:\n  push:\n    branches: ['**']\n"
                "jobs:\n  bad:\n    runs-on: [self-hosted, linux]\n"
                "    permissions:\n      contents: write\n"
                "    steps:\n      - run: echo secrets.SECRET_NAME\n")
        r=gate.inspect_workflow("unsafe.yml",source)
        self.assertIn("PUSH_CLAIM_BRANCH",r["risks"])
        self.assertIn("SELF_HOSTED",r["privilege_hints"])
        self.assertIn("CONTENTS_WRITE",r["privilege_hints"])
        self.assertIn("SECRET_REFERENCE",r["privilege_hints"])

    def test_every_workflow_is_scanned_and_baseline_is_blocked(self):
        files=sorted([*WORKFLOWS.glob("*.yml"),*WORKFLOWS.glob("*.yaml")])
        # Gate 1 Catalog consolidation: five original C0 workflow bodies are
        # preserved as Git-identical archives and one dispatcher remains live.
        # Normalize the fleet count without weakening the scanner's exact
        # observed-file equality and fail-closed exposure assertions below.
        archived = sorted((ROOT / "docs/archive/ci-workflows/stm32c0-stages").glob("*.yml"))
        self.assertEqual(len(archived), 5)
        self.assertIn("device-catalog-stm32c0-stage-dispatch.yml",
                      {f.name for f in files})
        # Three LA-only Issue #981 workflows were deliberately retired with
        # the fixed JSON Host Supervisor; keep the full remaining scan.
        for obsolete in ("plasma-codex-la2016.yml",
                         "plasma-codex-la2016-direct.yml",
                         "plasma-codex-la2016-diagnose.yml"):
            self.assertNotIn(obsolete, {f.name for f in files})
        self.assertGreaterEqual(len(files) + len(archived) - 1, 322)
        report=gate.workflow_audit(WORKFLOWS)
        self.assertEqual(report["total"],len(files))
        self.assertEqual(report["scanned"],len(files))
        self.assertEqual(len(report["results"]),len(files))
        self.assertEqual({x.name for x in files},
                         {x["workflow"] for x in report["results"]})
        self.assertGreater(report["potential_exposures"],0)
        self.assertEqual(report["status"],"NO_GO_WORKFLOW_TRIGGER_RISK")
        prod=next(x for x in report["results"] if x["workflow"]=="product-release.yml")
        self.assertIn("PUSH_CLAIM_BRANCH",prod["risks"])
        self.assertFalse(report["runtime_enabled"])

    def test_invalid_files_and_missing_trigger_cannot_pass(self):
        with self.assertRaisesRegex(gate.Denied,"WORKFLOW_DIRECTORY_INVALID"):
            gate.workflow_audit(Path("/nonexistent/dir/for-gate1c"))
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/"a.yml").write_text("name: no trigger\njobs: {}\n")
            (folder/"b.yaml").symlink_to("a.yml")
            rows=gate.workflow_audit(folder)["results"]
            self.assertEqual(len(rows),2)
            self.assertIn("UNCLASSIFIED_TRIGGER",rows[0]["risks"])
            self.assertIn("UNREADABLE_FILE",rows[1]["risks"])

    def test_credential_roles_are_separated_not_deployed(self):
        r=gate.credential_contract(self.credentials)
        self.assertEqual(r["status"],"CREDENTIAL_CONTRACT_ONLY_PASS")
        self.assertFalse(r["runtime_enabled"])
        roles=self.credentials["roles"]
        self.assertTrue(roles["claimer"]["create_claim"])
        self.assertFalse(roles["claimer"]["run_codex"])
        self.assertTrue(roles["worker"]["run_codex"])
        self.assertFalse(roles["worker"]["create_claim"])
        self.assertEqual(roles["worker"]["permissions"],{"contents":"read"})

    def test_credential_escalation_and_token_exposure_denied(self):
        changes=[
            ("claimer","run_codex",True),
            ("worker","create_claim",True),
            ("worker","github_write_token_to_codex",True),
            ("worker","permissions",{"contents":"write"}),
            ("publisher","run_codex",True),
            ("authorizer","hosted_only",False),
            ("claimer","persist_credentials",True),
            ("claimer","permissions",{"contents":"write","issues":"write"}),
        ]
        for role,key,value in changes:
            with self.subTest(role=role,key=key):
                altered=copy.deepcopy(self.credentials)
                altered["roles"][role][key]=value
                with self.assertRaisesRegex(gate.Denied,"CREDENTIAL_PRIVILEGE_BOUNDARY_DENIED"):
                    gate.credential_contract(altered)

    def test_ci_has_no_issue_dispatch_or_live_secrets(self):
        wf=OWN_WORKFLOW.read_text()
        self.assertIn("runs-on: ubuntu-24.04",wf)
        self.assertIn("persist-credentials: false",wf)
        self.assertIn("contents: read",wf)
        for forbidden in ("\n  issue_comment:","\n  workflow_dispatch:",
                          "runs-on: [self-hosted","contents: write","OPENAI_API_KEY:",
                          "GITHUB_TOKEN:"):
            self.assertNotIn(forbidden,wf)
        src=(ROOT/"scripts/plasma_engineering_dispatch_gate1c.py").read_text()
        for forbidden in ("import subprocess","urllib.request","os.system("):
            self.assertNotIn(forbidden,src)

    def test_strict_cli_refuses_current_ruleset(self):
        cli=ROOT/"scripts/plasma_engineering_dispatch_gate1c.py"
        base=[sys.executable,str(cli)]
        negative=subprocess.run(base+["check-rulesets","--input",
            str(SPEC/"fixtures/rulesets-main-only-negative.json"),"--strict"],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(negative.returncode,2)
        self.assertEqual(json.loads(negative.stdout)["status"],"NO_GO_CLAIM_RULESET_MISSING")
        credential=subprocess.run(base+["check-credentials","--input",
            str(SPEC/"credential-boundaries-v1.json"),"--strict"],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(credential.returncode,0,credential.stderr)
        synthetic=subprocess.run(base+["check-rulesets","--input",
            str(SPEC/"fixtures/rulesets-claim-protected-synthetic.json"),"--strict"],
            capture_output=True,text=True,timeout=10)
        self.assertEqual(synthetic.returncode,0,synthetic.stderr)
        self.assertEqual(json.loads(synthetic.stdout)["live_create_update_delete_attestation"],
                         "NOT_RUN")


if __name__ == "__main__":
    unittest.main(verbosity=2)
