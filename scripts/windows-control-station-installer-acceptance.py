#!/usr/bin/env python3
"""Install and exercise the unsigned Windows Control Station MSI pilot."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import ProxyHandler, Request, build_opener

MANAGER_SERVICE = "PlasmaManager"
CONSOLE_SERVICE = "PlasmaControlStationConsole"
MANAGER_PORT = 18180
CONSOLE_PORT = 18000
_DIRECT_HTTP = build_opener(ProxyHandler({}))
_ASSET_REF_RE = re.compile(
    r'''(?:href|src)=["']([^"']+\.(?:css|js)(?:\?[^"']*)?)["']''',
    re.IGNORECASE,
)


class InstallerAcceptanceError(RuntimeError):
    pass


def _run(args: Sequence[str], *, check: bool = True, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(args), check=check, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallerAcceptanceError(f"command failed: {' '.join(args)}: {exc}") from exc


def _powershell(script: str, *, check: bool = True, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    return _run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
        check=check, timeout=timeout,
    )


def _request_json(url: str, *, method: str = "GET", payload: dict[str, object] | None = None, timeout: float = 2) -> tuple[int, dict[str, object]]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with _DIRECT_HTTP.open(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read()
    except HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    except (URLError, TimeoutError) as exc:
        raise InstallerAcceptanceError(f"request failed: {url}: {exc}") from exc
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InstallerAcceptanceError(f"non-JSON response from {url}: status={status}") from exc
    if not isinstance(decoded, dict):
        raise InstallerAcceptanceError(f"JSON root is not an object: {url}")
    return status, decoded


def _wait_manager(deadline_s: float = 30) -> None:
    deadline = time.monotonic() + deadline_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            status, payload = _request_json(f"http://127.0.0.1:{MANAGER_PORT}/api/health/live", timeout=1)
            last = f"status={status} payload={payload}"
            if status == 200 and payload.get("ok") is True and payload.get("service") == "plasma-manager":
                return
        except InstallerAcceptanceError as exc:
            last = str(exc)
        time.sleep(0.25)
    raise InstallerAcceptanceError(f"Manager health did not become ready: {last}")


def _wait_console(deadline_s: float = 30) -> None:
    deadline = time.monotonic() + deadline_s
    url = f"http://127.0.0.1:{CONSOLE_PORT}/"
    last = "no response"
    while time.monotonic() < deadline:
        try:
            with _DIRECT_HTTP.open(Request(url, headers={"Accept": "text/html"}), timeout=1) as response:
                last = f"status={response.status}"
                if int(response.status) == 200:
                    return
        except (HTTPError, URLError, TimeoutError) as exc:
            last = str(exc)
        time.sleep(0.25)
    raise InstallerAcceptanceError(f"Console did not become ready: {last}")


def _console_asset_paths(html: str) -> tuple[str, ...]:
    return tuple(sorted({match.group(1) for match in _ASSET_REF_RE.finditer(html)}))


def _assert_console_static_assets() -> None:
    root_url = f"http://127.0.0.1:{CONSOLE_PORT}/"
    try:
        with _DIRECT_HTTP.open(Request(root_url, headers={"Accept": "text/html"}), timeout=2) as response:
            status = int(response.status)
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
    except (HTTPError, URLError, TimeoutError) as exc:
        raise InstallerAcceptanceError(f"Console HTML request failed while checking static assets: {exc}") from exc
    if status != 200:
        raise InstallerAcceptanceError(f"Console HTML returned status {status} while checking static assets")
    try:
        html = raw.decode(charset)
    except (LookupError, UnicodeDecodeError) as exc:
        raise InstallerAcceptanceError(f"Console HTML could not be decoded as {charset}: {exc}") from exc

    if 'data-route-marker="Choose a Demo"' not in html:
        raise InstallerAcceptanceError("Console root did not resolve to the Control Station product entry")
    if "SITE MATRIX" in html or "PPU CONTROL" in html:
        raise InstallerAcceptanceError("Console root still exposes the retired Single PPU Programming UI")

    assets = _console_asset_paths(html)
    stylesheets = [path for path in assets if path.split("?", 1)[0].lower().endswith(".css")]
    scripts = [path for path in assets if path.split("?", 1)[0].lower().endswith(".js")]
    if not stylesheets:
        raise InstallerAcceptanceError("Console HTML does not reference any packaged CSS assets")
    if not scripts:
        raise InstallerAcceptanceError("Console HTML does not reference any packaged JavaScript assets")

    for asset in assets:
        if asset.startswith(("http://", "https://", "//")):
            raise InstallerAcceptanceError(f"Console product HTML references a non-local static asset: {asset}")
        asset_url = urljoin(root_url, asset)
        try:
            with _DIRECT_HTTP.open(Request(asset_url, headers={"Accept": "*/*"}), timeout=2) as response:
                asset_status = int(response.status)
                payload = response.read()
        except HTTPError as exc:
            raise InstallerAcceptanceError(
                f"Console static asset returned HTTP {exc.code}: {asset}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise InstallerAcceptanceError(f"Console static asset request failed: {asset}: {exc}") from exc
        if asset_status != 200 or not payload:
            raise InstallerAcceptanceError(
                f"Console static asset is not servable: {asset}: status={asset_status} bytes={len(payload)}"
            )


def _assert_clean_install_managed_routing() -> None:
    status, payload = _request_json(f"http://127.0.0.1:{CONSOLE_PORT}/api/manager/ppu")
    if status != 503:
        raise InstallerAcceptanceError(
            f"clean-install Manager routing discovery returned HTTP {status}; expected 503 without a selected PPU"
        )
    if payload.get("managed") is not True or payload.get("configured") is not False:
        raise InstallerAcceptanceError(
            f"clean-install Console is not fail-closed in managed mode: {payload}"
        )
    error = payload.get("error")
    if not isinstance(error, dict) or error.get("code") != "manager_bff_misconfigured":
        raise InstallerAcceptanceError(
            f"clean-install managed routing returned an unexpected error contract: {payload}"
        )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _service_state(name: str) -> str | None:
    result = _powershell(
        f"$s=Get-Service -Name '{name}' -ErrorAction SilentlyContinue; if ($s) {{$s.Status.ToString()}} else {{'MISSING'}}",
        check=False,
    )
    state = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "MISSING"
    return None if state == "MISSING" else state


def _wait_service(name: str, expected: str, deadline_s: float = 30) -> None:
    deadline = time.monotonic() + deadline_s
    last = None
    while time.monotonic() < deadline:
        last = _service_state(name)
        if last == expected:
            return
        time.sleep(0.25)
    raise InstallerAcceptanceError(f"service {name} did not become {expected}: last={last}")


def _stop_services() -> None:
    for name in (CONSOLE_SERVICE, MANAGER_SERVICE):
        _powershell(f"Stop-Service -Name '{name}' -Force -ErrorAction SilentlyContinue", check=False)
    for name in (CONSOLE_SERVICE, MANAGER_SERVICE):
        if _service_state(name) is not None:
            _wait_service(name, "Stopped")


def _start_services() -> None:
    _powershell(f"Start-Service -Name '{MANAGER_SERVICE}'")
    _wait_service(MANAGER_SERVICE, "Running")
    _powershell(f"Start-Service -Name '{CONSOLE_SERVICE}'")
    _wait_service(CONSOLE_SERVICE, "Running")
    _wait_manager()
    _wait_console()


def _write_smoke_config(program_data: Path) -> None:
    fake_ppu_port = _free_port()
    config = program_data / "config"
    state = program_data / "state"
    config.mkdir(parents=True, exist_ok=True)
    state.mkdir(parents=True, exist_ok=True)
    (config / "manager.yaml").write_text(
        "\n".join([
            "manager:", "  host: 127.0.0.1", f"  port: {MANAGER_PORT}",
            "  request_timeout_s: 0.2", "  poll_interval_s: 60",
            f"  observation_db_path: {state / 'manager-observations.sqlite3'}", "ppus:",
            "  - alias: installer-smoke-ppu", f"    endpoint: http://127.0.0.1:{fake_ppu_port}", "",
        ]), encoding="utf-8",
    )
    (config / "selected-ppu-alias").write_text("installer-smoke-ppu\n", encoding="utf-8")


def _browser_fetch(node: Path, deadline_s: float = 25) -> None:
    if not node.is_file():
        raise InstallerAcceptanceError(f"bundled Node.js is unavailable for browser-style Fetch smoke: {node}")
    script = r'''const url = process.argv[1];
const deadline = Date.now() + Number(process.argv[2]);
const payload = { endpoint: "ps", timeout_ms: 100, payload: "windows-installer-smoke" };
let last = "no response";
while (Date.now() < deadline) {
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(5000),
    });
    const text = await response.text();
    last = `status=${response.status} body=${text}`;
    let decoded = null;
    try { decoded = JSON.parse(text); } catch {}
    if (response.status === 504 && decoded?.error?.code === "ppu_transport_error") {
      console.log(last);
      process.exit(0);
    }
  } catch (error) { last = error?.message ?? String(error); }
  await new Promise((resolve) => setTimeout(resolve, 250));
}
console.error(last);
process.exit(2);'''
    result = _run(
        [str(node), "--input-type=module", "-e", script,
         f"http://127.0.0.1:{CONSOLE_PORT}/api/manager/diagnostics/loopback", str(int(deadline_s * 1000))],
        check=False, timeout=deadline_s + 10,
    )
    if result.returncode != 0:
        raise InstallerAcceptanceError(f"browser-style BFF relay failed: {result.stdout.strip()}")


def _find_release(program_files: Path) -> Path:
    releases = program_files / "Plasma" / "releases"
    candidates = [path.parent for path in releases.glob("*/windows-installer.json") if path.is_file()]
    if len(candidates) != 1:
        raise InstallerAcceptanceError(f"expected one installed release, found {len(candidates)} under {releases}")
    return candidates[0]


def _assert_bundled_runtime_contract(release: Path) -> tuple[Path, Path]:
    manifest_path = release / "windows-installer.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallerAcceptanceError(f"cannot read installed Windows manifest: {exc}") from exc
    if manifest.get("runtime_ownership") != "bundled":
        raise InstallerAcceptanceError("installed Windows manifest does not declare bundled runtime ownership")
    if "external_prerequisites" in manifest:
        raise InstallerAcceptanceError("installed Windows manifest still declares external runtime prerequisites")

    python = release / "host-runtime" / "python" / "python.exe"
    node = release / "host-runtime" / "node" / "node.exe"
    for path in (python, node):
        if not path.is_file():
            raise InstallerAcceptanceError(f"bundled runtime executable is missing: {path}")

    manager_probe = _powershell(f"& '{release / 'bin' / 'run-manager.ps1'}' -PreflightOnly")
    expected_python = f"Plasma Manager bundled Python runtime: {python.resolve()}"
    if expected_python not in manager_probe.stdout:
        raise InstallerAcceptanceError(
            f"Manager launcher did not bind to installed bundled Python: {manager_probe.stdout.strip()}"
        )
    console_probe = _powershell(f"& '{release / 'bin' / 'run-console.ps1'}' -PreflightOnly")
    expected_node = f"Plasma Console bundled Node.js runtime: {node.resolve()}"
    if expected_node not in console_probe.stdout:
        raise InstallerAcceptanceError(
            f"Console launcher did not bind to installed bundled Node.js: {console_probe.stdout.strip()}"
        )
    return python, node


def run_acceptance(msi: Path) -> None:
    if sys.platform != "win32":
        raise InstallerAcceptanceError("Windows installer acceptance requires Windows")
    msi = msi.resolve()
    if not msi.is_file():
        raise InstallerAcceptanceError(f"MSI does not exist: {msi}")

    program_files = Path(os.environ["ProgramFiles"])
    program_data = Path(os.environ["ProgramData"]) / "Plasma"
    log_path = msi.with_suffix(".install.log")
    install = _run(["msiexec.exe", "/i", str(msi), "/qn", "/norestart", "/l*v", str(log_path)], check=False, timeout=180)
    if install.returncode != 0:
        raise InstallerAcceptanceError(f"msiexec install failed with {install.returncode}; log={log_path}")

    release = _find_release(program_files)
    required = (
        release / "runtime" / "console" / "server.js", release / "runtime" / "manager" / "manager.pyz",
        release / "host-runtime" / "python" / "python.exe", release / "host-runtime" / "python" / "LICENSE.txt",
        release / "host-runtime" / "node" / "node.exe", release / "host-runtime" / "node" / "LICENSE.txt",
        release / "bin" / "plasma-manager-service.exe", release / "bin" / "plasma-manager-service.xml",
        release / "bin" / "plasma-console-service.exe", release / "bin" / "plasma-console-service.xml",
        release / "THIRD_PARTY_LICENSES" / "WinSW.txt", program_data / "config" / "manager.yaml",
        program_data / "config" / "selected-ppu-alias",
    )
    for path in required:
        if not path.exists():
            raise InstallerAcceptanceError(f"installed path is missing: {path}")
    _, bundled_node = _assert_bundled_runtime_contract(release)
    if _service_state(MANAGER_SERVICE) != "Running" or _service_state(CONSOLE_SERVICE) != "Running":
        raise InstallerAcceptanceError("MSI did not register and start both SCM services")
    _wait_manager()
    _wait_console()
    _assert_console_static_assets()
    _assert_clean_install_managed_routing()
    print("Windows installer self-contained runtime binding: PASS", flush=True)
    print("Windows installer initial SCM launch: PASS", flush=True)
    print("Windows installer Control Station product entry and static assets: PASS", flush=True)
    print("Windows installer clean-install managed routing: PASS", flush=True)

    _write_smoke_config(program_data)
    _stop_services()
    _start_services()
    _assert_console_static_assets()
    _browser_fetch(bundled_node)
    print("Windows installer Browser -> Console/BFF -> Manager: PASS", flush=True)

    _stop_services()
    _start_services()
    _assert_console_static_assets()
    _browser_fetch(bundled_node)
    print("Windows installer Control Station entry/assets after SCM restart: PASS", flush=True)
    print("Windows installer SCM restart persistence: PASS", flush=True)

    _stop_services()
    if _service_state(MANAGER_SERVICE) != "Stopped" or _service_state(CONSOLE_SERVICE) != "Stopped":
        raise InstallerAcceptanceError("service stop did not reach Stopped state")
    _start_services()
    _assert_console_static_assets()
    print("Windows installer SCM stop/start: PASS", flush=True)

    mutable_config = (program_data / "config" / "manager.yaml").read_text(encoding="utf-8")
    uninstall_log = msi.with_suffix(".uninstall.log")
    uninstall = _run(["msiexec.exe", "/x", str(msi), "/qn", "/norestart", "/l*v", str(uninstall_log)], check=False, timeout=180)
    if uninstall.returncode != 0:
        raise InstallerAcceptanceError(f"msiexec uninstall failed with {uninstall.returncode}; log={uninstall_log}")
    if _service_state(MANAGER_SERVICE) is not None or _service_state(CONSOLE_SERVICE) is not None:
        raise InstallerAcceptanceError("uninstall left SCM services registered")
    if release.exists():
        raise InstallerAcceptanceError(f"uninstall left immutable release directory: {release}")
    if not (program_data / "config" / "manager.yaml").is_file():
        raise InstallerAcceptanceError("uninstall removed persistent Manager configuration")
    if (program_data / "config" / "manager.yaml").read_text(encoding="utf-8") != mutable_config:
        raise InstallerAcceptanceError("uninstall mutated persistent Manager configuration")
    print("Windows installer basic uninstall with mutable config preservation: PASS", flush=True)
    shutil.rmtree(program_data, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accept the Plasma Windows Control Station MSI pilot")
    parser.add_argument("--msi", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run_acceptance(args.msi)
    except InstallerAcceptanceError as exc:
        print(f"windows-control-station-installer-acceptance: {exc}", file=sys.stderr)
        log_root = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Plasma" / "logs"
        if log_root.is_dir():
            for path in sorted(log_root.glob("*")):
                if path.is_file():
                    print(f"--- {path.name} ---", file=sys.stderr)
                    print(path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
        return 2
    print("Windows Control Station Installer Pilot: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
