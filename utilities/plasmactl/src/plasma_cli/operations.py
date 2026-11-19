"""Deployment/maintenance profile routing to the EXISTING platform backends.

The portable CLI core never calls systemd, sudo, SSH or a Z2 directly. Every
install/deploy/verify/status/logs/restart operation is executed by the
platform backend that already owns it (installer, Bundle v3/Bootstrap,
Deployment Coordinator, Root Guard and rollback live there, not here).

Backends are found in ``PLASMA_CLI_BACKEND_DIR`` (set by the repository
launcher ``scripts/plasmactl``). A standalone wheel without a checkout has no
backends and refuses these commands instead of guessing.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROFILES = ("integration", "local-control-station", "swpc-z2like", "z2-ps")
# Overrides keep the existing test/operator hooks of the former Bash router.
_BACKENDS = {
    "integration": ("PLASMACTL_INTEGRATION_BACKEND", "plasmactl-integration"),
    "local-control-station": ("PLASMA_LOCAL_CONTROL_STATION_BACKEND",
                              "plasmactl-local-control-station"),
    "swpc-z2like": ("PLASMA_SWPC_Z2LIKE_BACKEND", "plasmactl-swpc-z2like-orchestrator"),
    "swpc-z2like-bootstrap": ("PLASMA_SWPC_Z2LIKE_BOOTSTRAP_BACKEND",
                              "plasmactl-swpc-z2like-bootstrap-sites"),
    "z2-ps": ("PLASMA_Z2_PS_BACKEND", "plasmactl-z2-ps"),
    "integration-verify": ("PLASMACTL_VERIFY_BACKEND", "plasmactl-verify"),
}
# Which profile backend implements which maintenance command.
SUPPORTED = {
    "install": PROFILES, "deploy": PROFILES, "verify": PROFILES, "status": PROFILES,
    "logs": ("integration", "local-control-station", "z2-ps"),
    "restart": ("integration", "local-control-station"),
}
INTEGRATION_ONLY = {
    "update": "update_code", "test": "run_tests", "web-restart": "restart_web_console",
    "restart-web": "restart_web_console", "start": "start_services",
    "stop": "stop_services", "ports": "show_ports", "update-and-restart": "deploy",
}
_INTEGRATION_FUNCTION = {"install": "install_services", "deploy": "deploy",
                         "status": "show_status", "restart": "restart_services",
                         "logs": "show_logs"}
# Load the integration backend as a library, then re-exec deploy through the
# operator launcher so an updated checkout keeps using the unified CLI.
_INTEGRATION_SHIM = (
    'PLASMACTL_LIB_ONLY=1; source "$0"; unset PLASMACTL_LIB_ONLY; '
    'script_path="${PLASMACTL_WRAPPER:-$script_path}"; '
    '"$@"'
)


class OperationError(RuntimeError):
    pass


def backend(name: str) -> Path:
    env, filename = _BACKENDS[name]
    override = os.environ.get(env)
    if override:
        path = Path(override)
    else:
        root = os.environ.get("PLASMA_CLI_BACKEND_DIR")
        if not root:
            raise OperationError(
                f"{name} backend is not available on this host: deployment operations run "
                "through a PLASMA checkout launcher (scripts/plasmactl)")
        path = Path(root) / filename
    if not path.is_file():
        raise OperationError(f"{name} backend is missing: {path}")
    return path


def _run(argv: list[str]) -> int:
    return subprocess.run(argv, check=False).returncode


def run_profile(command: str, profile: str, args: list[str]) -> int:
    """Delegate one maintenance command to its existing profile backend."""
    if profile not in PROFILES:
        raise OperationError(f"unknown deployment profile: {profile}")
    if profile not in SUPPORTED.get(command, ()):
        raise OperationError(f"{command} is not provided by the {profile} backend")
    if profile == "integration":
        if command == "logs":
            if len(args) > 1:
                raise OperationError("logs accepts at most one integration log target")
            args = [args[0] if args else "all"]
        elif command == "verify":
            if len(args) > 1:
                raise OperationError("integration verify accepts at most one target")
        elif args:
            raise OperationError(f"integration {command} does not accept profile options")
        if command == "verify":
            return _run(["bash", str(backend("integration-verify")), *args])
        return integration(_INTEGRATION_FUNCTION[command], args)
    if command in ("status", "logs", "restart") and args:
        raise OperationError(f"{command} accepts one deployment profile only")
    return _run(["bash", str(backend(profile)), command, *args])


def integration(function: str, args: list[str] | None = None) -> int:
    return _run(["bash", "-c", _INTEGRATION_SHIM, str(backend("integration")),
                 function, *(args or [])])


def bootstrap_sites(profile: str, args: list[str]) -> int:
    if profile != "swpc-z2like":
        raise OperationError("bootstrap-sites currently supports swpc-z2like only")
    if args:
        raise OperationError("bootstrap-sites swpc-z2like accepts no additional arguments")
    return _run(["bash", str(backend("swpc-z2like-bootstrap"))])


def hil_programming(args: list[str]) -> int:
    """SWPC engineering Blue Pill A/B + USB CDC harness (retained, separate)."""
    root = os.environ.get("PLASMA_CLI_BACKEND_DIR")
    script = Path(root) / "plasma_engineering_hil.py" if root else None
    if script is None or not script.is_file():
        raise OperationError("hil programming requires a PLASMA checkout launcher")
    os.execvp("python3", ["python3", str(script), *args])
    return 1  # pragma: no cover - exec does not return
