#!/usr/bin/env python3
"""Full-stack browser acceptance harness for Console-managed PPU Bootstrap.

The harness intentionally starts with *no Plasma Runtime/Gateway* on the target
PPU.  It proves the first-install control path:

Browser -> Control Station BFF -> Manager -> PPU Bootstrap

A deterministic fake kit executor is injected only at the final deployment
engine seam so CI can observe a successful lifecycle without pretending that a
container exercised systemd, ARMv7, reboot, or real PYNQ-Z2 hardware.
"""

from __future__ import annotations

import json
import os
import shutil
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
BOOTSTRAP_SCRIPT = ROOT / "scripts" / "ppu-bootstrap.py"
BOOTSTRAP_SERVICE = ROOT / "scripts" / "ppu-bootstrap-service.py"
ARTIFACT_DIR = Path(
    os.environ.get(
        "PPU_BOOTSTRAP_BROWSER_ARTIFACT_DIR",
        ROOT / "artifacts" / "ppu-bootstrap-browser",
    )
).resolve()
LOG_DIR = ARTIFACT_DIR / "logs"
MANAGER_PORT = 19881
WEB_PORT = 15174
BOOTSTRAP_PORT = 18081
ALIAS = "ppu-bootstrap"
FUTURE_GATEWAY = "http://127.0.0.1:19811"


class StackError(RuntimeError):
    pass


def log(message: str) -> None:
    print(f"[ppu-bootstrap-browser] {message}", flush=True)


def http_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 3.0,
) -> dict[str, Any]:
    encoded = None
    headers = {"Accept": "application/json"}
    if body is not None:
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=encoded, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise StackError(f"{url} did not return a JSON object")
    return payload


def wait_json(
    url: str,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    timeout_s: float,
    label: str,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    last_payload: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        try:
            last_payload = http_json(url)
            if predicate(last_payload):
                log(f"PASS {label}")
                return last_payload
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, StackError) as exc:
            last_error = exc
        time.sleep(0.2)
    detail = f"last_error={last_error}" if last_error else f"last_payload={last_payload!r}"
    raise StackError(f"timeout waiting for {label}: {detail}")


def start_process(
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.Popen[str]:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = (LOG_DIR / f"{name}.log").open("w", encoding="utf-8")
    merged = os.environ.copy()
    merged["PYTHONUNBUFFERED"] = "1"
    if env:
        merged.update(env)
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=merged,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    process._plasma_log_handle = handle  # type: ignore[attr-defined]
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
        handle = getattr(process, "_plasma_log_handle", None)
        if handle is not None and not handle.closed:
            handle.close()


def assert_processes_alive(processes: list[tuple[str, subprocess.Popen[str]]]) -> None:
    failed = [(name, process.returncode) for name, process in processes if process.poll() is not None]
    if failed:
        raise StackError(f"stack process exited unexpectedly: {failed}")


def dump_logs() -> None:
    if not LOG_DIR.is_dir():
        return
    for path in sorted(LOG_DIR.glob("*.log")):
        try:
            content = path.read_text(encoding="utf-8")[-8000:]
        except OSError:
            continue
        print(f"\n===== {path.name} =====\n{content}", file=sys.stderr)


def write_fake_kit_tool(path: Path) -> None:
    path.write_text(
        '''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

GIT_SHA = "1" * 40
VERSION = "mock-bootstrap-1.0.0"

parser = argparse.ArgumentParser()
parser.add_argument("command", choices=["deploy"])
parser.add_argument("kit", type=Path)
parser.add_argument("--sidecar", type=Path, required=True)
parser.add_argument("--gateway-host", required=True)
parser.add_argument("--ppu-id", required=True)
parser.add_argument("--facility-id", required=True)
parser.add_argument("--display-name", required=True)
parser.add_argument("--product-root", type=Path, required=True)
args = parser.parse_args()

if not args.kit.is_file() or not args.sidecar.is_file():
    raise SystemExit("mock kit or sidecar missing")

release_id = f"{VERSION}-{GIT_SHA[:12]}"
release = args.product_root / "releases" / release_id
release.mkdir(parents=True, exist_ok=True)
(release / "release.json").write_text(
    json.dumps(
        {
            "role": "ppu",
            "target": "linux-armv7l",
            "product_version": VERSION,
            "git_sha": GIT_SHA,
        },
        indent=2,
        sort_keys=True,
    ) + "\\n",
    encoding="utf-8",
)
args.product_root.mkdir(parents=True, exist_ok=True)
temporary = args.product_root / "current.new"
try:
    temporary.unlink()
except FileNotFoundError:
    pass
temporary.symlink_to(release)
os.replace(temporary, args.product_root / "current")
print(json.dumps({"result": "PASS", "release_id": release_id, "simulated": True}, sort_keys=True))
''',
        encoding="utf-8",
    )


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="plasma-ppu-bootstrap-browser-"))
    processes: list[tuple[str, subprocess.Popen[str]]] = []
    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    try:
        product_root = work / "product"
        bootstrap_state = work / "bootstrap-state"
        machine_id = work / "machine-id"
        machine_id.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
        bootstrap_state.mkdir(parents=True, exist_ok=True)
        (bootstrap_state / "identity.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "ppu_id": "mock-bootstrap-ppu",
                    "facility_id": "mock-facility",
                    "hardware_revision": "mock-pynq-z2-rev1",
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        fake_kit = work / "mock-bootstrap-kit.py"
        write_fake_kit_tool(fake_kit)

        provision = subprocess.run(
            [
                sys.executable,
                str(BOOTSTRAP_SERVICE),
                "--product-root",
                str(product_root),
                "--state-root",
                str(bootstrap_state),
                "--machine-id",
                str(machine_id),
                "--bootstrap-script",
                str(BOOTSTRAP_SCRIPT),
                "--kit-tool",
                str(fake_kit),
                "provision-token",
            ],
            cwd=ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if provision.returncode != 0:
            raise StackError(f"cannot provision Bootstrap token: {provision.stdout}")
        token_file = bootstrap_state / "control-token"
        if not token_file.is_file() or token_file.stat().st_mode & 0o077:
            raise StackError("Bootstrap test token was not created with private permissions")

        bootstrap = start_process(
            "bootstrap",
            [
                sys.executable,
                str(BOOTSTRAP_SERVICE),
                "--product-root",
                str(product_root),
                "--state-root",
                str(bootstrap_state),
                "--machine-id",
                str(machine_id),
                "--bootstrap-script",
                str(BOOTSTRAP_SCRIPT),
                "--kit-tool",
                str(fake_kit),
                "serve",
                "--host",
                "127.0.0.1",
                "--port",
                str(BOOTSTRAP_PORT),
            ],
            cwd=ROOT,
        )
        processes.append(("bootstrap", bootstrap))
        wait_json(
            f"http://127.0.0.1:{BOOTSTRAP_PORT}/v1/status",
            lambda payload: payload.get("bootstrap", {}).get("state") == "bootstrap_ready",
            timeout_s=20.0,
            label="PPU Bootstrap ready without Plasma Runtime",
        )

        manager_config = work / "manager.yaml"
        manager_config.write_text(
            yaml.safe_dump(
                {
                    "manager": {
                        "host": "127.0.0.1",
                        "port": MANAGER_PORT,
                        "request_timeout_s": 1.0,
                        "poll_interval_s": 0.2,
                        "observation_db_path": str((work / "manager-observations.sqlite3").resolve()),
                        "registry_state_path": str((work / "manager-registry.json").resolve()),
                    },
                    "ppus": [],
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        manager = start_process(
            "manager",
            [sys.executable, "-m", "plasma_manager.server_bootstrap", "--config", str(manager_config)],
            cwd=PYTHON_DIR,
        )
        processes.append(("manager", manager))
        wait_json(
            f"http://127.0.0.1:{MANAGER_PORT}/api/health/live",
            lambda payload: payload.get("ok") is True,
            timeout_s=20.0,
            label="Bootstrap-aware Manager live",
        )
        added = http_json(
            f"http://127.0.0.1:{MANAGER_PORT}/api/registry",
            method="POST",
            body={"alias": ALIAS, "endpoint": FUTURE_GATEWAY},
        )
        if added.get("entry", {}).get("lifecycle") != "pending":
            raise StackError(f"first-install PPU must enter pending lifecycle: {added!r}")
        wait_json(
            f"http://127.0.0.1:{MANAGER_PORT}/api/registry/{ALIAS}/bootstrap",
            lambda payload: (
                payload.get("ok") is True
                and payload.get("pairing", {}).get("paired") is False
                and payload.get("bootstrap", {}).get("runtime", {}).get("state") == "runtime_absent"
            ),
            timeout_s=20.0,
            label="Manager reaches independent PPU Bootstrap",
        )

        web = start_process(
            "web",
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(WEB_PORT)],
            cwd=WEB_DIR,
            env={
                "PLASMA_FLEET_UI_ENABLED": "1",
                "PLASMA_CONTROL_STATION_MODE": "managed",
                "PLASMA_MANAGER_API_URL": f"http://127.0.0.1:{MANAGER_PORT}",
                "PLASMA_MANAGER_PPU_ALIAS": "",
            },
        )
        processes.append(("web", web))
        wait_json(
            f"http://127.0.0.1:{WEB_PORT}/api/manager/registry/{ALIAS}/bootstrap",
            lambda payload: payload.get("ok") is True and payload.get("ppu_alias") == ALIAS,
            timeout_s=45.0,
            label="Control Station BFF reaches Manager Bootstrap route",
        )
        assert_processes_alive(processes)

        runtime = {
            "schema_version": 1,
            "state": "ready",
            "web_url": f"http://127.0.0.1:{WEB_PORT}",
            "manager_url": f"http://127.0.0.1:{MANAGER_PORT}",
            "bootstrap_url": f"http://127.0.0.1:{BOOTSTRAP_PORT}",
            "alias": ALIAS,
            "future_gateway": FUTURE_GATEWAY,
            "token_file": str(token_file),
            "proof_boundary": "Browser -> BFF -> Manager -> independent Bootstrap; fake kit executor only after authenticated deployment admission",
            "not_proven": ["systemd", "ARMv7", "reboot", "real PYNQ-Z2", "FPGA", "Site", "real IC"],
        }
        (ARTIFACT_DIR / "runtime.json").write_text(
            json.dumps(runtime, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        log("STACK READY")

        while not stop_requested:
            assert_processes_alive(processes)
            time.sleep(0.5)
    except Exception:
        dump_logs()
        raise
    finally:
        stop_processes(processes)
        shutil.rmtree(work, ignore_errors=True)
        log("STACK STOPPED")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ppu-bootstrap-browser] RESULT: FAIL: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1)
