#!/usr/bin/env python3
"""Gate 1 executor choice: hardware-capability separation and fail closed."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import plasma_engineering_dispatch_v1 as core
import plasma_engineering_gate1_executor as gate

POLICY=ROOT/"specs/engineering-dispatch/capabilities-v1.json"
EXAMPLE=ROOT/"specs/engineering-dispatch/examples/software-readonly-v1.json"
WORKFLOW=ROOT/".github/workflows/plasma-engineering-gate1-executor-contract.yml"
OLD_WFS=ROOT/".github/workflows"


class Gate1ExecutorContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=json.loads(POLICY.read_text(encoding="utf-8"))
        cls.example=json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def example_for(self, cap: str) -> dict:
        order=copy.deepcopy(self.example)
        rule=self.policy["capabilities"][cap]
        order["capability"]=cap
        order["entrypoint"]=rule["entrypoint"]
        order["authorization_kind"]=("hardware-one-shot" if rule["hardware_authorization"]
                                      else "gate1-implementation")
        order["scope"]["required_permissions"]=list(rule["permissions"])
        order["scope"]["deny_resources"]=list(rule["must_deny"])
        order["timeout_seconds"]=min(120,rule["max_timeout_seconds"])
        return order

    def route(self, order: dict, executor: str) -> dict:
        return gate.plan_route(order,self.policy,{
            "executor":executor,"work_order_sha256":core.digest(order)})

    def test_software_chatgpt_direct_and_codex_are_alternatives(self):
        for cap in ("software-readonly","software-pr"):
            order=self.example_for(cap)
            for executor in ("chatgpt","codex"):
                with self.subTest(capability=cap,executor=executor):
                    result=self.route(order,executor)
                    expected=("chatgpt-direct-github" if executor=="chatgpt" else
                              "swpc-dedicated-codex")
                    self.assertEqual(result["lane"],expected)
                    self.assertFalse(result["hardware"])
                    self.assertFalse(result["hardware_permission_granted"])
                    self.assertFalse(result["runtime_enabled"])
                    self.assertFalse(result["github_owner_approval_verified"])

    def test_hardware_capabilities_route_to_swpc_for_either_executor(self):
        caps={"la2016-loopback":["repo:read","usb:la2016"],
              "z2-readonly":["repo:read","ssh:z2-readonly"],
              "z2-privileged":["repo:read","z2:hardware-owner"]}
        for cap,permissions in caps.items():
            for executor in ("chatgpt","codex"):
                with self.subTest(capability=cap,executor=executor):
                    order=self.example_for(cap)
                    result=self.route(order,executor)
                    self.assertEqual(result["lane"],"swpc-controlled-hardware")
                    self.assertTrue(result["hardware"])
                    self.assertTrue(result["hardware_one_shot_required"])
                    self.assertEqual(result["required_permissions"],permissions)
                    self.assertFalse(result["hardware_permission_granted"])
                    self.assertFalse(result["qualified_runtime_path"])
                    self.assertFalse(result["runtime_enabled"])
                    self.assertFalse(result["automatic_fallback_or_executor_switch"])

    def test_selection_change_changes_bound_digest(self):
        order=self.example_for("la2016-loopback")
        a=self.route(order,"chatgpt")
        b=self.route(order,"codex")
        self.assertNotEqual(a["selection_sha256"],b["selection_sha256"])
        self.assertEqual(len(a["selection_sha256"]),64)
        changed=copy.deepcopy(order)
        changed["objective"]="Perform a different, separately scoped hardware acceptance task."
        self.assertNotEqual(a["selection_sha256"],self.route(changed,"chatgpt")["selection_sha256"])

    def test_executor_is_not_a_new_capability_or_permission(self):
        for executor in ("chatgpt","codex"):
            order=self.example_for("software-pr")
            order["scope"]["required_permissions"].append("usb:la2016")
            with self.assertRaisesRegex(core.ContractDenied,"CAPABILITY_PERMISSIONS_MISMATCH"):
                self.route(order,executor)

    def test_hardware_one_shot_mandatory_for_both_executors(self):
        for cap in ("la2016-loopback","z2-readonly","z2-privileged"):
            for executor in ("chatgpt","codex"):
                order=self.example_for(cap)
                order["authorization_kind"]="gate1-implementation"
                with self.subTest(cap=cap,executor=executor):
                    with self.assertRaisesRegex(core.ContractDenied,"HARDWARE_ONE_SHOT_APPROVAL_REQUIRED"):
                        self.route(order,executor)

    def test_no_implicit_fpga_or_power_or_other_hardware_escalation(self):
        for cap in ("la2016-loopback","z2-readonly"):
            order=self.example_for(cap)
            order["scope"]["deny_resources"].remove("hub-power")
            with self.assertRaisesRegex(core.ContractDenied,"CAPABILITY_NEGATIVE_SCOPE_MISSING"):
                self.route(order,"codex")
        order=self.example_for("z2-privileged")
        order["scope"]["required_permissions"]=["repo:read","z2:hardware-owner","usb:la2016"]
        with self.assertRaisesRegex(core.ContractDenied,"CAPABILITY_PERMISSIONS_MISMATCH"):
            self.route(order,"codex")

    def test_rejects_unknown_executor_and_invalid_selection(self):
        order=self.example_for("software-pr")
        good={"executor":"chatgpt","work_order_sha256":core.digest(order)}
        for bad in (
            {**good,"executor":"chatgpt+codex"},
            {**good,"executor":"shell"},
            {**good,"executor":None},
            {**good,"executor":["chatgpt"]},
            {**good,"work_order_sha256":"0"*64},
            {**good,"sudo":True},
            "chatgpt",
        ):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(core.ContractDenied):
                    gate.plan_route(order,self.policy,bad)

    def test_approval_does_not_follow_from_route_plan(self):
        for cap in self.policy["capabilities"]:
            order=self.example_for(cap)
            for executor in ("chatgpt","codex"):
                result=self.route(order,executor)
                self.assertEqual(result["status"],gate.NO_RUNTIME_STATUS)
                self.assertFalse(result["github_owner_approval_verified"])
                self.assertFalse(result["runtime_enabled"])
                self.assertFalse(result["hardware_permission_granted"])
                self.assertTrue(result["gate2_merge_requires_separate_approval"])

    def test_policy_remains_entirely_disabled(self):
        self.assertTrue(all(x["runtime_enabled"] is False
                            for x in self.policy["capabilities"].values()))
        self.assertEqual(set(self.policy["capabilities"]),set(core.CAPABILITIES))

    def test_ci_hosted_offline_and_existing_codex_triggers_unchanged(self):
        s=WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-24.04",s)
        self.assertIn("persist-credentials: false",s)
        self.assertIn("contents: read",s)
        for forbidden in ("\n  issue_comment:","\n  workflow_dispatch:",
                          "runs-on: [self-hosted","contents: write",
                          "OPENAI_API_KEY:","GITHUB_TOKEN:"):
            self.assertNotIn(forbidden,s)
        # Current main has eleven legacy Codex workflows other than
        # the separate fixed software MVP. Keep this baseline explicit;
        # the reusable Dispatcher must not add a new plasma-codex-* workflow.
        existing=[p for p in OLD_WFS.glob("plasma-codex-*.yml")
                  if p.name != "plasma-codex-software-mvp.yml"]
        self.assertEqual(len(existing),11)
        self.assertTrue((OLD_WFS/"plasma-codex-software-mvp.yml").is_file())
        src=(ROOT/"scripts/plasma_engineering_gate1_executor.py").read_text()
        for forbidden in ("import subprocess","urllib.request","os.system(", "paramiko",
                          "create_ref(", "run_codex("):
            self.assertNotIn(forbidden,src)

    def test_offline_cli_never_runs_hardware(self):
        cli=ROOT/"scripts/plasma_engineering_gate1_executor.py"
        result=subprocess.run([sys.executable,str(cli),"--work-order",str(EXAMPLE),
               "--policy",str(POLICY),"--executor","chatgpt"],
               capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        body=json.loads(result.stdout)
        self.assertEqual(body["lane"],"chatgpt-direct-github")
        self.assertFalse(body["runtime_enabled"])
        self.assertFalse(body["github_owner_approval_verified"])


if __name__=="__main__":
    unittest.main(verbosity=2)
