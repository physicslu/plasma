#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import signal
import subprocess
import sys
import tempfile
import threading
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


def main() -> None:
    cd = load_baseline_harness()
    artifact_dir = cd.ARTIFACT_DIR
    artifact_dir.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[str, subprocess.Popen[str]]] = []
    stop_event = threading.Event()
    work = Path(tempfile.mkdtemp(prefix="plasma-mock-cd-browser-"))

    def request_stop(_signum: int, _frame: object) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    try:
        configs: list[Path] = []
        for item in cd.PPUS:
            config = work / f"{item['name']}.yaml"
            cd.write_ppu_config(
                config,
                ppu_id=str(item["ppu_id"]),
                site_count=int(item["sites"]),
                port=int(item["server_port"]),
                work=work,
            )
            configs.append(config)

        manager_config = work / "manager.yaml"
        cd.write_manager_config(manager_config, work)

        for item, config in zip(cd.PPUS, configs, strict=True):
            server = cd.start_process(
                f"{item['name']}-server",
                [sys.executable, "-m", "plasma_server.server", "--config", str(config)],
                cwd=cd.PYTHON_DIR,
            )
            processes.append((f"{item['name']}-server", server))
            # Read downloads are served by the REST Gateway from the same job
            # output directory written by the Plasma Server.
            output_root = work / f"{item['ppu_id']}-output"
            gateway = cd.start_process(
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
                    str(output_root),
                ],
                cwd=cd.PYTHON_DIR,
            )
            processes.append((f"{item['name']}-gateway", gateway))

        for item in cd.PPUS:
            cd.wait_json(
                f"http://127.0.0.1:{item['gateway_port']}/api/health/ready",
                lambda value: value.get("ok") is True and value.get("execution") == "ready",
                label=f"{item['name']} gateway ready",
            )

        manager = cd.start_process(
            "manager",
            [sys.executable, "-m", "plasma_manager.server", "--config", str(manager_config)],
            cwd=cd.PYTHON_DIR,
        )
        processes.append(("manager", manager))
        cd.wait_json(
            f"http://127.0.0.1:{cd.MANAGER_PORT}/api/health/live",
            lambda value: value.get("ok") is True,
            label="Manager liveness",
        )
        manager_fleet = cd.wait_json(
            f"http://127.0.0.1:{cd.MANAGER_PORT}/api/fleet",
            cd.manager_is_current,
            timeout_s=20.0,
            label="Manager two-PPU fleet",
        )
        cd.validate_manager_fleet(manager_fleet)

        web = cd.start_process(
            "web",
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(cd.WEB_PORT)],
            cwd=cd.WEB_DIR,
            env={
                "PLASMA_FLEET_UI_ENABLED": "1",
                "PLASMA_MANAGER_API_URL": f"http://127.0.0.1:{cd.MANAGER_PORT}",
                "NEXT_PUBLIC_PLASMA_API_URL": f"http://127.0.0.1:{cd.PPUS[0]['gateway_port']}",
            },
        )
        processes.append(("web", web))
        web_fleet = cd.wait_json(
            f"http://127.0.0.1:{cd.WEB_PORT}/api/fleet",
            lambda value: value.get("ok") is True,
            host="plasma.open4th.com",
            timeout_s=45.0,
            label="Web Fleet BFF",
        )
        cd.validate_web_fleet(web_fleet)
        cd.assert_public_routes()
        cd.assert_processes_alive(processes)

        runtime = {
            "schema_version": 1,
            "state": "ready",
            "web_url": f"http://127.0.0.1:{cd.WEB_PORT}",
            "gateway_url": f"http://127.0.0.1:{cd.PPUS[0]['gateway_port']}",
            "unreachable_gateway_url": "http://127.0.0.1:19899",
            "ppu_id": str(cd.PPUS[0]["ppu_id"]),
            "enabled_sites": int(cd.PPUS[0]["sites"]),
            "fleet": {"ppus": 2, "sites": 12},
        }
        (artifact_dir / "runtime.json").write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        cd.log("BROWSER STACK READY")

        while not stop_event.wait(0.5):
            cd.assert_processes_alive(processes)
    except Exception:
        cd.dump_failure_logs()
        raise
    finally:
        cd.stop_processes(processes)
        cd.log("BROWSER STACK STOPPED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[mock-cd-browser] RESULT: FAIL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
