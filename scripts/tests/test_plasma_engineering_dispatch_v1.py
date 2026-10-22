#!/usr/bin/env python3
"""Gate 1A: standalone, HOSTED/OFFLINE only dispatcher security contracts."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_engineering_dispatch_v1 as dispatch

SCHEMA_PATH = ROOT / "specs/engineering-dispatch/work-order-v1.schema.json"
POLICY_PATH = ROOT / "specs/engineering-dispatch/capabilities-v1.json"
SAMPLE_PATH = ROOT / "specs/engineering-dispatch/examples/software-readonly-v1.json"
WORKFLOW_PATH = ROOT / ".github/workflows/plasma-engineering-dispatch-contract.yml"


class DispatchGate1AContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.policy = json.loads(POLICY_PATH.read_text())
        cls.sample = json.loads(SAMPLE_PATH.read_text())
        cls.schema = json.loads(SCHEMA_PATH.read_text())

    def order(self) -> dict:
        return copy.deepcopy(self.sample)

    def event(self, order: dict | None = None, *, comment_id: int = 101) -> dict:
        order = order or self.order()
        return {
            "action": "created", "issue": {"number": order["issue_number"]},
            "comment": {"id": comment_id, "user": {"login": "physicslu"},
                        "body": dispatch.approval_command(order)},
            "sender": {"login": "physicslu"},
            "repository": {"full_name": "physicslu/plasma"},
        }

    def context(self, order: dict | None = None) -> dict:
        order = order or self.order()
        return {
            "event_name": "issue_comment", "actor": "physicslu",
            "repository": "physicslu/plasma", "ref": "refs/heads/main",
            "checked_out_sha": order["reviewed_main_sha"],
            "run_id": 99999901, "run_attempt": 1,
        }

    def check_denied(self, order: dict, expected: str, policy: dict | None = None) -> None:
        with self.assertRaisesRegex(dispatch.ContractDenied, expected):
            dispatch.validate_work_order(order, policy or self.policy)

    def test_schema_and_offline_mode_match_implementation(self) -> None:
        self.assertEqual(self.schema["$schema"],
                         "https://json-schema.org/draft/2020-12/schema")
        self.assertFalse(self.schema["additionalProperties"])
        self.assertEqual(set(self.schema["required"]), dispatch.ORDER_KEYS)
        self.assertEqual(set(self.schema["properties"]), dispatch.ORDER_KEYS)
        self.assertEqual(set(self.schema["properties"]["scope"]["required"]),
                         dispatch.SCOPE_KEYS)
        self.assertFalse(self.schema["properties"]["scope"]["additionalProperties"])
        self.assertEqual(self.policy["status"], dispatch.NO_RUNTIME)
        self.assertEqual(set(self.policy["capabilities"]), dispatch.CAPABILITIES)
        self.assertTrue(all(p["runtime_enabled"] is False
                            for p in self.policy["capabilities"].values()))
        self.assertEqual(self.sample["issue_number"], 900001)  # inert fixture only
        rule = dispatch.validate_work_order(self.order(), self.policy)
        self.assertEqual(rule["worker_class"], "hosted-offline")
        self.assertEqual(self.sample["reviewed_main_sha"],
                         "e93ce8974d00d3e930026333785a5645e89d61cf")

    def test_digest_is_canonical_and_approval_binds_immutable_content(self) -> None:
        original = self.order()
        reversed_order = dict(reversed(list(original.items())))
        self.assertEqual(dispatch.digest(original), dispatch.digest(reversed_order))
        self.assertEqual(len(dispatch.digest(original)), 64)
        self.assertRegex(dispatch.approval_command(original),
                         r"^/plasma-dispatch approve offline-safety-review rev=1 "
                         r"sha256=[0-9a-f]{64} kind=gate1-implementation$")
        valid = dispatch.authorize(self.event(original), self.context(original),
                                   original, self.policy)
        self.assertEqual(valid["status"], "AUTH_CONTRACT_PASS_NO_DISPATCH")
        self.assertIs(valid["runtime_enabled"], False)
        self.assertEqual(valid["worker_class"], "hosted-offline")
        self.assertEqual(valid["work_order_sha256"], dispatch.digest(original))
        tampered = copy.deepcopy(original)
        tampered["objective"] += " unauthorized append"
        with self.assertRaisesRegex(dispatch.ContractDenied, "APPROVAL_DIGEST_OR_BODY_MISMATCH"):
            dispatch.authorize(self.event(original), self.context(original),
                               tampered, self.policy)
        tampered = self.order()
        tampered["revision"] += 1
        with self.assertRaisesRegex(dispatch.ContractDenied, "APPROVAL_DIGEST_OR_BODY_MISMATCH"):
            dispatch.authorize(self.event(original), self.context(original),
                               tampered, self.policy)

    def test_event_provenance_and_exact_owner_command_negative(self) -> None:
        order = self.order()
        event = self.event(order)
        ctx = self.context(order)
        for field, bad in {
            "event_name": "pull_request", "actor": "untrusted",
            "repository": "attacker/plasma", "ref": "refs/heads/feature",
            "checked_out_sha": "0"*40, "run_id": False,
            "run_attempt": 0,
        }.items():
            with self.subTest(field=field):
                mutated = copy.deepcopy(ctx)
                mutated[field] = bad
                with self.assertRaises(dispatch.ContractDenied):
                    dispatch.authorize(event, mutated, order, self.policy)
        for dotted, bad in (
            ("action", "edited"), ("issue.number", 42),
            ("issue.pull_request", {"url": "https://example.invalid/pull"}),
            ("sender.login", "untrusted"),
            ("comment.user.login", "untrusted"),
            ("repository.full_name", "untrusted/plasma"),
            ("comment.body", dispatch.approval_command(order) + "\n"),
            ("comment.body", "/plasma-dispatch approve x; touch /tmp/unsafe"),
            ("comment.id", 0),
        ):
            with self.subTest(dotted=dotted):
                mutated = copy.deepcopy(event)
                x = mutated
                parts = dotted.split(".")
                for item in parts[:-1]:
                    x = x[item]
                x[parts[-1]] = bad
                with self.assertRaises(dispatch.ContractDenied):
                    dispatch.authorize(mutated, ctx, order, self.policy)
        ctx["injected_context_field"] = "untrusted"
        with self.assertRaisesRegex(dispatch.ContractDenied, "GITHUB_CONTEXT_INVALID"):
            dispatch.authorize(event, ctx, order, self.policy)

    def test_paths_unknown_fields_and_strict_numeric_types(self) -> None:
        for path in ("../secrets", "/etc/passwd", "docs/../other", "a//b",
                     "docs\0bad", "a\\b", "-danger"):
            with self.subTest(path=repr(path)):
                order = self.order()
                order["scope"]["allow_repo_paths"] = [path]
                self.check_denied(order, "WORK_ORDER_PATHS_INVALID")
        for key,value,reason in (
            ("revision",True,"WORK_ORDER_REVISION_INVALID"),
            ("issue_number",False,"WORK_ORDER_ISSUE_INVALID"),
            ("timeout_seconds",0,"WORK_ORDER_TIMEOUT_INVALID"),
            ("reviewed_main_sha","HEAD","WORK_ORDER_PIN_INVALID"),
            ("requested_by","untrusted","WORK_ORDER_OWNER_DENIED"),
            ("authorization_kind","merge","WORK_ORDER_AUTHORIZATION_KIND_INVALID"),
            ("capability","sudo-shell","CAPABILITY_UNKNOWN"),
        ):
            with self.subTest(key=key):
                order = self.order()
                order[key] = value
                self.check_denied(order, reason)
        order = self.order()
        order["arbitrary_shell"] = "echo hello"
        self.check_denied(order, "WORK_ORDER_FIELDS_INVALID")
        order = self.order()
        order["scope"]["extra"] = True
        self.check_denied(order, "WORK_ORDER_SCOPE_INVALID")
        order = self.order()
        order["acceptance"] = ["repeat this"] * 2
        self.check_denied(order, "WORK_ORDER_ACCEPTANCE_INVALID")

    def test_capability_segregation_hardware_must_have_one_shot(self) -> None:
        order = self.order()
        order["capability"] = "la2016-loopback"
        order["entrypoint"] = "la2016-direct"
        order["scope"]["required_permissions"] = ["repo:read", "usb:la2016"]
        order["scope"]["deny_resources"].remove("usb")
        order["timeout_seconds"] = 300
        self.check_denied(order, "HARDWARE_ONE_SHOT_APPROVAL_REQUIRED")
        order["authorization_kind"] = "hardware-one-shot"
        rule = dispatch.validate_work_order(order, self.policy)
        self.assertEqual(rule["worker_class"], "la2016-isolated")
        self.assertIs(rule["runtime_enabled"], False)
        self.assertTrue(rule["hardware_authorization"])
        order["scope"]["deny_resources"].remove("z2")
        self.check_denied(order, "CAPABILITY_NEGATIVE_SCOPE_MISSING")
        order["scope"]["deny_resources"].append("z2")
        order["scope"]["required_permissions"].append("z2:hardware-owner")
        self.check_denied(order, "CAPABILITY_PERMISSIONS_MISMATCH")
        order = self.order()
        order["scope"]["required_permissions"] = ["repo:read", "repo:write-branch"]
        self.check_denied(order, "CAPABILITY_PERMISSIONS_MISMATCH")
        bad_policy = copy.deepcopy(self.policy)
        bad_policy["capabilities"]["la2016-loopback"]["runtime_enabled"] = True
        self.check_denied(self.order(), "RUNTIME_DISPATCH_FORBIDDEN_GATE1A",bad_policy)
        bad_policy = copy.deepcopy(self.policy)
        bad_policy["capabilities"]["z2-privileged"]["runtime_enabled"] = True
        self.check_denied(self.order(), "RUNTIME_DISPATCH_FORBIDDEN_GATE1A",bad_policy)

    def test_offline_local_claim_deduplicates_comment_and_run_retries(self) -> None:
        order = self.order()
        plan = dispatch.authorize(self.event(order), self.context(order),
                                  order, self.policy)
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t) / "ledger"
            folder.mkdir(mode=0o700)
            result = dispatch.claim_offline(plan, folder)
            self.assertTrue(result.exists())
            self.assertEqual(result.stat().st_mode & 0o777, 0o600)
            repeated = copy.deepcopy(plan)
            repeated["comment_id"] = 102
            repeated["run_id"] += 1
            with self.assertRaisesRegex(dispatch.ContractDenied,
                                        "WORK_ORDER_REVISION_ALREADY_CLAIMED"):
                dispatch.claim_offline(repeated, folder)
            upgraded = copy.deepcopy(plan)
            upgraded["revision"] = 2
            # Version 2 still requires independently validated owner approval
            # in production; this only tests ledger key isolation.
            self.assertNotEqual(dispatch.replay_key(upgraded),
                                dispatch.replay_key(plan))
            self.assertTrue(dispatch.claim_offline(upgraded, folder).exists())
            os.chmod(folder, 0o755)
            with self.assertRaisesRegex(dispatch.ContractDenied, "REPLAY_DIRECTORY_NOT_PRIVATE"):
                dispatch.claim_offline(plan, folder)
            os.chmod(folder, 0o700)

    def test_parallel_claim_only_one_wins(self) -> None:
        from concurrent.futures import ThreadPoolExecutor
        plan = dispatch.authorize(self.event(), self.context(),
                                  self.order(), self.policy)
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t) / "ledger"
            folder.mkdir(mode=0o700)
            def attempt(_: int) -> str:
                try:
                    dispatch.claim_offline(plan, folder)
                    return "CLAIMED"
                except dispatch.ContractDenied:
                    return "DENIED"
            with ThreadPoolExecutor(max_workers=12) as pool:
                results = list(pool.map(attempt, range(12)))
            self.assertEqual(results.count("CLAIMED"), 1)
            self.assertEqual(results.count("DENIED"), 11)

    def test_json_parser_rejects_duplicate_or_nonfinite_keys(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            file = Path(t) / "input.json"
            for content,code in (
                ('{"revision":1,"revision":2}', "JSON_DUPLICATE_KEY"),
                ('{"foo":NaN}',"JSON_CONSTANT_DENIED"),
                ("{" * 33000,"JSON_FILE_DENIED"),
            ):
                file.write_text(content)
                with self.assertRaisesRegex(dispatch.ContractDenied, code):
                    dispatch.load_json(file)

    def test_cli_only_validates_and_never_executes_workflow(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "scripts/plasma_engineering_dispatch_v1.py"),
             "validate", "--work-order", str(SAMPLE_PATH),
             "--policy", str(POLICY_PATH)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            check=False, timeout=8,
        )
        self.assertEqual(completed.returncode, 0,completed.stderr)
        out = json.loads(completed.stdout)
        self.assertEqual(out["status"], "VALIDATED_OFFLINE_ONLY_NO_DISPATCH")
        self.assertIs(out["runtime_enabled"], False)
        source = (ROOT / "scripts/plasma_engineering_dispatch_v1.py").read_text()
        self.assertNotIn("import subprocess",source)
        self.assertNotIn("import requests",source)
        self.assertNotIn("os.system(",source)
        self.assertNotIn("os.exec",source)
        self.assertNotIn("urllib",source)
        self.assertNotIn("github.event.comment.body",source)
        wf = WORKFLOW_PATH.read_text()
        self.assertIn("runs-on: ubuntu-24.04", wf)
        self.assertIn("persist-credentials: false", wf)
        self.assertNotIn("issue_comment:", wf)
        self.assertNotIn("workflow_dispatch:", wf)
        self.assertNotIn("runs-on: [self-hosted", wf)
        self.assertNotIn("actions/upload-artifact", wf)
        self.assertNotIn("permissions: write-all", wf)
        self.assertNotIn("sudo ", wf)



KL25_PREFLIGHT_PATH = ROOT / "specs/engineering-dispatch/work-orders/kl25-hardware-identity-preflight-v1.json"
DEV_TASKS_PATH = ROOT / "specs/engineering-dispatch/development-tasks-v1.json"


class Kl25HardwareIdentityPreflightContracts(unittest.TestCase):
    """Path 1 only: validate a future Path 2 plan without any live hardware."""

    @classmethod
    def setUpClass(cls):
        cls.order = dispatch.load_json(KL25_PREFLIGHT_PATH)
        cls.policy = dispatch.load_json(POLICY_PATH)

    def test_kl25_scope_is_contract_only_not_hardware_inventory(self):
        o = self.order
        rule = dispatch.validate_work_order(o, self.policy)
        self.assertEqual(o["work_order_id"], "kl25-hardware-identity-preflight")
        self.assertEqual(o["authorization_kind"], "gate1-implementation")
        self.assertEqual(o["capability"], "software-readonly")
        self.assertEqual(o["entrypoint"], "offline-analysis")
        self.assertFalse(rule["hardware_authorization"])
        self.assertFalse(rule["runtime_enabled"])
        self.assertEqual(rule["worker_class"], "hosted-offline")
        self.assertEqual(o["scope"]["required_permissions"], ["repo:read"])
        self.assertEqual(set(o["scope"]["deny_resources"]), set(rule["must_deny"]))
        self.assertIn("MKL25Z128VLK4", o["objective"])
        self.assertIn("9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c", o["objective"])
        required = " ".join(o["acceptance"])
        for term in ("SDID", "FCFG1", "FCFG2", "NOT_RUN",
                     "L1 CANDIDATE", "NXP L2=0", "Execution Authorized=false",
                     "Job Selectable=false", "mass-erase", "unprotect"):
            with self.subTest(term=term):
                self.assertIn(term, required)
        # No executable Path 2 task is registered by this offline contract.
        active = dispatch.load_json(DEV_TASKS_PATH)
        self.assertNotIn(o["work_order_id"], active["tasks"])
        self.assertEqual(self.policy["status"], dispatch.NO_RUNTIME)

    def test_kl25_capability_and_resource_escalations_fail_closed(self):
        for key, value in (
            ("capability", "z2-readonly"),
            ("capability", "z2-privileged"),
            ("authorization_kind", "hardware-one-shot"),
            ("entrypoint", "z2-inventory"),
            ("reviewed_main_sha", "HEAD"),
            ("requested_by", "not-owner"),
        ):
            o = copy.deepcopy(self.order)
            o[key] = value
            with self.subTest(field=key, value=value):
                with self.assertRaises(dispatch.ContractDenied):
                    dispatch.validate_work_order(o, self.policy)
        for resource in self.order["scope"]["deny_resources"]:
            o = copy.deepcopy(self.order)
            o["scope"]["deny_resources"].remove(resource)
            with self.subTest(missing=resource):
                with self.assertRaisesRegex(dispatch.ContractDenied,
                                            "CAPABILITY_NEGATIVE_SCOPE_MISSING"):
                    dispatch.validate_work_order(o, self.policy)

    def test_kl25_runtime_and_operation_fields_are_never_admitted(self):
        for field, value in (
            ("runtime_enabled", True),
            ("allow_hardware", True),
            ("execution_authorized", True),
            ("job_selectable", True),
            ("catalog_level", 2),
            ("commands", ["openocd -c init", "flash erase", "reset"]),
            ("privileged_device_paths", ["/dev/bus/usb"]),
        ):
            o = copy.deepcopy(self.order)
            o[field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(dispatch.ContractDenied, "WORK_ORDER_FIELDS_INVALID"):
                    dispatch.validate_work_order(o, self.policy)
        o = copy.deepcopy(self.order)
        o["scope"]["required_permissions"] = ["usb:la2016"]
        with self.assertRaises(dispatch.ContractDenied):
            dispatch.validate_work_order(o, self.policy)
        p = copy.deepcopy(self.policy)
        p["capabilities"]["software-readonly"]["runtime_enabled"] = True
        with self.assertRaisesRegex(dispatch.ContractDenied,
                                    "RUNTIME_DISPATCH_FORBIDDEN_GATE1A"):
            dispatch.validate_work_order(self.order, p)

    def test_kl25_approval_digest_is_offline_and_mutation_bound(self):
        o = self.order
        e = {
            "action": "created",
            "issue": {"number": 981},
            "comment": {"id": 1234, "user": {"login": "physicslu"},
                        "body": dispatch.approval_command(o)},
            "sender": {"login": "physicslu"},
            "repository": {"full_name": "physicslu/plasma"},
        }
        ctx = {"event_name": "issue_comment", "actor": "physicslu",
               "repository": "physicslu/plasma", "ref": "refs/heads/main",
               "checked_out_sha": o["reviewed_main_sha"],
               "run_id": 1001, "run_attempt": 1}
        # Synthetic offline owner-event fixture: not an actual issue comment.
        receipt = dispatch.authorize(e, ctx, o, self.policy)
        self.assertEqual(receipt["status"], "AUTH_CONTRACT_PASS_NO_DISPATCH")
        self.assertIs(receipt["runtime_enabled"], False)
        self.assertEqual(receipt["work_order_sha256"], dispatch.digest(o))
        for changed in (
            {"revision": 2},
            {"objective": o["objective"] + " bypass source identity"},
            {"capability": "z2-readonly"},
        ):
            mutant = copy.deepcopy(o)
            mutant.update(changed)
            with self.subTest(changed=changed):
                with self.assertRaises(dispatch.ContractDenied):
                    dispatch.authorize(e, ctx, mutant, self.policy)

    def test_kl25_only_existing_offline_ci_acceptance_no_device_trigger(self):
        wf = WORKFLOW_PATH.read_text()
        self.assertIn('"specs/engineering-dispatch/**"', wf)
        self.assertIn("python3 scripts/tests/test_plasma_engineering_dispatch_v1.py", wf)
        self.assertIn("runs-on: ubuntu-24.04", wf)
        self.assertNotIn("runs-on: [self-hosted", wf)
        self.assertNotIn("issue_comment:", wf)
        self.assertNotIn("workflow_dispatch:", wf)
        self.assertNotIn("sudo ", wf)

if __name__ == "__main__":
    unittest.main(verbosity=2)
