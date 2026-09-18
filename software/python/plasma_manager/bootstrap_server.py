from __future__ import annotations

import re
import time
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
from .client import PPUHTTPError, PPUHttpClient, PPUTransportError
from .registry import RegistryEntryNotFound
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
    runtime_client_factory = PPUHttpClient
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
        # Platform maintenance authorization is independent from programming
        # Registration. Registration controls managed Site/programming admission;
        # this gate instead proves the PPU is safe to mutate at the Platform layer.
        if self._alias_has_active_execution(alias):
            self._json(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": {
                        "code": "ppu_busy",
                        "message": "active PPU Jobs must finish or be cancelled before Platform maintenance",
                    },
                },
            )
            return False

        try:
            platform = self._bootstrap().status(alias)
        except Exception as exc:
            self._bootstrap_error(exc)
            return False
        bootstrap = platform.get("bootstrap")
        runtime = bootstrap.get("runtime") if isinstance(bootstrap, dict) else None
        deployment = bootstrap.get("deployment") if isinstance(bootstrap, dict) else None
        runtime_state = runtime.get("state") if isinstance(runtime, dict) else None
        deployment_state = deployment.get("state") if isinstance(deployment, dict) else None

        if runtime_state == "recovery_required" or deployment_state == "recovery_required":
            self._json(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": {
                        "code": "ppu_recovery_required",
                        "message": "explicit Platform recovery is required before normal Runtime maintenance",
                    },
                },
            )
            return False

        # A factory/first-install target has no Runtime whose idle state can be
        # observed yet. Pairing/authentication remains enforced by the Bootstrap
        # coordinator before any mutation reaches the device.
        if runtime_state == "runtime_absent":
            return True

        if runtime_state == "runtime_active":
            if not self._trusted_idle_observation(alias):
                self._json(
                    HTTPStatus.CONFLICT,
                    {
                        "ok": False,
                        "error": {
                            "code": "ppu_idle_state_unproven",
                            "message": (
                                "a current trusted idle PPU observation is required for normal Runtime maintenance; "
                                "programming Registration state does not lower this Platform safety gate"
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
                    "code": "ppu_platform_state_invalid",
                    "message": f"Runtime state {runtime_state!r} is not eligible for normal Platform maintenance",
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

    def _platform_ps_loopback(self, alias: str, body: dict[str, Any]) -> None:
        try:
            platform = self._bootstrap().status(alias)
        except Exception as exc:
            self._bootstrap_error(exc)
            return
        pairing = platform.get("pairing")
        if not isinstance(pairing, dict) or pairing.get("paired") is not True or pairing.get("device_match") is not True:
            self._bootstrap_error(
                BootstrapCredentialError("Platform maintenance pairing is required before PS Loop Test")
            )
            return
        if body.get("endpoint") != "ps":
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "unsupported_endpoint", "message": "Platform Loop Test supports PS only"}},
            )
            return
        timeout_ms = body.get("timeout_ms")
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or timeout_ms <= 0:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_request", "message": "timeout_ms must be a positive integer"}},
            )
            return
        entry = self._resolve_ppu_alias(alias)
        if entry is None:
            self._json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": {"code": "ppu_not_found", "message": "configured PPU alias was not found"}},
            )
            return
        relay_timeout_s = min(max(timeout_ms / 1000.0 + 1.0, self._config().request_timeout_s), 121.0)
        client = type(self).runtime_client_factory(entry.endpoint, self._config().request_timeout_s)
        started = time.monotonic()
        try:
            status, payload = client.ps_loopback(body, timeout_s=relay_timeout_s)
        except PPUTransportError:
            self._json(
                HTTPStatus.GATEWAY_TIMEOUT,
                {"ok": False, "error": {"code": "ppu_transport_error", "message": "PPU Runtime loopback transport failed"}},
            )
            return
        except PPUHTTPError:
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": {"code": "ppu_protocol_error", "message": "PPU Runtime loopback response was invalid"}},
            )
            return
        manager_rtt_ms = round((time.monotonic() - started) * 1000, 3)
        if status == HTTPStatus.OK and payload.get("ok") is True:
            payload = dict(payload)
            payload["manager"] = {
                "relay": "platform-maintenance",
                "context": "platform",
                "ppu_alias": alias,
                "manager_rtt_ms": manager_rtt_ms,
            }
        self._json(status, payload)

    def _bootstrap_post(self, alias: str, action: str) -> None:
        coordinator = self._bootstrap()
        try:
            body = self._read_json_object()
            if action == "pair":
                if set(body) != {"token"} or not isinstance(body.get("token"), str):
                    raise ValueError("Bootstrap pairing request requires only token")
                self._json(HTTPStatus.OK, coordinator.pair(alias, body["token"]))
                return
            if action == "ps-loopback":
                self._platform_ps_loopback(alias, body)
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
