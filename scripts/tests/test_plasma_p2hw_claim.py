#!/usr/bin/env python3
"""Offline contract tests: Path 2 one-shot hardware cross-Run claim.

No GitHub API, SWPC, SSH, Z2, FPGA, Manager or DUT is ever exercised. The
GitHub ref store is an in-memory fake with GitHub's atomic create semantics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts/tests"))
import plasma_development_dispatch as dispatch
import test_plasma_path2_operator_cli as op

SHA = "c" * 40
WF = ROOT / ".github/workflows/plasma-engineering-runtime-dispatch.yml"
# Frozen from main aaacc16a8: the A2 one-shot contract must stay byte-identical.
A2_BLOCK_SHA256 = {
    "workflow_a2_job": "e787f19c4fad39697cc5fd9cee0b6f197120f49cfb69c2f5137529af97241852",
    "authorize_a2": "fa6689f2e6ebec4d6793c5910041a06376d7d1c5e0c631bb9dbce7126349c587",
    "run_task_a2": "42aa0f5e85b1b871bcb9ee0e294c86c753c933487dfe4e428d948e3a8eeabb6c",
}


def load_order(argv=None, **changes):
    return op.work_order(script=dispatch.P2HW_SCRIPT,
                         argv=argv if argv is not None else
                         ["measure", "--output", "x", "--run-batch"], **changes)


class FakeGitHub:
    """GitHub git refs: create is atomic (201 once, then 422); never update."""

    def __init__(self):
        self.refs, self.lock, self.creates = {}, threading.Lock(), 0

    def create(self, ref, sha):
        with self.lock:
            self.creates += 1
            if ref in self.refs:
                return 422, {"message": "Reference already exists"}
            self.refs[ref] = sha
            return 201, {"ref": ref, "object": {"sha": sha}}

    def read(self, ref):
        with self.lock:
            if ref not in self.refs:
                return 404, {}
            return 200, {"ref": ref, "object": {"sha": self.refs[ref]}}


class Classification(unittest.TestCase):
    def test_only_run_batch_of_the_load_script_is_one_shot(self):
        task = lambda **k: {"capability": "operator-cli", "script": dispatch.P2HW_SCRIPT, **k}
        # Over-classifying only demands a claim; any argparse abbreviation counts.
        for argv in (["--run-batch"], ["measure", "--run-b"], ["--run"], ["--ru"], ["--r"],
                     ["--run-batch=1"]):
            self.assertTrue(dispatch.one_shot_hardware(task(argv=argv)), argv)
        for argv in (["measure", "--output", "x"], ["--recovery-sec", "15"], ["--"], []):
            self.assertFalse(dispatch.one_shot_hardware(task(argv=argv)), argv)
        self.assertFalse(dispatch.one_shot_hardware(
            {"capability": "operator-cli", "script": "scripts/plasmactl", "argv": ["--run-batch"]}))
        self.assertFalse(dispatch.one_shot_hardware(
            {"capability": "cpu-only", "script": dispatch.P2HW_SCRIPT, "argv": ["--run-batch"]}))

    def test_ref_is_keyed_by_full_digest(self):
        ref = dispatch.p2hw_claim_ref("ab" * 32)
        self.assertEqual(ref, "refs/heads/plasma-engineering-claims/981/p2hw-" + "ab" * 32)
        for bad in ("ab" * 16, "AB" * 32, None, 1):
            with self.assertRaisesRegex(dispatch.Denied, "P2HW_WORK_ORDER_DIGEST_INVALID"):
                dispatch.p2hw_claim_ref(bad)


class AtomicClaim(unittest.TestCase):
    ref = dispatch.P2HW_CLAIM_PREFIX + "d" * 64

    def claim(self, gh, attempt="1", ref=None):
        return dispatch.claim_hardware_once(gh.create, gh.read, claim_ref=ref or self.ref,
                                            sha=SHA, run_attempt=attempt)

    def test_first_claim_creates_and_reads_back(self):
        gh = FakeGitHub()
        receipt = self.claim(gh)
        self.assertEqual(receipt["status"], "CLAIM_CREATED_AND_READBACK")
        self.assertEqual(gh.refs, {self.ref: SHA})

    def test_repeated_authorization_is_denied(self):
        gh = FakeGitHub()
        self.claim(gh)
        with self.assertRaisesRegex(dispatch.Denied, "P2HW_CLAIM_DUPLICATE"):
            self.claim(gh)
        self.assertEqual(gh.creates, 2)
        self.assertEqual(gh.refs, {self.ref: SHA})

    def test_independent_concurrent_runs_exactly_one_wins(self):
        for _ in range(25):
            gh, barrier, results = FakeGitHub(), threading.Barrier(4), []

            def run():
                barrier.wait()
                try:
                    results.append(self.claim(gh)["status"])
                except dispatch.Denied as exc:
                    results.append(str(exc))
            threads = [threading.Thread(target=run) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(sorted(results), ["CLAIM_CREATED_AND_READBACK"] +
                             ["P2HW_CLAIM_DUPLICATE"] * 3)
            self.assertEqual(len(gh.refs), 1)

    def test_replay_attempt_denied_before_any_api_call(self):
        create, read = Mock(), Mock()
        for attempt in ("2", None, "01"):
            with self.assertRaisesRegex(dispatch.Denied, "P2HW_REPLAY_RUN_ATTEMPT_DENIED"):
                dispatch.claim_hardware_once(create, read, claim_ref=self.ref, sha=SHA,
                                             run_attempt=attempt)
        create.assert_not_called()
        read.assert_not_called()

    def test_ambiguous_creation_fails_closed_without_retry(self):
        for outcome in (TimeoutError(), OSError(), (500, {}), (201, {}),
                        (201, {"ref": "refs/heads/x", "object": {"sha": SHA}})):
            create = Mock(side_effect=[outcome] if isinstance(outcome, Exception) else None,
                          return_value=None if isinstance(outcome, Exception) else outcome)
            read = Mock()
            with self.assertRaisesRegex(dispatch.Denied, "P2HW_CLAIM_UNKNOWN"):
                dispatch.claim_hardware_once(create, read, claim_ref=self.ref, sha=SHA,
                                             run_attempt="1")
            self.assertEqual(create.call_count, 1)
            read.assert_not_called()

    def test_rejected_or_mismatched_readback_denied(self):
        create = Mock(return_value=(422, {}))
        read = Mock(return_value=(404, {}))
        with self.assertRaisesRegex(dispatch.Denied, "P2HW_CLAIM_REJECTED"):
            dispatch.claim_hardware_once(create, read, claim_ref=self.ref, sha=SHA,
                                         run_attempt="1")
        create = Mock(return_value=(201, {"ref": self.ref, "object": {"sha": SHA}}))
        for readback in ((200, {"ref": self.ref, "object": {"sha": "e" * 40}}), (404, {}),
                         TimeoutError()):
            read = Mock(side_effect=[readback] if isinstance(readback, Exception) else None,
                        return_value=None if isinstance(readback, Exception) else readback)
            with self.assertRaisesRegex(dispatch.Denied, "P2HW_CLAIM_READBACK_DENIED"):
                dispatch.claim_hardware_once(create, read, claim_ref=self.ref, sha=SHA,
                                             run_attempt="1")

    def test_ref_and_sha_validation(self):
        gh = FakeGitHub()
        for ref in ("refs/heads/plasma-engineering-claims/981/a2-1-" + "d" * 16 + "-r1",
                    dispatch.P2HW_CLAIM_PREFIX + "d" * 63):
            with self.assertRaisesRegex(dispatch.Denied, "P2HW_CLAIM_REF_INVALID"):
                self.claim(gh, ref=ref)
        self.assertEqual(gh.creates, 0)


class Admission(unittest.TestCase):
    def test_authorize_binds_claim_to_work_order_digest(self):
        order = load_order()
        task, approval = op.admitted(order)
        self.assertEqual(approval["hardware_claim_ref"],
                         dispatch.p2hw_claim_ref(approval["work_order_sha256"]))
        self.assertEqual(approval["work_order_sha256"], dispatch.work_order_digest(order))

    def test_identical_order_from_new_comment_maps_to_same_claim(self):
        order = load_order()
        first = dispatch.authorize(op.event(order), op.context(), op.REGISTRY)
        ev = op.event(order)
        ev["comment"]["id"] = 999999
        second = dispatch.authorize(ev, op.context(), op.REGISTRY)
        self.assertEqual(first["hardware_claim_ref"], second["hardware_claim_ref"])

    def test_authorize_denies_workflow_rerun(self):
        ctx = {**op.context(), "GITHUB_RUN_ATTEMPT": "2"}
        with self.assertRaisesRegex(dispatch.Denied, "P2HW_REPLAY_RUN_ATTEMPT_DENIED"):
            dispatch.authorize(op.event(load_order()), ctx, op.REGISTRY)

    def test_non_one_shot_operator_cli_unchanged(self):
        for order in (load_order(argv=["measure", "--output", "x"]), op.work_order()):
            _task, approval = op.admitted(order)
            self.assertNotIn("hardware_claim_ref", approval)
            ctx = {**op.context(), "GITHUB_RUN_ATTEMPT": "2"}
            self.assertNotIn("hardware_claim_ref",
                             dispatch.authorize(op.event(order), ctx, op.REGISTRY))

    def run_admitted(self, env, approval_change=None):
        task, approval = op.admitted(load_order())
        approval = {**approval, **(approval_change or {})}
        executor = Mock(return_value=subprocess.CompletedProcess(
            args=[], returncode=69, stdout=b"", stderr=b""))
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / dispatch.P2HW_SCRIPT
            script.parent.mkdir(parents=True)
            script.write_text("raise SystemExit(69)\n")
            with patch.dict(os.environ, env, clear=False):
                if "PLASMA_P2HW_CLAIM_REF" not in env:
                    os.environ.pop("PLASMA_P2HW_CLAIM_REF", None)
                try:
                    dispatch.run_task(task, workspace=Path(td), approval=approval,
                                      executor=executor, sandbox=False)
                except dispatch.Denied as exc:
                    return str(exc), executor
        return "EXECUTED", executor

    def test_execution_requires_exact_trusted_claim(self):
        expected = op.admitted(load_order())[1]["hardware_claim_ref"]
        for env, change in (({}, None),
                            ({"PLASMA_P2HW_CLAIM_REF": ""}, None),
                            ({"PLASMA_P2HW_CLAIM_REF": dispatch.P2HW_CLAIM_PREFIX + "0" * 64}, None),
                            ({"PLASMA_P2HW_CLAIM_REF": expected}, {"hardware_claim_ref": None})):
            code, executor = self.run_admitted(env, change)
            self.assertEqual(code, "OPERATOR_CLI_HARDWARE_CLAIM_REQUIRED")
            executor.assert_not_called()
        code, executor = self.run_admitted({"PLASMA_P2HW_CLAIM_REF": expected})
        self.assertNotEqual(code, "OPERATOR_CLI_HARDWARE_CLAIM_REQUIRED")
        executor.assert_called_once()


class HostedClaimEntry(unittest.TestCase):
    def args(self, order, td, **changes):
        req = dispatch.request(op.event(order), op.context())
        values = dict(work_order_sha256=req["work_order_sha256"],
                      claim_ref=dispatch.p2hw_claim_ref(req["work_order_sha256"]),
                      pinned_sha=req["source_sha"], evidence_dir=Path(td))
        values.update(changes)
        return req, argparse.Namespace(**values)

    def test_claim_entry_binds_event_and_writes_private_evidence(self):
        gh = FakeGitHub()
        with tempfile.TemporaryDirectory() as td:
            req, args = self.args(load_order(), td)
            env = {"GITHUB_TOKEN": "t" * 20, "GITHUB_RUN_ATTEMPT": "1"}
            with patch.dict(os.environ, env):
                receipt = dispatch.p2hw_claim_main(req, args, transport=lambda token: (gh.create, gh.read))
                self.assertNotIn("GITHUB_TOKEN", os.environ)
            path = Path(td) / "plasma-p2hw-claim.json"
            self.assertEqual(json.loads(path.read_text())["claim_ref"], args.claim_ref)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(receipt["work_order_sha256"], req["work_order_sha256"])
            # A second independent Run for the same Work Order is denied.
            with tempfile.TemporaryDirectory() as td2, patch.dict(os.environ, env):
                req2, args2 = self.args(load_order(), td2)
                with self.assertRaisesRegex(dispatch.Denied, "P2HW_CLAIM_DUPLICATE"):
                    dispatch.p2hw_claim_main(req2, args2, transport=lambda token: (gh.create, gh.read))

    def test_claim_entry_rejects_tampered_binding_before_network(self):
        transport = Mock()
        with tempfile.TemporaryDirectory() as td:
            for change in ({"work_order_sha256": "0" * 64},
                           {"claim_ref": dispatch.P2HW_CLAIM_PREFIX + "0" * 64},
                           {"pinned_sha": "f" * 40}):
                req, args = self.args(load_order(), td, **change)
                with patch.dict(os.environ, {"GITHUB_TOKEN": "t" * 20, "GITHUB_RUN_ATTEMPT": "1"}):
                    with self.assertRaisesRegex(dispatch.Denied, "P2HW_CLAIM_BINDING_DENIED"):
                        dispatch.p2hw_claim_main(req, args, transport=transport)
        transport.assert_not_called()

    def test_real_transport_requires_token(self):
        with self.assertRaisesRegex(dispatch.Denied, "P2HW_CLAIM_TOKEN_MISSING"):
            dispatch.github_claim_transport(None)


class WorkflowContract(unittest.TestCase):
    def setUp(self):
        self.wf = WF.read_text()
        self.dp = (ROOT / "scripts/plasma_development_dispatch.py").read_text()

    def job(self, name):
        start = self.wf.index(f"  {name}:\n")
        end = re.compile(r"\n  [a-z][a-z0-9-]+:\n").search(self.wf, start + 1)
        return self.wf[start:end.start() if end else len(self.wf)]

    def test_a2_contract_is_byte_identical(self):
        wf, dp = self.wf, self.dp
        i = wf.index("  development-claim:\n")
        j = re.compile(r"\n  development-[a-z-]+:\n").search(wf, i + 1).start()
        a = dp.index('    if req["task_id"] == "hil-a2-cpu-only":')
        b = dp.index("\n        }\n", a)
        c = dp.index('    if task.get("capability") == "z2-cpu-only":')
        d = dp.index("return a2.run_once(work_order, artifact_dir, approval=approval)", c)
        got = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in (
            ("workflow_a2_job", wf[i:j]), ("authorize_a2", dp[a:b]), ("run_task_a2", dp[c:d]))}
        self.assertEqual(got, A2_BLOCK_SHA256)
        self.assertIn("""          (needs.development-authorize.outputs.execution_capability == 'z2-cpu-only' &&
           needs.development-authorize.outputs.task_id == 'hil-a2-cpu-only' &&
           needs.development-claim.result == 'success' &&
           needs.development-claim.outputs.claim_ref == needs.development-authorize.outputs.claim_ref &&
           needs.development-claim.outputs.work_order_sha256 == needs.development-authorize.outputs.work_order_sha256 &&
           github.run_attempt == 1)""", self.job("development-execute"))

    def test_hosted_claim_job_is_least_privilege_and_one_shot(self):
        job = self.job("development-hardware-claim")
        self.assertIn("runs-on: ubuntu-24.04", job)
        self.assertIn("permissions:\n      contents: write\n    outputs:", job)
        self.assertNotIn("self-hosted", job)
        for clause in ("github.event_name == 'issue_comment'",
                       "needs.development-authorize.outputs.hardware_claim_ref != ''",
                       "github.run_attempt == 1",
                       "persist-credentials: false",
                       "plasma_development_dispatch.py p2hw-claim"):
            self.assertIn(clause, job)

    def test_execute_requires_matching_claim_for_one_shot(self):
        job = self.job("development-execute")
        self.assertIn("needs: [development-authorize, development-claim, development-hardware-claim]", job)
        self.assertIn("""contains(fromJSON('["cpu-only","vivado-host-build"]'),""", job)
        self.assertNotIn('"vivado-host-build","operator-cli"]', job)
        self.assertIn("""          (needs.development-authorize.outputs.execution_capability == 'operator-cli' &&
           needs.development-authorize.outputs.hardware_claim_ref != '' &&
           needs.development-hardware-claim.result == 'success' &&
           needs.development-hardware-claim.outputs.hardware_claim_ref == needs.development-authorize.outputs.hardware_claim_ref &&
           github.run_attempt == 1)""", job)
        self.assertIn("PLASMA_P2HW_CLAIM_REF: ${{ needs.development-hardware-claim.outputs.hardware_claim_ref }}", job)
        self.assertIn("hardware_claim_ref: ${{ steps.approve.outputs.hardware_claim_ref }}",
                      self.job("development-authorize"))


if __name__ == "__main__":
    unittest.main()
