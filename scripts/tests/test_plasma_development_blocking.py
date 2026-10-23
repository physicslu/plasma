"""Host-only behavioral regressions for the shared B1/B2/B3 policy."""
import copy
import json
import re
from pathlib import Path
import os
import hashlib
import struct
from io import StringIO
from contextlib import redirect_stdout
from unittest.mock import patch
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plasma_development_dispatch as dispatch
import plasma_codex_native_preflight as native
import plasma_path2_stage_orchestrator as stages
import test_plasma_development_dispatch as fixtures


class BlockingPolicy(unittest.TestCase):
    def test_successful_stderr_is_evidence_not_failure(self):
        CPU = fixtures.DevelopmentPath2Contracts
        CPU.setUpClass()
        expected = subprocess.run([sys.executable, str(dispatch.ROOT / CPU.task['script'])],
                                  capture_output=True, check=True).stdout
        with tempfile.TemporaryDirectory() as td:
            result = dispatch.run_task(
                CPU.task, evidence_dir=Path(td),
                executor=lambda *a, **k: subprocess.CompletedProcess(
                    a[0], 0, expected, b'nonfatal diagnostic\n'))
            self.assertEqual(result['exit_code'], 0)
            self.assertEqual((Path(td) / 'plasma-path2-stderr.txt').read_bytes(),
                             b'nonfatal diagnostic\n')
            with self.assertRaisesRegex(dispatch.Denied, 'COMMAND_FAILED'):
                dispatch.run_task(CPU.task, executor=lambda *a, **k:
                                  subprocess.CompletedProcess(a[0], 7, expected, b''))

    def test_inert_options_do_not_add_stages(self):
        for initial in ('build', 'download', 'test'):
            opts = {flag: True for flag in stages.FLAGS}
            request = dict(stage=initial, source_sha='a'*40,
                           profile_id='f1b-site1-v1', target_id='z2-development',
                           options=opts)
            receipt = dict(stage='build', status='PASS', source_sha='a'*40,
                           profile_id='f1b-site1-v1', artifact_sha256='b'*64,
                           evidence_sha256='c'*64)
            if initial != 'build':
                request['artifact_sha256'] = 'b'*64
                if initial == 'download':
                    request['build_receipt'] = receipt
                else:
                    request['load_receipt'] = receipt | dict(
                        stage='download', target_id='z2-development',
                        lease_id='development-held', load_evidence_sha256='d'*64)
            clean = stages.validate_request(request)
            expected = {'build': ('build','download','test'),
                        'download': ('download','test'), 'test': ('test',)}[initial]
            self.assertEqual(stages.required_stages(initial, clean['options']), expected)
            called = []
            def fail(ctx):
                called.append(ctx['stage'])
                return dict(stage=ctx['stage'], status='NO_GO', reason='EXECUTION_FAILED')
            outcome = stages.run(request, adapters={s: fail for s in expected})
            self.assertEqual(called, [initial])
            self.assertEqual(outcome['status'], 'NO_GO')
            self.assertEqual(outcome['completed'], [])

    def test_both_paths_can_reauthorize_same_host_order_but_not_tamper(self):
        fixtures.GenericWorkOrderContracts.setUpClass()
        fixture = fixtures.GenericWorkOrderContracts()
        registry = dispatch.parse_json(dispatch.MANIFEST)
        for path in ('path2-cli', 'path3-codex'):
            order = fixture._order(path=path)
            event = fixture._event(order)
            first = dispatch.authorize(event, fixture._context(), registry)
            again = dispatch.authorize(event, fixture._context() |
                                       {'GITHUB_RUN_ATTEMPT': '2'}, registry)
            self.assertEqual(first, again)
            changed = copy.deepcopy(event)
            changed['comment']['user']['login'] = 'attacker'
            with self.assertRaises(dispatch.Denied):
                dispatch.authorize(changed, fixture._context(), registry)

    def test_real_workflow_dependency_matrix(self):
        workflow = (dispatch.ROOT / '.github/workflows/plasma-engineering-runtime-dispatch.yml').read_text()
        guard = workflow.split('  development-execute:', 1)[1].split(
            '    if: >-', 1)[1].split('    # PR #1046', 1)[0].strip()
        expression = guard.replace('&&', ' and ').replace('||', ' or ')
        expression = re.sub(r'(?:needs|github)\.[a-zA-Z0-9_.-]+',
                            lambda m: 'values.get(' + repr(m[0]) + ', "")', expression)
        def admitted(path, capability, **overrides):
            values = {
                'needs.development-authorize.result': 'success',
                'needs.development-authorize.outputs.execution_path': path,
                'needs.development-authorize.outputs.execution_capability': capability,
                'needs.development-claim.result': 'skipped',
                'needs.development-codex.result': 'skipped',
                'github.run_attempt': 2,
            } | overrides
            return eval('(' + expression + ')', {'__builtins__': {}}, {
                'values': values, 'always': lambda: True,
                'contains': lambda items, item: item in items,
                'fromJSON': json.loads,
            })
        for capability in ('cpu-only', 'vivado-host-build', 'path2-stage-contract'):
            self.assertTrue(admitted('path2-cli', capability))
            self.assertTrue(admitted('path2-cli', capability, **{
                'needs.development-claim.result': 'failure'}))
            self.assertFalse(admitted('path2-cli', capability, **{
                'needs.development-authorize.result': 'failure'}))
        self.assertFalse(admitted('path3-codex', 'codex-guarded-hardware'))
        self.assertFalse(admitted('path3-codex', 'codex-guarded-hardware', **{
            'needs.development-codex.result': 'success'}))
        self.assertFalse(admitted('path2-cli', 'z2-cpu-only'))
        self.assertFalse(admitted('path2-cli', 'arbitrary-shell'))


class NativePreflightWorkOrder(unittest.TestCase):
    SHA = "a" * 40

    def order(self):
        return {"schema": dispatch.WORK_ORDER_SCHEMA,
                "objective": "Inspect fixed native Codex installation, metadata and ELF only.",
                "acceptance": "Report sanitized path category, hash and dependencies, no model.",
                "execution_path": "path2-cli", "capability": "cpu-only",
                "scope": "host-only",
                "native_preflight": dispatch.NATIVE_PREFLIGHT,
                "pr_number": 0, "source_sha": self.SHA}

    def event(self, value=None):
        return {"action": "created",
                "issue": {"number": 981},
                "comment": {"id": 12345, "user": {"login": "physicslu"},
                            "body": dispatch.WORK_ORDER_PREFIX +
                                    json.dumps(self.order() if value is None else value)},
                "sender": {"login": "physicslu"},
                "repository": {"full_name": "physicslu/plasma"}}

    def context(self):
        return {"GITHUB_EVENT_NAME": "issue_comment",
                "GITHUB_REPOSITORY": "physicslu/plasma",
                "GITHUB_REF": "refs/heads/main", "GITHUB_SHA": self.SHA,
                "GITHUB_ACTOR": "physicslu"}

    def test_fixed_main_work_order_without_new_registry_id(self):
        order = self.order()
        req = dispatch.request(self.event(), self.context())
        self.assertEqual(req["task_id"], "path2-work-order")
        self.assertEqual(req["source_sha"], self.SHA)
        self.assertEqual(req["trusted_sha"], self.SHA)
        self.assertEqual(req["pr_number"], 0)
        registry = dispatch.parse_json(dispatch.MANIFEST)
        task = dispatch.task_for_request(registry, req, self.event())
        self.assertEqual(task["native_preflight"], dispatch.NATIVE_PREFLIGHT)
        self.assertNotIn("script", task)
        self.assertNotIn("argv", task)
        self.assertEqual(
            dispatch.authorize(self.event(), self.context(), registry)["execution_path"],
            "path2-cli")

    def test_preflight_cannot_be_repurposed_or_source_replayed(self):
        order = self.order()
        for k, v in (("scope", "guarded-hardware"),
                     ("execution_path", "path3-codex"),
                     ("capability", "codex-workspace"),
                     ("native_preflight", "arbitrary-command"),
                     ("pr_number", 1135),
                     ("source_sha", "f" * 40)):
            with self.subTest(field=k), self.assertRaises(dispatch.Denied):
                dispatch.request(self.event(order | {k: v}), self.context())
        for field, value in (("script", "scripts/experiments/x.py"),
                             ("argv", ["cat", "/etc/passwd"]),
                             ("expected_stdout_sha256", "0" * 64),
                             ("stage", "download"),
                             ("session_resume", "page-boundary-off-by-one"),
                             ("path", "/home/runner"),
                             ("command", "bash")):
            with self.subTest(field=field), self.assertRaises(dispatch.Denied):
                dispatch.request(self.event(order | {field: value}),
                                 self.context())
        for field, value in (("GITHUB_SHA", "b"*40),
                             ("GITHUB_REF", "refs/heads/feature"),
                             ("GITHUB_ACTOR", "attacker")):
            with self.subTest(field=field), self.assertRaises(dispatch.Denied):
                dispatch.request(self.event(), self.context() | {field: value})
        forged = self.event()
        forged["comment"]["user"]["login"] = "other"
        with self.assertRaises(dispatch.Denied):
            dispatch.request(forged, self.context())

    def test_exact_worker_route_no_codex_no_script_no_session(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            event = root / "event.json"
            registry = root / "registry.json"
            candidate = root / "candidate"
            candidate.mkdir()
            event.write_text(json.dumps(self.event()))
            registry.write_text(dispatch.MANIFEST.read_text())
            args = ["execute", "--event", str(event),
                    "--registry", str(registry),
                    "--workspace", str(candidate),
                    "--trusted-sha", self.SHA,
                    "--pinned-sha", self.SHA, "--pr-number", "0",
                    "--registry-sha256",
                    hashlib.sha256(registry.read_bytes()).hexdigest(),
                    "--execution-capability", "cpu-only",
                    "--work-order-sha256",
                    dispatch.work_order_digest(self.order())]
            env = self.context() | {
                "GITHUB_JOB": "development-execute",
                "GITHUB_RUN_ATTEMPT": "1",
                "RUNNER_NAME": dispatch.EXPECTED_RUNNER,
                "RUNNER_ENVIRONMENT": "self-hosted"}
            receipt = {"schema": "plasma.codex.native_preflight.v1",
                       "status": "OBSERVED", "model_session": "NOT_RUN"}
            with patch.dict(os.environ, env, clear=True), \
                 patch.object(sys, "argv", ["dispatcher.py", *args]), \
                 patch.object(dispatch, "worker_admission", return_value={
                     "status": "WORKER_SOURCE_ADMITTED"}), \
                 patch.object(native, "inspect", return_value=receipt) as inspected, \
                 patch.object(dispatch, "run_task",
                              side_effect=AssertionError("candidate run")) as run_script, \
                 patch.object(dispatch, "run_codex_task",
                              side_effect=AssertionError("Codex invoked")) as model:
                with redirect_stdout(StringIO()) as output:
                    self.assertEqual(dispatch.main(), 0)
                self.assertEqual(json.loads(output.getvalue())["model_session"],
                                 "NOT_RUN")
                inspected.assert_called_once()
                model.assert_not_called()
                run_script.assert_not_called()
                with patch.object(native, "inspect",
                                  return_value={**receipt, "status": "INCOMPLETE"}):
                    with redirect_stdout(StringIO()) as partial:
                        self.assertEqual(dispatch.main(), 2)
                    self.assertEqual(json.loads(partial.getvalue())["status"],
                                     "INCOMPLETE")
                diagnostic = native.PreflightDenied(
                    "NATIVE_PATH_PERMISSIONS_DENIED",
                    stage="CLI_MANIFEST", cause="PEER_WRITABLE",
                    component_index=9)
                with patch.object(native, "inspect", side_effect=diagnostic):
                    with redirect_stdout(StringIO()) as denied:
                        self.assertEqual(dispatch.main(), 2)
                    record = json.loads(denied.getvalue())
                    self.assertEqual(record["status"], "NOT_RUN_OR_FAIL")
                    self.assertEqual(record["reason"],
                                     "NATIVE_PATH_PERMISSIONS_DENIED")
                    self.assertEqual(record["denial_stage"], "CLI_MANIFEST")
                    self.assertEqual(record["denial_cause"], "PEER_WRITABLE")
                    self.assertEqual(record["denial_component_index"], 9)
                    self.assertEqual(record["model_session"], "NOT_RUN")
                    self.assertNotIn(str(root), json.dumps(record))
                    self.assertNotIn("auth.json", json.dumps(record))
                    model.assert_not_called()
                    run_script.assert_not_called()
                for name, value in (("GITHUB_JOB", "development-codex"),
                                    ("GITHUB_RUN_ATTEMPT", "2"),
                                    ("RUNNER_NAME", "another-runner"),
                                    ("RUNNER_ENVIRONMENT", "github-hosted")):
                    with self.subTest(name=name), \
                         patch.dict(os.environ, {name: value}):
                        with redirect_stdout(StringIO()) as denied:
                            self.assertEqual(dispatch.main(), 2)
                        inspected.assert_called_once()
                        self.assertEqual(
                            json.loads(denied.getvalue())["status"],
                            "NOT_RUN_OR_FAIL")

    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        home = Path(temp.name) / "home"
        prefix = home / ".nvm" / "versions" / "node" / native.NODE_VERSION
        package = prefix / "lib" / "node_modules" / "@openai" / "codex"
        wrapper = package / "bin" / "codex.js"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text("#!/usr/bin/env node\n")
        (package / "package.json").write_text(json.dumps({
            "name": "@openai/codex", "version": native.NATIVE_VERSION,
            "bin": {"codex": "bin/codex.js"}}))
        entry = prefix / "bin" / "codex"
        entry.parent.mkdir()
        entry.symlink_to(wrapper)
        platform = (package / "node_modules" / "@openai" / "codex-linux-x64")
        platform.mkdir(parents=True)
        (platform / "package.json").write_text(json.dumps({
            "name": "@openai/codex-linux-x64",
            "version": native.NATIVE_VERSION}))
        executable = platform / "vendor" / native.ARCH / "bin" / "codex"
        executable.parent.mkdir(parents=True)
        elf = bytearray(120)
        elf[:7] = b"\x7fELF\x02\x01\x01"
        struct.pack_into("<HH", elf, 16, 2, 62)
        struct.pack_into("<Q", elf, 32, 64)
        struct.pack_into("<HH", elf, 54, 56, 1)
        struct.pack_into("<IIQQQQQQ", elf, 64,
                         1, 5, 0, 0, 0, 120, 120, 4096)
        executable.write_bytes(elf)
        executable.chmod(0o755)
        return home, entry, executable, platform

    def test_native_inventory_sanitizes_and_never_executes_model(self):
        home, entry, executable, platform = self.fixture()
        def safe_tool(program, argv):
            if program.endswith("file"):
                return "ELF 64-bit LSB executable"
            if "-lW" in argv:
                return "Program Headers:"
            return "There is no dynamic section in this file."
        with patch.object(native, "fixed_readonly_tool", side_effect=safe_tool), \
             patch.object(native.subprocess, "run",
                          side_effect=AssertionError("subprocess invoked")):
            result = native.inspect(home=home, which=lambda _: str(entry))
        self.assertEqual(result["status"], "OBSERVED")
        self.assertEqual(result["native_sha256"],
                         hashlib.sha256(executable.read_bytes()).hexdigest())
        self.assertEqual(result["pt_interp"], "ABSENT")
        self.assertEqual(result["dt_needed_count"], 0)
        self.assertFalse(result["sha256_pin_authorized"])
        self.assertEqual(result["model_session"], "NOT_RUN")
        self.assertNotIn(str(home), json.dumps(result))
        self.assertNotIn(str(executable), json.dumps(result))
        self.assertNotIn("auth.json", json.dumps(result))

    def test_permission_denial_stage_owner_and_component_index(self):
        home, entry, binary, platform = self.fixture()
        which = lambda _: str(entry)
        package = (home / ".nvm" / "versions" / "node" /
                   native.NODE_VERSION / "lib" / "node_modules" /
                   "@openai" / "codex")
        cases = (
            (package / "bin", "CLI_WRAPPER"),
            (package / "package.json", "CLI_MANIFEST"),
            (platform / "package.json", "PLATFORM_MANIFEST"),
            (binary, "NATIVE_BINARY"),
        )
        for node, stage in cases:
            with self.subTest(stage=stage):
                original_mode = node.stat().st_mode & 0o777
                try:
                    node.chmod(original_mode | 0o022)
                    with self.assertRaises(native.PreflightDenied) as caught:
                        native.inspect(home=home, which=which)
                    err = caught.exception
                    self.assertEqual(str(err),
                                     "NATIVE_PATH_PERMISSIONS_DENIED")
                    self.assertEqual(err.stage, stage)
                    self.assertEqual(err.cause, "PEER_WRITABLE")
                    self.assertEqual(err.component_index,
                                     len(node.relative_to(home).parts))
                    self.assertNotIn(str(home), str(err))
                    self.assertNotIn(str(node), str(err))
                finally:
                    node.chmod(original_mode)

        # Simulate an unexpected owner without requiring chown or root.
        target = home / ".nvm"
        actual_lstat = native.Path.lstat
        def fake_lstat(path, *args, **kwargs):
            metadata = actual_lstat(path, *args, **kwargs)
            if path == target:
                return type("StatForTest", (), {
                    "st_mode": metadata.st_mode, "st_uid": 999999999})()
            return metadata
        with patch.object(native.Path, "lstat", fake_lstat):
            with self.assertRaises(native.PreflightDenied) as caught:
                native.inspect(home=home, which=which)
        err = caught.exception
        self.assertEqual(str(err), "NATIVE_PATH_PERMISSIONS_DENIED")
        self.assertEqual(err.stage, "CLI_WRAPPER")
        self.assertEqual(err.cause, "OWNER_MISMATCH")
        self.assertEqual(err.component_index, 1)

    def test_native_denial_receipt_never_uses_host_path_or_dynamic_code(self):
        # Fail closed on malformed stage/cause/index metadata.
        for stage, cause, idx in (
            ("../../home", "PEER_WRITABLE", 1),
            ("CLI_WRAPPER", "/private/path", 1),
            ("NATIVE_BINARY", "OWNER_MISMATCH", 25),
        ):
            with self.subTest(stage=stage, cause=cause, index=idx):
                self.assertFalse(
                    stage in native.SAFE_PERMISSION_STAGES and
                    cause in native.SAFE_PERMISSION_CAUSES and
                    type(idx) is int and 1 <= idx <= 24)

    def test_native_missing_wrong_source_dynamic_and_unsafe_denied(self):
        home, entry, binary, platform = self.fixture()
        which = lambda _: str(entry)
        binary.chmod(0o777)
        with self.assertRaisesRegex(native.PreflightDenied,
                                    "NATIVE_PATH_PERMISSIONS_DENIED"):
            native.inspect(home=home, which=which)
        binary.chmod(0o755)
        original = binary.read_bytes()
        modified = bytearray(original + b"\x00" * 56)
        struct.pack_into("<H", modified, 56, 2)  # Keep executable PT_LOAD
        struct.pack_into("<I", modified, 120, 3)  # Add PT_INTERP separately
        binary.write_bytes(modified)
        with patch.object(native, "fixed_readonly_tool", return_value=None):
            result = native.inspect(home=home, which=which)
        self.assertEqual(result["pt_interp"], "PRESENT")
        self.assertEqual(result["status"], "INCOMPLETE")
        binary.write_bytes(original)
        with self.assertRaisesRegex(native.PreflightDenied, "NATIVE_ENTRY_DENIED"):
            native.inspect(home=home, which=lambda _: "/tmp/injected")
        manifest = platform / "package.json"
        manifest.write_text(json.dumps({"name": "@attacker/codex",
                                        "version": native.NATIVE_VERSION}))
        with self.assertRaisesRegex(native.PreflightDenied,
                                    "NATIVE_MANIFEST_ID_DENIED"):
            native.inspect(home=home, which=which)
        manifest.write_text(json.dumps({"name": "@openai/codex-linux-x64",
                                        "version": native.NATIVE_VERSION}))
        original = binary.read_bytes()
        binary.unlink()
        outside = Path(home.parent) / "untrusted"
        outside.write_bytes(original)
        binary.symlink_to(outside)
        with self.assertRaisesRegex(native.PreflightDenied,
                                    "NATIVE_PATH_TYPE_DENIED"):
            native.inspect(home=home, which=which)



if __name__ == '__main__':
    unittest.main()
