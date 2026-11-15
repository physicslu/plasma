"""Host-only source-boundary proofs for WP01 G0/G1/G2. No remote sockets."""
import threading
from types import SimpleNamespace

import pytest

from plasma_manager.bootstrap import BootstrapCredentialStore, ManagerBootstrapCoordinator
from plasma_manager.bootstrap_server import BootstrapPlasmaManagerHandler
from plasma_manager.client import PPUTransportError, _cloudflare_access_headers
from plasma_manager.poller import FleetPoller
from plasma_manager.programming import ProgrammingError
from plasma_manager.shared_control import SharedControlError
from .test_programming_batch_targets import rig, one, with_start
from .test_programming_batch_lanes import Harness, WAIT


@pytest.fixture
def authority(tmp_path, monkeypatch):
    for key in ('ORIGIN', 'CLIENT_ID', 'CLIENT_SECRET'):
        monkeypatch.delenv('PLASMA_MANAGER_CF_ACCESS_' + key, raising=False)
    batches, workflow, gateways, _ = rig(tmp_path, aliases=('z2', 'peer'))
    registry = workflow.registry
    registry.records = lambda: tuple(registry.record_by_alias(a) for a in registry.aliases)
    credentials = BootstrapCredentialStore(None)  # persistence optional, enrollment local
    class Client:
        def status(self):
            return 200, {'bootstrap': {'state': 'bootstrap_ready'},
                         'identity': {'device_id': 'ppu-device-0000000000000001'},
                         'runtime': {'state': 'runtime_absent'}}
    coordinator = ManagerBootstrapCoordinator(registry, credentials, 1,
                                              client_factory=lambda *_: Client())
    poller = FleetPoller(SimpleNamespace(fleet_snapshot=lambda: {'ppus': []}), 1000)
    poller.start()
    class Handler(BootstrapPlasmaManagerHandler):
        registry_store = registry
        bootstrap_coordinator = coordinator
    Handler.poller = poller
    try:
        yield batches, workflow, gateways, Handler, credentials
    finally:
        poller.stop()


def fail():
    raise RuntimeError('synthetic local dependency unavailable')


@pytest.mark.parametrize('fault', ['registry', 'poller', 'refresh', 'coordinator',
                                  'credentials', 'cf_partial', 'cf_invalid', 'transport_policy'])
def test_initial_global_failure_is_503_no_admission(authority, monkeypatch, tmp_path, fault):
    batches, workflow, gateways, handler, credentials = authority
    batches.shared_control_gate = handler.shared_control_gate
    workflow.shared_control_gate = handler.shared_control_gate
    assert handler.shared_control_gate() is None  # optional security absent is valid
    body = with_start(workflow, [one('z2', 2), one('peer', 2)])
    before = (tmp_path / 'batches.json').read_bytes()
    if fault == 'registry':
        monkeypatch.setattr(handler.registry_store, 'records', fail)
    elif fault == 'poller':
        handler.poller.stop()
    elif fault == 'refresh':
        monkeypatch.setattr(handler.poller.source, 'fleet_snapshot', fail)
        with pytest.raises(RuntimeError):
            handler.poller.refresh()
    elif fault == 'coordinator':
        handler.bootstrap_coordinator = object()
    elif fault == 'credentials':
        monkeypatch.setattr(credentials, 'public_state', lambda _a: fail())
    elif fault.startswith('cf_'):
        monkeypatch.setenv('PLASMA_MANAGER_CF_ACCESS_ORIGIN', 'invalid' if fault == 'cf_invalid' else 'https://example.invalid')
        if fault == 'cf_invalid':
            monkeypatch.setenv('PLASMA_MANAGER_CF_ACCESS_CLIENT_ID', 'synthetic-id')
            monkeypatch.setenv('PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET', 'synthetic-secret')
    else:
        monkeypatch.setenv('PLASMA_MANAGER_BOOTSTRAP_TRANSPORT', 'invalid')
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(body)
    assert caught.value.status == 503 and caught.value.code == 'manager_shared_control_failure'
    assert workflow._starts[body['start_id']]['state'] == 'ISSUED'
    workflow.require_batch_start(body['start_id'])
    assert batches.reconcile_start(body['start_id'])['reconciliation']['state'] == 'ACCEPTANCE_PENDING'
    assert (tmp_path / 'batches.json').read_bytes() == before
    assert not batches._batches and not workflow._runs
    assert all(not g.posts for g in gateways.values())


@pytest.mark.parametrize('site', [False, True])
@pytest.mark.parametrize('fault', ['registry', 'credential', 'client_configuration', 'remote_transport'])
def test_actual_source_boundaries_keep_shared_and_remote_distinct(authority, monkeypatch, site, fault):
    _, workflow, _, handler, credentials = authority
    coordinator = handler.bootstrap_coordinator
    workflow.coordinator = coordinator
    if site:
        from plasma_manager.bootstrap import BootstrapCredential
        credentials._credentials['z2'] = BootstrapCredential('z2', 'ppu-device-0000000000000001', 'synthetic', '')
    if fault == 'registry':
        monkeypatch.setattr(coordinator.registry, 'record_by_alias', lambda _a: fail())
    elif fault == 'credential':
        # public_state applies to anonymous Platform, record_for to enrolled Site.
        monkeypatch.setattr(credentials, 'public_state', lambda _a: fail())
        monkeypatch.setattr(credentials, 'record_for', lambda _a: fail())
    elif fault == 'client_configuration':
        monkeypatch.setattr(coordinator, 'client_factory', lambda *_: (_ for _ in ()).throw(PPUTransportError('local factory fault')))
    else:
        class Remote:
            def status(self, *args):
                raise PPUTransportError('remote read timed out')
        monkeypatch.setattr(coordinator, 'client_factory', lambda *_: Remote())
        if site:
            from plasma_manager.bootstrap import BootstrapCredential
            credentials._credentials['z2'] = BootstrapCredential('z2', 'ppu-device-0000000000000001', 'synthetic', '')
    if site:
        try:
            verdict = workflow.target_block('z2', 2)
        except SharedControlError:
            verdict = ('SHARED_CONTROL_FAILURE', 'source boundary propagated')
    else:
        verdict = handler.platform_gate_reason('z2')
    assert verdict[0] == ('TARGET_STATE_UNAVAILABLE' if fault == 'remote_transport' else 'SHARED_CONTROL_FAILURE')


def test_optional_cloudflare_and_exact_origin(monkeypatch):
    for key in ('ORIGIN', 'CLIENT_ID', 'CLIENT_SECRET'):
        monkeypatch.delenv('PLASMA_MANAGER_CF_ACCESS_' + key, raising=False)
    assert _cloudflare_access_headers('http://example.invalid') == {}
    monkeypatch.setenv('PLASMA_MANAGER_CF_ACCESS_ORIGIN', 'https://protected.invalid')
    with pytest.raises(SharedControlError):
        _cloudflare_access_headers('http://unrelated.invalid')
    monkeypatch.setenv('PLASMA_MANAGER_CF_ACCESS_CLIENT_ID', 'synthetic-id')
    monkeypatch.setenv('PLASMA_MANAGER_CF_ACCESS_CLIENT_SECRET', 'synthetic-secret')
    assert _cloudflare_access_headers('http://unrelated.invalid') == {}
    assert len(_cloudflare_access_headers('https://protected.invalid')) == 2


@pytest.mark.parametrize('stage', ['reservation', 'start', 'post'])
def test_late_shared_check_observes_accepted_job_and_never_submits_peer(tmp_path, stage):
    h = Harness(tmp_path, (1,), aliases=('z2', 'peer'))
    failed = threading.Event()
    gate = lambda: ('SHARED_CONTROL_FAILURE', 'AUTHORITY_LOST') if failed.is_set() else None
    h.batches.shared_control_gate = h.workflow.shared_control_gate = gate
    original = h.workflow.plan
    def plan(alias, body):
        if alias == 'peer':
            assert h.gateways['z2'].submitted[1].wait(WAIT)
        result = original(alias, body)
        if alias == 'peer' and stage == 'reservation':
            failed.set()
        return result
    h.workflow.plan = plan
    if stage == 'start':
        original_start = h.workflow.start
        def start(alias, body, **kw):
            if alias == 'peer':
                failed.set()
            return original_start(alias, body, **kw)
        h.workflow.start = start
    if stage == 'post':
        submit = h.workflow._submit_once
        def post(run, *args):
            if run.alias == 'peer':
                failed.set()
            return submit(run, *args)
        h.workflow._submit_once = post
    h.start([one('z2', 1), one('peer', 1)])
    assert h.gateways['z2'].submitted[1].wait(WAIT)
    assert failed.wait(WAIT)
    batch = h.finish()
    assert batch['failure_domain'] == 'SHARED_CONTROL_FAILURE'
    assert batch['units'][0]['outcome'] == 'PASS'
    assert batch['units'][1]['outcome'] is None
    assert len(h.gateways['z2'].posts) == 1 and not h.gateways['peer'].posts
    assert h.workflow._starts[h.request['start_id']]['state'] == 'CONSUMED'
    assert h.batches.reconcile_start(h.request['start_id'])['reconciliation']['state'] == 'TERMINAL_CONFIRMED'
    with pytest.raises(ProgrammingError) as caught:
        h.batches.start_batch(h.request)
    assert caught.value.status == 503


@pytest.mark.parametrize('count', [1, 2, 8])
@pytest.mark.parametrize('stage', ['platform', 'readiness', 'plan', 'start'])
def test_held_ppu_does_not_hold_healthy_1_2_8_site_ppu(tmp_path, count, stage):
    entered, release = threading.Event(), threading.Event()
    def platform(alias):
        if alias == 'z2' and stage == 'platform':
            entered.set()
            assert release.wait(WAIT)
        elif alias == 'peer' and stage == 'platform':
            assert entered.wait(WAIT)
    h = Harness(tmp_path, tuple(range(1, count + 1)), aliases=('z2', 'peer'), platform_gate=platform)
    method = {'readiness': 'target_block', 'plan': 'plan', 'start': 'start'}.get(stage)
    if method:
        original = getattr(h.workflow, method)
        def held(alias, body, **kw):
            if alias == 'z2':
                entered.set()
                assert release.wait(WAIT)
            else:
                assert entered.wait(WAIT)
            return original(alias, body, **kw)
        setattr(h.workflow, method, held)
    h.start([one('z2', *range(1, count + 1)), one('peer', *range(1, count + 1))])
    try:
        assert entered.wait(WAIT)
        assert all(event.wait(WAIT) for event in h.gateways['peer'].submitted.values())
        assert not release.is_set() and not h.gateways['z2'].posts
    finally:
        release.set()
        batch = h.finish()
    assert batch['counts']['pass'] == count * 2


@pytest.mark.parametrize('count', [2, 8])
@pytest.mark.parametrize('stage', ['readiness', 'plan', 'start'])
def test_held_site_keeps_same_ppu_peers_independent(tmp_path, count, stage):
    entered, release = threading.Event(), threading.Event()
    h = Harness(tmp_path, tuple(range(1, count + 1)))
    method = {'readiness': 'target_block', 'plan': 'plan', 'start': 'start'}[stage]
    original = getattr(h.workflow, method)
    def held(alias, body, **kw):
        site = body if stage == 'readiness' else (
            body['site_id'] if stage == 'plan' else h.workflow._plans[body['plan_id']].site)
        if site == 1:
            entered.set()
            assert release.wait(WAIT)
        else:
            assert entered.wait(WAIT)
        return original(alias, body, **kw)
    setattr(h.workflow, method, held)
    h.start()
    try:
        assert entered.wait(WAIT)
        assert all(h.gateways['z2'].submitted[s].wait(WAIT) for s in range(2, count + 1))
        assert not release.is_set() and not h.gateways['z2'].submitted[1].is_set()
    finally:
        release.set()
        batch = h.finish()
    assert batch['counts']['pass'] == count


def test_single_lane_uses_same_shared_checks(tmp_path):
    h = Harness(tmp_path, (1,))
    calls = []
    def gate():
        calls.append(True)
        return None
    h.batches.shared_control_gate = h.workflow.shared_control_gate = gate
    h.start()
    assert h.gateways['z2'].submitted[1].wait(WAIT)
    assert h.finish()['outcome'] == 'PASS'
    assert len(calls) >= 5  # G0, reservation, Start, pre-POST


def test_repaired_g0_preserves_issued_token_for_one_real_admission(tmp_path):
    bad = [True]
    batches, workflow, gateways, _ = rig(tmp_path, shared_control_gate=lambda:
        ('SHARED_CONTROL_FAILURE', 'CONFIG_UNAVAILABLE') if bad[0] else None)
    request = with_start(workflow, [one('z2', 2)])
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(request)
    assert caught.value.status == 503
    bad[0] = False
    batch = batches.start_batch(request)['batch']
    assert batch['outcome'] == 'PASS' and len(gateways['z2'].posts) == 1
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(request)
    assert caught.value.status == 409 and len(gateways['z2'].posts) == 1


@pytest.mark.parametrize('verdict', [object(), False, ('TARGET_NOT_READY', 'local'), ('SHARED_CONTROL_FAILURE', '')])
def test_malformed_shared_authority_never_admits(tmp_path, verdict):
    batches, workflow, gateways, _ = rig(tmp_path, shared_control_gate=lambda: verdict)
    request = with_start(workflow, [one('z2', 2)])
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(request)
    assert caught.value.status == 503
    assert workflow._starts[request['start_id']]['state'] == 'ISSUED'
    assert not gateways['z2'].posts


def test_g0_never_calls_remote_status(authority, monkeypatch):
    _, _, _, handler, _ = authority
    monkeypatch.setattr(handler.bootstrap_coordinator, 'client_factory', lambda *_: fail())
    assert handler.shared_control_gate() is None
    assert handler.platform_gate_reason('z2')[0] == 'SHARED_CONTROL_FAILURE'


def test_ambiguous_site_authority_stops_all_submission(tmp_path):
    batches, workflow, gateways, _ = rig(tmp_path, aliases=('z2', 'peer'))
    workflow.coordinator.assets = lambda _alias: fail()
    batch = batches.start_batch(with_start(workflow, [one('z2', 2), one('peer', 2)]))['batch']
    assert batch['failure_domain'] == 'SHARED_CONTROL_FAILURE'
    assert all(not g.posts for g in gateways.values())
    assert all(u['outcome'] is None for u in batch['units'])


def test_unclassified_plan_state_read_stops_global_dispatch(tmp_path, monkeypatch):
    batches, workflow, gateways, _ = rig(tmp_path, aliases=('z2', 'peer'))
    monkeypatch.setattr(workflow, '_gateway_get', lambda *_: fail())
    with pytest.raises(RuntimeError):
        workflow._ppu_resources('z2', 2)
    assert all(not g.posts for g in gateways.values())


def test_workflow_shared_latch_refuses_new_batch_before_consuming_token(tmp_path):
    batches, workflow, gateways, _ = rig(tmp_path)
    request = with_start(workflow, [one('z2', 2)])
    workflow._control_failure = 'EARLIER_RUN_SHARED_AUTHORITY_LOSS'
    with pytest.raises(ProgrammingError) as caught:
        batches.start_batch(request)
    assert caught.value.status == 503
    assert workflow._starts[request['start_id']]['state'] == 'ISSUED'
    assert not batches._batches and not gateways['z2'].posts
