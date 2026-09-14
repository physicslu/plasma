from __future__ import annotations

import re
from http import HTTPStatus
from threading import RLock
from typing import Any
from urllib.parse import urlparse

from . import server as base_server
from .bootstrap import (
    BootstrapCredentialError,
    BootstrapCredentialStore,
    BootstrapManagerError,
    ManagerBootstrapCoordinator,
)
from .registry import (
    REGISTRY_LIFECYCLE_COMMISSIONED,
    REGISTRY_LIFECYCLE_DISABLED,
    REGISTRY_LIFECYCLE_PENDING,
    RegistryEntryNotFound,
)
from .verified_bootstrap import VerifiedManagerBootstrapCoordinator

BOOTSTRAP_ROUTE_RE = re.compile(r"^/api/registry/([^/]+)/bootstrap(?:/(.*))?$")
UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class BootstrapPlasmaManagerHandler(base_server.PlasmaManagerHandler):
    """Current Manager handler plus the independent PPU Bootstrap policy surface.

    This subclasses the current Manager rather than copying it. Registry, fleet,
    network commissioning and managed Gateway routing therefore remain owned by
    ``plasma_manager.server`` and evolve with that implementation.
    """

    bootstrap_coordinator: ManagerBootstrapCoordinator | None = None
    _bootstrap_init_lock = RLock()

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
        cls = type(self)
        if cls.bootstrap_coordinator is not None:
            return cls.bootstrap_coordinator
        with cls._bootstrap_init_lock:
            if cls.bootstrap_coordinator is not None:
                return cls.bootstrap_coordinator
            if self.registry_store is None:
                raise BootstrapManagerError("Manager runtime registry is unavailable")
            config = self._config()
            credentials = BootstrapCredentialStore(
                BootstrapCredentialStore.path_for_registry(config.registry_state_path)
            )
            cls.bootstrap_coordinator = VerifiedManagerBootstrapCoordinator(
                self.registry_store,
                credentials,
                config.request_timeout_s,
            )
            return cls.bootstrap_coordinator

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

    def _trusted_idle_observation(self, alias: str) -> bool:
        item = self._fleet_item_for_alias(alias)
        if item is None or self._alias_has_active_execution(alias):
            return False
        observation = item.get("observation")
        return (
            isinstance(observation, dict)
            and observation.get("state") == "current"
            and item.get("gateway_live") is True
            and item.get("identity_conflict") is False
            and not item.get("errors")
        )

    def _bootstrap_mutation_allowed(self, alias: str) -> bool:
        lifecycle = self._registry_lifecycle(alias)
        if lifecycle == REGISTRY_LIFECYCLE_PENDING:
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

        if lifecycle == REGISTRY_LIFECYCLE_COMMISSIONED:
            self._json(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": {
                        "code": "ppu_maintenance_required",
                        "message": "disable this commissioned PPU before Runtime maintenance",
                    },
                },
            )
            return False

        if lifecycle == REGISTRY_LIFECYCLE_DISABLED:
            if not self._trusted_idle_observation(alias):
                self._json(
                    HTTPStatus.CONFLICT,
                    {
                        "ok": False,
                        "error": {
                            "code": "ppu_idle_state_unproven",
                            "message": (
                                "a current trusted idle PPU observation is required for normal Runtime maintenance; "
                                "use the explicit recovery procedure when Runtime health cannot be observed"
                            ),
                        },
                    },
                )
                return False
            return True

        self._json(
            HTTPStatus.CONFLICT,
            {
                "ok": False,
                "error": {
                    "code": "ppu_lifecycle_invalid",
                    "message": f"PPU lifecycle {lifecycle!r} is not eligible for Runtime maintenance",
                },
            },
        )
        return False

    def _bootstrap_get(self, alias: str, action: str) -> None:
        if action:
            self._json(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": {
                        "code": "bootstrap_route_not_allowed",
                        "message": "Bootstrap GET route is not allowlisted",
                    },
                },
            )
            return
        try:
            payload = self._bootstrap().status(alias)
        except Exception as exc:
            self._bootstrap_error(exc)
            return
        self._json(HTTPStatus.OK, payload)

    def _bootstrap_post(self, alias: str, action: str) -> None:
        coordinator = self._bootstrap()
        try:
            body = self._read_json_object()
            if action == "pair":
                if set(body) != {"token"} or not isinstance(body.get("token"), str):
                    raise ValueError("Bootstrap pairing request requires only token")
                self._json(HTTPStatus.OK, coordinator.pair(alias, body["token"]))
                return
            if not self._bootstrap_mutation_allowed(alias):
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
        except Exception as exc:
            self._bootstrap_error(exc)
            return
        self._json(
            HTTPStatus.NOT_FOUND,
            {
                "ok": False,
                "error": {
                    "code": "bootstrap_route_not_allowed",
                    "message": "Bootstrap POST route is not allowlisted",
                },
            },
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


def main(argv: list[str] | None = None) -> None:
    """Run current Manager with Bootstrap routes composed into its handler.

    ``base_server.main`` remains authoritative for configuration, registry,
    polling, persistence and service lifecycle. Only the handler class is
    extended before that current entrypoint runs.
    """

    if argv is not None:
        raise ValueError("bootstrap Manager entrypoint does not accept injected argv")
    base_server.PlasmaManagerHandler = BootstrapPlasmaManagerHandler
    base_server.main()


if __name__ == "__main__":
    main()
