#!/usr/bin/env python3
"""PLASMA Gate 1B hosted-only, simulated GitHub / software-Codex contracts.

Never use live GitHub tokens, Codex credentials, SWPC runner, Z2 or instruments.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_engineering_dispatch_v1 as core
import plasma_engineering_dispatch_gate1b as gate

FIXTURE = ROOT / "specs/engineering-dispatch/examples/software-pr-gate1b-mock.json"
POLICY = ROOT / "specs/engineering-dispatch/capabilities-v1.json"
WF = ROOT / ".github/workflows/plasma-engineering-dispatch-gate1b-contract.yml"
DOC = ROOT / "docs/architecture/plasma-engineering-dispatch-v1.md"


class SimulatedGitHub:
    """One in-memory GitHub ref store shared by many independent mock runs."""
    def __init__(self):
        self.refs = {}
        self.lock = threading.Lock()
        self.calls = []

    def __call__(self, endpoint: str, payload: dict) -> tuple[int, object]:
        with self.lock:
            self.calls.append((endpoint, dict(payload)))
            if endpoint != gate.API:
                return 404, {}
            if payload["ref"] in self.refs:
                return 422, {}
            self.refs[payload["ref"]] = payload["sha"]
            return 201, {"ref": payload["ref"],
                         "object": {"sha": payload["sha"], "type": "commit"}}


class Gate1BContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.order = json.loads(FIXTURE.read_text())
        cls.policy = json.loads(POLICY.read_text())

    def work(self):
        return copy.deepcopy(self.order)

    def event(self, order=None):
        order = order or self.work()
        return {
            "action": "created",
            "issue": {"number": order["issue_number"]},
            "comment": {"id": 223, "body": core.approval_command(order),
                        "user": {"login": "physicslu"}},
            "sender": {"login": "physicslu"},
            "repository": {"full_name": "physicslu/plasma"},
        }

    def env(self):
        return {
            "GITHUB_EVENT_NAME": "issue_comment",
            "GITHUB_ACTOR": "physicslu",
            "GITHUB_REPOSITORY": "physicslu/plasma",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_RUN_ID": "3981000",
            "GITHUB_RUN_ATTEMPT": "1",
        }

    def auth(self, order=None, event=None, env=None, sha=None):
        order = order or self.work()
        event = event or self.event(order)
        return gate.authorize_from_event(event, env or self.env(), order,
                                         self.policy, sha or order["reviewed_main_sha"])

    def test_mock_software_pr_order_validation(self):
        rule = core.validate_work_order(self.work(), self.policy)
        self.assertEqual(rule["worker_class"], "software-isolated")
        self.assertFalse(rule["runtime_enabled"])
        self.assertFalse(rule["hardware_authorization"])
        self.assertNotIn("usb:la2016", rule["permissions"])
        self.assertNotIn("z2:hardware-owner", rule["permissions"])

    def test_exact_owner_reviewed_sha_and_approval_binding(self):
        plan, ref = self.auth()
        self.assertEqual(plan["status"], "AUTH_CONTRACT_PASS_NO_DISPATCH")
        self.assertFalse(plan["runtime_enabled"])
        self.assertEqual(ref.path, gate.API)
        self.assertEqual(ref.sha, self.order["reviewed_main_sha"])
        self.assertEqual(ref.ref,
            "refs/heads/plasma-engineering-claims/900002/gate1b-software-smoke-r1")
        self.assertEqual(ref.json_payload(), {"ref": ref.ref, "sha": ref.sha})
        alt = self.work()
        alt["objective"] += " [unapproved edit]"
        with self.assertRaisesRegex(core.ContractDenied, "APPROVAL_DIGEST_OR_BODY_MISMATCH"):
            self.auth(order=alt, event=self.event())
        with self.assertRaisesRegex(core.ContractDenied, "REVIEWED_SHA_CHANGED"):
            self.auth(sha="0"*40)
        with self.assertRaisesRegex(core.ContractDenied, "EVENT_OWNER_DENIED"):
            bad = self.event()
            bad["comment"]["user"]["login"] = "attacker"
            self.auth(event=bad)
        with self.assertRaisesRegex(core.ContractDenied, "APPROVAL_DIGEST_OR_BODY_MISMATCH"):
            bad = self.event()
            bad["comment"]["body"] += "\n"
            self.auth(event=bad)
        with self.assertRaisesRegex(core.ContractDenied, "GITHUB_CONTEXT_DENIED"):
            e = self.env()
            e["GITHUB_REF"] = "refs/pull/123/merge"
            self.auth(env=e)

    def test_non_owner_context_and_fake_numerics_denied(self):
        for key, bad in (
            ("GITHUB_EVENT_NAME", "pull_request"),
            ("GITHUB_ACTOR", "attacker"),
            ("GITHUB_REPOSITORY", "attacker/repo"),
            ("GITHUB_RUN_ID", "8; rm -rf /"),
            ("GITHUB_RUN_ID", "0"),
            ("GITHUB_RUN_ATTEMPT", "-1"),
        ):
            with self.subTest(key=key):
                env = self.env()
                env[key] = bad
                with self.assertRaises(core.ContractDenied):
                    self.auth(env=env)

    def test_same_revision_claim_once_across_fake_runners(self):
        plan, ref = self.auth()
        github = SimulatedGitHub()
        self.assertEqual(gate.claim_with_transport(ref, github),
                         "CLAIMED_ONCE_GITHUB_REF_CREATE_CONFIRMED")
        other_plan, other_ref = self.auth()
        self.assertEqual(other_plan["work_order_sha256"], plan["work_order_sha256"])
        with self.assertRaisesRegex(core.ContractDenied,
                                    "WORK_ORDER_ALREADY_CLAIMED_OR_REF_INVALID"):
            gate.claim_with_transport(other_ref, github)
        self.assertEqual(len(github.refs),1)
        self.assertEqual(github.refs[ref.ref],ref.sha)
        # A new GitHub job attempt does not create a new ref.
        env = self.env()
        env["GITHUB_RUN_ATTEMPT"] = "2"
        _, repeated = self.auth(env=env)
        with self.assertRaises(core.ContractDenied):
            gate.claim_with_transport(repeated,github)

    def test_atomic_parallel_claim_only_one_is_accepted(self):
        _, ref = self.auth()
        github = SimulatedGitHub()
        def attempt(n):
            try:
                return gate.claim_with_transport(ref,github)
            except core.ContractDenied as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=16) as executor:
            outcomes = list(executor.map(attempt,range(16)))
        self.assertEqual(outcomes.count("CLAIMED_ONCE_GITHUB_REF_CREATE_CONFIRMED"),1)
        self.assertEqual(outcomes.count("WORK_ORDER_ALREADY_CLAIMED_OR_REF_INVALID"),15)
        self.assertEqual(len(github.refs),1)

    def test_ambiguous_network_failure_does_not_retry(self):
        _, ref = self.auth()
        for status in (200, 400, 401, 403, 409, 429, 500, 502):
            with self.subTest(status=status):
                with self.assertRaisesRegex(core.ContractDenied,
                                            "GITHUB_CLAIM_NOT_CONFIRMED"):
                    gate.claim_with_transport(ref,lambda u,p:(status,{}))
        for response in ({"ref":"wrong","object":{"sha":ref.sha}},
                         {"ref":ref.ref,"object":{"sha":"0"*40}},[],
                         {"ref":ref.ref}):
            with self.assertRaisesRegex(core.ContractDenied,
                                        "GITHUB_CLAIM_RECEIPT_MISMATCH"):
                gate.accept_claim_response(ref,201,response)
        hits = []
        def down(url,payload):
            hits.append(1)
            raise OSError("network unavailable: do not leak")
        with self.assertRaisesRegex(core.ContractDenied,
                                    "GITHUB_CLAIM_TRANSPORT_FAILED_CLOSED"):
            gate.claim_with_transport(ref,down)
        self.assertEqual(len(hits),1)  # no implicit retries

    def test_git_ref_request_rejects_hardware_route_and_forged_plan(self):
        order = self.work()
        plan, _ = self.auth()
        for key, value in (("work_order_sha256","0"*64),
                           ("status","EXECUTE"),
                           ("runtime_enabled",True),
                           ("revision",2),
                           ("work_order_id","hijack")):
            altered = copy.deepcopy(plan)
            altered[key] = value
            with self.assertRaisesRegex(core.ContractDenied,"CLAIM_PLAN_MISMATCH"):
                gate.claim_request(order,altered,self.policy)
        hardware = self.work()
        hardware["capability"] = "la2016-loopback"
        hardware["entrypoint"] = "la2016-direct"
        hardware["authorization_kind"] = "hardware-one-shot"
        hardware["scope"]["required_permissions"] = ["repo:read","usb:la2016"]
        hardware["scope"]["deny_resources"].remove("usb")
        hardware["scope"]["deny_resources"].append("repository-write")
        with self.assertRaisesRegex(core.ContractDenied,"SOFTWARE_ONLY_CAPABILITY_REQUIRED"):
            gate.claim_request(hardware,plan,self.policy)
        self.assertFalse(self.policy["capabilities"]["software-pr"]["runtime_enabled"])

    def test_future_ref_transport_never_accepts_arbitrary_url_or_credentials(self):
        with self.assertRaisesRegex(core.ContractDenied,"GITHUB_CLAIM_TOKEN_MISSING"):
            gate.github_ref_transport("")
        transport = gate.github_ref_transport("fake-test-token-over-sixteen")
        with self.assertRaisesRegex(core.ContractDenied,"GITHUB_CLAIM_ENDPOINT_INVALID"):
            transport("https://example.com/attack",{"ref":"refs/heads/x","sha":"0"*40})
        with self.assertRaisesRegex(core.ContractDenied,"GITHUB_CLAIM_PAYLOAD_INVALID"):
            transport(gate.API,{"ref":"refs/heads/unapproved","sha":"0"*40})
        _, ref = self.auth()
        with mock.patch("urllib.request.urlopen") as mock_net:
            response = mock.MagicMock()
            response.status=201
            response.read.return_value=json.dumps({
                "ref":ref.ref,"object":{"sha":ref.sha}}).encode()
            mock_net.return_value.__enter__.return_value=response
            self.assertEqual(gate.claim_with_transport(ref,transport),
                             "CLAIMED_ONCE_GITHUB_REF_CREATE_CONFIRMED")
            request=mock_net.call_args.args[0]
            self.assertEqual(request.get_method(),"POST")
            self.assertEqual(request.full_url,gate.API)
            self.assertEqual(json.loads(request.data),ref.json_payload())
            self.assertEqual(mock_net.call_args.kwargs["timeout"],10)

    def test_future_codex_argv_is_fixed_and_shell_free(self):
        order = self.work()
        argv = gate.software_only_command(order,Path("/tmp/software-scratch"),
                                         Path("/usr/bin/codex"))
        self.assertEqual(argv[:4],[
            "/usr/bin/codex","--ask-for-approval","never","exec"])
        self.assertIn("workspace-write",argv)
        self.assertEqual(argv[-1],"-")
        self.assertNotIn("sh", argv)
        order["capability"]="z2-readonly"
        with self.assertRaisesRegex(core.ContractDenied,"CODEX_SOFTWARE_ONLY_REQUIRED"):
            gate.software_only_command(order,Path("/tmp/scratch"),Path("/usr/bin/codex"))

    def test_fake_codex_offline_acceptance_produces_sanitized_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake = root / "mock-codex"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "from pathlib import Path\n"
                "import sys\n"
                "assert sys.argv[1] == '--simulate-codex-v1'\n"
                "Path(sys.argv[2], 'result.txt').write_text("
                "'GATE1B_FAKE_CODEX_PASS\\n')\n"
                "print('fake-codex-wrote-only-scratch')\n"
            )
            fake.chmod(0o700)
            scratch = root / "scratch"
            scratch.mkdir()
            with mock.patch.dict(os.environ,{
                "GITHUB_TOKEN":"do-not-leak-github-token",
                "ACTIONS_RUNTIME_TOKEN":"do-not-leak-actions-token",
                "OPENAI_API_KEY":"do-not-leak-model-token",
            }):
                report=gate.offline_mock_codex_acceptance(
                    self.work(),self.policy,scratch,fake)
            self.assertEqual(
                report["status"],"OFFLINE_FAKE_CODEX_CONTRACT_PASS_NOT_REAL_CODEX")
            self.assertFalse(report["runtime_enabled"])
            self.assertFalse(report["hardware_access_verified"])
            self.assertFalse(report["codex_model_access_verified"])
            self.assertTrue(report["software_only"])
            self.assertTrue((scratch/"result.txt").is_file())
            self.assertNotIn("do-not-leak",str(report))
            self.assertEqual(len(report["evidence_sha256"]),64)
            # Real binary absence must be NO-GO.
            with self.assertRaisesRegex(core.ContractDenied,
                                        "OFFLINE_MOCK_CODEX_REQUIRED"):
                gate.offline_mock_codex_acceptance(
                    self.work(),self.policy,scratch,root/"missing")

    def test_hosted_contract_only_no_live_trigger(self):
        text = WF.read_text()
        self.assertIn("runs-on: ubuntu-24.04",text)
        self.assertIn("persist-credentials: false",text)
        self.assertNotIn("\n  issue_comment:",text)
        self.assertNotIn("\n  workflow_dispatch:",text)
        self.assertNotIn("runs-on: [self-hosted",text)
        self.assertNotIn("contents: write",text)
        self.assertNotIn("GITHUB_TOKEN:",text)
        self.assertNotIn("OPENAI_API_KEY:",text)
        self.assertNotIn("sudo ",text)
        self.assertNotIn("github.ref == 'refs/heads/main' && issue",text)
        source=Path(gate.__file__).read_text()
        self.assertNotIn("def execute_live_work_order",source)
        self.assertNotIn("def trigger_hardware",source)
        result=subprocess.run([sys.executable,str(Path(gate.__file__))],
            capture_output=True,text=True,timeout=5,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"],gate.CI_NO_RUNTIME)
        self.assertIn("one at a time",DOC.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
