from __future__ import annotations

import argparse
import sys
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import gateway_phase2 as phase2
from .runtime_activation import (
    RuntimeActivationError,
    RuntimeActivationHelperClient,
    SiteRuntimeActivationController,
    desired_runtime_revision,
)


SITE_RUNTIME_ACTIVATION_PATH = "/api/settings/sites/activation"


class SiteRuntimeActivationSupportMixin:
    """PPU-level activation of persisted Site Desired state via bounded restart helper."""

    _runtime_activation_socket: Path | None = None

    @classmethod
    def configure_runtime_activation(cls, socket_path: Path | None) -> None:
        cls._runtime_activation_socket = socket_path.expanduser().resolve() if socket_path is not None else None

    def _runtime_activation_status_payload(self) -> dict[str, Any]:
        desired = self._site_configuration_controller().current()
        configuration = {
            "sites": [
                {
                    "site_id": site["site_id"],
                    "desired_revision": site["desired_revision"],
                }
                for site in desired["sites"]
            ]
        }
        revision = desired_runtime_revision(configuration)
        try:
            snapshot = self._local_snapshot()
            site_payload = self._site_configuration_payload(actual_snapshot=snapshot)
            reconciliation = site_payload["site_configuration"]["reconciliation"]
            ppu = snapshot.get("ppu") if isinstance(snapshot, dict) else None
            ppu_id = ppu.get("ppu_id") if isinstance(ppu, dict) else None
        except Exception:
            reconciliation = "actual_unavailable"
            ppu_id = None
        return {
            "ok": True,
            "rest_contract_version": phase2.canonical_gateway.WEB_REST_CONTRACT_VERSION,
            "runtime_activation": {
                "supported": self._runtime_activation_socket is not None,
                "state": "in_sync" if reconciliation == "in_sync" else "activation_required" if reconciliation == "restart_required" else reconciliation,
                "desired_runtime_revision": revision,
                "ppu_id": ppu_id,
                "reconciliation": reconciliation,
            },
        }

    def _runtime_activation_controller(self) -> SiteRuntimeActivationController:
        socket_path = self._runtime_activation_socket
        if socket_path is None:
            raise RuntimeActivationError(
                "runtime activation helper is not configured",
                error_type="RUNTIME_ACTIVATION_UNAVAILABLE",
                http_status=503,
            )
        return SiteRuntimeActivationController(
            RuntimeActivationHelperClient(socket_path),
            lambda: self._site_configuration_payload(),
            self._local_snapshot,
            lambda snapshot: self._site_configuration_payload(actual_snapshot=snapshot),
        )

    def _runtime_activation_error(self, exc: RuntimeActivationError) -> None:
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

    def _handle_runtime_activation_get(self, path: str) -> bool:
        if path.rstrip("/") != SITE_RUNTIME_ACTIVATION_PATH:
            return False
        self._json(HTTPStatus.OK, self._runtime_activation_status_payload())
        return True

    def _handle_runtime_activation_post(self, path: str) -> bool:
        if path.rstrip("/") != SITE_RUNTIME_ACTIVATION_PATH:
            return False
        controller = self._runtime_activation_controller()
        result = controller.activate(self._body())
        self._json(
            HTTPStatus.OK,
            {
                "ok": True,
                "rest_contract_version": phase2.canonical_gateway.WEB_REST_CONTRACT_VERSION,
                "runtime_activation": result,
            },
        )
        return True


class Phase3PlasmaWebHandler(SiteRuntimeActivationSupportMixin, phase2.Phase2PlasmaWebHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if self._handle_runtime_activation_get(path):
                return
        except RuntimeActivationError as exc:
            self._runtime_activation_error(exc)
            return
        except Exception as exc:
            self._error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if self._handle_runtime_activation_post(path):
                return
        except RuntimeActivationError as exc:
            self._runtime_activation_error(exc)
            return
        except Exception as exc:
            self._error(exc)
            return
        super().do_POST()


PlasmaWebHandler = Phase3PlasmaWebHandler


def _strip_phase3_options(argv: list[str]) -> list[str]:
    stripped: list[str] = []
    index = 0
    while index < len(argv):
        value = argv[index]
        if value == "--runtime-activation-socket":
            index += 2
            continue
        if value.startswith("--runtime-activation-socket="):
            index += 1
            continue
        stripped.append(value)
        index += 1
    return stripped


def main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--runtime-activation-socket", type=Path)
    known, _ = pre.parse_known_args(sys.argv[1:])
    handler = PlasmaWebHandler
    if not issubclass(handler, SiteRuntimeActivationSupportMixin):
        raise RuntimeError("configured Phase 3 Gateway handler lacks Site runtime activation support")
    handler.configure_runtime_activation(known.runtime_activation_socket)

    original_handler = phase2.PlasmaWebHandler
    original_argv = list(sys.argv)
    phase2.PlasmaWebHandler = handler
    sys.argv[:] = _strip_phase3_options(sys.argv)
    try:
        phase2.main()
    finally:
        phase2.PlasmaWebHandler = original_handler
        sys.argv[:] = original_argv


if __name__ == "__main__":
    main()
