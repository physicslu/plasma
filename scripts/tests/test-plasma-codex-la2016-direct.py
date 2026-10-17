#!/usr/bin/env python3
"""Offline-only tests for the pending LA2016 direct Codex experiment."""
from __future__ import annotations
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/plasma-codex-la2016-direct.py"
WORKFLOW = ROOT / ".github/workflows/plasma-codex-la2016-direct.yml"
spec = importlib.util.spec_from_file_location("plasma_la2016_direct", SOURCE)
assert spec and spec.loader
direct = importlib.util.module_from_spec(spec)
spec.loader.exec_module(direct)


class OfflineDirectContracts(unittest.TestCase):
    def test_exact_owner_only_auth(self) -> None:
        e = {"action":"created", "issue":{"number":981},
             "comment":{"user":{"login":"physicslu"},
                        "body":"/plasma-codex la2016-direct 981"},
             "sender":{"login":"physicslu"},
             "repository":{"full_name":"physicslu/plasma"}}
        self.assertTrue(direct.authorized(e, "physicslu", "physicslu/plasma", "refs/heads/main"))
        for actor, repo, ref in [
            ("mallory","physicslu/plasma","refs/heads/main"),
            ("physicslu","fake/plasma","refs/heads/main"),
            ("physicslu","physicslu/plasma","refs/heads/feature")
        ]:
            self.assertFalse(direct.authorized(e,actor,repo,ref))
        for payload in ["/plasma-codex la2016-direct 981\n",
                        "/plasma-codex la2016-direct 981; echo injected",
                        "/plasma-codex la2016 981",
                        "/plasma-codex la2016-diag 981"]:
            copy=json.loads(json.dumps(e))
            copy["comment"]["body"]=payload
            self.assertFalse(direct.authorized(copy,"physicslu","physicslu/plasma",
                                               "refs/heads/main"))
        copy=json.loads(json.dumps(e))
        copy["issue"]["pull_request"]={"url":"some-pr"}
        self.assertFalse(direct.authorized(copy,"physicslu","physicslu/plasma",
                                           "refs/heads/main"))

    def test_real_archived_capture_positive_and_negative(self) -> None:
        root=ROOT/"docs/evidence/la2016-pwm-loopback/2026-10-16"
        for hz,duty,dir in [(1000,50,"1khz-50pct"),(2000,25,"2khz-25pct")]:
            actual=direct.validate_pair(root/dir/"on.sr",root/dir/"off.sr",hz,duty)
            self.assertEqual(actual["result"],"PASS")
            self.assertGreaterEqual(actual["off_samples"],20_000)
            with self.assertRaisesRegex(ValueError,"WAVEFORM_OUTSIDE_TOLERANCE"):
                direct.validate_pair(root/dir/"on.sr",root/dir/"off.sr",hz,60)
        with tempfile.TemporaryDirectory() as temp:
            rootpath=Path(temp)/"bad.sr"
            with zipfile.ZipFile(rootpath,"w") as z:
                z.writestr("metadata","incorrect")
            with self.assertRaises(ValueError):
                direct.bits(rootpath)

    def test_minimal_off_command_never_uses_agent_reply(self) -> None:
        fake=subprocess.CompletedProcess(["sigrok"],0)
        with mock.patch.object(direct.subprocess,"run",return_value=fake) as call:
            self.assertTrue(direct.physical_off("1.15"))
            cmd=call.call_args.args[0]
            self.assertEqual(cmd[0],str(direct.APP))
            self.assertEqual(cmd[cmd.index("--driver")+1],"kingst-la2016:conn=1.15")
            self.assertEqual(cmd[cmd.index("--config")+1],"channel_group=PWM1:enabled=off")
            self.assertEqual(cmd[-1],"--set")
            self.assertNotIn("enabled=on"," ".join(cmd))
            self.assertFalse(call.call_args.kwargs["check"])

    def test_namespace_shape_exposes_one_device_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)/"home";home.mkdir()
            (home/".codex").mkdir()
            evidence=Path(temp)/"evidence";evidence.mkdir()
            old_get=direct.pwd.getpwuid
            with mock.patch.object(direct.shutil,"which",side_effect=lambda cmd:
                                   "/usr/bin/"+cmd if cmd in {"bwrap","codex"} else None), \
                 mock.patch.object(direct.pwd,"getpwuid",return_value=types.SimpleNamespace(pw_dir=str(home))):
                args=direct.sandbox_prefix(Path("/dev/bus/usb/001/015"),evidence)
            self.assertEqual(args[0],"/usr/bin/bwrap")
            self.assertIn("--dev",args)
            self.assertIn("--dev-bind",args)
            n=args.index("--dev-bind")
            self.assertEqual(args[n+1:n+3],["/dev/bus/usb/001/015"]*2)
            self.assertIn("--ro-bind",args)
            self.assertIn("--bind",args)
            with self.assertRaisesRegex(ValueError,"UNSAFE_USB_PATH"):
                with mock.patch.object(direct.shutil,"which",return_value="/usr/bin/bwrap"):
                    direct.sandbox_prefix(Path("/dev/mem"),evidence)

    def test_workflow_has_no_pr_runner_or_auto_issue_execution(self) -> None:
        text=WORKFLOW.read_text()
        assert "github.event_name != 'issue_comment'" in text
        assert "needs.authorize.result == 'success'" in text
        assert "github.event.comment.body == '/plasma-codex la2016-direct 981'" in text
        assert "github.actor == 'physicslu'" in text
        assert "github.event.issue.number == 981" in text
        assert "needs.authorize.outputs.reviewed_sha" in text
        assert "persist-credentials: false" in text
        assert "runs-on: [self-hosted, linux, x64, plasma-codex]" in text
        assert "python3 scripts/plasma-codex-la2016-direct.py --self-test" in text
        assert "python3 scripts/plasma-codex-la2016-direct.py --run" in text
        for string in ("pull_request_target:", "permissions: write-all",
                       "secrets: inherit","sudo ", "docker.sock"):
            assert string not in text
        source=SOURCE.read_text()
        assert "AGENT_REQUEST_SCHEMA" not in source.split("def self_test")[0]
        assert "validate_agent_request(" not in source
        assert "codex" in source and "--sandbox" in source
        assert "--dev-bind" in source and "--tmpfs" in source
        assert "physical_off(conn)" in source
        assert "input=prompt(evidence,conn)" in source
        assert "CALL_SUPERVISOR" not in source
        assert "pwm-off-confirmed" not in source  # separate marker from legacy path

    def test_no_hardware_if_runner_identity_unverified(self) -> None:
        with mock.patch.object(direct.socket,"gethostname",return_value="untrusted"):
            with self.assertRaisesRegex(ValueError,"WORKER_IDENTITY_DENIED"):
                direct.worker_identity()


if __name__ == "__main__":
    unittest.main(verbosity=2)
