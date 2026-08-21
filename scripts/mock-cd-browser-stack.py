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
        ci_mock_profile = work / "mock-runtime-ci.json"
        write_ci_mock_profile(ci_mock_profile)

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
            gateway_command = [
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
            ]
            # Only the browser-facing PPU-A Gateway owns the Engineering mock
            # provider in this acceptance stack. Its provider creates twelve
            # virtual PlasmaServer runtimes behind the same Gateway contract.
            if item is cd.PPUS[0]:
                gateway_command.extend(
                    [
                        "--engineering-mock",
                        "--engineering-mock-root",
                        str(work / "engineering-mock"),
                        "--engineering-mock-profile",
                        str(ci_mock_profile),
                    ]
                )
            gateway = cd.start_process(
                f"{item['name']}-gateway",
                gateway_command,
                cwd=cd.PYTHON_DIR,
            )
            processes.append((f"{item['name']}-gateway", gateway))

        for item in cd.PPUS:
            cd.wait_json(
                f"http://127.0.0.1:{item['gateway_port']}/api/health/ready",
                lambda value: value.get("ok") is True and value.get("execution") == "ready",
                label=f"{item['name']} gateway ready",
            )

        engineering_catalog = cd.wait_json(
            f"http://127.0.0.1:{cd.PPUS[0]['gateway_port']}/api/engineering/targets",
            lambda value: (
                value.get("ok") is True
                and value.get("facility_count") == 3
                and value.get("ppu_count") == 12
                and value.get("site_count") == 60
            ),
            timeout_s=20.0,
            label="Engineering server-side mock PPU catalog",
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
            "schema_version": 2,
            "state": "ready",
            "web_url": f"http://127.0.0.1:{cd.WEB_PORT}",
            "gateway_url": f"http://127.0.0.1:{cd.PPUS[0]['gateway_port']}",
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