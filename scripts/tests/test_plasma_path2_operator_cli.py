#!/usr/bin/env python3
"""Offline contract tests for owner-approved Path 2 generic operator CLI.

No SWPC, SSH, Z2, FPGA Manager, USB, LA2016 or DUT is ever exercised.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_development_dispatch as dispatch

SHA = "a" * 40
REGISTRY = json.loads(
    (ROOT / "specs/engineering-dispatch/development-tasks-v1.json").read_text())


def work_order(**changes):
    data = {
        "schema": "plasma.development.work_order.v1",
        "objective": "Run a deterministic source-reviewed operator CLI.",
        "acceptance": "Record the real process exit without claiming hardware PASS.",
        "execution_path": "path2-cli",
        "capability": "operator-cli",
        "scope": "guarded-hardware",
        "script": "scripts/experiments/example.py",
        "argv": ["--probe", "value with spaces"],
        "timeout_seconds": 600,
    }
    data.update(changes)
    return data


def event(order):
    return {
        "action": "created",
        "issue": {"number": 981},
        "comment": {"id": 321123, "user": {"login": "physicslu"},
                    "body": dispatch.WORK_ORDER_PREFIX + json.dumps(order)},
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


def admitted(order):
    ev = event(order)
    req = dispatch.request(ev, context())
    task = dispatch.task_for_request(REGISTRY, req, ev)
    approval = dispatch.authorize(ev, context(), REGISTRY)
    return task, approval


class Path2OperatorCLI(unittest.TestCase):
    def test_generic_cli_has_no_operation_or_f1b_dependency(self):
        task, approval = admitted(work_order(
            script="pl/hil/swd04.py", argv=["--dpidr", "0x1ba01477"]))
        self.assertEqual(task["capability"], "operator-cli")
        self.assertEqual(task["verification"], "exit-code")
        self.assertEqual(task["timeout_seconds"], 600)
        self.assertNotIn("operation", task)
        self.assertNotIn("project", task)
        self.assertNotIn("authorized_operation", task)
        self.assertEqual(approval["execution_capability"], "operator-cli")
        self.assertEqual(approval["monitor_stage"], "Guarded CLI")

    def test_checked_in_script_runs_as_bounded_nonshell_process(self):
        task, approval = admitted(work_order())
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "scripts/experiments/example.py"
            source.parent.mkdir(parents=True)
            source.write_text('print("offline")\n')
            executor = Mock(return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout=b"offline\n", stderr=b""))
            result = dispatch.run_task(
                task, workspace=Path(td), approval=approval,
                executor=executor, sandbox=False)
        args, kwargs = executor.call_args
        self.assertEqual(args[0],
                         [sys.executable, str(source), "--probe", "value with spaces"])
        self.assertEqual(kwargs["timeout"], 600)
        self.assertFalse(kwargs.get("shell", False))
        self.assertEqual(result["status"],
                         "REAL_HARDWARE_CLI_EVIDENCE_REVIEW_REQUIRED")
        self.assertEqual(result["physical_hil"], "NOT_VERIFIED")
        self.assertEqual(result["exit_code"], 0)

    def test_invalid_fields_paths_and_timeouts_fail_before_execution(self):
        cases = (
            {"scope": "host-only"},
            {"operation": "download"},
            {"project": "pl/projects/z2-fixed-unified-site1"},
            {"script": "/usr/bin/python3"},
            {"script": "scripts/../private.py"},
            {"script": "scripts/experiments/bad.sh"},
            {"script": "scripts/experiments/../bad.py"},
            {"timeout_seconds": 1801},
            {"timeout_seconds": 0},
            {"timeout_seconds": True},
            {"argv": "not-an-array"},
            {"argv": ["good", "\nmalicious"]},
            {"argv": ["x" * 2049]},
            {"verification": "stdout-sha256"},
        )
        for fields in cases:
            with self.subTest(fields=fields), self.assertRaises(dispatch.Denied):
                admitted(work_order(**fields))

    def test_unapproved_digest_denied_and_no_process_spawn(self):
        task, approval = admitted(work_order())
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "scripts/experiments/example.py"
            source.parent.mkdir(parents=True)
            source.write_text('print("offline")\n')
            executor = Mock()
            with self.assertRaisesRegex(dispatch.Denied,
                                        "OPERATOR_CLI_APPROVAL_DENIED"):
                dispatch.run_task(
                    task, workspace=Path(td),
                    approval={**approval, "work_order_sha256": "b" * 64},
                    executor=executor)
            executor.assert_not_called()

    def test_missing_and_symlink_scripts_fail_closed(self):
        task, approval = admitted(work_order())
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "scripts/experiments"
            base.mkdir(parents=True)
            executor = Mock()
            with self.assertRaisesRegex(dispatch.Denied, "SCRIPT_NOT_FOUND"):
                dispatch.run_task(
                    task, workspace=Path(td), approval=approval,
                    executor=executor)
            external = Path(td) / "actual.py"
            external.write_text('print("outside")\n')
            (base / "example.py").symlink_to(external)
            with self.assertRaisesRegex(dispatch.Denied, "SCRIPT_NOT_FOUND"):
                dispatch.run_task(
                    task, workspace=Path(td), approval=approval,
                    executor=executor)
            executor.assert_not_called()

    def test_nonzero_exit_is_never_reported_pass(self):
        task, approval = admitted(work_order())
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "scripts/experiments/example.py"
            source.parent.mkdir(parents=True)
            source.write_text('raise RuntimeError("offline")\n')
            executor = Mock(return_value=subprocess.CompletedProcess(
                args=[], returncode=7, stdout=b"", stderr=b"error"))
            with self.assertRaisesRegex(dispatch.Denied, "COMMAND_FAILED"):
                dispatch.run_task(
                    task, workspace=Path(td), approval=approval,
                    executor=executor)

    def test_candidate_source_sha_binding_is_preserved(self):
        task, approval = admitted(work_order())
        approval = dict(approval)
        approval["pr_number"] = 1
        approval["pinned_sha"] = "b" * 40
        approval["source_sha"] = "b" * 40
        # Owner PR HEAD binding is provided by the trusted Dispatcher.
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "scripts/experiments/example.py"
            source.parent.mkdir(parents=True)
            source.write_text('print("offline")\n')
            executor = Mock(return_value=subprocess.CompletedProcess(
                args=[], returncode=0, stdout=b"ok", stderr=b""))
            result = dispatch.run_task(
                task, workspace=Path(td), approval=approval,
                executor=executor)
            self.assertEqual(result["exit_code"], 0)
            executor.assert_called_once()
            approval["source_sha"] = SHA
            executor.reset_mock()
            with self.assertRaisesRegex(dispatch.Denied,
                                        "OPERATOR_CLI_APPROVAL_DENIED"):
                dispatch.run_task(
                    task, workspace=Path(td), approval=approval,
                    executor=executor)
            executor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
