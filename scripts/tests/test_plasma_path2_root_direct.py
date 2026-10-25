#!/usr/bin/env python3
"""Host-only contract tests for direct Path 2 CLI -> Protected Root Executor.

No SSH, FPGA load, MMIO or DUT is executed; mocked Root receipts are not HIL.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import plasma_development_dispatch as dispatch
import plasma_path2_runtime_integration as runtime

SHA = "a" * 40
PROJECT = "pl/projects/z2-fixed-unified-site1"
REGISTRY = json.loads((ROOT / "specs/engineering-dispatch/development-tasks-v1.json").read_text())


def make_event(operation="download", **changes):
    order = {
        "schema": "plasma.development.work_order.v1",
        "objective": "Run an explicitly approved protected Z2 operation.",
        "acceptance": "Return a verified real hardware receipt or fail closed.",
        "execution_path": "path2-cli",
        "capability": "z2-root-operation",
        "scope": "guarded-hardware",
        "operation": operation,
    }
    order.update(changes)
    return {
        "action": "created",
        "issue": {"number": 981},
        "comment": {
            "id": 91234, "user": {"login": "physicslu"},
            "body": dispatch.WORK_ORDER_PREFIX + json.dumps(order),
        },
        "sender": {"login": "physicslu"},
        "repository": {"full_name": "physicslu/plasma"},
    }


def context():
    return {
        "GITHUB_EVENT_NAME": "issue_comment",
        "GITHUB_ACTOR": "physicslu",
        "GITHUB_REPOSITORY": "physicslu/plasma",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": SHA,
        "GITHUB_RUN_ATTEMPT": "1",
    }


class RootDirectTests(unittest.TestCase):
    def test_dynamic_owner_work_order_needs_no_stage_or_profile(self):
        for operation in ("download", "test", "restore"):
            with self.subTest(operation=operation):
                event = make_event(operation)
                req = dispatch.request(event, context())
                task = dispatch.task_for_request(REGISTRY, req, event)
                admission = dispatch.authorize(event, context(), REGISTRY)
                self.assertEqual(task["operation"], operation)
                self.assertNotIn("stage", task)
                self.assertNotIn("project", task)
                self.assertNotIn("profile", task)
                self.assertEqual(admission["authorized_operation"], operation)
                self.assertEqual(admission["execution_capability"], "z2-root-operation")
                receipt = {
                    "stage": operation, "project": PROJECT, "source_sha": SHA,
                    "boot_id": "test-boot-12345", "real_z2": True,
                    "result": {
                        "download": "LOADED_AND_HELD",
                        "test": "IDENTITY_PASS",
                        "restore": "RESTORED_VERIFIED",
                    }[operation],
                }
                with patch.object(runtime.transport, "execute_operation",
                                  return_value=receipt) as execute:
                    result = dispatch.run_task(task, approval=admission)
                execute.assert_called_once_with(operation, SHA)
                self.assertEqual(result["operation"], operation)
                self.assertEqual(result["status"],
                                 "REAL_Z2_ROOT_OPERATION_EVIDENCE_REVIEW_REQUIRED")
                self.assertFalse(result["auto_next_operation"])

    def test_no_shell_project_stage_profile_or_automation(self):
        invalid = (
            {"operation": "full"},
            {"operation": "build"},
            {"operation": "../evil"},
            {"project": PROJECT},
            {"stage": "download"},
            {"profile_id": "f1b-site1-v1"},
            {"argv": ["--force"]},
            {"scope": "host-only"},
            {"capability": "cpu-only"},
        )
        for change in invalid:
            with self.subTest(change=change):
                with self.assertRaises(dispatch.Denied):
                    dispatch.request(make_event(**change), context())

    def test_denial_before_transport_and_no_unverified_receipt(self):
        event = make_event("test")
        req = dispatch.request(event, context())
        task = dispatch.task_for_request(REGISTRY, req, event)
        approval = dispatch.authorize(event, context(), REGISTRY)
        with patch.object(runtime.transport, "execute_operation") as execute:
            with self.assertRaisesRegex(runtime.RuntimeDenied,
                                        "PATH2_ROOT_OPERATION_APPROVAL_DENIED"):
                runtime.direct_root_operation(
                    task, {**approval, "authorized_operation": "restore"})
            execute.assert_not_called()
        for receipt in (
            {"stage": "test", "result": "IDENTITY_PASS"},
            {"stage": "download", "project": PROJECT, "source_sha": SHA,
             "boot_id": "test-boot-12345", "real_z2": True,
             "result": "LOADED_AND_HELD"},
            {"stage": "test", "project": PROJECT, "source_sha": SHA,
             "boot_id": "test-boot-12345", "real_z2": False,
             "result": "IDENTITY_PASS"},
        ):
            with self.subTest(receipt=receipt):
                with patch.object(runtime.transport, "execute_operation",
                                  return_value=receipt):
                    with self.assertRaisesRegex(runtime.RuntimeDenied,
                                                "PATH2_ROOT_OPERATION_RECEIPT_DENIED"):
                        runtime.direct_root_operation(task, approval)


if __name__ == "__main__":
    unittest.main()
