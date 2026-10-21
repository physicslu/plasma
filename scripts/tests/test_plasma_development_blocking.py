"""Host-only behavioral regressions for the shared B1/B2/B3 policy."""
import copy
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plasma_development_dispatch as dispatch
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


if __name__ == '__main__':
    unittest.main()
