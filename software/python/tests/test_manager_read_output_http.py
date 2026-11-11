"""Host-only HTTP integration: Read Memory binary download from a real Manager server.

A real ``ThreadingHTTPServer`` serves ``BootstrapPlasmaManagerHandler`` backed by a
real ``BundleProgrammingWorkflow`` (fake PPU Gateway only). The response is read
off a raw socket so a repeated header cannot be folded away by a client library.

Root cause pinned here (SWPC, 2026-11-11): the handler and ``_raw_response`` each
emitted ``Content-Length``; Node.js fetch rejects that response, so the Console
BFF answered ``503 manager_unavailable`` for a PASS Read. This is not HIL.
"""
from __future__ import annotations

import hashlib
import json
import socket
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_bundle_programming_workflow import (  # noqa: E402
    ALIAS, ICPN, READ_BODY, ops_workflow, plan_run,
)
from test_manager_bootstrap_rest import FakeBootstrapCoordinator, FakePoller  # noqa: E402

from plasma_manager.bootstrap_server import BootstrapPlasmaManagerHandler  # noqa: E402
from plasma_manager.config import ManagerConfig  # noqa: E402
from plasma_manager.registry import PPURegistryStore  # noqa: E402
from plasma_manager.server import PPUOperationGate  # noqa: E402

BASE = f"/api/registry/{ALIAS}/bootstrap/programming"


def raw_get(port: int, path: str) -> tuple[int, list[tuple[str, str]], bytes]:
    """One HTTP/1.1 GET over a plain socket: status, every header line, body."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n"
                     .encode("ascii"))
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    head, _, body = b"".join(chunks).partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    status = int(lines[0].split(" ")[1])
    headers = [(k.strip(), v.strip()) for k, _, v in (line.partition(":") for line in lines[1:])]
    return status, headers, body


def values(headers: list[tuple[str, str]], name: str) -> list[str]:
    return [v for k, v in headers if k.lower() == name.lower()]


@pytest.fixture
def read_manager(tmp_path: Path):
    workflow, coord, gateway = ops_workflow(tmp_path)
    _planned, run = plan_run(workflow, READ_BODY)
    assert run["outcome"] == "PASS", run
    registry = PPURegistryStore((), tmp_path / "registry.json")
    registry.add(alias=ALIAS, endpoint="http://192.168.2.99:18080")
    names = ("config", "registry_store", "poller", "bootstrap_coordinator",
             "operation_gate", "programming_workflow")
    previous = {n: getattr(BootstrapPlasmaManagerHandler, n) for n in names}
    BootstrapPlasmaManagerHandler.config = ManagerConfig(
        registry_state_path=tmp_path / "registry.json")
    BootstrapPlasmaManagerHandler.registry_store = registry
    BootstrapPlasmaManagerHandler.poller = FakePoller()
    BootstrapPlasmaManagerHandler.bootstrap_coordinator = FakeBootstrapCoordinator()
    BootstrapPlasmaManagerHandler.operation_gate = PPUOperationGate()
    BootstrapPlasmaManagerHandler.programming_workflow = workflow
    server = ThreadingHTTPServer(("127.0.0.1", 0), BootstrapPlasmaManagerHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server.server_address[1], workflow, coord, gateway, run
    finally:
        server.shutdown()
        server.server_close()
        for name, value in previous.items():
            setattr(BootstrapPlasmaManagerHandler, name, value)


def test_read_binary_has_exactly_one_content_length_and_matches_the_receipt(read_manager):
    port, workflow, coord, gateway, run = read_manager
    receipt = run["receipt"]["read_output"]
    posts, downloads, calls = len(gateway.posts), gateway.downloads, list(coord.calls)
    before = workflow.run_status(ALIAS, run["run_id"])["run"]

    status, headers, body = raw_get(port, f"{BASE}/runs/{run['run_id']}/output")

    assert status == 200
    assert values(headers, "Content-Length") == [str(len(body))]
    assert len(body) == receipt["bytes"] == READ_BODY["length"]
    assert hashlib.sha256(body).hexdigest() == receipt["sha256"]
    assert values(headers, "X-Plasma-Read-Sha256") == [receipt["sha256"]]
    assert values(headers, "Content-Type") == ["application/octet-stream"]
    assert values(headers, "Content-Disposition") == [
        f'attachment; filename="read-{ICPN}-0x08000010-777.bin"']
    assert values(headers, "Cache-Control") == ["no-store"]
    assert values(headers, "X-Content-Type-Options") == ["nosniff"]
    # No header of the binary response may repeat.
    names = [k.lower() for k, _ in headers]
    assert len(names) == len(set(names)), headers
    # A download is a read of retained bytes: no new Job, no PPU fetch, no B1/B2/B3,
    # and the run (PASS, SAFE_OFF evidence, single submission) is untouched.
    assert len(gateway.posts) == posts == 1 and gateway.downloads == downloads
    assert coord.calls == calls
    after = workflow.run_status(ALIAS, run["run_id"])["run"]
    assert after == before
    assert after["outcome"] == "PASS" and after["job_submission_count"] == 1
    assert after["auto_retry"] == "DISABLED"


def test_repeated_downloads_stay_single_headed_and_never_resubmit(read_manager):
    port, _workflow, _coord, gateway, run = read_manager
    bodies = set()
    for _ in range(3):
        status, headers, body = raw_get(port, f"{BASE}/runs/{run['run_id']}/output")
        assert status == 200 and values(headers, "Content-Length") == [str(len(body))]
        bodies.add(body)
    assert len(bodies) == 1 and len(gateway.posts) == 1 and gateway.downloads == 1


def test_tampered_or_missing_retained_bytes_fail_closed_as_json(read_manager, tmp_path):
    port, workflow, _coord, gateway, run = read_manager
    run_id = run["run_id"]
    retained = tmp_path / "programming-read-outputs" / f"{run_id}.bin"
    original = retained.read_bytes()

    # SHA-256 no longer matches the receipt: never served as a binary.
    tampered = bytes([original[0] ^ 0xFF]) + original[1:]
    workflow._read_outputs[run_id] = tampered
    status, headers, body = raw_get(port, f"{BASE}/runs/{run_id}/output")
    assert status == 410
    assert values(headers, "Content-Type") == ["application/json; charset=utf-8"]
    assert values(headers, "Content-Length") == [str(len(body))]
    assert json.loads(body)["error"]["code"] == "read_output_unavailable"
    assert not values(headers, "X-Plasma-Read-Sha256")

    # The retained binary is gone entirely.
    del workflow._read_outputs[run_id]
    retained.unlink()
    status, headers, body = raw_get(port, f"{BASE}/runs/{run_id}/output")
    assert status == 410 and json.loads(body)["error"]["code"] == "read_output_unavailable"
    assert values(headers, "Content-Length") == [str(len(body))]

    # Unknown run: 404, still JSON. Nothing above re-read the DUT.
    status, _headers, body = raw_get(port, f"{BASE}/runs/{'f' * 32}/output")
    assert status == 404 and json.loads(body)["error"]["code"] == "programming_run_not_found"
    assert len(gateway.posts) == 1 and gateway.downloads == 1
