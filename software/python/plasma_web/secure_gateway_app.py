from __future__ import annotations

import os
import stat
from pathlib import Path

from plasma_core.errors import ErrorCode, PlasmaError

from . import gateway
from .gateway_security import GatewaySecurityController
from .secure_gateway import SecurePlasmaWebHandler


SECURITY_CONFIG_ENV = "PLASMA_SECURITY_CONFIG"
SECURITY_STATE_ENV = "PLASMA_SECURITY_STATE"


def _required_path_from_env(name: str) -> Path:
    raw = os.environ.get(name)
    if not raw:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{name} is required for the secure Gateway launcher")
    return Path(raw).expanduser().resolve()


def _require_owner_only_file(path: Path, *, label: str) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            f"cannot access {label}: {path}",
            original_exception=exc,
        ) from exc
    if not path.is_file():
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{label} must be a regular file: {path}")
    if mode & 0o077:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            f"{label} must be owner-only (chmod 600): {path}",
            context={"mode": oct(mode)},
        )


def load_security_controller_from_env() -> GatewaySecurityController:
    config_path = _required_path_from_env(SECURITY_CONFIG_ENV)
    state_path = _required_path_from_env(SECURITY_STATE_ENV)
    _require_owner_only_file(config_path, label="Gateway security config")
    state_path.parent.mkdir(parents=True, exist_ok=True)

    previous_umask = os.umask(0o077)
    try:
        controller = GatewaySecurityController.from_paths(config_path, state_path)
    finally:
        os.umask(previous_umask)

    if state_path.exists():
        state_path.chmod(0o600)
    return controller


class DeployedSecurePlasmaWebHandler(SecurePlasmaWebHandler):
    """Secure handler used by the deployable Gateway launcher.

    The canonical Gateway keeps its current CORS contract. Secure deployment
    extends only the authenticated boundary so existing non-secure deployments
    are not silently changed by this integration slice.
    """

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if "*" in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, Authorization, Idempotency-Key",
        )
        self.send_header("Access-Control-Max-Age", "600")


def main() -> None:
    controller = load_security_controller_from_env()
    original_handler = gateway.PlasmaWebHandler
    DeployedSecurePlasmaWebHandler.security_controller = controller
    gateway.PlasmaWebHandler = DeployedSecurePlasmaWebHandler
    try:
        gateway.main()
    finally:
        gateway.PlasmaWebHandler = original_handler
        DeployedSecurePlasmaWebHandler.security_controller = None
        controller.close()


if __name__ == "__main__":
    main()
