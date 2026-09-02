#!/usr/bin/env python3
"""One-command packaged ARMv7 acceptance for PPU Network Configuration Phase 1.

Host mode builds the canonical PPU runtime and linux-armv7l release, verifies the
release from a clean extraction, ensures ARMv7 QEMU/binfmt is available, then
runs this same script inside a capability-restricted ARMv7 container.

Container mode starts the packaged Plasma Server/Gateway and proves the Phase 1
contract end to end:
- default DHCP desired state;
- static desired-state round trip;
- durable persistence across Gateway restart;
- invalid configuration rejection without state mutation;
- activation remains explicitly not implemented;
- actual Linux eth0 IPv4 remains unchanged; and
- CAP_NET_ADMIN is absent from the acceptance container.

This harness is software-only. It does not claim PYNQ-Z2 hardware or real Linux
network activation.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import shutil
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence


ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
BINFMT_IMAGE = "docker.io/tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0"
DEFAULT_WORK_REL = Path(".work/ppu-network-phase1-acceptance")
DEFAULT_REPORT_REL = Path(".work/reports/ppu-network-phase1-acceptance.json")
RESULT_MARKER = "PLASMA_PPU_NETWORK_PHASE1_RESULT="
CAP_NET_ADMIN = 12
SIOCGIFADDR = 0x8915
PPU_INTERFACE = "eth0"
STATIC_SETTINGS = {
    "mode": "static",
    "address": "192.168.50.21",
    "prefix_length": 24,
    "gateway": "192.168.50.1",
    "dns_servers": ["1.1.1.1", "8.8.8.8"],
}


class AcceptanceError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=capture,
        check=check,
    )


def _host_python(repo: Path) -> Path:
    venv_python = repo / "software/python/.venv/bin/python"
    if venv_python.is_file():
        return venv_python
    if sys.version_info < (3, 11):
        raise AcceptanceError(f"Python >= 3.11 is required, got {platform.python_version()}")
    return Path(sys.executable).resolve()


def _git_sha(repo: Path) -> str:
    result = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    value = result.stdout.strip()
    if len(value) != 40:
        raise AcceptanceError(f"unexpected git SHA: {value!r}")
    return value


def _product_version(repo: Path) -> str:
    try:
        payload = json.loads((repo / "release/product.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"cannot read release/product.json: {exc}") from exc
    version = payload.get("product_version") if isinstance(payload, dict) else None
    if not isinstance(version, str) or not version:
        raise AcceptanceError("release/product.json is missing product_version")
    return version


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_sidecar(archive: Path, sidecar: Path) -> str:
    try:
        line = sidecar.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise AcceptanceError(f"cannot read release sidecar: {sidecar}") from exc
    parts = line.split()
    if len(parts) != 2 or len(parts[0]) != 64 or parts[1] != archive.name:
        raise AcceptanceError(f"invalid release SHA-256 sidecar: {line!r}")
    actual = _sha256(archive)
    if actual != parts[0]:
        raise AcceptanceError(f"release SHA-256 mismatch: expected {parts[0]}, got {actual}")
    return actual


def _docker_preflight() -> bool:
    if shutil.which("docker") is None:
        raise AcceptanceError("docker is not available on PATH")
    probe = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/arm/v7",
        ARM_IMAGE,
        "python3",
        "-c",
        "import platform; print(platform.machine())",
    ]
    installed_binfmt = False
    result = _run(probe, check=False)
    if result.returncode != 0:
        install = _run(
            ["docker", "run", "--privileged", "--rm", BINFMT_IMAGE, "--install", "arm"],
            check=False,
        )
        if install.returncode != 0:
            raise AcceptanceError(
                "ARM binfmt installation failed:\n"
                + (install.stdout or "")
                + (install.stderr or "")
            )
        installed_binfmt = True
        result = _run(probe, check=False)
    if result.returncode != 0 or result.stdout.strip().lower() not in {"armv7", "armv7l"}:
        raise AcceptanceError(
            "ARMv7 Docker preflight failed:\n" + (result.stdout or "") + (result.stderr or "")
        )
    return installed_binfmt


def _build_release(repo: Path, work_root: Path, python: Path, git_sha: str, version: str) -> tuple[Path, Path, Path]:
    runtime = work_root / "build-runtime"
    release_dir = work_root / "release"
    extracted = work_root / "extracted"
    _run([str(python), "scripts/ppu-runtime.py", "build", "--output-dir", str(runtime)], cwd=repo)
    _run([str(python), "scripts/ppu-runtime.py", "validate", str(runtime)], cwd=repo)
    _run(
        [
            str(python),
            "scripts/ppu-release.py",
            "--runtime-dir",
            str(runtime),
            "--output-dir",
            str(release_dir),
            "--git-sha",
            git_sha,
        ],
        cwd=repo,
    )
    archive = release_dir / f"plasma-ppu-{version}-linux-armv7l.tar.gz"
    sidecar = Path(f"{archive}.sha256")
    if not archive.is_file() or not sidecar.is_file():
        raise AcceptanceError(f"canonical PPU release was not produced under {release_dir}")
    _verify_sidecar(archive, sidecar)
    _run(
        [
            str(python),
            "scripts/product-release.py",
            "verify",
            str(archive),
            "--sidecar",
            str(sidecar),
            "--extract-to",
            str(extracted),
            "--expect-role",
            "ppu",
            "--expect-platform",
            "linux",
            "--expect-architecture",
            "armv7l",
            "--expect-version",
            version,
        ],
        cwd=repo,
    )
    clean_runtime = extracted / "plasma-release/runtime"
    _run([str(python), "scripts/ppu-runtime.py", "validate", str(clean_runtime)], cwd=repo)
    if not (clean_runtime / "ppu/ppu.pyz").is_file():
        raise AcceptanceError("clean extracted release is missing runtime/ppu/ppu.pyz")
    return archive, sidecar, clean_runtime


def _parse_result(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.startswith(RESULT_MARKER):
            value = json.loads(line[len(RESULT_MARKER) :])
            if isinstance(value, dict):
                return value
    raise AcceptanceError("ARMv7 acceptance container did not emit a result marker")


def _network_settings(payload: Mapping[str, Any]) -> dict[str, Any]:
    if payload.get("ok") is not True:
        raise AcceptanceError(f"network settings response is not ok: {payload!r}")
    settings = payload.get("ppu_network_settings")
    if not isinstance(settings, dict):
        raise AcceptanceError("network settings response is missing ppu_network_settings")
    activation = payload.get("activation")
    if activation != {"supported": False, "state": "not_implemented"}:
        raise AcceptanceError(f"unexpected activation boundary: {activation!r}")
    return settings


def _assert_settings(settings: Mapping[str, Any], expected: Mapping[str, Any], *, revision: int) -> None:
    if settings.get("revision") != revision:
        raise AcceptanceError(f"expected revision {revision}, got {settings.get('revision')!r}")
    if settings.get("interface") != PPU_INTERFACE:
        raise AcceptanceError(f"expected interface eth0, got {settings.get('interface')!r}")
    for key, value in expected.items():
        if settings.get(key) != value:
            raise AcceptanceError(f"expected {key}={value!r}, got {settings.get(key)!r}")


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
    timeout_s: float = 10.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(dict(body)).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    except urllib.error.URLError as exc:
        raise AcceptanceError(f"request failed for {url}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AcceptanceError(f"non-JSON response from {url}: HTTP {status}") from exc
    if not isinstance(payload, dict):
        raise AcceptanceError(f"JSON response from {url} is not an object")
    return status, payload


def _write_server_config(work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    config = work / "ppu.yaml"
    config.write_text(
        "ppu:\n"
        "  id: swpc-armv7-network-phase1\n"
        "  facility_id: swpc-qemu\n"
        "  model: qemu-armv7\n"
        "  display_name: Plasma PPU Network Phase 1 Acceptance\n\n"
        "server:\n"
        "  host: 127.0.0.1\n"
        "  port: 9900\n"
        "  max_supported_sites: 8\n"
        "  max_concurrent_jobs: 1\n"
        "  max_queue_depth_per_site: 16\n"
        "  output_root: /work/server-output\n"
        "  log_root: /work/logs\n"
        "  max_metadata_bytes: 65536\n"
        "  max_map_bytes: 1048576\n"
        "  max_binary_bytes: 67108864\n\n"
        "sites: []\n",
        encoding="utf-8",
    )
    return config


def _terminate(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _start_gateway(app: Path, work: Path, env: Mapping[str, str]) -> subprocess.Popen[Any]:
    return subprocess.Popen(
        [
            sys.executable,
            str(app),
            "gateway",
            "--host",
            "127.0.0.1",
            "--port",
            "18080",
            "--plasma-host",
            "127.0.0.1",
            "--plasma-port",
            "9900",
            "--output-root",
            str(work / "gateway-output"),
        ],
        cwd=work,
        env=dict(env),
    )


def _wait_ready(base_url: str, server: subprocess.Popen[Any], gateway: subprocess.Popen[Any], timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if server.poll() is not None or gateway.poll() is not None:
            raise AcceptanceError("Plasma Server or Gateway exited before readiness")
        try:
            status, payload = _request_json(f"{base_url}/api/health/ready", timeout_s=2.0)
            if status == 200 and payload.get("ok") is True and payload.get("execution") == "ready":
                return
        except AcceptanceError:
            pass
        time.sleep(0.2)
    raise AcceptanceError("Gateway readiness deadline exceeded")


def _effective_capabilities() -> int:
    for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("CapEff:"):
            return int(line.split(":", 1)[1].strip(), 16)
    raise AcceptanceError("/proc/self/status does not expose CapEff")


def _has_capability(capability: int) -> bool:
    return bool(_effective_capabilities() & (1 << capability))


def _interface_ipv4(interface: str = PPU_INTERFACE) -> str:
    ifname = interface.encode("ascii")[:15]
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            response = fcntl.ioctl(sock.fileno(), SIOCGIFADDR, struct.pack("256s", ifname))
        except OSError as exc:
            raise AcceptanceError(f"cannot read IPv4 address for {interface}: {exc}") from exc
    return socket.inet_ntoa(response[20:24])


def _inside_mode(args: argparse.Namespace) -> int:
    architecture = platform.machine().lower()
    if architecture not in {"armv7", "armv7l"}:
        raise AcceptanceError(f"inside mode requires ARMv7, got {architecture}")
    if sys.version_info < (3, 11):
        raise AcceptanceError(f"inside mode requires Python >= 3.11, got {platform.python_version()}")
    if _has_capability(CAP_NET_ADMIN):
        raise AcceptanceError("acceptance container unexpectedly has CAP_NET_ADMIN")

    runtime = args.runtime_dir.resolve()
    app = runtime / "ppu/ppu.pyz"
    if not app.is_file():
        raise AcceptanceError(f"PPU zipapp is missing: {app}")
    manifest = json.loads((runtime / "ppu-runtime.json").read_text(encoding="utf-8"))
    catalog = runtime / str((manifest.get("data") or {}).get("device_catalog_manifest"))
    if not catalog.is_file():
        raise AcceptanceError(f"Device Catalog manifest is missing: {catalog}")

    work = Path("/work")
    for directory in (work / "server-output", work / "logs", work / "gateway-output"):
        directory.mkdir(parents=True, exist_ok=True)
    config = _write_server_config(work)
    persistence = work / "gateway-output/ppu-network-settings.yaml"
    if persistence.exists():
        persistence.unlink()

    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PLASMA_DEVICE_CATALOG_MANIFEST"] = str(catalog)
    server: subprocess.Popen[Any] | None = None
    gateway: subprocess.Popen[Any] | None = None
    tests: dict[str, str] = {}
    try:
        server = subprocess.Popen([sys.executable, str(app), "server", "--config", str(config)], cwd=work, env=env)
        gateway = _start_gateway(app, work, env)
        base = "http://127.0.0.1:18080"
        _wait_ready(base, server, gateway)
        tests["packaged_runtime_ready"] = "PASS"

        actual_before = _interface_ipv4()
        tests["cap_net_admin_absent"] = "PASS"

        status, payload = _request_json(f"{base}/api/settings/ppu-network")
        if status != 200:
            raise AcceptanceError(f"default network GET returned HTTP {status}")
        default = _network_settings(payload)
        _assert_settings(
            default,
            {
                "mode": "dhcp",
                "address": None,
                "prefix_length": None,
                "gateway": None,
                "dns_servers": [],
            },
            revision=1,
        )
        tests["default_dhcp"] = "PASS"
        tests["activation_not_implemented"] = "PASS"

        status, payload = _request_json(
            f"{base}/api/settings/ppu-network", method="POST", body=STATIC_SETTINGS
        )
        if status != 200:
            raise AcceptanceError(f"static network POST returned HTTP {status}: {payload!r}")
        static = _network_settings(payload)
        _assert_settings(static, STATIC_SETTINGS, revision=2)
        tests["static_update"] = "PASS"

        status, payload = _request_json(f"{base}/api/settings/ppu-network")
        if status != 200:
            raise AcceptanceError(f"static round-trip GET returned HTTP {status}")
        _assert_settings(_network_settings(payload), STATIC_SETTINGS, revision=2)
        tests["static_round_trip"] = "PASS"

        actual_after_static = _interface_ipv4()
        if actual_after_static != actual_before or actual_after_static == STATIC_SETTINGS["address"]:
            raise AcceptanceError(
                f"actual eth0 changed unexpectedly: before={actual_before}, after={actual_after_static}"
            )
        tests["actual_network_unchanged"] = "PASS"

        if not persistence.is_file():
            raise AcceptanceError(f"network persistence file was not created: {persistence}")
        tests["persistence_file_created"] = "PASS"

        _terminate(gateway)
        gateway = _start_gateway(app, work, env)
        _wait_ready(base, server, gateway)
        status, payload = _request_json(f"{base}/api/settings/ppu-network")
        if status != 200:
            raise AcceptanceError(f"post-restart network GET returned HTTP {status}")
        _assert_settings(_network_settings(payload), STATIC_SETTINGS, revision=2)
        tests["gateway_restart_persistence"] = "PASS"

        invalid_ipv4 = dict(STATIC_SETTINGS)
        invalid_ipv4["address"] = "999.168.50.21"
        status, payload = _request_json(
            f"{base}/api/settings/ppu-network", method="POST", body=invalid_ipv4
        )
        if status != 400 or payload.get("ok") is not False:
            raise AcceptanceError(f"invalid IPv4 was not rejected: HTTP {status}: {payload!r}")
        tests["invalid_ipv4_rejected"] = "PASS"

        invalid_dhcp = {
            "mode": "dhcp",
            "address": "192.168.50.21",
            "prefix_length": 24,
            "gateway": None,
            "dns_servers": [],
        }
        status, payload = _request_json(
            f"{base}/api/settings/ppu-network", method="POST", body=invalid_dhcp
        )
        if status != 400 or payload.get("ok") is not False:
            raise AcceptanceError(f"DHCP/static field mix was not rejected: HTTP {status}: {payload!r}")
        tests["dhcp_static_mix_rejected"] = "PASS"

        status, payload = _request_json(f"{base}/api/settings/ppu-network")
        if status != 200:
            raise AcceptanceError(f"final network GET returned HTTP {status}")
        final_settings = _network_settings(payload)
        _assert_settings(final_settings, STATIC_SETTINGS, revision=2)
        tests["rejected_requests_preserve_state"] = "PASS"

        actual_final = _interface_ipv4()
        if actual_final != actual_before:
            raise AcceptanceError(
                f"actual eth0 changed during acceptance: before={actual_before}, final={actual_final}"
            )

        result = {
            "functional_result": "PASS",
            "overall_result": "PASS",
            "evidence_level": "packaged-release-swpc-qemu-armv7-userspace",
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "tests": tests,
            "network": {
                "interface": PPU_INTERFACE,
                "actual_ipv4_before": actual_before,
                "actual_ipv4_after": actual_final,
                "desired_ipv4": STATIC_SETTINGS["address"],
                "final_revision": final_settings["revision"],
                "activation": {"supported": False, "state": "not_implemented"},
                "cap_net_admin": False,
            },
            "persistence": {
                "path": str(persistence),
                "bytes": persistence.stat().st_size,
            },
            "not_claimed": [
                "PYNQ-Z2 hardware",
                "Linux eth0 activation",
                "DHCP client activation",
                "route or DNS mutation",
                "Manager reconnect",
                "same-ppu_id post-network verification",
                "network rollback",
                "PS-to-PL",
                "Site I/O",
                "real IC programming",
            ],
        }
        print(RESULT_MARKER + json.dumps(result, sort_keys=True), flush=True)
        return 0
    finally:
        _terminate(gateway)
        _terminate(server)


def _print_summary(result: Mapping[str, Any], *, git_sha: str, version: str, archive: Path, archive_sha256: str, binfmt_installed: bool, report_path: Path) -> None:
    tests = result.get("tests") if isinstance(result.get("tests"), dict) else {}
    network = result.get("network") if isinstance(result.get("network"), dict) else {}
    print("=" * 68)
    print("Plasma PPU Network Phase 1 Acceptance")
    print("=" * 68)
    print(f"Git SHA                  : {git_sha}")
    print(f"Product Version          : {version}")
    print(f"Architecture             : {result.get('architecture')}")
    print(f"Release Artifact         : {archive.name}")
    print(f"Release SHA-256          : {archive_sha256}")
    print(f"ARM binfmt installed now : {'yes' if binfmt_installed else 'no'}")
    print()
    ordered = [
        ("Packaged runtime ready", "packaged_runtime_ready"),
        ("Default DHCP", "default_dhcp"),
        ("Static update", "static_update"),
        ("Static GET round-trip", "static_round_trip"),
        ("Persistence file created", "persistence_file_created"),
        ("Gateway restart persistence", "gateway_restart_persistence"),
        ("Invalid IPv4 rejected", "invalid_ipv4_rejected"),
        ("DHCP/static mix rejected", "dhcp_static_mix_rejected"),
        ("Rejected requests preserve state", "rejected_requests_preserve_state"),
        ("Activation not implemented", "activation_not_implemented"),
        ("CAP_NET_ADMIN absent", "cap_net_admin_absent"),
        ("Actual eth0 unchanged", "actual_network_unchanged"),
    ]
    for label, key in ordered:
        print(f"[{tests.get(key, 'FAIL')}] {label}")
    print()
    print(f"Actual eth0 IPv4         : {network.get('actual_ipv4_before')}")
    print(f"Desired IPv4             : {network.get('desired_ipv4')}")
    print(f"Final revision           : {network.get('final_revision')}")
    print("-" * 68)
    print(f"PHASE 1 FUNCTIONAL RESULT : {result.get('functional_result')}")
    print("NETWORK MUTATION          : NOT IMPLEMENTED")
    print("Z2 HARDWARE CLAIM         : NONE")
    print(f"OVERALL RESULT            : {result.get('overall_result')}")
    print("-" * 68)
    print(f"JSON report               : {report_path}")
    print("=" * 68)


def _host_mode(args: argparse.Namespace) -> int:
    repo = _repo_root()
    python = _host_python(repo)
    work_root = (repo / args.work_dir).resolve() if not args.work_dir.is_absolute() else args.work_dir.resolve()
    report_path = (repo / args.report).resolve() if not args.report.is_absolute() else args.report.resolve()
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    git_sha = _git_sha(repo)
    version = _product_version(repo)
    archive, _sidecar, clean_runtime = _build_release(repo, work_root, python, git_sha, version)
    archive_sha256 = _sha256(archive)
    binfmt_installed = _docker_preflight()

    container_work = work_root / "container-work"
    container_work.mkdir(parents=True, exist_ok=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/arm/v7",
        "--security-opt",
        "no-new-privileges=true",
        "-v",
        f"{clean_runtime}:/runtime:ro",
        "-v",
        f"{Path(__file__).resolve()}:/acceptance.py:ro",
        "-v",
        f"{container_work}:/work",
        ARM_IMAGE,
        "python3",
        "/acceptance.py",
        "--inside",
        "--runtime-dir",
        "/runtime",
    ]
    completed = _run(command, check=False)
    if completed.returncode != 0:
        raise AcceptanceError(
            "ARMv7 Phase 1 acceptance failed:\n"
            + (completed.stdout or "")
            + (completed.stderr or "")
        )
    result = _parse_result(completed.stdout)
    if result.get("overall_result") != "PASS":
        raise AcceptanceError(f"ARMv7 Phase 1 acceptance did not PASS: {result!r}")

    report = dict(result)
    report["git_sha"] = git_sha
    report["product_version"] = version
    report["release"] = {
        "artifact": archive.name,
        "sha256": archive_sha256,
    }
    report["host"] = {
        "python": str(python),
        "binfmt_installed_during_run": binfmt_installed,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _print_summary(
        report,
        git_sha=git_sha,
        version=version,
        archive=archive,
        archive_sha256=archive_sha256,
        binfmt_installed=binfmt_installed,
        report_path=report_path,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plasma PPU Network Phase 1 packaged ARMv7 acceptance")
    parser.add_argument("--inside", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--runtime-dir", type=Path, default=Path("/runtime"))
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_REL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_REL)
    args = parser.parse_args(argv)
    try:
        return _inside_mode(args) if args.inside else _host_mode(args)
    except (AcceptanceError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"ppu-network-phase1-acceptance: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
