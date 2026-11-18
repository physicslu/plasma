#!/usr/bin/env python3
"""Offline positive/negative HIL-A2 contract tests. Never execute SSH or hardware."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_development_dispatch as dev
import plasma_hil_a2_cpu_only as a2

TASK_ID = "hil-a2-cpu-only"
WORK_ORDER = ROOT / "specs/engineering-dispatch/work-orders/hil-a2-cpu-only-r1.json"
POLICY = ROOT / "specs/engineering-dispatch/capabilities-v1.json"
SCHEMA = ROOT / "specs/engineering-dispatch/work-order-v1.schema.json"
REGISTRY = ROOT / "specs/engineering-dispatch/development-tasks-v1.json"
WORKFLOW = ROOT / ".github/workflows/plasma-engineering-runtime-dispatch.yml"


def expected_report():
    return {
        "schema": "plasma.hil.a2.z2.cpu-only.v1",
        "status": "PASS", "execution_target": "ENROLLED_REAL_Z2_CORTEX_A9",
        "os": "Linux", "cpu": "Cortex-A9", "cpu_part": "0xc09",
        "machine": "armv7l", "pointer_bits": 32, "byteorder": "little",
        "device_tree_zynq7000": True, "board_identity_exact": "NOT_QUALIFIED",
        "library_sha256": a2.ARTIFACT_SHA256, "function": a2.FUNCTION,
        "calls": 1000, "library_load": "PASS", "temporary_cleanup": "PASS",
        "mmio_uio": "NOT_RUN", "fpga_reload": "NOT_RUN",
        "dut_programming": "NOT_RUN", "hub_power": "NOT_RUN", "m1": "NO_GO",
    }


class A2Gate1OfflineContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work_order = json.loads(WORK_ORDER.read_text())
        cls.policy = json.loads(POLICY.read_text())
        cls.schema = json.loads(SCHEMA.read_text())
        cls.registry = json.loads(REGISTRY.read_text())
        cls.task = dev.task_by_id(cls.registry, TASK_ID)

    def test_work_order_and_capability_are_disabled_and_bounded(self):
        task = self.task
        work = self.work_order
        capability = self.policy["capabilities"]["z2-cpu-only"]
        self.assertNotIn("activation", task)
        self.assertEqual(task["execution_path"], "path2-cli")
        self.assertEqual(task["capability"], "z2-cpu-only")
        self.assertNotIn("runtime_status", work)
        self.assertEqual(work["reviewed_main_sha"], "121a7b3da6ecc1513b47d397ad70e68c9820f789")
        self.assertEqual(work["authorization_kind"], "hardware-one-shot")
        self.assertEqual(work["capability"], capability["entrypoint"])
        self.assertEqual(work["entrypoint"], "z2-cpu-only")
        self.assertEqual(work["scope"]["required_permissions"], capability["permissions"])
        self.assertFalse(capability["runtime_enabled"])
        self.assertTrue(capability["hardware_authorization"])
        self.assertEqual(self.policy["status"], "CONTRACT_ONLY_NO_RUNTIME_DISPATCH")
        self.assertNotIn("runtime_status", self.schema["properties"])
        for forbidden in ("usb", "fpga", "mmio", "dut", "hub-power",
                          "network-instrument", "repository-write", "host-root"):
            self.assertIn(forbidden, work["scope"]["deny_resources"])
            self.assertIn(forbidden, capability["must_deny"])
        self.assertNotIn("z2:hardware-owner", capability["permissions"])
        self.assertNotIn("sudo", capability["permissions"])

    def test_live_admission_needs_exact_claim_and_first_attempt(self):
        with self.assertRaisesRegex(a2.Denied, "A2_APPROVAL_RECEIPT_INVALID"):
            a2.live_gate(self.work_order, env={})
        claim = self.owner_plan()
        work_sha = claim["work_order_sha256"]
        expected = "refs/heads/plasma-engineering-claims/981/a2-1234-" + work_sha[:16] + "-r1"
        self.assertEqual(claim["claim_ref"], expected)
        trusted = {
            "PLASMA_HIL_A2_CLAIM_REF": expected,
            "PLASMA_HIL_A2_WORK_ORDER_SHA256": work_sha,
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_REF": "refs/heads/main",
            "RUNNER_NAME": "SWPC-plasma-codex",
            "RUNNER_ENVIRONMENT": "self-hosted",
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_SHA": claim["pinned_sha"],
        }
        with patch.object(a2.os, "geteuid", return_value=1001):
            a2.live_gate(self.work_order, approval=claim, env=trusted)
            for key, bad in (
                ("GITHUB_RUN_ATTEMPT", "2"),
                ("PLASMA_HIL_A2_CLAIM_REF", "wrong"),
                ("PLASMA_HIL_A2_WORK_ORDER_SHA256", "0" * 64),
                ("GITHUB_SHA", "f" * 40),
                ("RUNNER_NAME", "other-runner"),
                ("GITHUB_EVENT_NAME", "pull_request"),
            ):
                env = dict(trusted, **{key: bad})
                with self.subTest(key=key), self.assertRaisesRegex(
                    a2.Denied, "A2_LIVE_GATE_DENIED"
                ):
                    a2.live_gate(self.work_order, approval=claim, env=env)
            forged = dict(claim, comment_id=9999)
            with self.assertRaisesRegex(a2.Denied, "A2_CLAIM_BINDING_DENIED"):
                a2.live_gate(self.work_order, approval=forged, env=trusted)
        with patch.object(a2.os, "geteuid", return_value=0):
            with self.assertRaisesRegex(a2.Denied, "A2_LIVE_GATE_DENIED"):
                a2.live_gate(self.work_order, approval=claim, env=trusted)

    def event_and_context(self):
        ctx = {
            "GITHUB_EVENT_NAME": "issue_comment", "GITHUB_ACTOR": "physicslu",
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "a" * 40,
            "GITHUB_RUN_ATTEMPT": "1",
        }
        event = {
            "action": "created",
            "issue": {"number": 981},
            "comment": {"id": 1234, "user": {"login": "physicslu"},
                        "body": "/plasma-dispatch run hil-a2-cpu-only 981"},
            "sender": {"login": "physicslu"},
            "repository": {"full_name": "physicslu/plasma"},
        }
        return event, ctx

    def owner_plan(self):
        event, ctx = self.event_and_context()
        return dev.authorize(event, ctx, self.registry)

    def test_immutable_owner_task_authorization_and_hostile_negative(self):
        self.assertEqual(self.owner_plan()["task_id"], TASK_ID)
        plan = self.owner_plan()
        self.assertEqual(plan["pinned_sha"], "a" * 40)
        self.assertRegex(plan["work_order_sha256"], r"^[0-9a-f]{64}$")
        reg = copy.deepcopy(self.registry)
        reg["tasks"][TASK_ID]["execution_path"] = "path3-codex"
        with self.assertRaisesRegex(dev.Denied, "A2_TASK_FIELDS_DENIED"):
            dev.task_by_id(reg, TASK_ID)
        reg = copy.deepcopy(self.registry)
        reg["tasks"][TASK_ID]["work_order"] = "../../../untrusted.json"
        with self.assertRaisesRegex(dev.Denied, "A2_TASK_BINDING_DENIED"):
            dev.task_by_id(reg, TASK_ID)
        reg = copy.deepcopy(self.registry)
        reg["tasks"][TASK_ID]["activation"] = "OWNER_APPROVED_ONE_SHOT"
        with self.assertRaisesRegex(dev.Denied, "A2_TASK_FIELDS_DENIED"):
            dev.task_by_id(reg, TASK_ID)
        ev, ctx = self.event_and_context()
        for key, value in (
            ("GITHUB_RUN_ATTEMPT", "2"),
            ("GITHUB_REF", "refs/heads/feature"),
            ("GITHUB_ACTOR", "attacker"),
            ("GITHUB_EVENT_NAME", "pull_request"),
        ):
            with self.subTest(key=key), self.assertRaises(dev.Denied):
                dev.authorize(ev, dict(ctx, **{key: value}), self.registry)
        for field, value in (
            ("body", "/plasma-dispatch run hil-a2-cpu-only 981; echo bad"),
            ("body", "/plasma-dispatch run hil-a2-cpu-only 981\\n"),
            ("id", -2),
        ):
            forged = copy.deepcopy(ev)
            forged["comment"][field] = value
            with self.subTest(field=field), self.assertRaises(dev.Denied):
                dev.authorize(forged, ctx, self.registry)

    def test_a2_rejects_pr_candidate_even_if_owner_and_sha_are_valid(self):
        event, context = self.event_and_context()
        candidate_sha = "b" * 40
        event["comment"]["body"] = (
            "/plasma-dispatch run hil-a2-cpu-only --pr 1053 --sha "
            + candidate_sha + " 981"
        )
        pr = {
            "number": 1053, "state": "open", "merged_at": None,
            "user": {"login": "physicslu"},
            "base": {"ref": "main", "repo": {"full_name": "physicslu/plasma"}},
            "head": {
                "ref": "agent/hil-a2-cpu-only-path2-gate1-20261019",
                "sha": candidate_sha,
                "repo": {"full_name": "physicslu/plasma"}
            },
        }
        with self.assertRaisesRegex(dev.Denied, "A2_TRUSTED_MAIN_ONLY"):
            dev.authorize(event, context, self.registry, pr_info=pr)

    def test_a2_contract_never_uses_per_run_activation_toggles(self):
        self.assertNotIn("activation", self.task)
        self.assertNotIn("runtime_status", self.work_order)
        workflow = WORKFLOW.read_text()
        self.assertIn("path: trusted", workflow)
        self.assertIn("path: candidate", workflow)
        self.assertIn("  development-codex:", workflow)
        self.assertIn("plasma-path3-source.patch", workflow)
        self.assertIn("  development-claim:", workflow)
        self.assertNotIn("PLASMA_HIL_A2_CPU_ONLY_ENABLED", workflow)

    def test_remote_report_exact_positive_and_hostile_negative(self):
        report = expected_report()
        self.assertEqual(a2.verify_cpu_report(report)["calls"], 1000)
        mutants = (
            ("execution_target", "QEMU_ARMV7"),
            ("cpu", "Other"),
            ("cpu_part", "0xc08"),
            ("machine", "x86_64"),
            ("pointer_bits", 64),
            ("calls", 999),
            ("library_sha256", "0" * 64),
            ("mmio_uio", "PASS"),
            ("fpga_reload", "PASS"),
            ("temporary_cleanup", "NOT_RUN"),
            ("status", "FAIL"),
            ("board_identity_exact", "PASS"),
            ("exit_code", 0),
        )
        for key, value in mutants:
            changed = dict(report, **{key: value})
            with self.subTest(field=key), self.assertRaises(a2.Denied):
                a2.verify_cpu_report(changed)

    def test_fixed_remote_code_compiles_but_does_not_execute(self):
        compile(a2.REMOTE_PROGRAM, "<A2-REMOTE-NEVER-EXECUTED>", "exec")
        source = a2.REMOTE_PROGRAM
        self.assertIn("ctypes.CDLL", source)
        self.assertIn("range(1000)", source)
        self.assertIn("TemporaryDirectory", source)
        for forbidden in ("/dev/mem", "/dev/uio", "fpga_manager", "sudo",
                          "uhubctl", "plasmactl", "devmem", "os.system("):
            self.assertNotIn(forbidden, source)

    def test_no_network_before_double_gate(self):
        with patch.object(a2, "load_module", side_effect=AssertionError("MUST_NOT_IMPORT_SSH")):
            with self.assertRaisesRegex(a2.Denied, "A2_APPROVAL_RECEIPT_INVALID"):
                a2.run_once(self.work_order, Path("/nonexistent/a1"), approval={})

    def test_source_mismatch_fails_before_ssh(self):
        with self.assertRaises((a2.Denied, FileNotFoundError, ValueError, OSError)):
            a2.verify_source(Path("/nonexistent/plasma-hil-a1"))

    def test_shared_workflow_no_dedicated_yaml_or_pr_hardware(self):
        workflow = WORKFLOW.read_text()
        self.assertIn("development-authorize:", workflow)
        self.assertIn("development-execute:", workflow)
        self.assertIn("needs.development-authorize.outputs.execution_path == 'path2-cli'", workflow)
        self.assertIn("plasma-hil-a2-source", workflow)
        self.assertIn("scripts/tests/test_plasma_hil_a2_cpu_only.py", workflow)
        self.assertIn("development-claim:", workflow)
        self.assertIn("needs: [development-authorize, development-claim]", workflow)
        self.assertIn("needs.development-claim.result == 'success'", workflow)
        a2_job = workflow.split("  development-execute:", 1)[1].split("\n  development-codex:", 1)[0]
        self.assertNotIn("needs.development-codex.result == 'success'", a2_job)
        self.assertIn("needs.development-claim.outputs.claim_ref == needs.development-authorize.outputs.claim_ref", workflow)
        self.assertIn("github.rest.git.createRef", workflow)
        self.assertIn("github.rest.git.getRef", workflow)
        self.assertIn("github.run_attempt == 1", workflow)
        self.assertIn("always() &&", workflow)
        self.assertIn("PLASMA_HIL_A2_CLAIM_REF:", workflow)
        self.assertNotIn("PLASMA_HIL_A2_CPU_ONLY_ENABLED", workflow)
        self.assertIn("actions/download-artifact@", workflow)
        self.assertNotIn("plasma-hil-a2-cpu-only.yml", workflow)
        self.assertFalse((ROOT / ".github/workflows/plasma-hil-a2-cpu-only.yml").exists())
        self.assertIn("github.event_name == 'pull_request' || github.event_name == 'push'", workflow)
        self.assertIn("github.event_name == 'issue_comment'", workflow)
        self.assertNotIn("pull_request_target:", workflow)

    def test_existing_nine_nine_paths_unchanged(self):
        self.assertEqual(dev.task_by_id(self.registry, "nine-nine-path2")["execution_path"],
                         "path2-cli")
        self.assertEqual(dev.task_by_id(self.registry, "nine-nine-path3")["execution_path"],
                         "path3-codex")


if __name__ == "__main__":
    unittest.main()
