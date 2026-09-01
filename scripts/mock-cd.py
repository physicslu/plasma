#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = ROOT / "software" / "python"
WEB_DIR = ROOT / "software" / "web"
ARTIFACT_DIR = Path(os.environ.get("MOCK_CD_ARTIFACT_DIR", ROOT / "artifacts" / "mock-cd"))
LOG_DIR = ARTIFACT_DIR / "logs"

PPUS = (
    {"name": "ppu-a", "ppu_id": "mock-ppu-a", "sites": 8, "server_port": 19901, "gateway_port": 19801},
    {"name": "ppu-b", "ppu_id": "mock-ppu-b", "sites": 4, "server_port": 19902, "gateway_port": 19802},
)
MANAGER_PORT = 19880
WEB_PORT = 15173


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


def write_ppu_config(path: Path, *, ppu_id: str, site_count: int, port: int, work: Path) -> None:
    sites = [
        {
            "id": site_id,
            "enabled": True,
            "interface": "mock",
            "target": "MOCK-IC",
            "operation_timeout_s": 5.0,
            "max_retries": 0,
            "retry_backoff_s": 0.01,
            "mock": {"flash_size": 65536, "default_delay_s": 0.01, "progress_steps": 2},
        }
        for site_id in range(1, site_count + 1)
    ]
    payload = {
        "ppu": {
            "id": ppu_id,
            "facility_id": "mock-facility",
            "model": "MOCK-PPU",
            "display_name": ppu_id,
        },
        "server": {
            "host": "127.0.0.1",
            "port": port,
            "max_supported_sites": site_count,
            "max_concurrent_jobs": site_count,
            "max_queue_depth_per_site": 4,
            "output_root": str(work / f"{ppu_id}-output"),
            "log_root": str(work / f"{ppu_id}-logs"),
            "max_metadata_bytes": 65536,
            "max_map_bytes": 1048576,
            "max_binary_bytes": 67108864,
        },
        "sites": sites,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def write_manager_config(path: Path, work: Path) -> None:
    payload = {
        "manager": {
            "host": "127.0.0.1",
            "port": MANAGER_PORT,
            "request_timeout_s": 1.0,
            "poll_interval_s": 0.2,
            "observation_db_path": str((work / "manager-observations.sqlite3").resolve()),
        },
        "ppus": [
            {"alias": item["name"], "endpoint": f"http://127.0.0.1:{item['gateway_port']}"}
            for item in PPUS
        ],
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
        ("/fleet", "Factory Production Console"),
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


def write_acceptance(result: str, scenarios: dict[str, str], *, error: str | None = None) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "commit": os.environ.get("MOCK_CD_COMMIT", os.environ.get("GITHUB_SHA", "local")),
        "result": result,
        "stack": {"ppus": 2, "sites": 12, "manager": "read-only", "web_bff": True},
        "scenarios": scenarios,
    }
    if error:
        payload["error"] = error
    (ARTIFACT_DIR / "acceptance.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def run() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[str, subprocess.Popen[str]]] = []
    scenarios = {
        "ppu_runtime_ready": "PENDING",
        "two_ppu_heterogeneous_topology": "PENDING",
        "worker_binding": "PENDING",
        "browser_contract_sanitization": "PENDING",
        "local_product_routing": "PENDING",
    }
    work = Path(tempfile.mkdtemp(prefix="plasma-mock-cd-"))
    try:
        configs: list[Path] = []
        for item in PPUS:
            config = work / f"{item['name']}.yaml"
            write_ppu_config(
                config,
                ppu_id=str(item["ppu_id"]),
                site_count=int(item["sites"]),
                port=int(item["server_port"]),
                work=work,
            )
            configs.append(config)
        manager_config = work / "manager.yaml"
        write_manager_config(manager_config, work)

        for item, config in zip(PPUS, configs, strict=True):
            server = start_process(
                f"{item['name']}-server",
                [sys.executable, "-m", "plasma_server.server", "--config", str(config)],
                cwd=PYTHON_DIR,
            )
            processes.append((f"{item['name']}-server", server))
            gateway = start_process(
                f"{item['name']}-gateway",
                [
                    sys.executable,
                    "-m",
                    "plasma_web.gateway",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(item["gateway_port"]),
                    "--plasma-host",
                    "127.0.0.1",
                    "--plasma-port",
                    str(item["server_port"]),
                    "--output-root",
                    str(work / f"{item['name']}-gateway-output"),
                ],
                cwd=PYTHON_DIR,
            )
            processes.append((f"{item['name']}-gateway", gateway))

        for item in PPUS:
            wait_json(
                f"http://127.0.0.1:{item['gateway_port']}/api/health/ready",
                lambda value: value.get("ok") is True and value.get("execution") == "ready",
                label=f"{item['name']} gateway ready",
            )
        scenarios["ppu_runtime_ready"] = "PASS"

        manager = start_process(
            "manager",
            [sys.executable, "-m", "plasma_manager.server", "--config", str(manager_config)],
            cwd=PYTHON_DIR,
        )
        processes.append(("manager", manager))
        wait_json(
            f"http://127.0.0.1:{MANAGER_PORT}/api/health/live",
            lambda value: value.get("ok") is True,
            label="Manager liveness",
        )
        manager_fleet = wait_json(
            f"http://127.0.0.1:{MANAGER_PORT}/api/fleet",
            manager_is_current,
            timeout_s=20.0,
            label="Manager two-PPU fleet",
        )
        validate_manager_fleet(manager_fleet)
        scenarios["two_ppu_heterogeneous_topology"] = "PASS"

        web = start_process(
            "web",
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(WEB_PORT)],
            cwd=WEB_DIR,
            env={
                "PLASMA_FLEET_UI_ENABLED": "1",
                "PLASMA_MANAGER_API_URL": f"http://127.0.0.1:{MANAGER_PORT}",
                "PLASMA_GATEWAY_PROXY_URL": f"http://127.0.0.1:{PPUS[0]['gateway_port']}",
            },
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

        write_acceptance("PASS", scenarios)
        log("RESULT: PASS")
    except Exception as exc:
        for key, value in tuple(scenarios.items()):
            if value == "PENDING":
                scenarios[key] = "NOT_REACHED"
        write_acceptance("FAIL", scenarios, error=str(exc))
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