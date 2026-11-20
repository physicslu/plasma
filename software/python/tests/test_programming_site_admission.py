"""Host-only: Site-level Programming Admission (Gate 1, Path 1).

Three separate questions, three separate authorities:

* PPU Execution Ownership - one owner per PPU; one Batch may run several Site
  Jobs. Judged by the PPU's atomic lease; a different owner is ``PPU_BUSY``.
* Site Programming Admission - THIS Site released (no Job, idle row, lease free
  or held by this Batch). A busy peer Site of the same Batch never blocks it.
* Platform Maintenance - still requires the whole PPU idle (unchanged).

The real ``platform_gate_reason`` judges the Platform layer here, fed by a
fleet snapshot that lags the PPU (as the 2 s Manager poll does). The fake PPU
below models the PPU lease, Site rows, the post-terminal Site release and the
SITE_BUSY / PPU_BUSY refusals. No PPU, FPGA or DUT: timings measure Manager
scheduling only, never programming.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from plasma_manager.bootstrap_server import BootstrapPlasmaManagerHandler
from .test_bundle_programming_workflow import FakeGateway, image
from .test_programming_batch_targets import MultiplexGateway, one, rig, with_start

WAIT = 20.0


class AuthoritativePPU(MultiplexGateway):
    """The PPU side of admission: lease, Site rows, release, refusals."""

    def __init__(self, base, sites, *, job_s=0.05, release_s=0.0):
        super().__init__(image=image(), coordinator=base.coordinator,
                         resource_for=base.resource_for)
        self.sites = tuple(sites)
        self.lock = threading.RLock()
        self.job_s = job_s if callable(job_s) else (lambda _site: job_s)
        self.release_s = release_s
        self.hold: set[int] = set()       # Sites whose next Jobs run until finish()
        self.jobs: dict[str, dict] = {}
        self.released_at: dict[int, float] = {}
        self.lease_owner: str | None = None
        self.foreign: str | None = None   # a lease held by another Execution Owner
        self.quiesced = False             # Runtime activation / Asset Set quiesce
        self.refusals: list[tuple[int, str]] = []
        self.max_active = 0

    # -- authoritative state (always under self.lock)
    def _settle(self, now):
        for job in self.jobs.values():
            if job["terminal_at"] is None and job["end"] is not None and now >= job["end"]:
                job["terminal_at"] = job["end"]
                self.released_at[job["site"]] = job["end"] + self.release_s
        if not self._running():
            self.lease_owner = None

    def _running(self, site=None):
        return [j for j in self.jobs.values() if j["terminal_at"] is None
                and (site is None or j["site"] == site)]

    def _site_idle(self, site, now):
        return not self._running(site) and now >= self.released_at.get(site, 0.0)

    def active_at(self, site, t):
        with self.lock:
            return any(j["site"] == site and j["posted"] <= t
                       and (j["terminal_at"] is None or j["terminal_at"] > t)
                       for j in self.jobs.values())

    def finish(self, site):
        with self.lock:
            for job in self._running(site):
                job["end"] = time.monotonic()

    def _refuse(self, site, code):
        self.refusals.append((site, code))
        return self._resp(409, {"ok": False, "error": {"code": code}})

    def relay(self, method, path, **kw):
        now = time.monotonic()
        if method == "POST" and path == "/api/jobs":
            post = json.loads(kw["body"])
            site, owner = post["site_id"], post.get("execution_owner_id")
            with self.lock:
                self._settle(now)
                if self.quiesced:
                    return self._refuse(site, "PPU_BUSY")
                if self.foreign or (self.lease_owner not in (None, owner)):
                    return self._refuse(site, "PPU_BUSY")
                if not self._site_idle(site, now):
                    return self._refuse(site, "SITE_BUSY")
                child = FakeGateway(image=image(), coordinator=self.coordinator,
                                    resource_for=self.resource_for)
                job_id = f"job-{len(self.jobs) + 1:04d}"
                child._job_id = lambda: job_id
                child.relay(method, path, **kw)
                self.jobs[job_id] = {
                    "site": site, "owner": owner, "posted": now, "child": child,
                    "end": None if site in self.hold else now + self.job_s(site),
                    "terminal_at": None}
                self.lease_owner = owner
                self.posts.append(post)
                self.max_active = max(self.max_active, len(self._running()))
            return self._resp(202, {"job": {"job_id": job_id, "state": "queued"}})
        if method == "GET" and path.startswith("/api/status?job="):
            with self.lock:
                self._settle(now)
                job = self.jobs[path.split("=", 1)[1]]
                job["child"].polls = 0 if job["terminal_at"] is None else 1
                child = job["child"]
            return child.relay(method, path, **kw)
        result = super().relay(method, path, **kw)
        if method == "GET" and path.startswith("/api/status?site="):
            status, headers, payload = result
            data = json.loads(payload)
            site = int(path.split("=", 1)[1])
            with self.lock:
                self._settle(now)
                running = self._running()
                if self.foreign:
                    data["ppu"]["execution"] = {"busy": True, "active_job_count": 1,
                                                "owner_kind": "rest_client",
                                                "owner_id": self.foreign}
                elif running:
                    data["ppu"]["execution"] = {"busy": True, "active_job_count": len(running),
                                                "owner_kind": "rest_client",
                                                "owner_id": self.lease_owner}
                data["ppu"]["runtime_activation"] = {"active": self.quiesced}
                if self._running(site):
                    data["sites"][0].update(state="running", current_job_id="active")
                elif not self._site_idle(site, now):
                    data["sites"][0].update(state="stopping")   # releasing SAFE_OFF
            return status, headers, json.dumps(data).encode()
        return result


class LaggingFleet:
    """The Manager's fleet cache: ``lag_s`` behind the PPU, as the 2 s poll."""

    def __init__(self, ppu, lag_s=2.0):
        self.ppu, self.lag_s = ppu, lag_s
        self.observation = "current"
        self.present = True

    def snapshot(self):
        if not self.present:
            return {"ppus": []}
        t = time.monotonic() - self.lag_s
        sites = [{"site_id": s, "current_job_id": None,
                  "state": "running" if self.ppu.active_at(s, t) else "idle"}
                 for s in self.ppu.sites]
        return {"ppus": [{"alias": "z2", "observation": {"state": self.observation},
                          "gateway_live": True, "identity_conflict": False,
                          "errors": [], "sites": sites}]}

    def shared_control_check(self):
        return None


class Rig:
    def __init__(self, tmp_path, sites, *, legacy_gate=False, lag_s=2.0, **ppu):
        self.done, self.errors = threading.Event(), []
        handler = type("Handler", (BootstrapPlasmaManagerHandler,), {})
        self.handler = handler
        gate = handler.platform_gate_reason
        if legacy_gate:
            # The pre-change programming gate: the maintenance block, PPU-wide.
            def gate(alias, handler=handler):
                probe = object.__new__(handler)
                probe._fleet_item_for_alias = probe._programming_fleet_item_for_alias
                block = handler._platform_mutation_block(probe, alias)
                return None if block is None else ("TARGET_NOT_READY", block[0].upper())
        self.batches, self.workflow, gateways, coordinators = rig(
            tmp_path, sites=sites, spawn_batch=self.spawn, platform_gate=gate)
        self.ppu = AuthoritativePPU(gateways["z2"], sites, **ppu)
        gateways["z2"].relay = self.ppu.relay
        registry = self.workflow.registry
        registry.records = lambda: tuple(registry.record_by_alias(a) for a in registry.aliases)
        self.bootstrap_state = {}
        coordinator = coordinators["z2"]

        def status(alias):
            got = coordinator.status(alias)
            got["bootstrap"].update(self.bootstrap_state)
            return got
        handler.registry_store = registry
        handler.poller = self.fleet = LaggingFleet(self.ppu, lag_s)
        handler.bootstrap_coordinator = SimpleNamespace(
            registry=registry, status=status, shared_control_check=lambda: None)
        self.workflow.spawn = lambda target: threading.Thread(target=target, daemon=True).start()
        self.workflow.sleep = self.batches.sleep = time.sleep
        self.workflow.poll_interval_s = self.batches.poll_interval_s = 0.001
        self.admissions: list[tuple[float, int]] = []
        original = self.workflow.target_block

        def recorded(alias, site, **kw):
            verdict = original(alias, site, **kw)
            if verdict is None:
                self.admissions.append((time.monotonic(), site))
            return verdict
        self.workflow.target_block = recorded

    def spawn(self, target):
        def run():
            try:
                target()
            except BaseException as exc:  # noqa: BLE001 - reported by finish()
                self.errors.append(exc)
            finally:
                self.done.set()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def start(self, sites, **policy):
        self.batch_id = self.batches.start_batch(
            with_start(self.workflow, [one("z2", *sites)], **policy))["batch"]["batch_id"]
        return self.batch_id

    def view(self):
        return self.batches.status_batch(self.batch_id)["batch"]

    def until(self, predicate, what, wait=WAIT):
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.002)
        raise AssertionError(f"timed out waiting for {what}: {self.view()}")

    def posted(self, site):
        with self.ppu.lock:
            return sum(1 for j in self.ppu.jobs.values() if j["site"] == site)

    def finish(self, wait=WAIT):
        for site in list(self.ppu.hold):
            self.ppu.hold.discard(site)
            self.ppu.finish(site)
        assert self.done.wait(wait), self.view()
        self.thread.join(wait)
        assert not self.errors, self.errors
        return self.view()


def debug(**extra):
    return {"repeat": 2, "replace_ic_before_next_cycle": False, **extra}


# --------------------------------------------------------------- T1 / T2 / T3

def test_t1_peer_site_starts_while_site1_is_active(tmp_path):
    r = Rig(tmp_path, (1, 2))
    r.ppu.hold.add(1)
    r.ppu.job_s = lambda site: 0.05
    r.start((1, 2), repeat=2, replace_ic_before_next_cycle=False)
    # Site 2 runs BOTH its Cycles while Site 1's first Job is still active,
    # with a fleet snapshot (2 s behind) that never shows Site 1 idle.
    r.until(lambda: r.posted(2) == 2 and not r.ppu._running(2), "Site 2 two Cycles")
    assert r.posted(1) == 1 and r.ppu._running(1)
    batch = r.finish()
    assert batch["outcome"] == "PASS" and len(r.ppu.posts) == 4
    assert not r.ppu.refusals


def test_t2_same_site_is_refused_at_site_level_never_ppu_wide(tmp_path):
    r = Rig(tmp_path, (1, 2))
    r.ppu.hold.add(1)
    batch_id = r.start((1, 2), repeat=1)
    r.until(lambda: r.posted(1) == 1 and r.posted(2) == 1, "both Sites submitted")
    # Manager: a live run of Site 1 blocks Site 1 only.
    assert r.workflow.target_block("z2", 1, execution_owner_id=batch_id) == (
        "TARGET_NOT_READY", "RUN_IN_PROGRESS")
    # PPU (authoritative): Site 1's own row is busy under THIS Batch's lease.
    from plasma_manager.programming import _StepFailure
    client = r.workflow.gateway_client_factory("http://192.0.2.10:18080", 5.0)
    with pytest.raises(_StepFailure) as site_busy:
        r.workflow._readiness(client, 1, None, batch_id)
    assert site_busy.value.reason == "SITE_NOT_READY_OR_BUSY"
    # ...while Site 2, released under the same Batch lease, reads ready.
    r.until(lambda: not r.ppu._running(2), "Site 2 terminal")
    assert r.workflow._readiness(client, 2, None, batch_id)["state"] == "idle"
    # A second Job for Site 1 is refused by the PPU as SITE_BUSY, not PPU_BUSY.
    post = next(p for p in r.ppu.posts if p["site_id"] == 1)
    status, _h, _b = r.ppu.relay("POST", "/api/jobs", headers={}, body=json.dumps(post),
                                 timeout_s=1, max_response_bytes=1 << 20)
    assert status == 409 and r.ppu.refusals[-1] == (1, "SITE_BUSY")
    batch = r.finish()
    assert batch["outcome"] == "PASS" and len(r.ppu.posts) == 2


def test_t3_finished_site_starts_its_next_cycle_while_peer_is_active(tmp_path):
    r = Rig(tmp_path, (1, 2), job_s=0.03)
    r.ppu.hold.add(2)
    r.start((1, 2), repeat=3, replace_ic_before_next_cycle=False)
    unit1 = lambda: next(u for u in r.view()["units"] if u["site_id"] == 1)
    r.until(lambda: unit1()["cycle"]["settled"] == 3, "Site 1 all Cycles settled")
    assert r.posted(1) == 3 and unit1()["cycle"]["continue_seq"] == 0
    assert r.posted(2) == 1 and r.ppu._running(2)        # Site 2 Cycle 1 still active
    batch = r.finish()
    assert batch["outcome"] == "PASS" and batch["cycles"]["pass"] == 6


# ------------------------------------------------------------------------ T4

def test_t4_eight_sites_advance_independently_without_a_ppu_wide_barrier(tmp_path):
    sites = tuple(range(1, 9))
    # A live Job must span at least one 1s Manager poll to make the observed
    # overlap deterministic while the eighth Site remains held.
    r = Rig(tmp_path, sites, job_s=lambda site: 1.2 + 0.01 * site)
    r.ppu.hold.add(8)
    r.start(sites, repeat=3, replace_ic_before_next_cycle=False)
    # Sites 1..7 finish all three Cycles while Site 8's FIRST Job is active:
    # no Cycle waits for every Site of the PPU to finish the previous one.
    r.until(lambda: all(r.posted(s) == 3 for s in sites[:-1])
            and not any(r.ppu._running(s) for s in sites[:-1]), "Sites 1-7 done")
    assert r.posted(8) == 1 and r.ppu._running(8)
    batch = r.finish()
    assert batch["outcome"] == "PASS" and batch["cycles"]["pass"] == 24
    jobs = sorted(r.ppu.jobs.values(), key=lambda j: j["posted"])
    by_site = {s: [j for j in jobs if j["site"] == s] for s in sites}
    assert all(len(v) == 3 for v in by_site.values())
    assert max(by_site[s][2]["terminal_at"] for s in sites[:-1]) < by_site[8][0]["terminal_at"]
    assert r.ppu.max_active >= 4 and not r.ppu.refusals
    for site_jobs in by_site.values():                 # per-Site FIFO, no overlap
        for a, b in zip(site_jobs, site_jobs[1:]):
            assert a["terminal_at"] <= b["posted"]


# ------------------------------------------------------------------------ T5

def test_t5_another_execution_owner_is_ppu_busy_and_nothing_is_submitted(tmp_path):
    r = Rig(tmp_path, (1, 2))
    r.ppu.foreign = "another-owner"
    r.start((1, 2), repeat=1)
    batch = r.finish()
    assert {u["reason"] for u in batch["units"]} == {"ADMISSION_PPU_BUSY"}
    assert batch["outcome"] == "BLOCKED" and not r.ppu.posts


def test_t5_owner_change_between_cycles_pauses_not_waits(tmp_path):
    r = Rig(tmp_path, (1,), job_s=0.02)
    r.batches.release_wait_s = 30.0
    r.start((1,), **debug())
    r.until(lambda: r.posted(1) == 1 and not r.ppu._running(1), "Cycle 1")
    r.ppu.foreign = "another-owner"          # e.g. an Engineering session took the lease
    began = time.monotonic()
    r.until(lambda: r.view()["units"][0]["cycle"]["state"] == "AWAITING_CONTINUE", "pause")
    assert time.monotonic() - began < 5.0
    assert r.view()["units"][0]["cycle"]["wait_reason"] == "NEXT_CYCLE_EXECUTION_PPU_BUSY"
    assert r.posted(1) == 1
    r.batches.request_stop_batch(r.batch_id, {"stop": "STOP_QUEUING"})
    r.finish()
    assert r.posted(1) == 1


def test_t5_ppu_lease_refuses_a_foreign_post_while_a_batch_holds_it(tmp_path):
    r = Rig(tmp_path, (1, 2))
    r.ppu.hold.add(1)
    r.start((1,), repeat=1)
    r.until(lambda: r.posted(1) == 1, "Site 1 submitted")
    post = {**r.ppu.posts[0], "site_id": 2, "execution_owner_id": "another-owner"}
    status, _h, _b = r.ppu.relay("POST", "/api/jobs", headers={}, body=json.dumps(post),
                                 timeout_s=1, max_response_bytes=1 << 20)
    assert status == 409 and r.ppu.refusals[-1] == (2, "PPU_BUSY")
    r.finish()


# ------------------------------------------------------------------------ T6

def _probe(r, programming):
    probe = object.__new__(r.handler)
    probe._fleet_item_for_alias = probe._programming_fleet_item_for_alias
    return r.handler._platform_mutation_block(probe, "z2", programming=programming)


def test_t6_platform_maintenance_still_requires_the_whole_ppu_idle(tmp_path):
    r = Rig(tmp_path, (1, 2), lag_s=0.0)
    r.ppu.hold.add(1)
    r.start((1,), repeat=1)
    r.until(lambda: r.posted(1) == 1, "Site 1 active")
    assert _probe(r, programming=False)[0] == "ppu_busy"       # maintenance: unchanged
    assert _probe(r, programming=True) is None                 # programming: Site-level
    r.fleet.observation = "stale"
    assert _probe(r, programming=False)[0] == "ppu_busy"
    r.finish()
    r.until(lambda: not r.ppu._running(), "idle")
    assert _probe(r, programming=False)[0] == "ppu_idle_state_unproven"
    r.fleet.observation = "current"
    assert _probe(r, programming=False) is None


@pytest.mark.parametrize("state, reason", [
    ({"deployment": {"state": "recovery_required"}}, "ADMISSION_PPU_RECOVERY_REQUIRED"),
    ({"runtime": {"state": "recovery_required"}}, "ADMISSION_PPU_RECOVERY_REQUIRED"),
    ({"runtime": {"state": "runtime_activating"}}, "ADMISSION_PPU_PLATFORM_STATE_INVALID"),
])
def test_t6_platform_state_still_blocks_programming(tmp_path, state, reason):
    r = Rig(tmp_path, (1, 2))
    r.bootstrap_state.update(state)
    r.start((1, 2), repeat=1)
    batch = r.finish()
    assert {u["reason"] for u in batch["units"]} == {reason} and not r.ppu.posts


def test_t6_runtime_quiesce_refuses_new_programming(tmp_path):
    r = Rig(tmp_path, (1, 2))
    r.ppu.quiesced = True
    r.start((1, 2), repeat=1)
    batch = r.finish()
    assert {u["reason"] for u in batch["units"]} == {"ADMISSION_PPU_RUNTIME_QUIESCED"}
    assert not r.ppu.posts


def test_t6_quiesce_between_cycles_pauses_without_submitting(tmp_path):
    r = Rig(tmp_path, (1,), job_s=0.02)
    r.start((1,), **debug())
    r.until(lambda: r.posted(1) == 1 and not r.ppu._running(1), "Cycle 1")
    r.ppu.quiesced = True
    r.until(lambda: r.view()["units"][0]["cycle"]["state"] == "AWAITING_CONTINUE", "pause")
    assert r.view()["units"][0]["cycle"]["wait_reason"] == "NEXT_CYCLE_EXECUTION_PPU_RUNTIME_QUIESCED"
    r.batches.request_stop_batch(r.batch_id, {"stop": "STOP_QUEUING"})
    r.finish()
    assert r.posted(1) == 1


# ------------------------------------------------------------------------ T7

@pytest.mark.parametrize("fault, domain, reason", [
    ("stale", "TARGET_NOT_READY", "ADMISSION_PPU_OBSERVATION_UNTRUSTED"),
    ("absent", "TARGET_NOT_READY", "ADMISSION_PPU_OBSERVATION_UNTRUSTED"),
])
def test_t7_untrusted_fleet_observation_fails_closed(tmp_path, fault, domain, reason):
    r = Rig(tmp_path, (1, 2))
    if fault == "stale":
        r.fleet.observation = "stale"
    else:
        r.fleet.present = False
    r.start((1, 2), repeat=1)
    batch = r.finish()
    assert {(u["failure_domain"], u["reason"]) for u in batch["units"]} == {(domain, reason)}
    assert not r.ppu.posts


def test_t7_unreadable_platform_state_fails_closed(tmp_path):
    from plasma_manager.bootstrap import BootstrapManagerError
    r = Rig(tmp_path, (1, 2))
    original = r.handler.bootstrap_coordinator.status

    def broken(alias):
        raise BootstrapManagerError("remote status unreadable")
    r.handler.bootstrap_coordinator.status = broken
    r.start((1, 2), repeat=1)
    batch = r.finish()
    assert {u["failure_domain"] for u in batch["units"]} == {"TARGET_STATE_UNAVAILABLE"}
    assert not r.ppu.posts
    r.handler.bootstrap_coordinator.status = original


def test_t7_a_two_second_old_snapshot_does_not_hold_a_released_site(tmp_path):
    # The fleet keeps showing Site 1 running for 2 s after it ended; Site 1's
    # next Cycle is admitted from the PPU's own live state well before that.
    r = Rig(tmp_path, (1,), job_s=0.02, lag_s=2.0)
    r.start((1,), repeat=3, replace_ic_before_next_cycle=False)
    batch = r.finish()
    jobs = sorted(r.ppu.jobs.values(), key=lambda j: j["posted"])
    assert batch["cycles"]["pass"] == 3
    # Two further Job observations can each add at most one polling period.
    assert jobs[-1]["posted"] - jobs[0]["terminal_at"] < 2 * r.workflow.job_poll_interval_s + 0.5


# ------------------------------------------------------------------------ T8

def test_t8_unsafe_site_is_not_released_and_peer_keeps_cycling(tmp_path):
    r = Rig(tmp_path, (1, 2), job_s=0.02)
    original = r.ppu.relay

    def relay(method, path, **kw):
        result = original(method, path, **kw)
        if method == "POST" and path == "/api/jobs" and result[0] == 202:
            with r.ppu.lock:
                job = list(r.ppu.jobs.values())[-1]
                if job["site"] == 2:
                    job["child"].job_final, job["child"].safe_off = "failed", False
        return result
    r.ppu.relay = relay
    r.workflow.gateway_client_factory = lambda _e, _t: SimpleNamespace(relay=relay)
    r.start((1, 2), repeat=3, replace_ic_before_next_cycle=False)
    batch = r.finish()
    units = {u["site_id"]: u for u in batch["units"]}
    assert units[1]["cycle"]["pass"] == 3
    assert units[2]["cycle"]["settled"] == 1 and r.posted(2) == 1
    assert units[2]["reason"].startswith("CYCLE_NOT_RELEASED_SAFE_OFF_NOT_VERIFIED")


# ------------------------------------------------- Host-only latency measurement

def _measure(tmp_path, monkeypatch, *, legacy_gate, sites=(1, 2), repeat=4, job_s=0.15,
             release_s=0.05, lag_s=0.3):
    r = Rig(tmp_path, sites, legacy_gate=legacy_gate, lag_s=lag_s,
            job_s=job_s, release_s=release_s)
    r.batches.release_wait_s = 30.0
    if legacy_gate:
        # Reproduce #1503 exactly: PPU-wide gate + PPU_BUSY waited out.
        import plasma_manager.programming_batch as module
        monkeypatch.setattr(module, "RELEASE_PENDING_REASONS",
                            frozenset({"SITE_NOT_READY_OR_BUSY", "PPU_BUSY"}))
    began = time.monotonic()
    r.start(sites, repeat=repeat, replace_ic_before_next_cycle=False)
    batch = r.finish(wait=60)
    wall = time.monotonic() - began
    jobs = sorted(r.ppu.jobs.values(), key=lambda j: j["posted"])
    rows = []
    for site in sites:
        mine = [j for j in jobs if j["site"] == site]
        admitted = sorted(t for t, s in r.admissions if s == site)
        for prev, nxt in zip(mine, mine[1:]):
            released = prev["terminal_at"] + release_s
            admission = min((t for t in admitted if prev["terminal_at"] <= t <= nxt["posted"]),
                            default=None)
            rows.append({
                "site": site,
                "terminal_to_released_s": release_s,
                "released_to_admission_s": None if admission is None else admission - released,
                "admission_to_submitted_s": None if admission is None else nxt["posted"] - admission,
                "dispatch_latency_s": nxt["posted"] - prev["terminal_at"]})
    overlap = 0.0
    for a in jobs:
        for b in jobs:
            if a["site"] < b["site"]:
                overlap += max(0.0, min(a["terminal_at"], b["terminal_at"])
                               - max(a["posted"], b["posted"]))
    lat = [x["dispatch_latency_s"] for x in rows]
    return batch, {
        "gate": "legacy_ppu_wide" if legacy_gate else "site_level",
        "sites": len(sites), "cycles_per_site": repeat, "job_s": job_s,
        "release_s": release_s, "fleet_lag_s": lag_s, "wall_s": round(wall, 3),
        "dispatch_latency_max_s": round(max(lat), 3),
        "dispatch_latency_mean_s": round(sum(lat) / len(lat), 3),
        "cross_site_overlap_s": round(overlap, 3),
        "next_cycles": [{k: (round(v, 3) if isinstance(v, float) else v)
                         for k, v in row.items()} for row in rows]}


def test_host_latency_split_site_level_vs_legacy_ppu_wide(tmp_path, monkeypatch):
    layered, after = _measure(tmp_path / "after", monkeypatch, legacy_gate=False)
    legacy, before = _measure(tmp_path / "before", monkeypatch, legacy_gate=True)
    assert layered["outcome"] == "PASS" and layered["cycles"]["pass"] == 8
    # Every next Cycle waited only for its own Site's release (one 0.5 s
    # re-check at most), never for the peer Site or the fleet lag.
    from plasma_manager.programming_batch import RELEASE_RECHECK_S
    for row in after["next_cycles"]:
        assert row["released_to_admission_s"] is not None
        assert row["released_to_admission_s"] < RELEASE_RECHECK_S + 1.0 + 0.25
    assert after["cross_site_overlap_s"] > 0.5 * 4 * 0.15
    # The legacy (#1503) path completes too, only later: measured, not tuned.
    assert legacy["outcome"] == "PASS"
    out = os.environ.get("PLASMA_SITE_ADMISSION_METRICS")
    if out:
        Path(out).write_text(json.dumps({"after": after, "before": before,
                                         "before_outcome": legacy["outcome"]}, indent=1) + "\n")
