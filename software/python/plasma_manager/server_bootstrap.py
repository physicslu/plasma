from __future__ import annotations

import argparse
import re
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .bootstrap import (
    BootstrapCredentialError,
    BootstrapCredentialStore,
    BootstrapManagerError,
    ManagerBootstrapCoordinator,
)
from .config import ManagerConfig, load_manager_config
from .fleet import FleetAggregator
from .network_commissioning import NetworkCommissioningCoordinator, NetworkCommissioningStore
from .poller import FleetPoller
from .registry import RegistryEntryNotFound
from .server import PlasmaManagerHTTPServer, PlasmaManagerHandler, _build_observation_store


BOOTSTRAP_ROUTE_RE = re.compile(r"^/api/registry/([^/]+)/bootstrap(?:/(.*))?$")
UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class BootstrapPlasmaManagerHandler(PlasmaManagerHandler):
    """Manager HTTP handler extended with an exact PPU Bootstrap policy surface.

    Bootstrap is deliberately *not* routed through the generic Managed PPU
    Gateway relay. A factory PPU may not have Plasma Runtime/Gateway installed
    yet, and the root-capable Bootstrap service has a separate device-bound
    credential and admission model.
    """

    bootstrap_coordinator: ManagerBootstrapCoordinator | None = None

    @classmethod
    def _parse_bootstrap_route(cls, path: str) -> tuple[str, str] | None:
        match = BOOTSTRAP_ROUTE_RE.fullmatch(path)
        if match is None:
            return None
        alias = cls._valid_alias(match.group(1))
        if alias is None:
            return None
        action = (match.group(2) or "").strip("/")
        return alias, action

    def _bootstrap(self) -> ManagerBootstrapCoordinator:
        if self.bootstrap_coordinator is None:
            raise BootstrapManagerError("Manager Bootstrap coordinator is unavailable")
        return self.bootstrap_coordinator

    def _bootstrap_error(self, exc: Exception) -> None:
        if isinstance(exc, RegistryEntryNotFound):
            status = HTTPStatus.NOT_FOUND
            code = "ppu_not_found"
        elif isinstance(exc, BootstrapCredentialError):
            status = HTTPStatus.CONFLICT
            code = "bootstrap_pairing_required"
        elif isinstance(exc, BootstrapManagerError):
            status = HTTPStatus.CONFLICT
            code = "bootstrap_operation_rejected"
        elif isinstance(exc, ValueError):
            status = HTTPStatus.BAD_REQUEST
            code = "invalid_request"
        else:
            raise exc
        self._json(status, {"ok": False, "error": {"code": code, "message": str(exc)}})

    def _bootstrap_body(self) -> dict[str, Any]:
        return self._read_json_object()

    def _bootstrap_mutation_allowed(self, alias: str) -> bool:
        # Runtime deployment is a maintenance operation. It must never race a
        # programming execution, regardless of registry lifecycle. Pending PPUs
        # are intentionally allowed because first installation occurs before the
        # normal Gateway can satisfy Validate & Enable.
        if self._alias_has_active_execution(alias):
            self._json(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": {
                        "code": "ppu_busy",
                        "message": "active PPU Jobs must finish or be cancelled before runtime deployment",
                    },
                },
            )
            return False
        return True

    def _bootstrap_get(self, alias: str, action: str) -> None:
        if action:
            self._json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": {"code": "bootstrap_route_not_allowed", "message": "Bootstrap GET route is not allowlisted"}},
            )
            return
        try:
            payload = self._bootstrap().status(alias)
        except Exception as exc:  # mapped to stable Manager API errors below
            self._bootstrap_error(exc)
            return
        self._json(HTTPStatus.OK, payload)

    def _bootstrap_post(self, alias: str, action: str) -> None:
        if not self._bootstrap_mutation_allowed(alias):
            return
        coordinator = self._bootstrap()
        try:
            body = self._bootstrap_body()
            if action == "pair":
                if set(body) != {"token"} or not isinstance(body.get("token"), str):
                    raise ValueError("Bootstrap pairing request requires only token")
                # Re-pairing a commissioned appliance silently is too powerful.
                # Disable it first so credential rotation is an explicit
                # maintenance transition. Pending first-install PPUs are allowed.
                if self._registry_lifecycle(alias) == "commissioned":
                    raise BootstrapManagerError("disable a commissioned PPU before changing its Bootstrap pairing")
                self._json(HTTPStatus.OK, coordinator.pair(alias, body["token"]))
                return
            if action == "uploads":
                status, payload = coordinator.create_upload(alias, body)
                self._json(status, payload)
                return
            upload_match = re.fullmatch(r"uploads/([0-9a-f]{32})/(chunks|commit)", action)
            if upload_match is not None:
                upload_id, operation = upload_match.groups()
                if not UPLOAD_ID_RE.fullmatch(upload_id):
                    raise ValueError("Bootstrap upload_id is invalid")
                if operation == "chunks":
                    status, payload = coordinator.append_chunk(alias, upload_id, body)
                else:
                    if set(body) != {"action"} or body.get("action") != "commit":
                        raise ValueError("Bootstrap upload commit requires action=commit")
                    status, payload = coordinator.commit_upload(alias, upload_id)
                self._json(status, payload)
                return
            if action == "deployments":
                status, payload = coordinator.start_deployment(alias, body)
                self._json(status, payload)
                return
        except Exception as exc:  # mapped to stable Manager API errors below
            self._bootstrap_error(exc)
            return
        self._json(
            HTTPStatus.NOT_FOUND,
            {"ok": False, "error": {"code": "bootstrap_route_not_allowed", "message": "Bootstrap POST route is not allowlisted"}},
        )

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        bootstrap = self._parse_bootstrap_route(parsed.path)
        if bootstrap is not None:
            alias, action = bootstrap
            self._bootstrap_get(alias, action)
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        bootstrap = self._parse_bootstrap_route(parsed.path)
        if bootstrap is not None:
            alias, action = bootstrap
            self._bootstrap_post(alias, action)
            return
        super().do_POST()


def serve(config: ManagerConfig) -> None:
    registry = __import__("plasma_manager.registry", fromlist=["PPURegistryStore"]).PPURegistryStore(
        config.ppus,
        config.registry_state_path,
    )
    commissioning_store = NetworkCommissioningStore(
        NetworkCommissioningCoordinator.state_path_for_registry(config.registry_state_path)
    )
    commissioning = NetworkCommissioningCoordinator(
        registry,
        commissioning_store,
        config.request_timeout_s,
    )
    commissioning.recover()
    credentials = BootstrapCredentialStore(
        BootstrapCredentialStore.path_for_registry(config.registry_state_path)
    )
    bootstrap = ManagerBootstrapCoordinator(registry, credentials, config.request_timeout_s)
    aggregator = FleetAggregator(config, registry_provider=registry.entries)
    observations = _build_observation_store(config, aggregator)
    poller = FleetPoller(observations, config.poll_interval_s)

    BootstrapPlasmaManagerHandler.aggregator = aggregator
    BootstrapPlasmaManagerHandler.poller = poller
    BootstrapPlasmaManagerHandler.config = config
    BootstrapPlasmaManagerHandler.registry_store = registry
    BootstrapPlasmaManagerHandler.network_commissioning = commissioning
    BootstrapPlasmaManagerHandler.bootstrap_coordinator = bootstrap

    server = PlasmaManagerHTTPServer((config.host, config.port), BootstrapPlasmaManagerHandler)
    poller.start(prime_cache=False)
    print(f"Plasma Manager listening on http://{config.host}:{config.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        poller.stop(timeout_s=max(5.0, config.request_timeout_s * 4 + 1.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Plasma Manager fleet control plane")
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to an explicit Plasma Manager registry configuration",
    )
    args = parser.parse_args()
    serve(load_manager_config(args.config))


if __name__ == "__main__":
    main()
