"""Event-controlled Host-only lane acceptance; no services or devices.

Timeouts are watchdogs. Overlap is proven by all submission events occurring
before any terminal release, which cannot pass with the old sequential walk.
"""
from __future__ import annotations
import json
import threading
import time
import pytest
from plasma_manager.programming import ProgrammingError
from plasma_manager.programming_batch import ProgrammingBatchCoordinator
from .test_bundle_programming_workflow import FakeGateway, image
from .test_programming_batch_targets import rig, one, with_start

WAIT = 10


class EventGateway(FakeGateway):
    """Multiplex Job IDs and model the existing PPU REST execution owner."""
    def __init__(self, base, sites):
        super().__init__(image=image(), coordinator=base.coordinator, resource_for=base.resource_for)
        self.lock = threading.RLock()
        self.submitted = {s: threading.Event() for s in sites}
        self.release = {s: threading.Event() for s in sites}
        self.observed = {s: threading.Event() for s in sites}
        self.jobs, self.active, self.finals = {}, {}, {}
        self.unknown = set()
        self.max_active = 0
        self.before_post = None
        self.terminal_barrier = None
        self.sealed = set()
        self.safe_off_by_site = {}
        self.worker_failure_by_site = {}

    def relay(self, method, path, **kw):
        if method == "POST" and path == "/api/jobs":
            post = json.loads(kw["body"])
            site = post["site_id"]
            if self.before_post:
                self.before_post(post)
            with self.lock:
                assert site not in self.active, "same Site overlapped"
                owner = post["execution_owner_id"]
                assert all(o == owner for o in self.active.values()), "foreign lease owner"
                child = FakeGateway(image=image(), coordinator=self.coordinator,
                                    resource_for=self.resource_for,
                                    job_final=self.finals.get(site, "success"),
                                    safe_off=self.safe_off_by_site.get(site, True))
                child.worker_failure = self.worker_failure_by_site.get(site, False)
                job_id = f"job-{len(self.jobs) + 1}"
                child._job_id = lambda: job_id
                child.relay(method, path, **kw)
                self.jobs[job_id] = child
                self.posts.append(post)
                self.active[site] = owner
                self.max_active = max(self.max_active, len(self.active))
                self.submitted[site].set()
            if site in self.unknown:
                raise TimeoutError("lost POST answer; never resend")
            return self._resp(202, {"job": {"job_id": job_id, "state": "queued"}})
        if method == "GET" and path.startswith("/api/status?job="):
            child = self.jobs[path.split("=", 1)[1]]
            site = child.posts[0]["site_id"]
            assert self.release[site].wait(WAIT), "test did not release terminal observation"
            if self.terminal_barrier is not None:
                self.terminal_barrier.wait(WAIT)
            child.polls = 1
            result = child.relay(method, path, **kw)
            with self.lock:
                self.active.pop(site, None)
                self.observed[site].set()
            return result
        result = super().relay(method, path, **kw)
        if method == "GET" and path.startswith("/api/status?site="):
            status, headers, payload = result
            data = json.loads(payload)
            with self.lock:
                if self.active:
                    data["ppu"]["execution"] = {
                        "busy": True, "active_job_count": len(self.active),
                        "owner_kind": "rest_client", "owner_id": next(iter(self.active.values()))}
                    site = int(path.split("=", 1)[1])
                    if site in self.active:
                        data["sites"][0].update(state="busy", current_job_id="active")
            if int(path.split("=", 1)[1]) in self.sealed:
                data["sites"][0]["state"] = "sealed"
            return status, headers, json.dumps(data).encode()
        return result


class Harness:
    def __init__(self, tmp_path, sites, aliases=("z2",), **kwargs):
        self.done = threading.Event()
        self.errors = []
        self.batches, self.workflow, gateways, _ = rig(
            tmp_path, aliases=aliases, sites=sites, spawn_batch=self.spawn, **kwargs)
        self.gateways = {}
        for alias, base in gateways.items():
            gateway = EventGateway(base, sites)
            base.relay = gateway.relay
            self.gateways[alias] = gateway
        self.workflow.spawn = lambda target: threading.Thread(target=target, daemon=True).start()
        self.workflow.sleep = self.batches.sleep = time.sleep
        self.workflow.poll_interval_s = self.batches.poll_interval_s = 0.001

    def spawn(self, target):
        def run():
            try:
                target()
            except BaseException as exc:
                self.errors.append(exc)
            finally:
                self.done.set()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def start(self, targets=None, **kwargs):
        self.request = with_start(self.workflow, targets or [one("z2", *self.gateways["z2"].submitted)], **kwargs)
        self.started = self.batches.start_batch(self.request)
        return self.started

    def finish(self):
        for gateway in self.gateways.values():
            for event in gateway.release.values():
                event.set()
        assert self.done.wait(WAIT)
        self.thread.join(WAIT)
        assert not self.errors
        return self.batches.status_batch(self.started["batch"]["batch_id"])["batch"]


@pytest.mark.parametrize("count", [2, 8])
def test_independent_sites_overlap_and_persist_terminal_updates(tmp_path, count):
    h = Harness(tmp_path, range(1, count + 1))
    gateway = h.gateways["z2"]
    def journal_before_post(post):
        batch = json.loads((tmp_path / "batches.json").read_text())["batches"][0]
        unit = next(u for u in batch["units"] if u["site_id"] == post["site_id"])
        assert unit["attempts"][-1]["state"] in ("starting", "running")
        runs = json.loads((tmp_path / "runs.json").read_text())["runs"]
        assert any(r["site_id"] == post["site_id"] and r["job_submission_count"] == 1 for r in runs)
    gateway.before_post = journal_before_post
    gateway.terminal_barrier = threading.Barrier(count)
    h.start()
    try:
        assert all(e.wait(WAIT) for e in gateway.submitted.values()), "serial walk cannot reach held peers"
        assert gateway.max_active == count
        assert not any(e.is_set() for e in gateway.observed.values())
        assert len({p["execution_owner_id"] for p in gateway.posts}) == 1
        with pytest.raises(ProgrammingError) as duplicate:
            h.batches.start_batch(h.request)
        assert duplicate.value.code == "programming_start_not_startable"
        with pytest.raises(ProgrammingError) as busy:
            h.batches.start_batch(with_start(h.workflow, [one("z2", 1)]))
        assert busy.value.code == "programming_batch_in_progress"
    finally:
        batch = h.finish()
    assert batch["counts"]["pass"] == count
    assert batch["counts"]["attempts"] == count
    stored = json.loads((tmp_path / "batches.json").read_text())["batches"][0]
    assert [u["outcome"] for u in stored["units"]] == ["PASS"] * count
    reloaded = ProgrammingBatchCoordinator(h.workflow, journal_path=tmp_path / "batches.json")
    assert reloaded.status_batch(batch["batch_id"])["batch"]["outcome"] == "PASS"
    assert len(gateway.posts) == count


def test_every_running_site_reports_its_own_progress(tmp_path):
    """A Batch has one current_run; each unit still carries its own Site's progress."""
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    h.start()
    try:
        assert gateway.submitted[1].wait(WAIT) and gateway.submitted[2].wait(WAIT)
        deadline = time.monotonic() + WAIT
        while not all((r.job or {}).get("job_id") for r in list(h.workflow._runs.values())):
            assert time.monotonic() < deadline, "runs never recorded their Job"
            time.sleep(0.001)
        for run in list(h.workflow._runs.values()):
            h.workflow._update(run, job={**run.job, "state": "running", "stage": "program",
                                         "progress_percent": 30 + run.site})
        live = h.batches.status_batch(h.started["batch"]["batch_id"])["batch"]
        assert live["current_run"]["site_id"] in (1, 2)
        for unit in live["units"]:
            attempt = unit["attempts"][-1]
            run = h.workflow._runs[attempt["run_id"]]
            assert run.site == unit["site_id"]
            assert unit["progress"] == {
                "attempt": 1, "run_id": attempt["run_id"], "job_id": run.job["job_id"],
                "job_state": "running", "stage": "program", "progress_percent": 30 + unit["site_id"]}
        assert len({u["progress"]["job_id"] for u in live["units"]}) == 2
        stored = json.loads((tmp_path / "batches.json").read_text())["batches"][0]
        assert all("progress" not in u for u in stored["units"]), "display projection is never journaled"
    finally:
        batch = h.finish()
    assert [u["outcome"] for u in batch["units"]] == ["PASS", "PASS"]


@pytest.mark.parametrize("peer_final", ["success", "failed"])
def test_slow_site_does_not_hold_peer_or_site_local_fail(tmp_path, peer_final):
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    gateway.finals[2] = peer_final
    h.start()
    try:
        assert gateway.submitted[1].wait(WAIT) and gateway.submitted[2].wait(WAIT)
        gateway.release[2].set()
        assert gateway.observed[2].wait(WAIT)
        assert not gateway.observed[1].is_set() and not h.done.is_set()
    finally:
        batch = h.finish()
    assert [u["outcome"] for u in batch["units"]] == ["PASS", "PASS" if peer_final == "success" else "FAIL"]


def test_stop_observes_submitted_jobs_without_cancelling(tmp_path):
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    gateway.finals[1] = "failed"
    h.start(retry_limit=3)
    try:
        assert all(e.wait(WAIT) for e in gateway.submitted.values())
        result = h.batches.request_stop_batch(h.started["batch"]["batch_id"])["batch"]
        assert result["stop_requested"] and result["outcome"] is None
        assert all(u["outcome"] is None for u in result["units"])
    finally:
        batch = h.finish()
    assert batch["execution_status"] == "STOPPED"
    assert [u["outcome"] for u in batch["units"]] == ["FAIL", "PASS"]
    assert len(gateway.posts) == 2


def test_unknown_latches_only_its_ppu_without_resend(tmp_path):
    h = Harness(tmp_path, (1, 2), aliases=("z2", "peer"))
    bad, good = h.gateways["z2"], h.gateways["peer"]
    bad.unknown.add(1)
    h.workflow.spawn = lambda target: target()
    unknown = threading.Event()
    original_start = h.workflow.start
    def start(alias, body, **kwargs):
        result = original_start(alias, body, **kwargs)
        if alias == 'z2':
            unknown.set()
        return result
    h.workflow.start = start
    original_admission = h.batches._site_block
    def admission(alias, site):
        if alias == 'z2' and site == 2:
            assert unknown.wait(WAIT)
        return original_admission(alias, site)
    h.batches._site_block = admission
    good.release[1].set()
    good.release[2].set()
    h.start([one("z2", 1, 2), one("peer", 1, 2)], retry_limit=3)
    batch = h.finish()
    assert len(bad.posts) == 1 and len(good.posts) == 2
    assert batch["units"][0]["outcome"] == "OUTCOME_UNKNOWN"
    assert batch["units"][1]["status"] in ("SKIPPED", "BLOCKED")
    assert all(u["outcome"] == "PASS" for u in batch["units"][2:])
    assert h.workflow.target_block("z2", 2)[1] == "OUTCOME_UNKNOWN_UNRESOLVED"


def test_same_site_start_cannot_overlap_a_live_lane(tmp_path):
    h = Harness(tmp_path, (1,))
    gateway = h.gateways["z2"]
    h.start()
    try:
        assert gateway.submitted[1].wait(WAIT)
        request = {k: v for k, v in {**h.request, "site_id": 1}.items() if k not in ("targets", "start_id")}
        plan = h.workflow.plan("z2", request)["plan"]
        for owner in (None, h.started["batch"]["batch_id"], "foreign"):
            with pytest.raises(ProgrammingError) as caught:
                h.workflow.start("z2", {"plan_id": plan["plan_id"], "confirm": "PROGRAM"}, execution_owner_id=owner)
            assert caught.value.code == "programming_run_in_progress"
        assert len(gateway.posts) == 1
    finally:
        assert h.finish()["outcome"] == "PASS"


def test_retry_serializes_same_site_without_waiting_for_peer(tmp_path):
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    retried = threading.Event()
    gateway.finals[1] = "failed"
    def before_post(post):
        if post["site_id"] == 1 and any(p["site_id"] == 1 for p in gateway.posts):
            assert gateway.observed[1].is_set() and not gateway.observed[2].is_set()
            gateway.finals[1] = "success"
            retried.set()
    gateway.before_post = before_post
    h.start(retry_limit=1)
    try:
        assert all(e.wait(WAIT) for e in gateway.submitted.values())
        gateway.release[1].set()
        assert retried.wait(WAIT), "Retry must not wait for unrelated Site 2"
    finally:
        batch = h.finish()
    first, second = batch["units"][0]["attempts"]
    assert first["retry"]["decision"] == "RETRY" and first["safe_off"] is True
    assert first["job_id"] != second["job_id"] and first["plan_id"] != second["plan_id"]
    assert batch["outcome"] == "PASS" and len(gateway.posts) == 3


@pytest.mark.parametrize("mismatch", ["owner", "resource", "image", "activation"])
def test_overlapping_run_requires_same_owner_resources_image_and_no_activation(tmp_path, mismatch):
    h = Harness(tmp_path, (1, 2))
    h.start([one("z2", 1)])
    gateway = h.gateways["z2"]
    try:
        assert gateway.submitted[1].wait(WAIT)
        request = {k: v for k, v in {**h.request, "site_id": 2}.items() if k not in ("targets", "start_id")}
        payload = h.workflow.plan("z2", request)["plan"]
        owner = h.started["batch"]["batch_id"]
        if mismatch == "owner":
            owner = "foreign-batch"
        elif mismatch == "resource":
            payload["resource"] = {**payload["resource"], "resource_set_sha256": "f" * 64}
        elif mismatch == "image":
            payload["image_asset"] = {**payload["image_asset"], "sha256": "f" * 64}
        else:
            payload["activation_required"] = True
        with pytest.raises(ProgrammingError) as caught:
            h.workflow.start("z2", {"plan_id": payload["plan_id"], "confirm": "PROGRAM"}, execution_owner_id=owner)
        assert caught.value.code == "programming_run_in_progress" and len(gateway.posts) == 1
    finally:
        assert h.finish()["outcome"] == "PASS"


def test_shared_failure_stops_global_admission_and_observes_accepted_job(tmp_path):
    armed, failed = threading.Event(), threading.Event()
    def gate(alias):
        if armed.is_set() and alias == "peer":
            assert h.gateways["z2"].submitted[1].wait(WAIT)
            return "SHARED_CONTROL_FAILURE", "AUTHORITY_UNAVAILABLE"
    h = Harness(tmp_path, (1,), aliases=("z2", "peer", "third"), platform_gate=gate)
    original_plan = h.workflow.plan
    def plan(alias, body):
        if alias == 'third':
            assert failed.wait(WAIT)
        return original_plan(alias, body)
    h.workflow.plan = plan
    original_spawn = h.batches.spawn
    def spawn(target):
        armed.set()
        original_spawn(target)
    h.batches.spawn = spawn
    h.start([one("z2", 1), one("peer", 1), one("third", 1)])
    try:
        # Observe the latch independently of run_status: pool shutdown can
        # wait for third's Plan before accepted-run draining calls run_status.
        deadline = time.monotonic() + WAIT
        while h.batches._control_failure is None:
            assert time.monotonic() < deadline, "shared failure never latched"
            time.sleep(0.001)
        failed.set()
        with pytest.raises(ProgrammingError) as caught:
            h.batches.start_batch(with_start(h.workflow, [one("third", 1)]))
        assert caught.value.code == "manager_shared_control_failure"
        assert not h.gateways["peer"].posts and not h.gateways["third"].posts
        assert not h.done.is_set()
    finally:
        failed.set()
        batch = h.finish()
    assert h.gateways["z2"].observed[1].is_set()
    assert batch["failure_domain"] == "SHARED_CONTROL_FAILURE"
    assert [u["outcome"] for u in batch["units"]] == ["PASS", None, None]
    assert "AUTHORITY_UNAVAILABLE" in batch["reason"]


@pytest.mark.parametrize("journal", ["batch", "run"])
def test_journal_failure_never_submits_peer_or_retry(tmp_path, journal):
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    armed = threading.Event()
    if journal == "batch":
        original = h.batches._write_journal_locked
        def persist():
            if armed.is_set():
                failed.set()
                raise OSError("journal unavailable")
            original()
        h.batches._write_journal_locked = persist
    else:
        original = h.workflow._write_journal_locked
        def persist():
            if armed.is_set():
                failed.set()
                raise OSError("journal unavailable")
            original()
        h.workflow._write_journal_locked = persist
    failed = threading.Event()
    original_plan = h.workflow.plan
    def plan(alias, body):
        if body['site_id'] == 2:
            assert failed.wait(WAIT)
        return original_plan(alias, body)
    h.workflow.plan = plan
    original_status = h.workflow.run_status
    def status(*args, **kwargs):
        if h.batches._control_failure is not None:
            failed.set()
        return original_status(*args, **kwargs)
    h.workflow.run_status = status
    gateway.before_post = lambda _post: armed.set()
    # Causal fault boundary: the first Start returns only after its POST and
    # subsequent journal failure; peers have not crossed their Start yet.
    h.workflow.spawn = lambda target: target()
    gateway.release[1].set()
    h.start(retry_limit=3)
    try:
        assert gateway.submitted[1].wait(WAIT)
    finally:
        batch = h.finish()
    assert len(gateway.posts) == 1 and batch["failure_domain"] == "SHARED_CONTROL_FAILURE"
    assert not batch["units"][1]["attempts"]
    if journal == "batch":
        assert batch["journal_persisted"] is False
    else:
        assert batch["outcome"] == "OUTCOME_UNKNOWN"


@pytest.mark.parametrize("state, expected", [("planned", "BLOCKED"), ("starting", "OUTCOME_UNKNOWN")])
def test_crash_boundary_without_run_answer_never_resubmits(tmp_path, state, expected):
    pending = []
    batches, workflow, gateways, _ = rig(tmp_path, spawn_batch=pending.append)
    started = batches.start_batch(with_start(workflow, [one("z2", 1, 2)]))
    batch = batches._batches[started["batch"]["batch_id"]]
    batch["units"][0]["attempts"].append({"attempt": 1, "state": state, "plan_id": "lost-plan", "run_id": None})
    with batches._lock:
        batches._persist_locked()
    restarted = ProgrammingBatchCoordinator(workflow, journal_path=tmp_path / "batches.json")
    final = restarted.status_batch(batch["batch_id"])["batch"]
    assert [u["outcome"] for u in final["units"]] == [expected, "BLOCKED"]
    assert gateways["z2"].posts == []
    if state == "starting":
        assert restarted._site_block("z2", 2)[1] == "OUTCOME_UNKNOWN_UNRESOLVED"
        restarted.spawn = lambda target: target()
        another = restarted.start_batch(with_start(workflow, [one("z2", 2)]))["batch"]
        assert another["outcome"] == "BLOCKED" and gateways["z2"].posts == []



def test_stop_during_plan_prevents_start_and_does_not_fabricate_cancellation(tmp_path):
    h = Harness(tmp_path, (1,))
    planned, resume = threading.Event(), threading.Event()
    original = h.workflow.plan
    def plan(*args, **kwargs):
        result = original(*args, **kwargs)
        planned.set()
        assert resume.wait(WAIT)
        return result
    h.workflow.plan = plan
    h.start()
    try:
        assert planned.wait(WAIT)
        h.batches.request_stop_batch(h.started["batch"]["batch_id"])
    finally:
        resume.set()
        batch = h.finish()
    assert not h.gateways["z2"].posts
    assert batch["execution_status"] == "STOPPED" and batch["outcome"] == "BLOCKED"
    assert batch["units"][0]["status"] == "SKIPPED"


def test_simultaneous_failures_apply_threshold_before_any_retry(tmp_path):
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    gateway.finals.update({1: "failed", 2: "failed"})
    gateway.terminal_barrier = threading.Barrier(2)
    h.start(retry_limit=3, stop_policy={"kind": "failed_sites", "threshold": 1})
    try:
        assert all(e.wait(WAIT) for e in gateway.submitted.values())
    finally:
        batch = h.finish()
    assert len(gateway.posts) == 2 and batch["counts"]["fail"] == 2
    assert all(u["attempts"][0]["retry"]["decision"] == "NO_RETRY" for u in batch["units"])



def test_missing_safe_off_blocks_retry_while_healthy_peer_passes(tmp_path):
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    gateway.finals[1] = "failed"
    gateway.safe_off_by_site[1] = False
    h.start(retry_limit=3)
    try:
        assert all(e.wait(WAIT) for e in gateway.submitted.values())
    finally:
        batch = h.finish()
    assert [u["outcome"] for u in batch["units"]] == ["FAIL", "PASS"]
    assert batch["units"][0]["reason"] == "RETRY_NOT_ELIGIBLE_SAFE_OFF_NOT_VERIFIED"
    assert len(gateway.posts) == 2


@pytest.mark.parametrize("retry_limit, decision", [(0, "NO_RETRY"), (1, "RETRY")])
def test_definite_site_fail_in_ppu_error_shape_is_safe_off_verified(tmp_path, retry_limit,
                                                                     decision):
    """WP-07 step 6b: a VERIFY_MISMATCH reported as a PPU Job ``error`` keeps
    the Site Worker's SAFE_OFF, so it is a retry-eligible definite FAIL."""
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    gateway.finals[1] = "error"
    gateway.worker_failure_by_site[1] = True
    def before_post(post):
        if post["site_id"] == 1 and any(p["site_id"] == 1 for p in gateway.posts):
            gateway.finals[1] = "success"
            gateway.worker_failure_by_site[1] = False
    gateway.before_post = before_post
    h.start(retry_limit=retry_limit)
    try:
        assert all(e.wait(WAIT) for e in gateway.submitted.values())
    finally:
        batch = h.finish()
    first = batch["units"][0]["attempts"][0]
    assert first["outcome"] == "FAIL" and first["safe_off"] is True
    assert first["retry"] == {"eligible": True, "reason": "DEFINITE_FAIL_SAFE_OFF_VERIFIED",
                              "decision": decision}
    assert batch["units"][1]["outcome"] == "PASS"
    if retry_limit:
        assert batch["units"][0]["outcome"] == "PASS" and len(gateway.posts) == 3
    else:
        assert batch["units"][0]["outcome"] == "FAIL" and len(gateway.posts) == 2


@pytest.mark.parametrize("seal_before_start", [True, False])
def test_sealed_site_cannot_start_or_retry_and_peer_passes(tmp_path, seal_before_start):
    h = Harness(tmp_path, (1, 2))
    gateway = h.gateways["z2"]
    gateway.finals[1] = "failed"
    if seal_before_start:
        gateway.sealed.add(1)
    else:
        gateway.before_post = lambda post: gateway.sealed.add(1) if post["site_id"] == 1 else None
    h.start(retry_limit=3)
    try:
        assert gateway.submitted[2].wait(WAIT)
    finally:
        batch = h.finish()
    assert batch["units"][0]["outcome"] == ("BLOCKED" if seal_before_start else "FAIL")
    assert batch["units"][1]["outcome"] == "PASS"
    assert len(gateway.posts) == (1 if seal_before_start else 2)


@pytest.mark.parametrize('stage', ['readiness', 'plan', 'start'])
@pytest.mark.parametrize('shared_ppu', [False, True])
def test_pre_submit_blocked_lane_cannot_delay_healthy_post(tmp_path, stage, shared_ppu):
    h = Harness(tmp_path, (1, 2), aliases=('z2', 'peer'))
    entered, release = threading.Event(), threading.Event()
    method = {'readiness': 'target_block', 'plan': 'plan', 'start': 'start'}[stage]
    original = getattr(h.workflow, method)

    phase = threading.local()
    if stage == 'start':
        # Make Start synchronously drive its real pre-submit HTTP path, as
        # permitted by the workflow's injected spawn contract. Job observation
        # is also held, so B must POST while A's Start is still blocked.
        h.workflow.spawn = lambda target: target()

    def held(alias, body, **kwargs):
        site = body if stage == 'readiness' else (
            body['site_id'] if stage == 'plan' else h.workflow._plans[body['plan_id']].site)
        if (alias, site) != ('z2', 1):
            assert entered.wait(WAIT), 'establish slow HTTP before healthy dispatch'
        phase.current = stage
        try:
            return original(alias, body, **kwargs)
        finally:
            phase.current = None

    setattr(h.workflow, method, held)
    client = h.workflow.gateway_client_factory(h.workflow._record('z2').endpoint, 5)
    relay = client.relay
    def remote(method, path, **kwargs):
        if (method == 'GET' and path == '/api/status?site=1'
                and getattr(phase, 'current', None) == stage):
            entered.set()
            assert release.wait(WAIT), 'test must release slow remote HTTP'
        return relay(method, path, **kwargs)
    client.relay = remote
    peer = h.gateways['z2' if shared_ppu else 'peer']
    h.start([one('z2', 1, 2)] if shared_ppu else [one('z2', 1), one('peer', 2)])
    try:
        assert entered.wait(WAIT)
        assert peer.submitted[2].wait(WAIT), 'healthy POST must precede slow lane release'
        assert not release.is_set() and not h.gateways['z2'].submitted[1].is_set()
        runs = h.workflow._runs.values()
        assert any(r.site == 2 and r.alias == ('z2' if shared_ppu else 'peer') for r in runs)
    finally:
        release.set()
        batch = h.finish()
    assert batch['counts']['pass'] == 2


def test_slow_platform_admission_does_not_delay_other_ppu(tmp_path):
    entered, release = threading.Event(), threading.Event()
    def platform(alias):
        if alias == 'z2':
            entered.set()
            assert release.wait(WAIT)
        else:
            assert entered.wait(WAIT)
    h = Harness(tmp_path, (1,), aliases=('z2', 'peer'), platform_gate=platform)
    h.start([one('z2', 1), one('peer', 1)])
    try:
        assert entered.wait(WAIT)
        assert h.gateways['peer'].submitted[1].wait(WAIT)
        assert not release.is_set() and not h.gateways['z2'].posts
    finally:
        release.set()
        batch = h.finish()
    assert batch['outcome'] == 'PASS'


@pytest.mark.parametrize("count", [1, 2, 8])
def test_batch_wall_clock_is_16_seconds_for_overlapping_sites(tmp_path, monkeypatch, count):
    from datetime import datetime, timezone
    import plasma_manager.programming_batch as module

    class Clock(datetime):
        value = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.value

    monkeypatch.setattr(module, "datetime", Clock)
    h = Harness(tmp_path, range(1, count + 1))
    gateway = h.gateways["z2"]
    h.start()
    try:
        assert all(event.wait(WAIT) for event in gateway.submitted.values())
        assert gateway.max_active == count
        saved = json.loads((tmp_path / "batches.json").read_text())["batches"][0]
        assert saved["started_at"] == Clock.value.isoformat()
        assert saved["finished_at"] is None
        assert h.started["batch"]["started_at"] == saved["started_at"]
        Clock.value = datetime(2026, 11, 16, 12, 0, 16, tzinfo=timezone.utc)
    finally:
        batch = h.finish()
    assert batch["counts"]["pass"] == count
    assert (datetime.fromisoformat(batch["finished_at"])
            - datetime.fromisoformat(batch["started_at"])).total_seconds() == 16
    for _ in range(2):
        assert h.batches.status_batch(batch["batch_id"])["batch"]["finished_at"] == batch["finished_at"]
    reloaded = ProgrammingBatchCoordinator(h.workflow, journal_path=tmp_path / "batches.json")
    assert reloaded.status_batch(batch["batch_id"])["batch"]["finished_at"] == batch["finished_at"]
    assert len(gateway.posts) == count
