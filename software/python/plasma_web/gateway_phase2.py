from __future__ import annotations

import argparse
import sys
import threading
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from plasma_core.errors import ErrorCode, PlasmaError

from . import gateway as canonical_gateway
from . import gateway_base as base
from .ppu_network_activation import (
    PPUNetworkActivationController,
    PPUNetworkActivationError,
    PPUNetworkActivationHelperClient,
)
from .site_configuration import SiteConfigurationController


NETWORK_SETTINGS_PATH = "/api/settings/ppu-network"
NETWORK_ACTIVATION_PATH = "/api/settings/ppu-network/activation"
SITE_SETTINGS_PATH = "/api/settings/sites"
ACTIVE_SITE_STATES = frozenset(
    {"queued", "submitting", "running", "stopping", "erase", "program", "verify", "read"}
)


class PPUNetworkActivationSupportMixin:
    """Small integration seam that adds Phase 2 routes to the canonical Gateway.

    The canonical Gateway remains the owner of all existing REST behavior. This
    mixin only intercepts the PPU network settings/activation resource family.
    When no activation helper socket is configured, the Phase 1 response remains
    byte-for-byte compatible at the semantic JSON level (`not_implemented`).
    """

    _network_activation_socket: Path | None = None
    _network_activation_output_root: Path = Path("output")
    _network_activation_plasma_host: str = "127.0.0.1"
    _network_activation_plasma_port: int = 9900
    _network_activation_instance: PPUNetworkActivationController | None = None
    _network_activation_lock = threading.RLock()

    @classmethod
    def configure_network_activation(
        cls,
        *,
        socket_path: Path | None,
        output_root: Path,
        plasma_host: str,
        plasma_port: int,
    ) -> None:
        with cls._network_activation_lock:
            if cls._network_activation_instance is not None:
                cls._network_activation_instance.close()
            cls._network_activation_instance = None
            cls._network_activation_socket = socket_path.resolve() if socket_path is not None else None
            cls._network_activation_output_root = output_root.resolve()
            cls._network_activation_plasma_host = plasma_host
            cls._network_activation_plasma_port = plasma_port

    @classmethod
    def close_network_activation(cls) -> None:
        with cls._network_activation_lock:
            controller = cls._network_activation_instance
            cls._network_activation_instance = None
        if controller is not None:
            controller.close()

    @classmethod
    def _local_ppu_id_for_activation(cls) -> str:
        snapshot = base._run(
            base.PlasmaClient(
                cls._network_activation_plasma_host,
                cls._network_activation_plasma_port,
            ).status(job_id=None, site_id=None)
        )
        if not isinstance(snapshot, dict) or snapshot.get("ok") is not True:
            raise PPUNetworkActivationError(
                "local Plasma Server did not return a valid PPU identity",
                error_type="PPU_NETWORK_IDENTITY_UNAVAILABLE",
                http_status=503,
            )
        ppu = snapshot.get("ppu")
        ppu_id = ppu.get("ppu_id") if isinstance(ppu, dict) else None
        if not isinstance(ppu_id, str) or not ppu_id:
            raise PPUNetworkActivationError(
                "local Plasma Server did not return a canonical ppu_id",
                error_type="PPU_NETWORK_IDENTITY_UNAVAILABLE",
                http_status=503,
            )
        return ppu_id

    @classmethod
    def _network_activation_controller(cls) -> PPUNetworkActivationController | None:
        if cls._network_activation_socket is None:
            return None
        with cls._network_activation_lock:
            if cls._network_activation_instance is None:
                helper = PPUNetworkActivationHelperClient(cls._network_activation_socket)
                cls._network_activation_instance = PPUNetworkActivationController(
                    cls.ppu_network_settings,
                    helper,
                    cls._network_activation_output_root / "ppu-network-activation.json",
                    cls._local_ppu_id_for_activation,
                )
            return cls._network_activation_instance

    @classmethod
    def _network_activation_status(cls) -> dict[str, Any]:
        controller = cls._network_activation_controller()
        if controller is None:
            return {"supported": False, "state": "not_implemented"}
        return controller.status()

    @classmethod
    def _network_settings_payload(cls) -> dict[str, Any]:
        return {
            "ok": True,
            "rest_contract_version": canonical_gateway.WEB_REST_CONTRACT_VERSION,
            "ppu_network_settings": cls.ppu_network_settings.current(),
            "activation": cls._network_activation_status(),
        }

    @classmethod
    def _network_activation_payload(cls, activation: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "ok": True,
            "rest_contract_version": canonical_gateway.WEB_REST_CONTRACT_VERSION,
            "activation": activation if activation is not None else cls._network_activation_status(),
        }

    @staticmethod
    def _activation_commit_id(path: str) -> str | None:
        parts = [unquote(part) for part in path.strip("/").split("/") if part]
        if len(parts) == 6 and parts[:4] == ["api", "settings", "ppu-network", "activation"] and parts[5] == "commit":
            return parts[4] or None
        return None

    @classmethod
    def is_phase2_network_get_path(cls, path: str) -> bool:
        normalized = path.rstrip("/")
        return normalized in {NETWORK_SETTINGS_PATH, NETWORK_ACTIVATION_PATH}

    @classmethod
    def is_phase2_network_post_path(cls, path: str) -> bool:
        normalized = path.rstrip("/")
        return normalized in {NETWORK_SETTINGS_PATH, NETWORK_ACTIVATION_PATH} or cls._activation_commit_id(normalized) is not None

    def _activation_error(self, exc: PPUNetworkActivationError) -> None:
        self._json(
            exc.http_status,
            {
                "ok": False,
                "error": {
                    "error_type": exc.error_type,
                    "message": exc.message,
                    "context": dict(exc.context),
                },
            },
        )

    def _handle_phase2_network_get(self, path: str) -> bool:
        normalized = path.rstrip("/")
        if normalized == NETWORK_SETTINGS_PATH:
            self._json(HTTPStatus.OK, self._network_settings_payload())
            return True
        if normalized == NETWORK_ACTIVATION_PATH:
            self._json(HTTPStatus.OK, self._network_activation_payload())
            return True
        return False

    def _handle_phase2_network_post(self, path: str) -> bool:
        normalized = path.rstrip("/")
        controller = self._network_activation_controller()
        if normalized == NETWORK_SETTINGS_PATH:
            if controller is not None and controller.active():
                raise PPUNetworkActivationError(
                    "desired PPU network settings cannot change during an active activation",
                    error_type="PPU_NETWORK_ACTIVATION_BUSY",
                    http_status=409,
                    context={"state": controller.status()["state"]},
                )
            settings = self.ppu_network_settings.update(self._body())
            self._json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "rest_contract_version": canonical_gateway.WEB_REST_CONTRACT_VERSION,
                    "ppu_network_settings": settings,
                    "activation": self._network_activation_status(),
                },
            )
            return True
        if normalized == NETWORK_ACTIVATION_PATH:
            if controller is None:
                raise PPUNetworkActivationError(
                    "PPU network activation helper is not configured",
                    error_type="PPU_NETWORK_ACTIVATION_UNAVAILABLE",
                    http_status=503,
                )
            activation = controller.schedule(self._body())
            # The controller deliberately delays mutation after this ACK so the
            # response can leave through the old endpoint before eth0 changes.
            self._json(HTTPStatus.ACCEPTED, self._network_activation_payload(activation))
            return True
        activation_id = self._activation_commit_id(normalized)
        if activation_id is not None:
            if controller is None:
                raise PPUNetworkActivationError(
                    "PPU network activation helper is not configured",
                    error_type="PPU_NETWORK_ACTIVATION_UNAVAILABLE",
                    http_status=503,
                )
            activation = controller.commit(activation_id, self._body())
            self._json(HTTPStatus.OK, self._network_activation_payload(activation))
            return True
        return False


class SiteConfigurationSupportMixin:
    """Expose PPU-owned desired Site configuration without pretending hot apply.

    Desired values live in the canonical PPU YAML. Actual values come from the
    running Plasma Server. Phase 1 persists a desired change and reports whether
    the running process already matches it; it never restarts Plasma Server from
    inside an HTTP request.
    """

    site_configuration: SiteConfigurationController | None = None

    @classmethod
    def configure_site_configuration(cls, config_path: Path) -> None:
        cls.site_configuration = SiteConfigurationController(config_path)

    @staticmethod
    def _site_settings_id(path: str) -> int | None:
        parts = [unquote(part) for part in path.strip("/").split("/") if part]
        if len(parts) != 4 or parts[:3] != ["api", "settings", "sites"]:
            return None
        try:
            return base._parse_site_id(parts[3])
        except ValueError:
            return None

    def _site_configuration_controller(self) -> SiteConfigurationController:
        controller = self.site_configuration
        if controller is None:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "PPU Site configuration controller is unavailable",
            )
        return controller

    @staticmethod
    def _active_execution(snapshot: dict[str, Any]) -> dict[str, Any] | None:
        ppu = snapshot.get("ppu")
        execution = ppu.get("execution") if isinstance(ppu, dict) else None
        if isinstance(execution, dict) and execution.get("busy") is True:
            return execution
        sites = snapshot.get("sites")
        if isinstance(sites, list):
            for site in sites:
                if not isinstance(site, dict):
                    continue
                state = str(site.get("state", "")).strip().lower()
                if site.get("current_job_id") or state in ACTIVE_SITE_STATES:
                    return {
                        "busy": True,
                        "site_id": site.get("site_id"),
                        "current_job_id": site.get("current_job_id"),
                        "state": state,
                    }
        return None

    @staticmethod
    def _site_actual_view(site: dict[str, Any]) -> dict[str, Any]:
        return {
            "enabled": site.get("enabled") is True,
            "interface": site.get("interface"),
            "target": site.get("target"),
            "state": site.get("state"),
            "current_job_id": site.get("current_job_id"),
        }

    @classmethod
    def _site_reconciliation_state(
        cls,
        desired: dict[str, Any],
        actual: dict[str, Any] | None,
    ) -> str:
        if actual is None:
            return "actual_unavailable"
        if desired["enabled"] != actual["enabled"]:
            return "restart_required"
        if actual["enabled"]:
            if desired["interface"] != actual["interface"] or desired["target"] != actual["target"]:
                return "restart_required"
            return "in_sync"
        # Protocol v3.3 intentionally hides interface/target for a disabled Site.
        # We can prove effective disabled state, but not the dormant loaded binding.
        return "disabled_runtime_binding_unobservable"

    def _site_configuration_payload(
        self,
        *,
        actual_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        desired = self._site_configuration_controller().current()
        snapshot = actual_snapshot if actual_snapshot is not None else self._local_snapshot()
        raw_actual_sites = snapshot.get("sites")
        actual_sites = raw_actual_sites if isinstance(raw_actual_sites, list) else []
        actual_by_id = {
            site.get("site_id"): site
            for site in actual_sites
            if isinstance(site, dict) and isinstance(site.get("site_id"), int)
        }

        sites: list[dict[str, Any]] = []
        states: list[str] = []
        for desired_site in desired["sites"]:
            site_id = desired_site["site_id"]
            raw_actual = actual_by_id.get(site_id)
            actual = self._site_actual_view(raw_actual) if isinstance(raw_actual, dict) else None
            state = self._site_reconciliation_state(desired_site, actual)
            states.append(state)
            sites.append(
                {
                    "site_id": site_id,
                    "desired": {
                        "enabled": desired_site["enabled"],
                        "interface": desired_site["interface"],
                        "target": desired_site["target"],
                    },
                    "actual": actual,
                    "reconciliation": state,
                }
            )

        if any(state == "restart_required" for state in states):
            overall = "restart_required"
        elif any(state == "actual_unavailable" for state in states):
            overall = "actual_unavailable"
        elif any(state == "disabled_runtime_binding_unobservable" for state in states):
            overall = "partially_observable"
        else:
            overall = "in_sync"

        return {
            "ok": True,
            "rest_contract_version": canonical_gateway.WEB_REST_CONTRACT_VERSION,
            "site_configuration": {
                "source": desired["source"],
                "runtime_apply_supported": False,
                "reconciliation": overall,
                "sites": sites,
            },
        }

    def _handle_site_configuration_get(self, path: str) -> bool:
        if path.rstrip("/") != SITE_SETTINGS_PATH:
            return False
        try:
            snapshot = self._local_snapshot()
        except Exception:
            self._execution_unavailable()
            return True
        self._json(HTTPStatus.OK, self._site_configuration_payload(actual_snapshot=snapshot))
        return True

    def _handle_site_configuration_post(self, path: str) -> bool:
        site_id = self._site_settings_id(path)
        if site_id is None:
            return False
        try:
            snapshot = self._local_snapshot()
        except Exception:
            self._execution_unavailable()
            return True
        active = self._active_execution(snapshot)
        if active is not None:
            raise PlasmaError(
                ErrorCode.PPU_BUSY,
                "Site desired configuration cannot change while PPU execution is active",
                recoverable=True,
                context={"execution": active},
            )
        self._site_configuration_controller().update(site_id, self._body())
        self._json(HTTPStatus.OK, self._site_configuration_payload(actual_snapshot=snapshot))
        return True


class Phase2PlasmaWebHandler(
    SiteConfigurationSupportMixin,
    PPUNetworkActivationSupportMixin,
    canonical_gateway.PlasmaWebHandler,
):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if self._handle_site_configuration_get(path):
                return
            if self._handle_phase2_network_get(path):
                return
        except PPUNetworkActivationError as exc:
            self._activation_error(exc)
            return
        except Exception as exc:
            self._error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if self._handle_site_configuration_post(path):
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


# Secure deployment swaps this module variable before calling main().
PlasmaWebHandler = Phase2PlasmaWebHandler


def _strip_phase2_options(argv: list[str]) -> list[str]:
    stripped: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value in {"--network-activation-socket", "--ppu-config"}:
            index += 2
            continue
        if value.startswith("--network-activation-socket=") or value.startswith("--ppu-config="):
            index += 1
            continue
        stripped.append(value)
        index += 1
    return stripped


def main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--network-activation-socket", type=Path)
    pre.add_argument("--ppu-config", type=Path, default=Path("config/plasma.yaml"))
    pre.add_argument("--output-root", type=Path, default=Path("output"))
    pre.add_argument("--plasma-host", default="127.0.0.1")
    pre.add_argument("--plasma-port", type=int, default=9900)
    known, _ = pre.parse_known_args(sys.argv[1:])

    handler = PlasmaWebHandler
    if not issubclass(handler, PPUNetworkActivationSupportMixin):
        raise RuntimeError("configured Phase 2 Gateway handler lacks PPU network activation support")
    if not issubclass(handler, SiteConfigurationSupportMixin):
        raise RuntimeError("configured Phase 2 Gateway handler lacks Site configuration support")
    handler.configure_network_activation(
        socket_path=known.network_activation_socket,
        output_root=known.output_root,
        plasma_host=known.plasma_host,
        plasma_port=known.plasma_port,
    )
    handler.configure_site_configuration(known.ppu_config)

    original_handler = canonical_gateway.PlasmaWebHandler
    original_argv = list(sys.argv)
    canonical_gateway.PlasmaWebHandler = handler
    sys.argv[:] = _strip_phase2_options(sys.argv)
    try:
        canonical_gateway.main()
    finally:
        handler.close_network_activation()
        canonical_gateway.PlasmaWebHandler = original_handler
        sys.argv[:] = original_argv


if __name__ == "__main__":
    main()
