#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "software" / "python"
WEB_DIR = ROOT / "software" / "web"
ARTIFACT_DIR = Path(os.environ.get("MOCK_CD_ARTIFACT_DIR", ROOT / "artifacts" / "mock-cd"))
LOG_DIR = ARTIFACT_DIR / "logs"

SCRIPTS_DIR = ROOT / "scripts"

# One loopback address per Mock PPU: the Manager reaches a PPU Bootstrap at
# the fixed ``<gateway host>:18081`` (plasma_manager.bootstrap), exactly as on
# a Z2, so two PPUs cannot share one host.
PPUS = (
    {"name": "ppu-a", "ppu_id": "mock-ppu-a", "sites": 8, "host": "127.0.0.1",
     "server_port": 19901, "gateway_port": 19801},
    {"name": "ppu-b", "ppu_id": "mock-ppu-b", "sites": 4, "host": "127.0.0.2",
     "server_port": 19902, "gateway_port": 19802},
)
MANAGER_PORT = 19880
WEB_PORT = 15173
BOOTSTRAP_PORT = 18081

sys.path.insert(0, str(PYTHON_DIR))
from plasma_server import mock_ppu  # noqa: E402  the product Mock PPU launcher

# The built-in Mock Programming Route (data/opf/programming-routes).
MOCK_ROUTE_ICPN = mock_ppu.ROUTE_ICPN
MOCK_FLASH_BASE = mock_ppu.FLASH_BASE
MOCK_FLASH_SIZE = mock_ppu.FLASH_SIZE
MOCK_ERASE_GRANULARITY = mock_ppu.ERASE_GRANULARITY
PRODUCTION_ROUTES = ROOT / "data" / "opf" / "programming-routes"


class MockCDError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[mock-cd] {message}", flush=True)


def http_json(url: str, *, host: str | None = None, timeout: float = 3.0) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if host:
        headers["Host"] = host
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise MockCDError(f"{url} did not return a JSON object")
    return payload


def wait_json(
    url: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    host: str | None = None,
    timeout_s: float = 30.0,
    label: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last_payload = http_json(url, host=host)
            if predicate(last_payload):
                log(f"PASS {label}")
                return last_payload
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, MockCDError) as exc:
            last_error = exc
        time.sleep(0.2)
    detail = f"last_error={last_error}" if last_error else f"last_payload={last_payload!r}"
    raise MockCDError(f"timeout waiting for {label}: {detail}")


def gateway_url(item: dict[str, Any]) -> str:
    return f"http://{item['host']}:{item['gateway_port']}"


def write_manager_config(path: Path, work: Path) -> None:
    (work / "manager-state").mkdir(parents=True, exist_ok=True)
    payload = {
        "manager": {
            "host": "127.0.0.1",
            "port": MANAGER_PORT,
            "request_timeout_s": 1.0,
            "poll_interval_s": 0.2,
            "observation_db_path": str((work / "manager-observations.sqlite3").resolve()),
            # Persisted registry: configured PPUs are commissioned, and the
            # Bootstrap credentials / Batch journals live next to it.
            "registry_state_path": str((work / "manager-state" / "registry.json").resolve()),
        },
        # No seeded PPUs: each Mock PPU launcher registers, commissions and
        # enrolls itself through the Manager's own routes (product path).
        "ppus": [],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def start_process(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = (LOG_DIR / f"{name}.log").open("w", encoding="utf-8")
    merged_env = os.environ.copy()
    merged_env["PYTHONUNBUFFERED"] = "1"
    if env:
        merged_env.update(env)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=merged_env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    process._mock_cd_log_handle = handle  # type: ignore[attr-defined]
    log(f"started {name}: pid={process.pid}")
    return process


def stop_processes(processes: list[tuple[str, subprocess.Popen[str]]]) -> None:
    for _, process in reversed(processes):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 5.0
    for _, process in reversed(processes):
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        handle = getattr(process, "_mock_cd_log_handle", None)
        if handle is not None and not handle.closed:
            handle.close()


def assert_processes_alive(processes: list[tuple[str, subprocess.Popen[str]]]) -> None:
    failed = [(name, process.returncode) for name, process in processes if process.poll() is not None]
    if failed:
        raise MockCDError(f"process exited before acceptance completed: {failed}")


def manager_is_current(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary")
    ppus = payload.get("ppus")
    if not isinstance(summary, dict) or not isinstance(ppus, list):
        return False
    states = [
        item.get("observation", {}).get("state")
        for item in ppus
        if isinstance(item, dict) and isinstance(item.get("observation"), dict)
    ]
    return (
        summary.get("configured_ppus") == 2
        and summary.get("reachable_ppus") == 2
        and summary.get("ready_ppus") == 2
        and summary.get("known_ppus") == 2
        and summary.get("stale_ppus") == 0
        and summary.get("unknown_ppus") == 0
        and summary.get("reported_sites") == 12
        and summary.get("enabled_sites") == 12
        and states == ["current", "current"]
    )


def validate_manager_fleet(payload: dict[str, Any]) -> None:
    if payload.get("ok") is not True or not manager_is_current(payload):
        raise MockCDError("Manager fleet does not satisfy current two-PPU/12-Site contract")
    store = payload.get("observation_store")
    if not isinstance(store, dict) or store.get("mode") != "sqlite" or store.get("healthy") is not True:
        raise MockCDError("Manager SQLite observation store is not healthy")


def walk_forbidden(value: Any, forbidden: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in forbidden:
                raise MockCDError(f"browser Fleet payload exposes forbidden key: {key}")
            walk_forbidden(child, forbidden)
    elif isinstance(value, list):
        for child in value:
            walk_forbidden(child, forbidden)


def validate_web_fleet(payload: dict[str, Any]) -> None:
    if payload.get("ok") is not True or payload.get("contract_version") != "1":
        raise MockCDError("Web Fleet BFF did not return contract v1 success")
    summary = payload.get("summary")
    ppus = payload.get("ppus")
    if not isinstance(summary, dict) or not isinstance(ppus, list):
        raise MockCDError("Web Fleet BFF payload shape is incomplete")
    expected = {
        "configured_ppus": 2,
        "reachable_ppus": 2,
        "ready_ppus": 2,
        "current_ppus": 2,
        "stale_ppus": 0,
        "unknown_ppus": 0,
        "reported_sites": 12,
        "enabled_sites": 12,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            raise MockCDError(f"Web Fleet {key}={summary.get(key)!r}; expected {value}")
    walk_forbidden(payload, {"endpoint", "errors", "last_refresh_error", "observation_db_path"})
    for ppu in ppus:
        if not isinstance(ppu, dict):
            raise MockCDError("invalid PPU entry in Web Fleet payload")
        observation = ppu.get("observation")
        capacity = ppu.get("current_capacity")
        if not isinstance(observation, dict) or not isinstance(capacity, dict):
            raise MockCDError("Web Fleet PPU observation/capacity missing")
        if observation.get("state") != "current":
            raise MockCDError("baseline Mock CD expects current PPU observations")
        if capacity.get("site_count") not in {8, 4}:
            raise MockCDError("unexpected current Site capacity")


def assert_local_routes() -> None:
    for path, marker in (
        ("/", "Choose a Demo"),
        ("/demo", "Choose a Demo"),
        ("/engineering", "EMode"),
        ("/fleet", "PMODE · FACTORY CONSOLE"),
    ):
        request = Request(f"http://127.0.0.1:{WEB_PORT}{path}")
        with urlopen(request, timeout=3) as response_obj:
            if int(response_obj.status) != 200:
                raise MockCDError(f"{path} returned HTTP {response_obj.status}")
            html = response_obj.read().decode("utf-8", errors="replace")
        if marker not in html:
            raise MockCDError(f"{path} missing expected marker: {marker}")
        if "SITE MATRIX" in html or "PPU CONTROL" in html:
            raise MockCDError(f"{path} still exposes the retired Single PPU Programming UI")
        log(f"PASS same-origin route {path}")

    request = Request(f"http://127.0.0.1:{WEB_PORT}/ppu")
    with urlopen(request, timeout=3) as response_obj:
        if int(response_obj.status) != 200:
            raise MockCDError(f"/ppu compatibility route returned HTTP {response_obj.status}")
        final_url = response_obj.geturl()
        html = response_obj.read().decode("utf-8", errors="replace")
    if not final_url.endswith("/engineering"):
        raise MockCDError(f"/ppu did not redirect to /engineering: final_url={final_url}")
    if "SITE MATRIX" in html or "PPU CONTROL" in html:
        raise MockCDError("/ppu compatibility route still exposes the retired Single PPU Programming UI")
    log("PASS same-origin route /ppu -> /engineering")


def dump_failure_logs() -> None:
    for log_path in sorted(LOG_DIR.glob("*.log")):
        print(f"\n===== {log_path.name} =====", file=sys.stderr)
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            print("\n".join(lines[-120:]), file=sys.stderr)
        except OSError as exc:
            print(f"cannot read log: {exc}", file=sys.stderr)


# --------------------------------------------------------------------------
# Managed Mock PPUs (U10): the production Manager Programming Engine runs on
# the Mock PPUs. Each Mock PPU is the existing Mock Runtime + the REAL PPU
# Bootstrap service (B1/B2/B3, enrollment, G13 admission) + the REAL Phase 3
# Gateway. Nothing here is a Mock engine: this is fixture provisioning only.


def ppu_spec(work: Path, item: dict[str, Any], gateway_args: list[str] | None = None) -> Any:
    return mock_ppu.MockPPUSpec(
        root=work / str(item["name"]), control_plane=SCRIPTS_DIR, alias=str(item["name"]),
        ppu_id=str(item["ppu_id"]), sites=int(item["sites"]), host=str(item["host"]),
        gateway_port=int(item["gateway_port"]), server_port=int(item["server_port"]),
        gateway_args=tuple(gateway_args or ()))


def serve_command(spec: Any) -> list[str]:
    """The product launcher, exactly as plasma-mock-ppu.service runs it."""
    command = [
        sys.executable, "-m", "plasma_server.mock_ppu", "serve",
        "--root", str(spec.root), "--control-plane", str(spec.control_plane),
        "--alias", spec.alias, "--ppu-id", spec.device_id, "--sites", str(spec.sites),
        "--host", spec.host, "--gateway-port", str(spec.gateway_port),
        "--server-port", str(spec.server_port),
        "--manager-url", f"http://127.0.0.1:{MANAGER_PORT}",
        "--log-dir", str(LOG_DIR),
    ]
    for arg in spec.gateway_args:
        command.append(f"--gateway-arg={arg}")
    return command


def http_post_json(url: str, body: dict[str, Any], *, timeout: float = 30.0) -> tuple[int, dict[str, Any]]:
    raw = json.dumps(body).encode("utf-8")
    request = Request(url, data=raw, method="POST",
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), json.load(response)
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read() or b"{}")
        except ValueError:
            payload = {}
        return int(exc.code), payload if isinstance(payload, dict) else {}


def http_bytes(url: str, *, timeout: float = 30.0) -> tuple[bytes, dict[str, str]]:
    with urlopen(Request(url), timeout=timeout) as response:
        return response.read(), dict(response.headers)


def start_managed_ppus(work: Path, processes: list[tuple[str, subprocess.Popen[str]]], *,
                       gateway_extra: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """One product Mock PPU launcher per Mock PPU (Runtime -> Bootstrap ->
    Gateway, then Manager registration + ticket enrollment)."""
    specs = {str(item["name"]): ppu_spec(work, item, (gateway_extra or {}).get(str(item["name"])))
             for item in PPUS}
    for name, spec in specs.items():
        processes.append((f"{name}-ppu", start_process(f"{name}-ppu", serve_command(spec),
                                                       cwd=PYTHON_DIR)))
        # One at a time, so the Registry (and every Console list) keeps the
        # PPUS order instead of whichever launcher registered first.
        wait_json(f"http://127.0.0.1:{MANAGER_PORT}/api/registry",
                  lambda value, alias=name: any(p.get("alias") == alias for p in value.get("ppus") or []),
                  label=f"{name} registered", timeout_s=60.0)
    for item in PPUS:
        wait_json(
            f"{gateway_url(item)}/api/health/ready",
            lambda value: value.get("ok") is True and value.get("execution") == "ready",
            label=f"{item['name']} gateway ready", timeout_s=60.0,
        )
    return specs


def manager_command(manager_config: Path) -> list[str]:
    # bootstrap_server composes the current Manager handler (Fleet, relay,
    # registry) with the Bootstrap and Programming Batch routes.
    return [sys.executable, "-m", "plasma_manager.bootstrap_server", "--config", str(manager_config)]


def manager_env() -> dict[str, str]:
    # The committed production Routes root: the Physical Route and the
    # built-in Mock Route side by side, resolved per Batch PPU class.
    return {"PLASMA_PROGRAMMING_ROUTES_ROOT": str(PRODUCTION_ROUTES)}


def wait_enrolled(specs: dict[str, Any], processes: list[tuple[str, subprocess.Popen[str]]],
                  timeout_s: float = 60.0) -> dict[str, Any]:
    """Each launcher registered and enrolled its Mock PPU (credential proven)."""
    manager = f"http://127.0.0.1:{MANAGER_PORT}"
    statuses: dict[str, Any] = {}
    for name, spec in specs.items():
        deadline = time.monotonic() + timeout_s
        while True:
            assert_processes_alive(processes)
            pairing = mock_ppu.enrollment_state(spec, manager)
            if pairing.get("paired") and pairing.get("device_authenticated"):
                break
            if time.monotonic() > deadline:
                raise MockCDError(f"{name} was not enrolled by its launcher: {pairing}")
            time.sleep(0.25)
        if pairing.get("ppu_class") != "mock":
            raise MockCDError(f"{name} enrollment-proven class is {pairing.get('ppu_class')}")
        if spec.paths()["ticket"].exists():
            raise MockCDError(f"{name} enrollment ticket was not consumed")
        statuses[name] = http_json(f"{manager}/api/registry/{name}/bootstrap", timeout=10.0)
        log(f"PASS {name} registered + enrolled by the product launcher (class mock)")
    return statuses


def assert_mock_route_listed() -> dict[str, Any]:
    payload = http_json(
        f"http://127.0.0.1:{MANAGER_PORT}/api/registry/{PPUS[0]['name']}/bootstrap/programming/routes")
    routes = payload.get("routes")
    if not isinstance(routes, list) or len(routes) != 1:
        raise MockCDError(f"Manager Programming Routes are not the one Mock Route: {payload}")
    route = routes[0]
    if route.get("icpn") != MOCK_ROUTE_ICPN or route.get("site_interface") != "mock":
        raise MockCDError(f"unexpected Mock Route summary: {route}")
    log("PASS Manager lists the Mock Programming Route")
    return route


# -- the managed programming scenario (no browser) --------------------------

BATCH_TIMEOUT_S = 180.0


def mock_image(size: int, seed: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < size:
        out.extend(hashlib.sha256(f"{seed}:{counter}".encode()).digest())
        counter += 1
    return bytes(out[:size])


def run_manager_batch(body: dict[str, Any], *, label: str) -> dict[str, Any]:
    manager = f"http://127.0.0.1:{MANAGER_PORT}"
    status, issued = http_post_json(f"{manager}/api/programming/starts", {"kind": "batch"})
    start = issued.get("start") if isinstance(issued.get("start"), dict) else {}
    if status != 200 or type(start.get("start_id")) is not str:
        raise MockCDError(f"{label}: start_id not issued: HTTP {status} {issued}")
    status, accepted = http_post_json(f"{manager}/api/programming/batches",
                                      {**body, "start_id": start["start_id"]}, timeout=120.0)
    batch = accepted.get("batch") if isinstance(accepted.get("batch"), dict) else {}
    if status != 202 or type(batch.get("batch_id")) is not str:
        raise MockCDError(f"{label}: Batch not accepted: HTTP {status} {accepted}")
    deadline = time.monotonic() + BATCH_TIMEOUT_S
    while time.monotonic() < deadline:
        current = http_json(f"{manager}/api/programming/batches/{batch['batch_id']}",
                            timeout=10.0).get("batch")
        if isinstance(current, dict) and current.get("state") == "finished":
            if current.get("outcome") != "PASS":
                raise MockCDError(f"{label}: Batch outcome {current.get('outcome')} "
                                  f"reason={current.get('reason')}: {json.dumps(current)[:4000]}")
            for unit in current.get("units") or []:
                if unit.get("outcome") != "PASS":
                    raise MockCDError(f"{label}: unit {unit.get('ppu_alias')}/"
                                      f"{unit.get('site_id')} {unit.get('outcome')}")
            log(f"PASS {label} (batch {current['batch_id']})")
            return current
        time.sleep(0.25)
    raise MockCDError(f"{label}: Batch did not finish within {BATCH_TIMEOUT_S}s")


def activation_kind(batch: dict[str, Any], alias: str) -> str:
    """B1/B2/B3 activation, or a reuse of the PPU's VERIFIED Active Set."""
    record = (batch.get("resource_activation") or {}).get(alias)
    if not isinstance(record, dict):
        return "REUSED"
    if record.get("result") != "PASS":
        raise MockCDError(f"{alias} Resource activation {record}")
    steps = {step.get("step") for step in record.get("steps") or []}
    return "ACTIVATED" if steps else "REUSED"


def reservation_state(item: dict[str, Any]) -> Any:
    status = http_json(f"{gateway_url(item)}/api/status", timeout=10.0)
    ppu = status.get("ppu") if isinstance(status.get("ppu"), dict) else {}
    reservation = ppu.get("resource_reservation")
    return reservation.get("state") if isinstance(reservation, dict) else reservation


def unit_run_id(batch: dict[str, Any], alias: str, site_id: int) -> str:
    for unit in batch.get("units") or []:
        if unit.get("ppu_alias") == alias and unit.get("site_id") == site_id:
            for attempt in reversed(unit.get("attempts") or []):
                if type(attempt.get("run_id")) is str:
                    return attempt["run_id"]
            if type(unit.get("run_id")) is str:
                return unit["run_id"]
    raise MockCDError(f"no run_id for {alias}/{site_id}: {json.dumps(batch)[:2000]}")


def assert_site_interface_boundary(route: dict[str, Any]) -> dict[str, str]:
    """D1: a Mock Route never qualifies on a physical Site and vice versa."""
    sys.path.insert(0, str(PYTHON_DIR))
    from plasma_manager.programming import BundleProgrammingWorkflow, _StepFailure
    from plasma_opf import bundle_v3

    item = PPUS[0]
    live = lambda _client, path: http_json(f"{gateway_url(item)}{path}", timeout=10.0)  # noqa: E731

    def readiness(site_interface: str, get: Callable[[Any, str], Any]) -> str:
        workflow = SimpleNamespace(_gateway_get=get, _batch_session=lambda alias, owner: None,
                                   monotonic=time.monotonic)
        try:
            BundleProgrammingWorkflow._readiness_checked(workflow, None, 1, site_interface,
                                                         None, None)
        except _StepFailure as exc:
            return str(exc.args[0])
        return "READY"

    def as_physical(client: Any, path: str) -> Any:
        payload = live(client, path)
        for site in payload.get("sites") or []:
            site["interface"] = "openocd"
        return payload

    physical = next(r for r in bundle_v3.load_routes(PRODUCTION_ROUTES)
                    if r.target.get("platform") != "mock")
    result = {
        "mock_route_on_live_mock_site": readiness(route["site_interface"], live),
        "mock_route_on_physical_site": readiness(route["site_interface"], as_physical),
        "physical_route_on_live_mock_site": readiness(physical.site_interface, live),
    }
    expected = {"mock_route_on_live_mock_site": "READY",
                "mock_route_on_physical_site": "SITE_INTERFACE_NOT_READY",
                "physical_route_on_live_mock_site": "SITE_INTERFACE_NOT_READY"}
    if result != expected:
        raise MockCDError(f"Site interface boundary {result} != {expected}")
    log("PASS Mock Route never qualifies on a physical Site (D1)")
    return result


def run_managed_programming(route: dict[str, Any]) -> dict[str, Any]:
    """Manager Batch E/P/V across both Mock PPUs, Read, and a 1 MiB Image."""
    manager = f"http://127.0.0.1:{MANAGER_PORT}"
    a, b = (str(item["name"]) for item in PPUS)
    # Non-contiguous Sites on both PPUs.
    targets = [{"ppu_alias": a, "site_ids": [2, 5]}, {"ppu_alias": b, "site_ids": [1, 3]}]
    evidence: dict[str, Any] = {}

    def epv(image: bytes, name: str, batch_targets: list[dict[str, Any]], label: str):
        return run_manager_batch({
            "icpn": MOCK_ROUTE_ICPN, "targets": batch_targets,
            "operations": ["erase", "program", "verify"],
            "image_base64": base64.b64encode(image).decode("ascii"), "image_filename": name,
        }, label=label)

    first_image = mock_image(4096, 1)
    first = epv(first_image, "mock-cd-first.bin", targets, "Batch E/P/V ppu-a[2,5]+ppu-b[1,3]")
    first_kinds = {alias: activation_kind(first, alias) for alias in (a, b)}
    if first_kinds != {a: "ACTIVATED", b: "ACTIVATED"}:
        raise MockCDError(f"first Batch did not run B1/B2/B3 activation: {first_kinds}")
    second_image = mock_image(4096, 2)
    second = epv(second_image, "mock-cd-second.bin", targets, "Batch E/P/V Resource reuse")
    second_kinds = {alias: activation_kind(second, alias) for alias in (a, b)}
    if second_kinds != {a: "REUSED", b: "REUSED"}:
        raise MockCDError(f"second Batch did not reuse the Active Set: {second_kinds}")
    evidence["epv"] = {"first": {"batch_id": first["batch_id"], "activation": first_kinds},
                       "second": {"batch_id": second["batch_id"], "activation": second_kinds}}

    read = run_manager_batch({
        "icpn": MOCK_ROUTE_ICPN, "targets": [{"ppu_alias": a, "site_ids": [5]}],
        "operation": "read", "address": MOCK_FLASH_BASE, "length": len(second_image),
    }, label="Batch Read ppu-a[5]")
    run_id = unit_run_id(read, a, 5)
    data, _headers = http_bytes(f"{manager}/api/registry/{a}/bootstrap/programming/runs/{run_id}/output")
    if data != second_image:
        raise MockCDError("Read output bytes differ from the programmed Image")
    log("PASS Read output bytes equal the programmed Image")
    state = reservation_state(PPUS[0])
    if state == "RECOVERY_REQUIRED":
        raise MockCDError("ppu-a Resource Reservation is RECOVERY_REQUIRED after the Read")
    log(f"PASS ppu-a Resource Reservation released after Read (state={state})")
    evidence["read"] = {"batch_id": read["batch_id"], "run_id": run_id, "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "reservation_state_after": state}

    large = mock_image(1024 * 1024, 3)
    big = epv(large, "mock-cd-1mib.bin",
              [{"ppu_alias": a, "site_ids": [8]}, {"ppu_alias": b, "site_ids": [2]}],
              "Batch E/P/V 1 MiB Image ppu-a[8]+ppu-b[2]")
    evidence["one_mib"] = {"batch_id": big["batch_id"], "bytes": len(large)}
    evidence["site_interface_boundary"] = assert_site_interface_boundary(route)
    for item in PPUS:
        if reservation_state(item) == "RECOVERY_REQUIRED":
            raise MockCDError(f"{item['name']} Resource Reservation is RECOVERY_REQUIRED")
    return evidence


def write_acceptance(result: str, scenarios: dict[str, str], *, error: str | None = None,
                     evidence: dict[str, Any] | None = None) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "commit": os.environ.get("MOCK_CD_COMMIT", os.environ.get("GITHUB_SHA", "local")),
        "result": result,
        "stack": {"ppus": 2, "sites": 12, "manager": "bootstrap_server", "web_bff": True,
                  "mock_route_icpn": MOCK_ROUTE_ICPN},
        "scenarios": scenarios,
    }
    if error:
        payload["error"] = error
    if evidence:
        payload["evidence"] = evidence
    (ARTIFACT_DIR / "acceptance.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def web_env() -> dict[str, str]:
    return {
        "PLASMA_FLEET_UI_ENABLED": "1",
        "PLASMA_MANAGER_API_URL": f"http://127.0.0.1:{MANAGER_PORT}",
        # The Console is Manager-managed only (U10).
        "PLASMA_CONTROL_STATION_MODE": "managed",
        "PLASMA_MANAGER_PPU_ALIAS": str(PPUS[0]["name"]),
    }


def start_manager(work: Path, processes: list[tuple[str, subprocess.Popen[str]]], *,
                  extra_env: dict[str, str] | None = None) -> None:
    manager_config = work / "manager.yaml"
    write_manager_config(manager_config, work)
    processes.append(("manager", start_process(
        "manager", manager_command(manager_config), cwd=PYTHON_DIR,
        env={**manager_env(), **(extra_env or {})})))
    wait_json(
        f"http://127.0.0.1:{MANAGER_PORT}/api/health/live",
        lambda value: value.get("ok") is True,
        label="Manager liveness",
    )


def wait_manager_fleet() -> dict[str, Any]:
    manager_fleet = wait_json(
        f"http://127.0.0.1:{MANAGER_PORT}/api/fleet",
        manager_is_current,
        timeout_s=30.0,
        label="Manager two-PPU fleet",
    )
    validate_manager_fleet(manager_fleet)
    return manager_fleet


def run() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[str, subprocess.Popen[str]]] = []
    scenarios = {
        "ppu_runtime_ready": "PENDING",
        "two_ppu_heterogeneous_topology": "PENDING",
        "managed_ppu_enrollment": "PENDING",
        "managed_batch_epv_activation_then_reuse": "PENDING",
        "managed_read_download": "PENDING",
        "managed_reservation_released_after_read": "PENDING",
        "managed_batch_one_mib_image": "PENDING",
        "mock_route_site_interface_boundary": "PENDING",
        "worker_binding": "PENDING",
        "browser_contract_sanitization": "PENDING",
        "local_product_routing": "PENDING",
    }
    evidence: dict[str, Any] = {}
    work = Path(tempfile.mkdtemp(prefix="plasma-mock-cd-"))
    try:
        start_manager(work, processes)
        specs = start_managed_ppus(work, processes)
        scenarios["ppu_runtime_ready"] = "PASS"
        wait_enrolled(specs, processes)
        wait_manager_fleet()
        scenarios["two_ppu_heterogeneous_topology"] = "PASS"
        route = assert_mock_route_listed()
        scenarios["managed_ppu_enrollment"] = "PASS"
        programming = run_managed_programming(route)
        evidence["managed_programming"] = programming
        scenarios["managed_batch_epv_activation_then_reuse"] = "PASS"
        scenarios["managed_read_download"] = "PASS"
        scenarios["managed_reservation_released_after_read"] = "PASS"
        scenarios["managed_batch_one_mib_image"] = "PASS"
        scenarios["mock_route_site_interface_boundary"] = "PASS"

        web = start_process(
            "web",
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(WEB_PORT)],
            cwd=WEB_DIR,
            env=web_env(),
        )
        processes.append(("web", web))
        web_fleet = wait_json(
            f"http://127.0.0.1:{WEB_PORT}/api/fleet",
            lambda value: value.get("ok") is True,
            timeout_s=45.0,
            label="Web Fleet BFF",
        )
        scenarios["worker_binding"] = "PASS"
        validate_web_fleet(web_fleet)
        scenarios["browser_contract_sanitization"] = "PASS"
        log("PASS Web Fleet browser contract sanitization")

        assert_local_routes()
        scenarios["local_product_routing"] = "PASS"
        assert_processes_alive(processes)

        write_acceptance("PASS", scenarios, evidence=evidence)
        log("RESULT: PASS")
    except Exception as exc:
        for key, value in tuple(scenarios.items()):
            if value == "PENDING":
                scenarios[key] = "NOT_REACHED"
        write_acceptance("FAIL", scenarios, error=str(exc), evidence=evidence)
        stop_processes(processes)
        processes.clear()
        dump_failure_logs()
        raise
    finally:
        stop_processes(processes)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(f"[mock-cd] RESULT: FAIL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)