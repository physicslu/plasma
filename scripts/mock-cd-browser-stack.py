#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import signal
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
BASELINE_HARNESS = ROOT / "scripts" / "mock-cd.py"


def load_baseline_harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location("plasma_mock_cd_baseline", BASELINE_HARNESS)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load canonical Mock CD harness: {BASELINE_HARNESS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_ci_mock_profile(path: Path) -> None:
    """Keep acceptance deterministic while production defaults remain realistic.

    Product defaults intentionally inject low-rate failures. A regression test
    must not depend on a probability draw, so the browser stack explicitly uses
    a fixed, zero-error profile with short deterministic timings.
    """
    operation = {
        "error_rate_per_mille": 0,
        "base_time_ms": 0,
        "throughput_bytes_per_second": 64 * 1024 * 1024,
        "jitter_ms": 0,
    }
    payload = {
        "profile_id": "ci-browser",
        "revision": 1,
        "enabled": True,
        "default_image_size_bytes": 1024 * 1024,
        "operations": {
            "erase": dict(operation),
            "program": dict(operation),
            "verify": dict(operation),
            "read": dict(operation),
        },
        "seed": {"mode": "fixed", "fixed_seed": 1},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


HARNESS_CONTROL_PORT = 19890


class PPUHarnessControl:
    """Test-harness-only offline/online switch for one Mock PPU's Gateway.

    Not a product API: it binds 127.0.0.1 only and exists only while this
    browser stack runs. Offline stops the PPU's Gateway process (its Runtime
    and Bootstrap keep running), so the Manager observes an unreachable PPU;
    online restarts the same Gateway command and waits until it is ready.
    """

    def __init__(self, cd: ModuleType, processes: list[tuple[str, subprocess.Popen[str]]],
                 commands: dict[str, list[str]]) -> None:
        self.cd = cd
        self.processes = processes
        self.commands = commands
        self.offline: set[str] = set()
        self.lock = threading.RLock()

    def _item(self, alias: str) -> dict:
        for item in self.cd.PPUS:
            if item["name"] == alias:
                return item
        raise KeyError(alias)

    def _index(self, name: str) -> int:
        return next(i for i, (entry, _process) in enumerate(self.processes) if entry == name)

    def status(self) -> dict:
        with self.lock:
            out = {}
            for item in self.cd.PPUS:
                alias = item["name"]
                process = self.processes[self._index(f"{alias}-gateway")][1]
                out[alias] = {"state": "offline" if alias in self.offline else "online",
                              "gateway_url": self.cd.gateway_url(item),
                              "gateway_pid": None if alias in self.offline else process.pid}
            return {"ok": True, "ppus": out}

    def set_offline(self, alias: str) -> dict:
        self._item(alias)
        with self.lock:
            if alias not in self.offline:
                index = self._index(f"{alias}-gateway")
                self.cd.stop_processes([self.processes[index]])
                self.offline.add(alias)
        return self.status()

    def set_online(self, alias: str) -> dict:
        item = self._item(alias)
        with self.lock:
            if alias in self.offline:
                name = f"{alias}-gateway"
                process = self.cd.start_process(name, self.commands[alias], cwd=self.cd.PYTHON_DIR)
                self.processes[self._index(name)] = (name, process)
                self.cd.wait_json(
                    f"{self.cd.gateway_url(item)}/api/health/ready",
                    lambda value: value.get("ok") is True and value.get("execution") == "ready",
                    label=f"{alias} gateway back online")
                self.offline.discard(alias)
        return self.status()

    def assert_alive(self) -> None:
        with self.lock:
            stopped = {f"{alias}-gateway" for alias in self.offline}
            self.cd.assert_processes_alive(
                [(name, process) for name, process in self.processes if name not in stopped])

    def serve(self) -> ThreadingHTTPServer:
        control = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args: object) -> None:
                pass

            def _send(self, status: int, payload: dict) -> None:
                raw = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:  # noqa: N802
                if self.path.rstrip("/") == "/ppus":
                    self._send(200, control.status())
                else:
                    self._send(404, {"ok": False})

            def do_POST(self) -> None:  # noqa: N802
                parts = self.path.strip("/").split("/")
                if len(parts) != 3 or parts[0] != "ppus" or parts[2] not in {"offline", "online"}:
                    self._send(404, {"ok": False})
                    return
                try:
                    action = control.set_offline if parts[2] == "offline" else control.set_online
                    self._send(200, action(parts[1]))
                except KeyError:
                    self._send(404, {"ok": False, "error": "unknown PPU alias"})
                except Exception as exc:  # surfaced to the spec, never swallowed
                    self._send(500, {"ok": False, "error": str(exc)[:500]})

        server = ThreadingHTTPServer(("127.0.0.1", HARNESS_CONTROL_PORT), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server


def main() -> None:
    cd = load_baseline_harness()
    artifact_dir = cd.ARTIFACT_DIR
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[str, subprocess.Popen[str]]] = []
    stop_event = threading.Event()
    work = Path(tempfile.mkdtemp(prefix="plasma-mock-cd-browser-"))
    control_server: ThreadingHTTPServer | None = None

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    try:
        ci_mock_profile = work / "mock-runtime-ci.json"
        write_ci_mock_profile(ci_mock_profile)
        ppu_a = str(cd.PPUS[0]["name"])
        # Only the browser-facing PPU-A Gateway owns the Engineering mock
        # provider in this acceptance stack. Its provider creates virtual
        # PlasmaServer runtimes behind the same Gateway contract.
        gateway_extra = {ppu_a: [
            "--engineering-mock",
            "--engineering-mock-root", str(work / "engineering-mock"),
            "--engineering-mock-profile", str(ci_mock_profile),
        ]}
        fixtures = cd.start_managed_ppus(work, processes, gateway_extra=gateway_extra)
        gateway_commands = {
            str(item["name"]): cd.gateway_command(item, fixtures[str(item["name"])],
                                                  gateway_extra.get(str(item["name"])))
            for item in cd.PPUS
        }

        engineering_catalog = cd.wait_json(
            f"{cd.gateway_url(cd.PPUS[0])}/api/engineering/targets",
            lambda value: (
                value.get("ok") is True
                and value.get("facility_count") == 8
                and value.get("ppu_count") == 32
                and value.get("site_count") == 160
            ),
            timeout_s=20.0,
            label="Engineering server-side mock PPU catalog",
        )

        # Provision an isolated, qualified SQLite revision for the Mock CD
        # Manager, not via a live Selector fallback. PPU gateways remain
        # Catalog-free and use only their own execution authority.
        sys.path.insert(0, str(cd.PYTHON_DIR))
        from plasma_web.catalog_sqlite_repository import CatalogSqliteShadowRepository
        from plasma_web.device_catalog import default_catalog_manifest_path
        from plasma_web.programming_qualification import get_default_programming_qualification_registry

        catalog_database = work / "catalog.sqlite3"
        CatalogSqliteShadowRepository(catalog_database).import_verified_manifest(
            default_catalog_manifest_path(),
            qualification_registry=get_default_programming_qualification_registry(),
        )
        cd.start_manager(work, processes,
                         extra_env={"PLASMA_CATALOG_SQLITE_DB": str(catalog_database)})
        cd.enroll_mock_ppus(fixtures)
        route = cd.assert_mock_route_listed()

        web = cd.start_process(
            "web",
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(cd.WEB_PORT)],
            cwd=cd.WEB_DIR,
            env=cd.web_env(),
        )
        processes.append(("web", web))
        web_fleet = cd.wait_json(
            f"http://127.0.0.1:{cd.WEB_PORT}/api/fleet",
            lambda value: value.get("ok") is True,
            timeout_s=45.0,
            label="Web Fleet BFF",
        )
        cd.validate_web_fleet(web_fleet)
        cd.assert_local_routes()
        cd.assert_processes_alive(processes)

        control = PPUHarnessControl(cd, processes, gateway_commands)
        control_server = control.serve()
        pids = {name: process.pid for name, process in processes}

        runtime = {
            "schema_version": 3,
            "state": "ready",
            "web_url": f"http://127.0.0.1:{cd.WEB_PORT}",
            "gateway_url": cd.gateway_url(cd.PPUS[0]),
            "unreachable_gateway_url": "http://127.0.0.1:19899",
            "ppu_id": str(cd.PPUS[0]["ppu_id"]),
            "enabled_sites": int(cd.PPUS[0]["sites"]),
            "fleet": {"ppus": 2, "sites": 12},
            "engineering": {
                "provider": engineering_catalog.get("provider"),
                "facilities": engineering_catalog["facility_count"],
                "ppus": engineering_catalog["ppu_count"],
                "sites": engineering_catalog["site_count"],
                "test_facility_id": "mock-facility-02",
                "test_ppu_id": "mock-facility-02-ppu-03",
                "test_ppu_sites": 6,
            },
            # U10: Mock PPUs run the production Manager Programming Engine.
            "managed": {
                "manager_url": f"http://127.0.0.1:{cd.MANAGER_PORT}",
                "control_station_mode": "managed",
                "console_ppu_alias": ppu_a,
                "aliases": [str(item["name"]) for item in cd.PPUS],
                "ppus": [
                    {
                        "alias": str(item["name"]),
                        "ppu_id": str(item["ppu_id"]),
                        "sites": int(item["sites"]),
                        "site_ids": list(range(1, int(item["sites"]) + 1)),
                        "site_interface": "mock",
                        "gateway_url": cd.gateway_url(item),
                        "bootstrap_url": f"http://{item['host']}:{cd.BOOTSTRAP_PORT}",
                        "enrolled": True,
                        # Before its first Batch a PPU has no Active Set: the
                        # first Batch runs B1/B2/B3, later Batches reuse it.
                        "active_set": "NONE_UNTIL_FIRST_BATCH",
                        "pids": {kind: pids[f"{item['name']}-{kind}"]
                                 for kind in ("runtime", "bootstrap", "gateway")},
                    }
                    for item in cd.PPUS
                ],
                "route": {
                    "route_id": route.get("route_id"),
                    "icpn": cd.MOCK_ROUTE_ICPN,
                    "site_interface": "mock",
                    "operations": ["erase", "program", "verify", "read"],
                    "flash_base": cd.MOCK_FLASH_BASE,
                    "flash_size": cd.MOCK_FLASH_SIZE,
                    "erase_granularity": cd.MOCK_ERASE_GRANULARITY,
                    "max_image_bytes": cd.MOCK_FLASH_SIZE,
                },
                "harness_control_url": f"http://127.0.0.1:{HARNESS_CONTROL_PORT}",
                "harness_control": {
                    "status": "GET /ppus",
                    "offline": "POST /ppus/<alias>/offline",
                    "online": "POST /ppus/<alias>/online",
                    "scope": "test harness only; stops/restarts the PPU Gateway process",
                },
                "manager_pid": pids["manager"],
                "web_pid": pids["web"],
            },
        }
        (artifact_dir / "runtime.json").write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        cd.log("BROWSER STACK READY")

        while not stop_event.wait(0.5):
            control.assert_alive()
    except Exception:
        cd.dump_failure_logs()
        raise
    finally:
        if control_server is not None:
            control_server.shutdown()
            control_server.server_close()
        cd.stop_processes(processes)
        cd.log("BROWSER STACK STOPPED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[mock-cd-browser] RESULT: FAIL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
