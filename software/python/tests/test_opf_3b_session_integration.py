"""OPF-3B Host-only admission and C-3 ownership evidence."""
from __future__ import annotations

import os
import sys
import time

import pytest

from plasma_opf import OPF_PROGRAMMING_SCHEMA, TimeoutPolicy
from .test_ppu_bundle_v3_packages_contract import ROOT
from .test_ppu_open_provider_contract import observed, staged_provider

sys.path.insert(0, str(ROOT / "scripts"))
import ppu_opf_site_session as opf  # noqa: E402
import ppu_site_worker as worker  # noqa: E402


class Adapter:
    name = "host-only-ps"
    operations = frozenset({"erase"})
    supported_sites = frozenset({1, 2})

    def __init__(self):
        self.revision = 1
        self.safe = True

    def identity(self):
        return {"revision": self.revision}

    def startup_sealed_sites(self):
        return set()

    def run(self, site, operation, *, deadline, cancel, image=None):
        return {"result": "PASS", "safe_off": self.safe}


class Client:
    def __init__(self, core):
        self.core = core

    def call(self, op, **fields):
        reply = self.core.handle({"protocol": worker.PROTOCOL, "op": op, **fields},
                                 (os.getpid(), os.getuid(), os.getgid()), role="control")
        if not reply["ok"]:
            raise worker.SiteWorkerDenied(reply["error"])
        return reply["result"]

    def open_job_session(self, **fields):
        return self.call("open_job_session", **fields)


def test_route_identity_site_owner_deadline_and_safety(tmp_path):
    root, digest, _ = staged_provider(tmp_path / "bundle", provider_id="ps-engine",
                                      transport="ps-only", target="new-ic")
    leases = {"job-a", "job-b", "job-c"}
    adapter = Adapter()
    core = worker.SiteWorkerCore(adapter, runtime_pid=os.getpid,
                                 lease_verifier=lambda job, kind: job in leases,
                                 seal_dir=tmp_path / "seals")
    client = Client(core)
    selection = {"schema": OPF_PROGRAMMING_SCHEMA, "provider": "ps-engine",
                 "profile": "profile", "timeout_ms": 1000}
    policy = TimeoutPolicy(2000, 5000)

    def open_for(job, site=1, *, selected=selection, started=None):
        started = time.monotonic() if started is None else started
        return opf.open_provider_job_session(
            client, product_root=root, asset_set_sha256=digest,
            selection=selected, policy=policy, job_id=job, target="new-ic",
            operation="erase", site_id=site, image_size=0,
            hardware=observed(transport="ps-only"),
            job_deadline_monotonic=started + 1, job_timeout_s=1.0)

    first = open_for("job-a")
    assert first.timeout_ms == 1000 and first.timeout_source == "bundle_override"
    assert core._sessions[first.session_id].expires == first.deadline_monotonic
    assert core._sessions[first.session_id].provider_route["asset_set_sha256"] == digest
    assert core._sessions[first.session_id].provider_route["provider_package"] == "ps-engine"
    with pytest.raises(worker.SiteWorkerDenied, match="SITE_BUSY"):
        open_for("job-b")
    with pytest.raises(worker.SiteWorkerDenied, match="JOB_SESSION_ALREADY_ACTIVE"):
        open_for("job-a", site=2)
    second = open_for("job-b", site=2)
    assert client.call("run", session_id=second.session_id, site=2, operation="erase")["result"] == "PASS"
    with pytest.raises(worker.SiteWorkerDenied, match="PROVIDER_ROUTE_MISMATCH"):
        client.call("run", session_id=first.session_id, site=2, operation="erase")
    with pytest.raises(ValueError, match="JOB_DEADLINE_EXPIRED"):
        open_for("job-c", started=time.monotonic() - 2)
    adapter.revision = 2
    with pytest.raises(worker.SiteWorkerDenied, match="SESSION_INVALIDATED_FPGA_IDENTITY_CHANGED"):
        client.call("run", session_id=first.session_id, site=1, operation="erase")
    assert client.call("close_session", session_id=first.session_id)["sealed_sites"] == []
    assert client.call("close_session", session_id=second.session_id)["sealed_sites"] == []

    third = open_for("job-c")
    adapter.safe = False
    with pytest.raises(worker.SiteWorkerDenied, match="OUTCOME_UNKNOWN_SITE_SEALED"):
        client.call("run", session_id=third.session_id, site=1, operation="erase")
    assert 1 in core._sealed


def test_selection_mismatch_never_claims_site(tmp_path):
    root, digest, _ = staged_provider(tmp_path / "bundle", provider_id="ps-engine",
                                      transport="ps-only", target="new-ic")
    core = worker.SiteWorkerCore(Adapter(), runtime_pid=os.getpid,
                                 lease_verifier=lambda job, kind: True,
                                 seal_dir=tmp_path / "seals")
    with pytest.raises(ValueError, match="PROVIDER_SELECTION_MISMATCH"):
        opf.open_provider_job_session(
            Client(core), product_root=root, asset_set_sha256=digest,
            selection={"schema": OPF_PROGRAMMING_SCHEMA, "provider": "other",
                       "profile": "profile"}, policy=TimeoutPolicy(1000, 5000),
            job_id="job-a", target="new-ic", operation="erase", site_id=1,
            image_size=0, hardware=observed(transport="ps-only"),
            job_deadline_monotonic=time.monotonic() + 1, job_timeout_s=1.0)
    assert core._sessions == {}


def test_safe_failure_cancellation_and_runtime_restart(tmp_path):
    class SafeFailure(Adapter):
        def run(self, site, operation, *, deadline, cancel, image=None):
            raise worker.TransportFailed("OPENOCD_FLASH_FAILED")

    pid = [os.getpid()]
    core = worker.SiteWorkerCore(SafeFailure(), runtime_pid=lambda: pid[0],
                                 lease_verifier=lambda job, kind: True,
                                 seal_dir=tmp_path / "seals")
    client = Client(core)
    first = client.call("open_job_session", job_id="job-a", sites=[1], max_runtime_s=5)
    with pytest.raises(worker.SiteWorkerDenied, match="OPERATION_FAILED_SAFE"):
        client.call("run", session_id=first["session_id"], site=1, operation="erase")
    assert core._sealed == set()
    assert client.call("close_session", session_id=first["session_id"])["sealed_sites"] == []
    second = client.call("open_job_session", job_id="job-b", sites=[1], max_runtime_s=5)
    core._sessions[second["session_id"]].cancel.set()
    with pytest.raises(worker.SiteWorkerDenied, match="SESSION_CLOSED"):
        client.call("run", session_id=second["session_id"], site=1, operation="erase")
    client.call("close_session", session_id=second["session_id"])
    third = client.call("open_job_session", job_id="job-c", sites=[1], max_runtime_s=5)
    pid[0] = os.getpid() + 100000
    core._drop_if_runtime_restarted()
    assert third["session_id"] not in core._sessions
    assert core._site_owners == {}
