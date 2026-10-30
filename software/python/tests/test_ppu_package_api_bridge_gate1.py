"""Host-only API composition. Fixtures confer no production installation authority."""
from contextlib import contextmanager, nullcontext
from dataclasses import replace
import base64
import hashlib
import json
import threading
from types import SimpleNamespace

import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path

from .ppu_package_fixtures import (
    load, engine, package, coordinator, SOURCE, TARGET, SAMPLES,
)

service = load('ppu_package_api_bridge', 'ppu-bootstrap-service.py')


class ProgrammingFixture:
    """Models scheduler ownership; deliberately not a production interlock."""
    def __init__(self):
        self.blocked = False
        self.sites = [False] * 8
        self.active_job = False
        self.quiescent = True
        self.authorized = True
        self.events = []
        self.entered = threading.Event()
        self.proceed = threading.Event()
        self.proceed.set()
        self.co = None

    def admit_programming(self):
        return not self.blocked

    @contextmanager
    def exclude(self):
        self.blocked = True
        self.events.append('fence')
        self.entered.set()
        try:
            assert self.proceed.wait(5)
            self.events.append('idle_check')
            if any(self.sites) or self.active_job or not self.quiescent or not self.authorized:
                raise RuntimeError('deployment programming preflight denied')
            yield
        finally:
            record = self.co.journal.read()
            # Unknown outcomes retain programming exclusion for recovery.
            if record is None or record.state in {'package_active', 'rolled_back', 'verify_failed'}:
                self.blocked = False
            self.events.append('exit')


def composition(tmp, sample, *, fault=None, corrupt_receipt=False, grant_changes=None, network=False):
    name, kind, files = sample
    archive, digest = package(tmp, name, kind, files)
    paths = service.ServicePaths(state_root=tmp / 'state', product_root=tmp / 'untouched')
    co = coordinator(tmp)
    co.paths = replace(co.paths, bootstrap_state_root=paths.state_root)
    co.journal = engine.Journal(co.paths.journal)
    gate = ProgrammingFixture()
    gate.co = co
    grant = dict(kind=kind, source_commit=SOURCE, artifact_sha256=digest,
                 publisher='fixture-reviewed-publisher', target_profile=dict(TARGET))
    grant.update(grant_changes or {})

    def admit(body):
        if grant['publisher'] != 'fixture-reviewed-publisher':
            raise service.BootstrapServiceError('publisher not approved')
        return {**grant, 'upload_id': body['upload_id']}

    def run(paths, upload_id, request):
        assert gate.admit_programming()  # Fence is acquired inside Coordinator.
        result = co.execute_package_host_only(engine.HostOnlyPackageRequest(
            service._upload_paths(paths, upload_id).committed,
            request['source_commit'], request['artifact_sha256'], request['target_profile'],
            request['api_transaction_id'], publisher=request['publisher'],
        ), inject_failure=fault, programming_exclusion=gate.exclude)
        if corrupt_receipt:
            result['transaction']['api_transaction_id'] = '0' * 32
        return result

    with patch.object(service.ThreadingHTTPServer, '__init__', return_value=None) if not network else nullcontext():
        server = service.BootstrapHTTPServer(('127.0.0.1', 0), paths=paths,
            base_module=SimpleNamespace(), deployment_runner=run,
            host_only_package_admission=admit)
    if not network:
        server.server_close = lambda: None
    data = archive.read_bytes()
    uid = service.create_upload(paths, size=len(data), sha256=digest)['upload_id']
    offset = 0
    for chunk in (data[:100], data[100:]):
        if chunk:
            service.append_chunk(paths, uid, offset=offset,
                data_base64=base64.b64encode(chunk).decode(),
                sha256=hashlib.sha256(chunk).hexdigest())
            offset += len(chunk)
    service.commit_upload(paths, uid)
    return server, co, gate, dict(kind=kind, upload_id=uid)


def finish(server):
    server.deployment_thread.join(5)
    assert not server.deployment_thread.is_alive()
    return json.loads(server.bootstrap_paths.deployment_record.read_text())


class PackageAPIBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="plasma-1214-")
        self.addCleanup(self.temp.cleanup)
        self.counter = 0

    def case_temp(self):
        self.counter += 1
        path = Path(self.temp.name) / str(self.counter)
        path.mkdir()
        return path

    def test_api_queue_worker_coordinator_receipt(self):
        for sample in SAMPLES:
            with self.subTest(case=sample):
                tmp_path = self.case_temp()
                server, co, gate, body = composition(tmp_path, sample)
                try:
                    original_write = co.journal.write
                    def fenced_write(*args, **kwargs):
                        assert gate.blocked
                        return original_write(*args, **kwargs)
                    co.journal.write = fenced_write
                    queued = server.start_deployment(body)
                    record = finish(server)
                    assert record['state'] == 'succeeded'
                    receipt = record['result']['coordinator_receipt']
                    assert receipt['api_transaction_id'] == queued['transaction_id']
                    assert receipt['coordinator_transaction_id'] == co.journal.read().transaction_id
                    assert receipt['publisher'] == 'fixture-reviewed-publisher'
                    assert record['result']['install_qualified'] is False
                    assert gate.events == ['fence', 'idle_check', 'exit']
                    assert not gate.blocked
                    assert not co.paths.product_root.exists()
                finally:
                    server.server_close()


    def test_programming_preflight_denies_before_journal(self):
        for condition in ['site8', 'job', 'hardware', 'authority']:
            with self.subTest(case=condition):
                tmp_path = self.case_temp()
                server, co, gate, body = composition(tmp_path, SAMPLES[0])
                if condition == 'site8': gate.sites[7] = True
                if condition == 'job': gate.active_job = True
                if condition == 'hardware': gate.quiescent = False
                if condition == 'authority': gate.authorized = False
                try:
                    server.start_deployment(body)
                    assert finish(server)['state'] == 'recovery_required'
                    assert not co.paths.journal.exists()
                    assert not (co.paths.bootstrap_state_root / 'host-only-packages').exists()
                finally:
                    server.server_close()


    def test_concurrent_programming_denied_after_fence_before_final_idle_check(self):
        tmp_path = self.case_temp()
        server, co, gate, body = composition(tmp_path, SAMPLES[0])
        gate.proceed.clear()
        try:
            server.start_deployment(body)
            assert gate.entered.wait(5)
            assert gate.events == ['fence']
            assert not gate.admit_programming()
            assert not co.paths.journal.exists()
            gate.proceed.set()
            assert finish(server)['state'] == 'succeeded'
        finally:
            gate.proceed.set()
            server.server_close()


    def test_bridge_rollback_and_uncertainty(self):
        for (fault,state,blocked) in [
    ('after_stage', 'rolled_back', False),
    ('after_activate', 'rolled_back', False),
    ('rollback_unknown', 'recovery_required', True),
]:
            with self.subTest(case=(fault,state,blocked)):
                tmp_path = self.case_temp()
                server, co, gate, body = composition(tmp_path, SAMPLES[0], fault=fault)
                observed = []
                write = co.journal.write
                def fenced_write(*args, **kwargs):
                    assert not gate.admit_programming()
                    observed.append(args[1])
                    return write(*args, **kwargs)
                co.journal.write = fenced_write
                try:
                    server.start_deployment(body)
                    record = finish(server)
                    assert record['state'] == 'recovery_required'  # Never claim success on runner failure.
                    assert co.journal.read().state == state
                    assert gate.blocked is blocked
                    assert 'activating' in observed or fault == 'after_stage'
                    assert state in observed
                    with self.assertRaisesRegex(service.BootstrapServiceError, 'recovery'):
                        server.start_deployment(body)
                finally:
                    server.server_close()


    def test_trusted_grant_mismatch_rejected_before_worker(self):
        for (changes,reason) in [
    ({'publisher': 'forged'}, 'publisher not approved'),
    ({'source_commit': 'b'*40}, 'preflight failed'),
    ({'artifact_sha256': '0'*64}, 'IDENTITY_MISMATCH'),
    ({'target_profile': {**TARGET, 'board': 'other'}}, 'preflight failed'),
    ({'kind': 'native-c'}, 'AUTHORITY_INVALID'),
]:
            with self.subTest(case=(changes,reason)):
                tmp_path = self.case_temp()
                server, co, gate, body = composition(tmp_path, SAMPLES[0], grant_changes=changes)
                try:
                    with self.assertRaisesRegex(service.BootstrapServiceError, reason):
                        server.start_deployment(body)
                    assert server.deployment_thread is None
                    assert not co.paths.journal.exists()
                    assert not server.bootstrap_paths.deployment_record.exists()
                finally:
                    server.server_close()


    def test_caller_cannot_supply_authority_and_receipt_mismatch_fails_closed(self):
        tmp_path = self.case_temp()
        server, co, gate, body = composition(tmp_path, SAMPLES[0], corrupt_receipt=True)
        try:
            with self.assertRaisesRegex(service.BootstrapServiceError, 'CALLER_AUTHORITY_DENIED'):
                server.start_deployment({**body, 'publisher': 'fixture-reviewed-publisher'})
            server.start_deployment(body)
            assert finish(server)['state'] == 'recovery_required'
            assert co.journal.read().state == 'package_active'
        finally:
            server.server_close()


    def test_normal_service_never_admits_generic_package(self):
        for kind in ['native-c', 'python', 'fpga-image']:
            with self.subTest(case=kind):
                tmp_path = self.case_temp()
                with patch.object(service.ThreadingHTTPServer, '__init__', return_value=None):
                    server = service.BootstrapHTTPServer(('127.0.0.1', 0),
                        paths=service.ServicePaths(state_root=tmp_path), base_module=SimpleNamespace())
                server.server_close = lambda: None
                try:
                    with self.assertRaises(service.BootstrapServiceError):
                        server.start_deployment({'kind': kind, 'upload_id': 'a'*32})
                    assert server.deployment_thread is None
                    assert not server.bootstrap_paths.deployment_record.exists()
                finally:
                    server.server_close()


    def test_authenticated_http_upload_submit_and_status(self):
        api = load('ppu_package_loopback_client', 'ppu_deploy_api.py')
        for sample in [SAMPLES[0], SAMPLES[3], SAMPLES[4]]:
            with self.subTest(case=sample):
                tmp_path = self.case_temp()
                """Real loopback HTTP handlers; no claim of TLS or remote PPU acceptance."""
                import http.client
                try:
                    server, co, gate, body = composition(tmp_path, sample, network=True)
                except PermissionError as exc:
                    raise AssertionError(f"required loopback socket unavailable: {exc}") from exc
                token = service.provision_token(server.bootstrap_paths.token_file)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                connection = http.client.HTTPConnection(*server.server_address, timeout=5)
                def transport(method, path, payload, headers):
                    connection.request(method, path, body=payload, headers=dict(headers))
                    response = connection.getresponse()
                    return response.status, response.read()
                def call(path, payload=None, authenticated=True, method='POST'):
                    headers = {'Content-Type': 'application/json'}
                    if authenticated:
                        headers['Authorization'] = 'Bearer ' + token
                    connection.request(method, path, body=json.dumps(payload) if payload is not None else None,
                                       headers=headers)
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())
                try:
                    data = service._upload_paths(server.bootstrap_paths, body['upload_id']).committed.read_bytes()
                    digest = hashlib.sha256(data).hexdigest()
                    assert call('/v1/uploads', {'size': len(data), 'sha256': digest}, False)[0] == 401
                    client = api.BootstrapAPIClient('https://fixture.invalid', token, transport=transport)
                    uid = client.upload(data)
                    submitted = client.submit(kind=body['kind'], upload_id=uid)
                    result = finish(server)
                    assert result['state'] == 'succeeded'
                    polled = client.deployment_state(submitted.transaction_id)
                    assert polled['transaction_id'] == submitted.transaction_id
                    assert polled['result']['coordinator_receipt']['coordinator_transaction_id'] == co.journal.read().transaction_id
                finally:
                    connection.close()
                    server.shutdown()
                    thread.join(5)
                    server.server_close()


    def test_client_upload_http_handlers_to_coordinator_without_socket(self):
        import io
        api = load('ppu_package_bridge_client', 'ppu_deploy_api.py')
        for sample in (SAMPLES[0], SAMPLES[3], SAMPLES[4]):
            with self.subTest(kind=sample[1]):
                server, co, gate, body = composition(self.case_temp(), sample)
                token = service.provision_token(server.bootstrap_paths.token_file)
                calls = []

                class MemoryConnection:
                    def __init__(self, raw):
                        self.input = io.BytesIO(raw)
                        self.output = io.BytesIO()
                    def makefile(self, *args):
                        return self.input
                    def sendall(self, data):
                        self.output.write(data)

                def transport(method, path, payload, headers):
                    calls.append((method, path))
                    payload = payload or b''
                    raw = (method + ' ' + path + ' HTTP/1.0\r\n' +
                           ''.join(key + ': ' + value + '\r\n' for key, value in headers.items()) +
                           'Content-Length: ' + str(len(payload)) + '\r\n\r\n').encode() + payload
                    connection = MemoryConnection(raw)
                    service.BootstrapHandler(connection, ('127.0.0.1', 0), server)
                    header, data = connection.output.getvalue().split(b'\r\n\r\n', 1)
                    return int(header.split()[1]), data

                try:
                    data = service._upload_paths(server.bootstrap_paths, body['upload_id']).committed.read_bytes()
                    client = api.BootstrapAPIClient('https://fixture.invalid', bearer_token=token, transport=transport)
                    uid = client.upload(data)
                    submission = client.submit(kind=body['kind'], upload_id=uid)
                    record = finish(server)
                    assert record['state'] == 'succeeded'
                    state = client.deployment_state(submission.transaction_id)
                    assert state['result']['coordinator_receipt']['coordinator_transaction_id'] == co.journal.read().transaction_id
                    assert calls[-1] == ('GET', '/v1/deployment')
                    assert ('POST', f'/v1/uploads/{uid}/commit') in calls
                    # Caller-supplied target authority is rejected before transport.
                    count = len(calls)
                    with self.assertRaises(api.DeploymentAPIError):
                        client.submit(kind=body['kind'], upload_id=uid, ppu_id='forged')
                    assert len(calls) == count
                finally:
                    server.server_close()


    def test_malformed_package_preflight_prevents_worker(self):
        samples = (
            ('cross-kind', 'python', {'payload/bin/hidden': b'not python'}),
            ('traversal', 'python', {'payload/python/../escape.py': b'pass'}),
            ('missing-pair', 'fpga-image', {'payload/fpga/z2-identity.bit': b'image'}),
        )
        for sample in samples:
            with self.subTest(sample=sample[0]):
                server, co, gate, body = composition(self.case_temp(), sample)
                try:
                    with self.assertRaisesRegex(service.BootstrapServiceError, 'preflight failed'):
                        server.start_deployment(body)
                    assert server.deployment_thread is None
                    assert not co.paths.journal.exists()
                finally:
                    server.server_close()

    def test_shared_coordinator_lock_denies_api_worker(self):
        import fcntl
        server, co, gate, body = composition(self.case_temp(), SAMPLES[0])
        try:
            with co.paths.lock.open('a+b') as held:
                fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                server.start_deployment(body)
                assert finish(server)['state'] == 'recovery_required'
                assert not co.paths.journal.exists()
                assert gate.events == []
        finally:
            server.server_close()

    def test_repeated_submission_rechecks_cached_release(self):
        server, co, gate, body = composition(self.case_temp(), SAMPLES[0])
        try:
            server.start_deployment(body)
            assert finish(server)['state'] == 'succeeded'
            first = co.journal.read().transaction_id
            server.start_deployment(body)
            assert finish(server)['state'] == 'succeeded'
            assert co.journal.read().transaction_id != first
            root = co.paths.bootstrap_state_root / 'host-only-packages'
            cached = next((root / 'releases').rglob('wordport.py'))
            cached.chmod(0o600)
            cached.write_bytes(b'corrupt')
            server.start_deployment(body)
            assert finish(server)['state'] == 'recovery_required'
            assert co.journal.read().state == 'recovery_required'
            assert gate.blocked
            assert co.journal.read().error_message == 'HOST_ONLY_ACTIVE_CACHE_REQUIRES_RECOVERY'
        finally:
            server.server_close()

    def test_test_composition_cannot_use_runtime_runner_or_production_state(self):
        tmp_path = self.case_temp()
        for paths, kwargs in [
            (service.ServicePaths(state_root=tmp_path), {}),
            (service.ServicePaths(), {'deployment_runner': lambda *args: {}}),
        ]:
            with self.assertRaisesRegex(service.BootstrapServiceError, 'COMPOSITION_DENIED'):
                service.BootstrapHTTPServer(('127.0.0.1', 0), paths=paths,
                    base_module=SimpleNamespace(), host_only_package_admission=lambda body: body, **kwargs)


if __name__ == "__main__":
    unittest.main()
