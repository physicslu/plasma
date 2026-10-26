#!/usr/bin/env python3
"""Host-only regression: retired fixed Z2 root operation is not a Path 2 route.

No SSH, FPGA Manager, SWD, LA2016 or DUT access is performed here. The
separately installed protected FPGA Image recovery program is not removed.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_development_dispatch as dispatch
import plasma_path2_runtime_integration as runtime

SHA = "a" * 40
REGISTRY = json.loads(
    (ROOT / "specs/engineering-dispatch/development-tasks-v1.json").read_text()
)


def make_event(operation="download", **changes):
    order = {
        "schema": "plasma.development.work_order.v1",
        "objective": "Attempt retired Z2 root operation through Path 2.",
        "acceptance": "Reject it before any remote device operation.",
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


class RetiredRootRouteTests(unittest.TestCase):
    def test_all_former_root_work_orders_denied_before_authorize(self):
        for operation in ("download", "test", "restore", "full", "build"):
            with self.subTest(operation=operation):
                event = make_event(operation)
                with self.assertRaisesRegex(
                        dispatch.Denied, "WORK_ORDER_CAPABILITY_DENIED"):
                    dispatch.request(event, context())
                with self.assertRaisesRegex(
                        dispatch.Denied, "WORK_ORDER_CAPABILITY_DENIED"):
                    dispatch.authorize(event, context(), REGISTRY)

    def test_old_root_task_cannot_bypass_dynamic_parser(self):
        with patch.object(runtime, "direct_root_operation") as old:
            with self.assertRaisesRegex(
                    dispatch.Denied, "RETIRED_PATH2_ROOT_OPERATION"):
                dispatch.run_task(
                    {"capability": "z2-root-operation", "operation": "download"},
                    approval={"execution_capability": "z2-root-operation"})
            old.assert_not_called()

    def test_root_recovery_implementation_is_separately_retained(self):
        # Do not remove a still-important recovery program just to retire the
        # fixed Dispatcher command list; image restoration remains independent.
        source = (ROOT / "scripts/z2/plasma-path2-root-entry").read_text()
        self.assertIn("pl.hil.fpga_image_root", source)
        self.assertIn("PATH2_ROOT_REQUIRED", source)
        self.assertNotIn("scripts/plasma_development_dispatch.py", source)


if __name__ == "__main__":
    unittest.main()
