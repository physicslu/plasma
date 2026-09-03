from __future__ import annotations

import argparse
import sys
import threading
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from . import gateway as canonical_gateway
from . import gateway_base as base
from .ppu_network_activation import (
    PPUNetworkActivationController,
    PPUNetworkActivationError,
    PPUNetworkActivationHelperClient,
)


NETWORK_SETTINGS_PATH = "/api/settings/ppu-network"
NETWORK_ACTIVATION_PATH = "/api/settings/ppu-network/activation"


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


class Phase2PlasmaWebHandler(PPUNetworkActivationSupportMixin, canonical_gateway.PlasmaWebHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
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


def _strip_network_activation_option(argv: list[str]) -> list[str]:
    stripped: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--network-activation-socket":
            index += 2
            continue
        if value.startswith("--network-activation-socket="):
            index += 1
            continue
        stripped.append(value)
        index += 1
    return stripped


def main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--network-activation-socket", type=Path)
    pre.add_argument("--output-root", type=Path, default=Path("output"))
    pre.add_argument("--plasma-host", default="127.0.0.1")
    pre.add_argument("--plasma-port", type=int, default=9900)
    known, _ = pre.parse_known_args(sys.argv[1:])

    handler = PlasmaWebHandler
    if not issubclass(handler, PPUNetworkActivationSupportMixin):
        raise RuntimeError("configured Phase 2 Gateway handler lacks PPU network activation support")
    handler.configure_network_activation(
        socket_path=known.network_activation_socket,
        output_root=known.output_root,
        plasma_host=known.plasma_host,
        plasma_port=known.plasma_port,
    )

    original_handler = canonical_gateway.PlasmaWebHandler
    original_argv = list(sys.argv)
    canonical_gateway.PlasmaWebHandler = handler
    sys.argv[:] = _strip_network_activation_option(sys.argv)
    try:
        canonical_gateway.main()
    finally:
        handler.close_network_activation()
        canonical_gateway.PlasmaWebHandler = original_handler
        sys.argv[:] = original_argv


if __name__ == "__main__":
    main()
