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
    ControllerReplacedError,
    ManagerBootstrapCoordinator,
)
from .client import PPUHTTPError, PPUHttpClient, PPUTransportError
from .programming import BundleProgrammingWorkflow, ProgrammingError
from .programming_batch import ProgrammingBatchCoordinator
from .registry import RegistryEntryNotFound
from .verified_bootstrap import VerifiedManagerBootstrapCoordinator

BOOTSTRAP_ROUTE_RE = re.compile(r"^/api/registry/([^/]+)/bootstrap(?:/(.*))?$")
UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")
PROGRAMMING_RUN_RE = re.compile(r"^programming/runs/([0-9a-f]{32})$")
PROGRAMMING_OUTPUT_RE = re.compile(r"^programming/runs/([0-9a-f]{32})/output$")
PROGRAMMING_BATCH_RE = re.compile(r"^programming/batches/([0-9a-f]{32})$")
PROGRAMMING_BATCH_STOP_RE = re.compile(r"^programming/batches/([0-9a-f]{32})/stop$")
PROGRAMMING_ACK_RE = re.compile(r"^programming/runs/([0-9a-f]{32})/acknowledge$")
PROGRAMMING_START_RE = re.compile(r"^programming/starts/([0-9a-f]{32})$")
PROGRAMMING_START_VOID_RE = re.compile(r"^programming/starts/([0-9a-f]{32})/void$")


class BootstrapPlasmaManagerHandler(base_server.PlasmaManagerHandler):
    """Current Manager handler plus the independent PPU Bootstrap policy surface.

    This subclasses the current Manager rather than copying it. Registry, fleet,
    network commissioning and managed Gateway routing therefore remain owned by
    ``plasma_manager.server`` and evolve with that implementation.
    """

    bootstrap_coordinator: ManagerBootstrapCoordinator | None = None
    programming_workflow: BundleProgrammingWorkflow | None = None
    programming_batches: ProgrammingBatchCoordinator | None = None
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
            if self.network_commissioning is not None:
                self.network_commissioning.write_signer_for = cls.bootstrap_coordinator.gateway_signer
            return cls.bootstrap_coordinator

    def _programming(self) -> BundleProgrammingWorkflow:
        cls = type(self)
        if cls.programming_workflow is not None:
            return cls.programming_workflow
        with cls._bootstrap_init_lock:
            if cls.programming_workflow is None:
                config = self._config()
                journal = (config.registry_state_path.with_name("bundle-programming-runs.json")
                           if config.registry_state_path is not None else None)
                cls.programming_workflow = BundleProgrammingWorkflow(
                    coordinator=self._bootstrap(),
                    registry=self.registry_store,
                    gateway_client_factory=cls.runtime_client_factory,
                    gate=self._operation_gate(),
                    request_timeout_s=config.request_timeout_s,
                    journal_path=journal,
                )
            return cls.programming_workflow

    def _batches(self) -> ProgrammingBatchCoordinator:
        cls = type(self)
        if cls.programming_batches is not None:
            return cls.programming_batches
        workflow = self._programming()
        with cls._bootstrap_init_lock:
            if cls.programming_batches is None:
                config = self._config()
                journal = (config.registry_state_path.with_name("programming-batches.json")
                           if config.registry_state_path is not None else None)
                cls.programming_batches = ProgrammingBatchCoordinator(
                    workflow, journal_path=journal)
            return cls.programming_batches

    def _programming_call(self, call) -> None:
        try:
            status, payload = call()
        except ProgrammingError as exc:
            self._json(exc.status, exc.payload())
            return
        except Exception as exc:
            self._bootstrap_error(exc)
            return
        self._json(status, payload)

    def _ppu_client(self, alias: str, endpoint: str) -> PPUHttpClient:
        client = type(self).runtime_client_factory(endpoint, self._config().request_timeout_s)
        try:
            signer = getattr(self._bootstrap(), "gateway_signer", None)
        except BootstrapManagerError:
            signer = None          # unsigned writes are refused by a G13 PPU (fail closed)
        if signer is not None:
            client.write_signer = signer(alias)
        return client

    def _ppu_write_error(self, exc: Exception) -> bool:
        if isinstance(exc, (BootstrapManagerError, RegistryEntryNotFound)):
            self._bootstrap_error(exc)
            return True
        return False

    def _bootstrap_error(self, exc: Exception) -> None:
        if isinstance(exc, RegistryEntryNotFound):
            status = HTTPStatus.NOT_FOUND
            code = "ppu_not_found"
        elif isinstance(exc, ControllerReplacedError):
            status = HTTPStatus.CONFLICT
            code = "controller_replaced"
        elif isinstance(exc, BootstrapCredentialError):
            status = HTTPStatus.CONFLICT
            code = "controller_enrollment_required"
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

    def _platform_write_block(self, alias: str) -> tuple[str, str] | None:
        # Programming Registration remains independent, but managed writes must
        # not race a Platform deployment. Bootstrap deployment API state is
        # durable on the PPU, so this also survives a Manager restart.
        try:
            platform = self._bootstrap().status(alias)
        except Exception:
            # Bootstrap availability is not a normal programming prerequisite.
            # The process-local operation gate still closes the launch race;
            # ordinary Runtime writes are allowed when no durable state can be
            # observed here.
            return None
        bootstrap = platform.get("bootstrap")
        if not isinstance(bootstrap, dict):
            return None
        deployment = bootstrap.get("deployment")
        deployment_state = deployment.get("state") if isinstance(deployment, dict) else None
        runtime = bootstrap.get("runtime")
        runtime_state = runtime.get("state") if isinstance(runtime, dict) else None
        if deployment_state in {"queued", "running"}:
            return (
                "ppu_platform_maintenance_active",
                "Platform deployment is active; managed PPU writes are temporarily blocked",
            )
        if deployment_state == "recovery_required" or runtime_state == "recovery_required":
            return (
                "ppu_platform_recovery_required",
                "Platform recovery is required before managed PPU writes may resume",
            )
        return None

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
        if action == "programming/routes":
            self._programming_call(lambda: (HTTPStatus.OK, self._programming().list_routes()))
            return
        run_match = PROGRAMMING_RUN_RE.fullmatch(action)
        if run_match is not None:
            run_id = run_match.group(1)
            self._programming_call(
                lambda: (HTTPStatus.OK, self._programming().run_status(alias, run_id)))
            return
        batch_match = PROGRAMMING_BATCH_RE.fullmatch(action)
        if batch_match is not None:
            batch_id = batch_match.group(1)
            self._programming_call(
                lambda: (HTTPStatus.OK, self._batches().status(alias, batch_id)))
            return
        start_match = PROGRAMMING_START_RE.fullmatch(action)
        if start_match is not None:
            # Start Outcome Reconciliation: read-only, journal and memory only.
            start_id = start_match.group(1)
            self._programming_call(
                lambda: (HTTPStatus.OK, self._batches().reconcile_start(alias, start_id)))
            return
        output_match = PROGRAMMING_OUTPUT_RE.fullmatch(action)
        if output_match is not None:
            # Read Memory binary: Console -> BFF -> Manager only; the Manager
            # re-hashes the retained bytes against the run receipt first.
            try:
                data, output = self._programming().read_output(alias, output_match.group(1))
            except ProgrammingError as exc:
                self._json(exc.status, exc.payload())
                return
            except Exception as exc:
                self._bootstrap_error(exc)
                return
            # _raw_response is the only Content-Length producer; a second one
            # here made Node.js fetch reject the response (duplicate header).
            self._raw_response(HTTPStatus.OK, {
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f'attachment; filename="{output["filename"]}"',
                "X-Plasma-Read-Sha256": str(output["sha256"]),
                "X-Content-Type-Options": "nosniff",
            }, data)
            return
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
        client = self._ppu_client(alias, entry.endpoint)
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

    def _platform_openocd_control_plane(self, alias: str, body: dict[str, Any]) -> None:
        try:
            platform = self._bootstrap().status(alias)
        except Exception as exc:
            self._bootstrap_error(exc)
            return
        pairing = platform.get("pairing")
        if not isinstance(pairing, dict) or pairing.get("paired") is not True or pairing.get("device_match") is not True:
            self._bootstrap_error(
                BootstrapCredentialError(
                    "Platform maintenance pairing is required before OpenOCD Control Plane Test"
                )
            )
            return
        if set(body) != {"site_id", "timeout_ms"}:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_request",
                        "message": "OpenOCD Control Plane Test requires only site_id and timeout_ms",
                    },
                },
            )
            return
        site_id = body.get("site_id")
        timeout_ms = body.get("timeout_ms")
        if isinstance(site_id, bool) or not isinstance(site_id, int) or site_id < 1:
            self._json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_request", "message": "site_id must be a positive integer"}},
            )
            return
        if (
            isinstance(timeout_ms, bool)
            or not isinstance(timeout_ms, int)
            or timeout_ms < 100
            or timeout_ms > 30_000
        ):
            self._json(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_request",
                        "message": "timeout_ms must be between 100 and 30000",
                    },
                },
            )
            return
        entry = self._resolve_ppu_alias(alias)
        if entry is None:
            self._json(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": {"code": "ppu_not_found", "message": "configured PPU alias was not found"}},
            )
            return
        relay_timeout_s = min(max(timeout_ms / 1000.0 + 2.0, self._config().request_timeout_s), 35.0)
        client = self._ppu_client(alias, entry.endpoint)
        started = time.monotonic()
        try:
            status, payload = client.openocd_control_plane(body, timeout_s=relay_timeout_s)
        except PPUTransportError:
            self._json(
                HTTPStatus.GATEWAY_TIMEOUT,
                {"ok": False, "error": {"code": "ppu_transport_error", "message": "PPU OpenOCD diagnostic transport failed"}},
            )
            return
        except PPUHTTPError:
            self._json(
                HTTPStatus.BAD_GATEWAY,
                {"ok": False, "error": {"code": "ppu_protocol_error", "message": "PPU OpenOCD diagnostic response was invalid"}},
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
            if action == "enrollment":
                # LOM-P2A-2: button (start/claim) or engineering/SD ticket claim.
                result = coordinator.enrollment(alias, body)
                if not result.get("ok"):
                    result = {**result, "error": {
                        "code": result.get("state") or "enrollment_failed",
                        "message": "PPU enrollment did not complete; nothing was changed by this Manager",
                    }}
                self._json(HTTPStatus.OK if result.get("ok") else HTTPStatus.CONFLICT, result)
                return
            if action == "recovery":
                status, payload = coordinator.recovery_action(alias, body)
                self._json(status, payload)
                return
            if action == "deployment/reconcile":
                # P0: explicit close of one already-activated Runtime transaction.
                # Exclusive with every other Manager-launched PPU write.
                entry = self._resolve_ppu_alias(alias)
                if entry is None:
                    self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": {
                        "code": "ppu_not_found", "message": "configured PPU alias was not found"}})
                    return
                gate = self._operation_gate()
                if not gate.try_begin_platform_launch(alias):
                    self._json(HTTPStatus.CONFLICT, {"ok": False, "error": {
                        "code": "ppu_control_plane_busy",
                        "message": "another managed PPU write or Platform launch is in progress"}})
                    return
                try:
                    if self._alias_has_active_execution(alias):
                        self._json(HTTPStatus.CONFLICT, {"ok": False, "error": {
                            "code": "ppu_busy", "message": "active PPU Jobs must finish first"}})
                        return
                    status, payload = coordinator.reconcile_runtime_deployment(
                        alias, body, self._ppu_client(alias, entry.endpoint))
                    self._json(status, payload)
                    return
                finally:
                    gate.end_platform_launch(alias)
            if action == "programming/plans":
                self._programming_call(
                    lambda: (HTTPStatus.OK, self._programming().plan(alias, body)))
                return
            if action == "programming/runs":
                # Same Platform safety gate as manual B2/B3 (idle, no recovery).
                if not self._bootstrap_mutation_allowed(alias):
                    return
                self._programming_call(
                    lambda: (HTTPStatus.ACCEPTED, self._programming().start(alias, body)))
                return
            if action == "programming/batches":
                # A Batch submits Jobs: same Platform safety gate as a single run.
                if not self._bootstrap_mutation_allowed(alias):
                    return
                self._programming_call(
                    lambda: (HTTPStatus.ACCEPTED, self._batches().start(alias, body)))
                return
            if action == "programming/starts":
                # Issues a start ID only: nothing is planned, queued or submitted.
                self._programming_call(
                    lambda: (HTTPStatus.OK, self._programming().issue_batch_start(alias, body)))
                return
            void_match = PROGRAMMING_START_VOID_RE.fullmatch(action)
            if void_match is not None:
                # Drops an unconsumed plan / start ID; refuses an admitted start.
                start_id = void_match.group(1)
                self._programming_call(
                    lambda: (HTTPStatus.OK, self._programming().void_start(alias, start_id, body)))
                return
            stop_match = PROGRAMMING_BATCH_STOP_RE.fullmatch(action)
            if stop_match is not None:
                # Stop queuing only: allowed in any Platform state, changes nothing on the PPU.
                batch_id = stop_match.group(1)
                self._programming_call(
                    lambda: (HTTPStatus.OK, self._batches().request_stop(alias, batch_id, body)))
                return
            ack_match = PROGRAMMING_ACK_RE.fullmatch(action)
            if ack_match is not None:
                run_id = ack_match.group(1)
                self._programming_call(
                    lambda: (HTTPStatus.OK, self._programming().acknowledge(alias, run_id, body)))
                return
            if action == "ps-loopback":
                self._platform_ps_loopback(alias, body)
                return
            if action == "openocd-control-plane":
                self._platform_openocd_control_plane(alias, body)
                return
            if action == "deployments":
                gate = self._operation_gate()
                if not gate.try_begin_platform_launch(alias):
                    self._json(
                        HTTPStatus.CONFLICT,
                        {
                            "ok": False,
                            "error": {
                                "code": "ppu_control_plane_busy",
                                "message": (
                                    "a managed PPU write or another Platform deployment launch "
                                    "is already in progress"
                                ),
                            },
                        },
                    )
                    return
                try:
                    if not self._bootstrap_mutation_allowed(alias):
                        return
                    status, payload = coordinator.start_deployment(alias, body)
                    self._json(status, payload)
                    return
                finally:
                    gate.end_platform_launch(alias)
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
