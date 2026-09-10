from __future__ import annotations

import os
import stat
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from plasma_core.errors import ErrorCode, PlasmaError

from . import gateway_phase3 as gateway
from .gateway_phase2 import (
    PPUNetworkActivationSupportMixin,
    SITE_SETTINGS_PATH,
    SiteConfigurationSupportMixin,
)
from .gateway_phase3 import SITE_RUNTIME_ACTIVATION_PATH, SiteRuntimeActivationSupportMixin
from .gateway_security import GatewaySecurityController, Permission
from .ppu_network_activation import PPUNetworkActivationError
from .runtime_activation import RuntimeActivationError
from .secure_gateway import SecurePlasmaWebHandler


SECURITY_CONFIG_ENV = "PLASMA_SECURITY_CONFIG"
SECURITY_STATE_ENV = "PLASMA_SECURITY_STATE"
RUNTIME_ACTIVATION_PERMISSION = "settings.runtime_activation.write"


def _required_path_from_env(name: str) -> Path:
    raw = os.environ.get(name)
    if not raw:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{name} is required for the secure Gateway launcher")
    return Path(raw).expanduser().resolve()


def _require_owner_only_file(path: Path, *, label: str) -> None:
    try:
        metadata = path.stat()
    except OSError as exc:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"cannot access {label}: {path}", original_exception=exc) from exc
    if not path.is_file():
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{label} must be a regular file: {path}")
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise PlasmaError(ErrorCode.CONFIG_INVALID, f"{label} must be owned by the Gateway process user: {path}")
    mode = stat.S_IMODE(metadata.st_mode)
    if mode & 0o077:
        raise PlasmaError(
            ErrorCode.CONFIG_INVALID,
            f"{label} must be owner-only (chmod 600): {path}",
            context={"mode": oct(mode)},
        )


def _validate_existing_security_state(path: Path) -> None:
    for candidate, label in (
        (path, "Gateway security state"),
        (Path(f"{path}-wal"), "Gateway security state WAL"),
        (Path(f"{path}-shm"), "Gateway security state shared memory"),
    ):
        if candidate.exists():
            _require_owner_only_file(candidate, label=label)


def load_security_controller_from_env() -> GatewaySecurityController:
    config_path = _required_path_from_env(SECURITY_CONFIG_ENV)
    state_path = _required_path_from_env(SECURITY_STATE_ENV)
    if config_path == state_path:
        raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security config and state paths must be different files")
    _require_owner_only_file(config_path, label="Gateway security config")
    _validate_existing_security_state(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    previous_umask = os.umask(0o077)
    try:
        controller = GatewaySecurityController.from_paths(config_path, state_path)
    finally:
        os.umask(previous_umask)
    for candidate in (state_path, Path(f"{state_path}-wal"), Path(f"{state_path}-shm")):
        if candidate.exists():
            candidate.chmod(0o600)
    return controller


class DeployedSecurePlasmaWebHandler(
    SiteRuntimeActivationSupportMixin,
    SiteConfigurationSupportMixin,
    PPUNetworkActivationSupportMixin,
    SecurePlasmaWebHandler,
):
    """Secure deployed handler including P3 runtime activation.

    Runtime activation is an independent endpoint permission boundary. The
    current security schema expresses that boundary as an explicit Engineer/Admin
    role check named ``settings.runtime_activation.write`` while durable command
    admission reuses the existing Site-settings command ledger. This avoids
    granting operators or services a restart capability.
    """

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if "*" in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", "*")
        elif origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Idempotency-Key, If-Match")
        self.send_header("Access-Control-Max-Age", "600")

    def _guard_get(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        if path in {"/api/settings/ppu-network/activation", SITE_SETTINGS_PATH, SITE_RUNTIME_ACTIVATION_PATH}:
            self._authorize(Permission.SETTINGS_READ)
            return
        super()._guard_get()

    def _guard_runtime_activation(self) -> bool:
        principal = self._principal()
        if not set(principal.roles).intersection({"engineer", "admin"}):
            raise PlasmaError(
                ErrorCode.PERMISSION_DENIED,
                f"permission denied: {RUNTIME_ACTIVATION_PERMISSION}",
            )
        # Runtime activation remains in the durable idempotency ledger. The
        # independent Engineer/Admin role check above is authoritative for this
        # endpoint; SITE_SETTINGS_WRITE supplies the existing durable action ID.
        return self._admit_command(Permission.SITE_SETTINGS_WRITE)

    def _guard_post(self) -> bool:
        path = urlparse(self.path).path.rstrip("/")
        if path == SITE_RUNTIME_ACTIVATION_PATH:
            return self._guard_runtime_activation()
        if path == "/api/settings/ppu-network/activation" or self._activation_commit_id(path) is not None:
            return self._admit_command(Permission.PPU_NETWORK_SETTINGS_WRITE)
        site_id = self._site_settings_id(path)
        if site_id is not None:
            self._principal()
            return self._admit_command(
                Permission.SITE_SETTINGS_WRITE,
                resources=(self._local_resource(site_id),),
            )
        return super()._guard_post()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.rstrip("/") == SITE_RUNTIME_ACTIVATION_PATH:
            try:
                self._guard_get()
                if self._handle_runtime_activation_get(path):
                    return
            except RuntimeActivationError as exc:
                self._runtime_activation_error(exc)
                return
            except Exception as exc:
                self._error(exc)
                return
        if path.rstrip("/") == SITE_SETTINGS_PATH:
            try:
                self._guard_get()
                if self._handle_site_configuration_get(path):
                    return
            except Exception as exc:
                self._error(exc)
                return
        if self.is_phase2_network_get_path(path):
            try:
                self._guard_get()
                if self._handle_phase2_network_get(path):
                    return
            except PPUNetworkActivationError as exc:
                self._activation_error(exc)
                return
            except Exception as exc:
                self._error(exc)
                return
        if path == "/api/security/me":
            try:
                principal = self._principal()
                permissions = sorted(permission.value for permission in principal.permissions)
                if set(principal.roles).intersection({"engineer", "admin"}):
                    permissions.append(RUNTIME_ACTIVATION_PERMISSION)
                    permissions.sort()
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "principal": {
                            "id": principal.principal_id,
                            "roles": list(principal.roles),
                            "permissions": permissions,
                            "scopes": [scope.to_dict() for scope in principal.scopes],
                        },
                    },
                )
            except Exception as exc:
                self._error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path.rstrip("/") == SITE_RUNTIME_ACTIVATION_PATH:
            try:
                if self._guard_post():
                    return
                if self._handle_runtime_activation_post(path):
                    return
            except RuntimeActivationError as exc:
                self._runtime_activation_error(exc)
                return
            except Exception as exc:
                self._error(exc)
                return
        if self._site_settings_id(path) is not None:
            try:
                if self._guard_post():
                    return
                if self._handle_site_configuration_post(path):
                    return
            except Exception as exc:
                self._error(exc)
                return
        if self.is_phase2_network_post_path(path):
            try:
                if self._guard_post():
                    return
                if self._handle_phase2_network_post(path):
                    return
            except PPUNetworkActivationError as exc:
                self._activation_error(exc)
                return
            except Exception as exc:
                self._error(exc)
                return
        super().do_POST()


def main() -> None:
    controller = load_security_controller_from_env()
    original_handler = gateway.PlasmaWebHandler
    previous_umask = os.umask(0o077)
    DeployedSecurePlasmaWebHandler.security_controller = controller
    gateway.PlasmaWebHandler = DeployedSecurePlasmaWebHandler
    try:
        gateway.main()
    finally:
        gateway.PlasmaWebHandler = original_handler
        DeployedSecurePlasmaWebHandler.security_controller = None
        os.umask(previous_umask)
        controller.close()


if __name__ == "__main__":
    main()
