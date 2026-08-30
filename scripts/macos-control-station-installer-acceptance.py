#!/usr/bin/env python3
"""Install and exercise the unsigned macOS Control Station installer pilot."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

PRODUCT_ROOT = Path("/Library/Application Support/Plasma")
PACKAGE_ID = "com.plasma.control-station"
MANAGER_PORT = 18180
CONSOLE_PORT = 18000
_DIRECT_HTTP = build_opener(ProxyHandler({}))


class InstallerAcceptanceError(RuntimeError):
    pass


def _run(args: Sequence[str], *, check: bool = True, timeout: float = 60) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(list(args), check=check, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallerAcceptanceError(f"command failed: {' '.join(args)}: {exc}") from exc


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


def _wait_manager(deadline_s: float = 20) -> None:
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
        time.sleep(0.2)
    raise InstallerAcceptanceError(f"Manager health did not become ready: {last}")


def _wait_console(deadline_s: float = 20) -> None:
    deadline = time.monotonic() + deadline_s
    url = f"http://127.0.0.1:{CONSOLE_PORT}/"
    last = "no response"
    while time.monotonic() < deadline:
        request = Request(url, headers={"Accept": "text/html"})
        try:
            with _DIRECT_HTTP.open(request, timeout=1) as response:
                status = int(response.status)
                last = f"status={status}"
                if status == 200:
                    return
        except (HTTPError, URLError, TimeoutError) as exc:
            last = str(exc)
        time.sleep(0.2)
    raise InstallerAcceptanceError(f"Console did not become ready: {last}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _browser_fetch(node_path: Path, deadline_s: float = 20) -> None:
    script = r'''const url = process.argv[1];
const deadline = Date.now() + Number(process.argv[2]);
const payload = { endpoint: "ps", timeout_ms: 100, payload: "macos-installer-smoke" };
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
  } catch (error) {
    last = error?.message ?? String(error);
  }
  await new Promise((resolve) => setTimeout(resolve, 200));
}
console.error(last);
process.exit(2);'''
    result = _run([str(node_path), "--input-type=module", "-e", script, f"http://127.0.0.1:{CONSOLE_PORT}/api/manager/diagnostics/loopback", str(int(deadline_s * 1000))], check=False, timeout=deadline_s + 10)
    if result.returncode != 0:
        raise InstallerAcceptanceError(f"browser-style BFF relay failed: {result.stdout.strip()}")


def _write_smoke_config(home: Path) -> None:
    fake_ppu_port = _free_port()
    config_root = home / "Library" / "Application Support" / "Plasma" / "config"
    state_root = home / "Library" / "Application Support" / "Plasma" / "state"
    config_root.mkdir(parents=True, exist_ok=True)
    (config_root / "manager.yaml").write_text("\n".join(["manager:", "  host: 127.0.0.1", f"  port: {MANAGER_PORT}", "  request_timeout_s: 0.2", "  poll_interval_s: 60", f"  observation_db_path: {state_root / 'manager-observations.sqlite3'}", "ppus:", "  - alias: installer-smoke-ppu", f"    endpoint: http://127.0.0.1:{fake_ppu_port}", ""]), encoding="utf-8")
    (config_root / "selected-ppu-alias").write_text("installer-smoke-ppu\n", encoding="utf-8")


def _assert_launchagent(user_id: int, label: str) -> None:
    result = _run(["/bin/launchctl", "print", f"gui/{user_id}/{label}"], check=False)
    if result.returncode != 0:
        raise InstallerAcceptanceError(f"LaunchAgent is not loaded: {label}\n{result.stdout}")


def _assert_system_owned_immutable(path: Path, *, follow_symlinks: bool = True) -> None:
    info = path.stat() if follow_symlinks else path.lstat()
    if info.st_uid != 0:
        raise InstallerAcceptanceError(f"immutable system path is not root-owned: {path} uid={info.st_uid}")
    if stat.S_IMODE(info.st_mode) & 0o022:
        raise InstallerAcceptanceError(
            f"immutable system path is group/world writable: {path} mode={oct(stat.S_IMODE(info.st_mode))}"
        )


def _assert_user_owned(path: Path, user_id: int) -> None:
    info = path.stat()
    if info.st_uid != user_id:
        raise InstallerAcceptanceError(f"mutable user path has wrong owner: {path} uid={info.st_uid} expected={user_id}")


def run_acceptance(pkg: Path) -> None:
    if sys.platform != "darwin":
        raise InstallerAcceptanceError("macOS installer acceptance requires Darwin")
    pkg = pkg.resolve()
    if not pkg.is_file():
        raise InstallerAcceptanceError(f"package does not exist: {pkg}")

    user = getpass.getuser()
    if user == "root":
        raise InstallerAcceptanceError("acceptance must run from a non-root login user with passwordless sudo")
    home = Path.home().resolve()
    user_id = os.getuid()
    mutable_root = home / "Library" / "Application Support" / "Plasma"
    log_root = home / "Library" / "Logs" / "Plasma"
    launch_root = home / "Library" / "LaunchAgents"

    uninstall = PRODUCT_ROOT / "current" / "bin" / "uninstall-pilot.sh"
    if uninstall.is_file():
        _run(["sudo", str(uninstall), "--user", user], check=False)

    install = _run(["sudo", "installer", "-pkg", str(pkg), "-target", "/"], check=False, timeout=120)
    if install.returncode != 0:
        raise InstallerAcceptanceError(f"installer failed:\n{install.stdout}")

    current = PRODUCT_ROOT / "current"
    if not current.is_symlink():
        raise InstallerAcceptanceError("installer did not create the current release symlink")
    immutable_paths = (
        current / "runtime" / "console" / "server.js",
        current / "runtime" / "manager" / "manager.pyz",
        PRODUCT_ROOT / "install" / "node-path",
        PRODUCT_ROOT / "install" / "python-path",
    )
    user_paths = (
        launch_root / "com.plasma.manager.plist",
        launch_root / "com.plasma.console.plist",
        mutable_root / "config" / "manager.yaml",
        mutable_root / "config" / "selected-ppu-alias",
    )
    for required in (*immutable_paths, *user_paths):
        if not required.exists():
            raise InstallerAcceptanceError(f"installed path is missing: {required}")

    _assert_system_owned_immutable(PRODUCT_ROOT)
    _assert_system_owned_immutable(current, follow_symlinks=False)
    for path in immutable_paths:
        _assert_system_owned_immutable(path)
    for path in user_paths:
        _assert_user_owned(path, user_id)
    print("macOS installer ownership boundary: PASS", flush=True)

    node_path = Path((PRODUCT_ROOT / "install" / "node-path").read_text(encoding="utf-8").strip())
    python_path = Path((PRODUCT_ROOT / "install" / "python-path").read_text(encoding="utf-8").strip())
    if not node_path.is_absolute() or not node_path.is_file():
        raise InstallerAcceptanceError(f"recorded Node.js path is invalid: {node_path}")
    if not python_path.is_absolute() or not python_path.is_file():
        raise InstallerAcceptanceError(f"recorded Python path is invalid: {python_path}")

    _assert_launchagent(user_id, "com.plasma.manager")
    _assert_launchagent(user_id, "com.plasma.console")
    _wait_manager()
    _wait_console()
    print("macOS installer initial launch: PASS", flush=True)

    _write_smoke_config(home)
    service_control = current / "bin" / "service-control.sh"
    _run([str(service_control), "restart"], timeout=60)
    _wait_manager()
    _wait_console()
    _browser_fetch(node_path)
    print("macOS installer Browser -> Console/BFF -> Manager: PASS", flush=True)

    _run([str(service_control), "restart"], timeout=60)
    _wait_manager()
    _wait_console()
    _browser_fetch(node_path)
    print("macOS installer launchd restart persistence: PASS", flush=True)

    _run([str(service_control), "stop"], timeout=30)
    time.sleep(0.5)
    for label in ("com.plasma.manager", "com.plasma.console"):
        result = _run(["/bin/launchctl", "print", f"gui/{user_id}/{label}"], check=False)
        if result.returncode == 0:
            raise InstallerAcceptanceError(f"stop did not unload {label}")
    _run([str(service_control), "start"], timeout=60)
    _wait_manager()
    _wait_console()
    print("macOS installer service stop/start: PASS", flush=True)

    uninstall = current / "bin" / "uninstall-pilot.sh"
    result = _run(["sudo", str(uninstall), "--user", user], check=False, timeout=60)
    if result.returncode != 0:
        raise InstallerAcceptanceError(f"uninstall failed:\n{result.stdout}")
    if PRODUCT_ROOT.joinpath("current").exists() or PRODUCT_ROOT.joinpath("current").is_symlink():
        raise InstallerAcceptanceError("uninstall left the current runtime activation link")
    if (launch_root / "com.plasma.manager.plist").exists() or (launch_root / "com.plasma.console.plist").exists():
        raise InstallerAcceptanceError("uninstall left LaunchAgent definitions")
    receipt = _run(["/usr/sbin/pkgutil", "--pkg-info", PACKAGE_ID], check=False)
    if receipt.returncode == 0:
        raise InstallerAcceptanceError("uninstall left the package receipt registered")
    if not mutable_root.exists() or not log_root.exists():
        raise InstallerAcceptanceError("pilot uninstall should preserve mutable user config/state/logs")
    print("macOS installer basic uninstall: PASS", flush=True)

    shutil.rmtree(mutable_root, ignore_errors=True)
    shutil.rmtree(log_root, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accept the Plasma macOS Control Station installer pilot")
    parser.add_argument("--pkg", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        run_acceptance(args.pkg)
    except InstallerAcceptanceError as exc:
        print(f"macos-control-station-installer-acceptance: {exc}", file=sys.stderr)
        for name in ("manager.log", "console.log"):
            path = Path.home() / "Library" / "Logs" / "Plasma" / name
            if path.is_file():
                print(f"--- {name} ---", file=sys.stderr)
                print(path.read_text(encoding="utf-8", errors="replace"), file=sys.stderr)
        return 2
    print("macOS Control Station Installer Pilot: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
