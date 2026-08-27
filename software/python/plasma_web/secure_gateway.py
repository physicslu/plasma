from __future__ import annotations

import hashlib
import json
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError

from .gateway import PlasmaWebHandler as CanonicalPlasmaWebHandler
from .gateway_security import (
    CommandAdmission,
    GatewaySecurityController,
    Permission,
    Principal,
    ResourceRef,
)


_OPERATION_PERMISSIONS = {
    Operation.ERASE: Permission.PPU_ERASE,
    Operation.PROGRAM: Permission.PPU_PROGRAM,
    Operation.VERIFY: Permission.PPU_VERIFY,
    Operation.READ: Permission.PPU_READ,
}


class SecurePlasmaWebHandler(CanonicalPlasmaWebHandler):
    """Canonical Plasma REST Gateway with an explicit security boundary.

    This handler deliberately composes the existing canonical Gateway instead
    of reimplementing routes. Authentication/authorization happens before the
    inherited route is invoked, and state-changing requests are admitted through
    a durable idempotency ledger before they can reach a Batch runtime or PPU.

    Deployment wiring and browser identity integration are separate from this
    backend boundary. A SecurePlasmaWebHandler without a configured controller
    fails closed.
    """

    security_controller: GatewaySecurityController | None = None

    def _raw_body(self) -> bytes:
        cached = getattr(self, "_security_raw_body", None)
        if cached is not None:
            return cached
        raw = super()._raw_body()
        self._security_raw_body = raw
        return raw

    def _request_sha256(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.command.encode("ascii", "strict"))
        digest.update(b"\n")
        digest.update(self.path.encode("utf-8"))
        digest.update(b"\n")
        digest.update(self._raw_body())
        return digest.hexdigest()

    def _controller(self) -> GatewaySecurityController:
        controller = self.security_controller
        if controller is None:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "Secure Plasma Gateway has no authentication/authorization controller",
            )
        return controller

    def _principal(self) -> Principal:
        cached = getattr(self, "_security_principal", None)
        if cached is not None:
            return cached
        parsed = urlparse(self.path)
        principal = self._controller().authenticate(
            self.headers.get("Authorization"),
            method=self.command,
            path=parsed.path,
        )
        self._security_principal = principal
        return principal

    def _authorize(self, permission: Permission, resource: ResourceRef | None = None) -> Principal:
        principal = self._principal()
        parsed = urlparse(self.path)
        self._controller().authorize(
            principal,
            permission,
            method=self.command,
            path=parsed.path,
            resource=resource,
        )
        return principal

    @staticmethod
    def _resources_from_batch(snapshot: dict[str, Any]) -> tuple[ResourceRef, ...]:
        resources: list[ResourceRef] = []
        for site in snapshot.get("sites", []):
            if not isinstance(site, dict):
                continue
            facility_id = site.get("facility_id")
            ppu_id = site.get("ppu_id")
            site_id = site.get("site_id")
            if isinstance(facility_id, str) and isinstance(ppu_id, str) and isinstance(site_id, int):
                resources.append(ResourceRef(facility_id, ppu_id, site_id))
        return tuple(resources)

    @staticmethod
    def _resources_from_targets(raw_targets: Any) -> tuple[ResourceRef, ...]:
        if not isinstance(raw_targets, list):
            return ()
        resources: list[ResourceRef] = []
        for target in raw_targets:
            if not isinstance(target, dict):
                continue
            facility_id = target.get("facility_id")
            ppu_id = target.get("ppu_id")
            site_ids = target.get("site_ids")
            if not isinstance(facility_id, str) or not isinstance(ppu_id, str) or not isinstance(site_ids, list):
                continue
            for site_id in site_ids:
                if isinstance(site_id, int) and not isinstance(site_id, bool) and site_id >= 1:
                    resources.append(ResourceRef(facility_id, ppu_id, site_id))
        return tuple(resources)

    def _local_resource(self, site_id: int | None = None) -> ResourceRef:
        snapshot = self._local_snapshot()
        ppu = snapshot["ppu"]
        return ResourceRef(ppu_id=str(ppu["ppu_id"]), site_id=site_id)

    def _admit_command(
        self,
        permission: Permission,
        *,
        resources: tuple[ResourceRef, ...] = (),
    ) -> bool:
        principal = self._principal()
        parsed = urlparse(self.path)
        if resources:
            for resource in resources:
                self._controller().authorize(
                    principal,
                    permission,
                    method=self.command,
                    path=parsed.path,
                    resource=resource,
                )
        else:
            self._controller().authorize(
                principal,
                permission,
                method=self.command,
                path=parsed.path,
                resource=None,
            )
        admission = self._controller().admit_command(
            principal,
            permission=permission,
            command_id=self.headers.get("Idempotency-Key"),
            request_sha256=self._request_sha256(),
            method=self.command,
            path=parsed.path,
            resource=resources[0] if len(resources) == 1 else None,
        )
        if admission.replay:
            assert admission.replay_status is not None
            assert admission.replay_payload is not None
            super()._json(admission.replay_status, admission.replay_payload)
            return True
        self._security_active_command = admission
        return False

    def _authorize_operation(self, operation: Operation, resource: ResourceRef) -> None:
        self._authorize(_OPERATION_PERMISSIONS[operation], resource)

    def _guard_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/api/health/live", "/api/health/ready", "/api/node"}:
            return
        if path != "/api" and not path.startswith("/api/"):
            return
        if path == "/api/engineering/targets" or path == "/api/devices/search":
            self._authorize(Permission.CATALOG_READ)
            return
        if path == "/api/settings/gateway" or path == "/api/mock/runtime":
            self._authorize(Permission.SETTINGS_READ)
            return

        engineering = self._engineering_target(path)
        if engineering is not None:
            facility_id, ppu_id, tail = engineering
            resource = ResourceRef(facility_id, ppu_id)
            if tail == ["api", "status"]:
                query = parse_qs(parsed.query, keep_blank_values=True)
                site_values = query.get("site")
                site_id = None
                if site_values and len(site_values) == 1 and site_values[0].isdigit():
                    site_id = int(site_values[0])
                self._authorize(Permission.STATUS_READ, ResourceRef(facility_id, ppu_id, site_id))
                return
            if len(tail) == 5 and tail[:2] == ["api", "jobs"] and tail[3] == "files":
                self._authorize(Permission.JOB_OUTPUT_READ, resource)
                return

        if path == "/api/status":
            query = parse_qs(parsed.query, keep_blank_values=True)
            site_values = query.get("site")
            site_id = None
            if site_values and len(site_values) == 1 and site_values[0].isdigit():
                site_id = int(site_values[0])
            self._authorize(Permission.STATUS_READ, self._local_resource(site_id))
            return

        parts = path.split("/")
        if len(parts) == 6 and parts[1:3] == ["api", "jobs"] and parts[4] == "files":
            self._authorize(Permission.JOB_OUTPUT_READ, self._local_resource())
            return

        tail = self._batch_path(path)
        if tail is not None and len(tail) == 1 and self.batch_runtime is not None:
            snapshot = self.batch_runtime.get(tail[0])
            resources = self._resources_from_batch(snapshot)
            if resources:
                for resource in resources:
                    self._authorize(Permission.BATCH_READ, resource)
            else:
                self._authorize(Permission.BATCH_READ)

    def _guard_post(self) -> bool:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/settings/gateway":
            return self._admit_command(Permission.GATEWAY_SETTINGS_WRITE)
        if path == "/api/mock/runtime":
            return self._admit_command(Permission.MOCK_SETTINGS_WRITE)
        if path == "/api/engineering/session":
            return self._admit_command(Permission.ENGINEERING_SESSION_WRITE)

        engineering = self._engineering_target(path)
        if engineering is not None:
            facility_id, ppu_id, tail = engineering
            resource = ResourceRef(facility_id, ppu_id)
            if tail == ["api", "programming-assets", "check"]:
                self._authorize(Permission.PROGRAMMING_ASSET_READ, resource)
                return False
            if tail == ["api", "programming-assets"]:
                return self._admit_command(Permission.PROGRAMMING_ASSET_WRITE, resources=(resource,))
            if len(tail) == 4 and tail[:2] == ["api", "jobs"] and tail[3] == "cancel":
                return self._admit_command(Permission.JOB_CANCEL, resources=(resource,))
            if tail == ["api", "jobs"]:
                body = self._body()
                operation = Operation(str(body.get("operation")))
                site_id = body.get("site_id")
                site = site_id if isinstance(site_id, int) and not isinstance(site_id, bool) else None
                target = ResourceRef(facility_id, ppu_id, site)
                return self._admit_command(_OPERATION_PERMISSIONS[operation], resources=(target,))

        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            return self._admit_command(Permission.JOB_CANCEL, resources=(self._local_resource(),))
        if path == "/api/jobs":
            body = self._body()
            operation = Operation(str(body.get("operation")))
            site_id = body.get("site_id")
            site = site_id if isinstance(site_id, int) and not isinstance(site_id, bool) else None
            target = self._local_resource(site)
            return self._admit_command(_OPERATION_PERMISSIONS[operation], resources=(target,))

        tail = self._batch_path(path)
        if tail is None or self.batch_runtime is None:
            return False
        if not tail:
            body = self._body()
            resources = self._resources_from_targets(body.get("targets"))
            principal = self._principal()
            for resource in resources:
                self._controller().authorize(
                    principal,
                    Permission.BATCH_START,
                    method=self.command,
                    path=path,
                    resource=resource,
                )
            operations = body.get("operations")
            if isinstance(operations, list):
                for raw_operation in operations:
                    try:
                        permission = _OPERATION_PERMISSIONS[Operation(str(raw_operation))]
                    except (ValueError, KeyError):
                        continue
                    for resource in resources:
                        self._controller().authorize(
                            principal,
                            permission,
                            method=self.command,
                            path=path,
                            resource=resource,
                        )
            return self._admit_command(Permission.BATCH_START, resources=resources)
        if len(tail) == 2 and tail[1] == "cancel":
            snapshot = self.batch_runtime.get(tail[0])
            return self._admit_command(
                Permission.BATCH_CANCEL,
                resources=self._resources_from_batch(snapshot),
            )
        if len(tail) == 5 and tail[1] == "targets" and tail[4] == "cancel":
            return self._admit_command(
                Permission.BATCH_CANCEL,
                resources=(ResourceRef(tail[2], tail[3]),),
            )
        return False

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        admission: CommandAdmission | None = getattr(self, "_security_active_command", None)
        if admission is not None:
            self._security_active_command = None
            controller = self._controller()
            controller.store.complete_command(admission, http_status=int(status), response=payload)
            controller.store.audit(
                principal_id=admission.principal_id,
                decision="completed",
                action="command.complete",
                method=self.command,
                path=urlparse(self.path).path,
                resource=None,
                command_id=admission.command_id,
                detail={"http_status": int(status)},
            )
        super()._json(status, payload)

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, PlasmaError):
            status_by_code = {
                ErrorCode.AUTHENTICATION_REQUIRED: HTTPStatus.UNAUTHORIZED,
                ErrorCode.AUTHORIZATION_DENIED: HTTPStatus.FORBIDDEN,
                ErrorCode.COMMAND_REPLAY_CONFLICT: HTTPStatus.CONFLICT,
                ErrorCode.COMMAND_IN_PROGRESS: HTTPStatus.CONFLICT,
            }
            status = status_by_code.get(exc.code)
            if status is not None:
                self._json(
                    status,
                    {
                        "ok": False,
                        "error": {
                            "error_code": exc.code.value,
                            "error_type": exc.error_type,
                            "message": exc.message,
                            "recoverable": exc.recoverable,
                            "context": dict(exc.context),
                        },
                    },
                )
                return
        super()._error(exc)

    def do_GET(self) -> None:
        try:
            self._guard_get()
        except Exception as exc:
            self._error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        try:
            if self._guard_post():
                return
        except Exception as exc:
            self._error(exc)
            return
        super().do_POST()
