#!/usr/bin/env python3
"""Exercise the Render public demo through the product Control Station path."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def get(origin: str, path: str) -> tuple[int, str, bytes]:
    with urlopen(origin + path, timeout=10) as response:
        return response.status, response.headers.get_content_type(), response.read()


def post(origin: str, path: str, payload: dict[str, object]) -> dict[str, object]:
    request = Request(
        origin + path,
        json.dumps(payload).encode(),
        {"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=10) as response:
        assert response.status == 202
        return json.loads(response.read())


def child_memory_kib(supervisor_pid: int) -> int | None:
    children_path = Path(f"/proc/{supervisor_pid}/task/{supervisor_pid}/children")
    try:
        children = children_path.read_text().split()
        total = 0
        for pid in children:
            status = Path(f"/proc/{pid}/status").read_text()
            line = next(item for item in status.splitlines() if item.startswith("VmRSS:"))
            total += int(line.split()[1])
        return total if children else None
    except (OSError, StopIteration, ValueError):
        return None


def main() -> None:
    console_root = REPOSITORY_ROOT / "software/web/dist/standalone"
    if not (console_root / "server.js").is_file():
        raise SystemExit("Control Station runtime is missing; run npm run build:product in software/web")

    public_port = reserve_port()
    gateway_port = reserve_port()
    manager_port = reserve_port()
    origin = f"http://127.0.0.1:{public_port}"
    managed = "/api/manager/ppu"
    environment = {
        **os.environ,
        "PORT": str(public_port),
        "PLASMA_RENDER_GATEWAY_PORT": str(gateway_port),
        "PLASMA_RENDER_MANAGER_PORT": str(manager_port),
        "PLASMA_RENDER_PPU_ALIAS": "render-demo-ppu",
        "PYTHONUNBUFFERED": "1",
        "PLASMA_RENDER_ENGINEERING_MOCK": "1",
        "PLASMA_RENDER_FLASH_BYTES": str(1024 * 1024),
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
    }

    with tempfile.TemporaryFile(mode="w+t") as logs:
        process = subprocess.Popen(
            ["bash", "scripts/render-start.sh"],
            cwd=REPOSITORY_ROOT,
            env=environment,
            stdout=logs,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Render startup process exited before readiness")
                try:
                    _, _, payload = get(origin, f"{managed}/api/health/ready")
                    if json.loads(payload).get("execution") == "ready":
                        break
                except (HTTPError, URLError, TimeoutError):
                    time.sleep(0.1)
            else:
                raise RuntimeError("Managed Mock PPU path did not become ready")

            for route in ("/", "/demo", "/fleet", "/engineering", "/ppu"):
                status, content_type, payload = get(origin, route)
                assert status == 200 and content_type == "text/html"
                assert b"Plasma Control Station" in payload
                assert b"SITE MATRIX" not in payload
                assert b"PPU CONTROL" not in payload
                print(f"[render-runtime] {route}: HTTP {status} {content_type}")

            _, _, payload = get(origin, "/deployment.json")
            deployment = json.loads(payload)
            assert deployment["service"] == "plasma-public-demo"
            assert deployment["platform"] == "local"
            print("[render-runtime] deployment identity: product BFF / local")

            _, _, payload = get(origin, "/api/manager/registry")
            registry = json.loads(payload)
            aliases = {item.get("alias") for item in registry.get("ppus", []) if isinstance(item, dict)}
            assert aliases == {"render-demo-ppu"}, registry
            print("[render-runtime] Manager registry: render-demo-ppu")

            _, _, payload = get(origin, f"{managed}/api/status")
            status = json.loads(payload)
            assert status["ppu"]["ppu_id"] == "render-demo-ppu"
            assert len(status["sites"]) == 8
            print("[render-runtime] managed PPU: public-demo / render-demo-ppu / 8 Sites")

            _, _, payload = get(origin, f"{managed}/api/engineering/targets")
            catalog = json.loads(payload)
            assert catalog["provider"] == "mock"
            assert catalog["timing_profile"]["flash_size_bytes"] == 1024 * 1024
            print(
                "[render-runtime] Engineering mock: "
                f"{catalog['facility_count']} Facilities / {catalog['ppu_count']} PPUs / "
                f"{catalog['site_count']} Sites / 1 MiB each"
            )

            image = b"Plasma Render managed integration test" * 16
            response = post(
                origin,
                f"{managed}/api/jobs",
                {
                    "site_id": 1,
                    "operation": "program",
                    "asset_name": "render-demo.bin",
                    "asset_type": "image",
                    "asset_format": "binary",
                    "asset_size": len(image),
                    "asset_sha256": hashlib.sha256(image).hexdigest(),
                    "asset_base64": base64.b64encode(image).decode(),
                },
            )
            job_id = response["job"]["job_id"]
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                _, _, payload = get(origin, f"{managed}/api/status?job={job_id}")
                job = json.loads(payload)["job"]
                if job["state"] in {"success", "failed", "cancelled", "timeout", "aborted"}:
                    break
                time.sleep(0.05)
            else:
                raise RuntimeError("Managed Mock programming Job did not complete")
            assert job["state"] == "success", job
            print(f"[render-runtime] managed Mock program: SITE 1 / {len(image)} bytes / success")

            memory_kib = child_memory_kib(process.pid)
            if memory_kib is not None:
                print(f"[render-runtime] direct child RSS: {memory_kib / 1024:.1f} MiB")
                assert memory_kib < 512 * 1024
        except BaseException:
            logs.seek(0)
            print(logs.read(), file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
