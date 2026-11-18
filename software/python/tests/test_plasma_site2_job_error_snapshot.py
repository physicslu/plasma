"""Host-only diagnostic projection and read-only boundary regression tests."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('site2_snapshot', ROOT / 'scripts/plasma_site2_job_error_snapshot.py')
SCRIPT = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SCRIPT)
SHA = 'a' * 40
JOB = 'job-20261104-163558-9b09a6a8'
HOST = '192.168.2.99'


def error(code='OUTCOME_UNKNOWN_SITE_SEALED:SAFE_OFF_NOT_VERIFIED'):
    return {'error_code': 'E5002', 'error_type': 'INTERFACE_FAILURE',
            'failure_source': 'interface', 'message': 'PRIVATE MESSAGE',
            'original_exception': 'PRIVATE EXCEPTION',
            'context': {'site_worker_stage': 'run', 'site_worker_code': code,
                        'outcome_unknown': True, 'password': 'PRIVATE SECRET'}}


def test_nested_result_and_both_histories_preserve_distinct_evidence():
    first = {'attempt': 1, 'state': 'error', 'retry_scheduled': False, 'error': error()}
    second = {**first, 'attempt': 2, 'error': error('TRANSPORT_DENIED:ROOT_ADMISSION_DENIED')}
    job = {'state': 'error', 'stage': 'program', 'stage_state': 'error',
           'result': {'error': error(), 'attempt_history': [second]},
           'attempt_history': [first]}
    out = SCRIPT.job_observation(JOB, job)
    assert out['error_code'] == 'NOT_RECORDED'  # never manufacture a top-level error
    assert out['result_error']['error_code'] == 'E5002'
    assert out['result_error']['site_worker_stage'] == 'run'
    assert out['result_error']['outcome_unknown'] is True
    assert out['attempt_history'][0]['error']['site_worker_code'].endswith('SAFE_OFF_NOT_VERIFIED')
    assert out['result_attempt_history'][0]['error']['site_worker_code'].endswith('ROOT_ADMISSION_DENIED')
    assert out['stage'] == 'program'
    assert 'PRIVATE' not in json.dumps(out)


@pytest.mark.parametrize('value', [None, [], 'invalid', 42, {'context': []}])
def test_missing_or_malformed_errors_do_not_claim_safety(value):
    out = SCRIPT.job_observation(JOB, {'result': {'error': value, 'attempt_history': value},
                                     'attempt_history': [None, 'invalid', {'error': value}]})
    assert out['result_error']['site_worker_code'] == 'NOT_RECORDED'
    assert out['result_error']['outcome_unknown'] == 'NOT_RECORDED'
    assert len(out['attempt_history']) == 1


def test_untrusted_values_are_redacted_and_context_is_allowlisted():
    out = SCRIPT.error_observation({'error_code': 'bad\nvalue',
                                   'context': {'site_worker_code': {'secret': 1},
                                               'outcome_unknown': 'false', 'arbitrary': 'PRIVATE'}})
    assert out['error_code'] == 'REDACTED'
    assert out['site_worker_code'] == 'NOT_RECORDED'
    assert out['outcome_unknown'] == 'NOT_RECORDED'
    assert 'PRIVATE' not in json.dumps(out)


def test_recorded_worker_result_preserves_safe_off_without_inference():
    out = SCRIPT.error_observation({'context': {'site_worker_result': {
        'result': 'FAIL', 'code': 'READBACK_MISMATCH', 'safe_off': True,
        'log': 'PRIVATE LOG'}}})
    assert out['site_worker_result'] == {'result': 'FAIL', 'code': 'READBACK_MISMATCH', 'safe_off': True}
    assert 'PRIVATE' not in json.dumps(out)


@pytest.mark.parametrize('sha,host,job', [('b'*40, HOST, JOB), (SHA, '8.8.8.8', JOB), (SHA, HOST, '../bad')])
def test_invalid_scope_never_reaches_network(sha, host, job):
    with patch.object(SCRIPT.subprocess, 'run', return_value=SimpleNamespace(stdout=SHA)), \
         patch.object(SCRIPT.http.client, 'HTTPConnection') as conn:
        with pytest.raises(RuntimeError):
            SCRIPT.run(host, sha, job)
        conn.assert_not_called()


def test_get_only_and_job_mismatch_stops_before_ssh():
    response = SimpleNamespace(status=200, read=lambda limit: json.dumps({'job': {'job_id': 'wrong'}}).encode())
    conn = Mock()
    conn.getresponse.return_value = response
    helper, preflight = Mock(), Mock()
    with patch.object(SCRIPT.subprocess, 'run', return_value=SimpleNamespace(stdout=SHA)), \
         patch.object(SCRIPT.http.client, 'HTTPConnection', return_value=conn):
        with pytest.raises(RuntimeError, match='JOB_ID_MISMATCH'):
            SCRIPT.run(HOST, SHA, JOB, helper=helper, preflight=preflight)
    conn.request.assert_called_once_with('GET', '/api/status?job='+JOB)
    conn.close.assert_called_once()
    assert not helper.mock_calls and not preflight.mock_calls
