from __future__ import annotations

import hashlib
from http import HTTPStatus
from typing import Any
from urllib.parse import parse_qs, urlparse

from plasma_core.enums import Operation
from plasma_core.errors import ErrorCode, PlasmaError

from . import gateway_base as base
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

    Authentication happens before protected control-plane/PPU state is looked
    up. Authorization then checks the exact Facility/PPU/Site whenever the Job
    or Batch identity can resolve it. State-changing requests pass through the
    durable idempotency ledger before the inherited canonical route executes.
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
        self._controller().authorize(
            principal,
            permission,
            method=self.command,
            path=urlparse(self.path).path,
            resource=resource,
        )
        return principal

    @staticmethod
    def _filtered_status_payload(
        payload: dict[str, Any],
        principal: Principal,
        facility_id: str,
        ppu_id: str,
    ) -> dict[str, Any]:
        sites = payload.get("sites")
        if not isinstance(sites, list):
            return payload
        visible_sites: list[dict[str, Any]] = []
        for site in sites:
            if not isinstance(site, dict):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Status response contains an invalid Site resource")
            raw_site_id = site.get("site_id")
            try:
                site_id = base._parse_site_id(raw_site_id)
            except ValueError as exc:
                raise PlasmaError(
                    ErrorCode.CONFIG_INVALID,
                    "Status response contains an invalid Site identity",
                    original_exception=exc,
                ) from exc
            if principal.allows(
                Permission.STATUS_READ,
                ResourceRef(facility_id, ppu_id, site_id),
            ):
                visible_sites.append(site)
        filtered = dict(payload)
        filtered["sites"] = visible_sites
        ppu = filtered.get("ppu")
        if isinstance(ppu, dict):
            visible_ppu = dict(ppu)
            if "site_count" in visible_ppu:
                visible_ppu["site_count"] = len(visible_sites)
            if "enabled_site_count" in visible_ppu:
                visible_ppu["enabled_site_count"] = sum(
                    1 for site in visible_sites if site.get("enabled") is True
                )
            filtered["ppu"] = visible_ppu
        return filtered

    @staticmethod
    def _filtered_engineering_catalog(
        payload: dict[str, Any],
        principal: Principal,
    ) -> dict[str, Any]:
        facilities = payload.get("facilities")
        if not isinstance(facilities, list):
            return payload
        visible_facilities: list[dict[str, Any]] = []
        visible_ppu_count = 0
        visible_site_count = 0
        for facility in facilities:
            if not isinstance(facility, dict):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Engineering catalog contains an invalid Facility")
            facility_id = facility.get("facility_id")
            ppus = facility.get("ppus")
            if not isinstance(facility_id, str) or not facility_id or not isinstance(ppus, list):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Engineering catalog contains an invalid Facility identity")
            visible_ppus: list[dict[str, Any]] = []
            for ppu in ppus:
                if not isinstance(ppu, dict):
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "Engineering catalog contains an invalid PPU")
                ppu_id = ppu.get("ppu_id")
                if not isinstance(ppu_id, str) or not ppu_id:
                    raise PlasmaError(ErrorCode.CONFIG_INVALID, "Engineering catalog contains an invalid PPU identity")
                if principal.allows(
                    Permission.CATALOG_READ,
                    ResourceRef(facility_id, ppu_id),
                ):
                    visible_ppus.append(ppu)
                    raw_site_count = ppu.get("site_count", 0)
                    if isinstance(raw_site_count, int) and not isinstance(raw_site_count, bool) and raw_site_count >= 0:
                        visible_site_count += raw_site_count
            if visible_ppus:
                visible_facility = dict(facility)
                visible_facility["ppus"] = visible_ppus
                visible_facilities.append(visible_facility)
                visible_ppu_count += len(visible_ppus)
        filtered = dict(payload)
        filtered["facilities"] = visible_facilities
        if "facility_count" in filtered:
            filtered["facility_count"] = len(visible_facilities)
        if "ppu_count" in filtered:
            filtered["ppu_count"] = visible_ppu_count
        if "site_count" in filtered:
            filtered["site_count"] = visible_site_count
        return filtered

    @staticmethod
    def _resources_from_batch(snapshot: dict[str, Any]) -> tuple[ResourceRef, ...]:
        sites = snapshot.get("sites")
        if not isinstance(sites, list) or not sites:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Batch snapshot has no resolvable Site resources")
        resources: list[ResourceRef] = []
        for site in sites:
            if not isinstance(site, dict):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Batch snapshot contains an invalid Site resource")
            facility_id = site.get("facility_id")
            ppu_id = site.get("ppu_id")
            site_id = site.get("site_id")
            if (
                not isinstance(facility_id, str)
                or not facility_id
                or not isinstance(ppu_id, str)
                or not ppu_id
                or isinstance(site_id, bool)
                or not isinstance(site_id, int)
                or site_id < 1
            ):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Batch snapshot contains an invalid Site identity")
            resources.append(ResourceRef(facility_id, ppu_id, site_id))
        return tuple(resources)

    @staticmethod
    def _resources_from_targets(raw_targets: Any) -> tuple[ResourceRef, ...]:
        if not isinstance(raw_targets, list) or not raw_targets:
            raise ValueError("Batch targets must be a non-empty array")
        resources: list[ResourceRef] = []
        for index, raw in enumerate(raw_targets):
            if not isinstance(raw, dict):
                raise ValueError(f"Batch target {index} must be an object")
            base._require_declared_keys(
                raw,
                allowed={"facility_id", "ppu_id", "site_ids"},
                required={"facility_id", "ppu_id", "site_ids"},
                label=f"Batch target {index}",
            )
            site_ids = raw["site_ids"]
            if not isinstance(site_ids, list) or not site_ids:
                raise ValueError(f"Batch target {index} site_ids must be a non-empty array")
            facility_id = str(raw["facility_id"])
            ppu_id = str(raw["ppu_id"])
            for raw_site_id in site_ids:
                resources.append(
                    ResourceRef(
                        facility_id=facility_id,
                        ppu_id=ppu_id,
                        site_id=base._parse_site_id(raw_site_id),
                    )
                )
        return tuple(resources)

    @staticmethod
    def _job_site_id(payload: dict[str, Any]) -> int:
        job = payload.get("job")
        if not isinstance(job, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Job lookup did not return a Job object")
        site_id = job.get("site_id")
        if isinstance(site_id, bool) or not isinstance(site_id, int) or site_id < 1:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Job lookup did not return a valid Site identity")
        return site_id

    def _local_resource(self, site_id: int | None = None) -> ResourceRef:
        snapshot = self._local_snapshot()
        ppu = snapshot["ppu"]
        return ResourceRef(
            facility_id=str(ppu["facility_id"]),
            ppu_id=str(ppu["ppu_id"]),
            site_id=site_id,
        )

    def _local_job_resource(self, job_id: str) -> ResourceRef:
        self._principal()  # Authentication must precede any PPU lookup.
        payload = base._run(self.client_factory().status(job_id=job_id))
        local = self._local_resource(self._job_site_id(payload))
        return local

    def _engineering_job_resource(self, facility_id: str, ppu_id: str, job_id: str) -> ResourceRef:
        self._principal()  # Authentication must precede any Provider/PPU lookup.
        if self.engineering_provider is None:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Engineering Provider is not enabled")
        payload = base._run(
            self.engineering_provider.status(
                facility_id,
                ppu_id,
                job_id=job_id,
            )
        )
        return ResourceRef(facility_id, ppu_id, self._job_site_id(payload))

    def _admit_command(
        self,
        permission: Permission,
        *,
        resources: tuple[ResourceRef, ...] = (),
    ) -> bool:
        principal = self._principal()
        parsed = urlparse(self.path)
        for resource in resources:
            self._controller().authorize(
                principal,
                permission,
                method=self.command,
                path=parsed.path,
                resource=resource,
            )
        if not resources:
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

    def _deny_unclassified_api_route(self, path: str) -> None:
        principal = self._principal()
        raise PlasmaError(
            ErrorCode.AUTHORIZATION_DENIED,
            "Secure Gateway has no authorization rule for this API route",
            context={"principal_id": principal.principal_id, "path": path},
        )

    def _guard_get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/api/health/live", "/api/health/ready", "/api/node"}:
            return
        if path != "/api" and not path.startswith("/api/"):
            return
        if path == "/api/engineering/targets":
            self._authorize(Permission.CATALOG_READ)
            self._security_filter_engineering_catalog = True
            return
        if path == "/api/devices/search":
            self._authorize(Permission.CATALOG_READ)
            return
        if path in {"/api/settings/gateway", "/api/settings/ppu-network", "/api/mock/runtime"}:
            self._authorize(Permission.SETTINGS_READ)
            return

        engineering = self._engineering_target(path)
        if engineering is not None:
            facility_id, ppu_id, tail = engineering
            if tail == ["api", "status"]:
                principal = self._principal()
                query = parse_qs(parsed.query, keep_blank_values=True)
                base._require_declared_keys(query, allowed={"job", "site"}, label="status query")
                job = base._query_value(query, "job")
                site = base._query_value(query, "site")
                if job is not None:
                    resource = self._engineering_job_resource(facility_id, ppu_id, job)
                else:
                    site_id = base._parse_site_id(site) if site is not None else None
                    resource = ResourceRef(facility_id, ppu_id, site_id)
                self._controller().authorize(
                    principal,
                    Permission.STATUS_READ,
                    method=self.command,
                    path=path,
                    resource=resource,
                )
                self._security_status_scope = (principal, facility_id, ppu_id)
                return
            if len(tail) == 5 and tail[:2] == ["api", "jobs"] and tail[3] == "files":
                resource = self._engineering_job_resource(facility_id, ppu_id, tail[2])
                self._authorize(Permission.JOB_OUTPUT_READ, resource)
                return

        if path == "/api/status":
            principal = self._principal()
            query = parse_qs(parsed.query, keep_blank_values=True)
            base._require_declared_keys(query, allowed={"job", "site"}, label="status query")
            job = base._query_value(query, "job")
            site = base._query_value(query, "site")
            if job is not None:
                resource = self._local_job_resource(job)
            else:
                site_id = base._parse_site_id(site) if site is not None else None
                resource = self._local_resource(site_id)
            self._controller().authorize(
                principal,
                Permission.STATUS_READ,
                method=self.command,
                path=path,
                resource=resource,
            )
            if resource.facility_id is None or resource.ppu_id is None:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Local status resource identity is incomplete")
            self._security_status_scope = (principal, resource.facility_id, resource.ppu_id)
            return

        parts = path.split("/")
        if len(parts) == 6 and parts[1:3] == ["api", "jobs"] and parts[4] == "files":
            self._authorize(Permission.JOB_OUTPUT_READ, self._local_job_resource(parts[3]))
            return

        tail = self._batch_path(path)
        if tail is not None:
            if self.batch_runtime is None:
                self._principal()
                return
            if len(tail) == 1:
                principal = self._principal()
                snapshot = self.batch_runtime.get(tail[0])
                resources = self._resources_from_batch(snapshot)
                for resource in resources:
                    self._controller().authorize(
                        principal,
                        Permission.BATCH_READ,
                        method=self.command,
                        path=path,
                        resource=resource,
                    )
                return

        self._deny_unclassified_api_route(path)

    def _guard_post(self) -> bool:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/engineering/diagnostics/loopback":
            self._principal()  # Authenticate before the local PPU identity lookup.
            self._authorize(Permission.STATUS_READ, self._local_resource())
            return False
        if path == "/api/settings/gateway":
            return self._admit_command(Permission.GATEWAY_SETTINGS_WRITE)
        if path == "/api/settings/ppu-network":
            return self._admit_command(Permission.PPU_NETWORK_SETTINGS_WRITE)
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
                job_resource = self._engineering_job_resource(facility_id, ppu_id, tail[2])
                return self._admit_command(Permission.JOB_CANCEL, resources=(job_resource,))
            if tail == ["api", "jobs"]:
                body = self._body()
                operation = Operation(str(body.get("operation")))
                site = base._parse_site_id(body.get("site_id"))
                target = ResourceRef(facility_id, ppu_id, site)
                return self._admit_command(_OPERATION_PERMISSIONS[operation], resources=(target,))

        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            job_id = path.split("/")[3]
            return self._admit_command(
                Permission.JOB_CANCEL,
                resources=(self._local_job_resource(job_id),),
            )
        if path == "/api/jobs":
            self._principal()
            body = self._body()
            operation = Operation(str(body.get("operation")))
            site = base._parse_site_id(body.get("site_id"))
            return self._admit_command(
                _OPERATION_PERMISSIONS[operation],
                resources=(self._local_resource(site),),
            )

        tail = self._batch_path(path)
        if tail is None:
            if path == "/api" or path.startswith("/api/"):
                self._deny_unclassified_api_route(path)
            return False
        if self.batch_runtime is None:
            self._principal()
            return False
        if not tail:
            self._principal()
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
            if not isinstance(operations, list):
                raise ValueError("Batch operations must be an array")
            for raw_operation in operations:
                permission = _OPERATION_PERMISSIONS[Operation(str(raw_operation))]
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
            self._principal()
            snapshot = self.batch_runtime.get(tail[0])
            return self._admit_command(
                Permission.BATCH_CANCEL,
                resources=self._resources_from_batch(snapshot),
            )
        if len(tail) == 5 and tail[1] == "targets" and tail[4] == "cancel":
            self._principal()
            snapshot = self.batch_runtime.get(tail[0])
            resources = tuple(
                resource
                for resource in self._resources_from_batch(snapshot)
                if resource.facility_id == tail[2] and resource.ppu_id == tail[3]
            )
            if not resources:
                resources = (ResourceRef(tail[2], tail[3]),)
            return self._admit_command(Permission.BATCH_CANCEL, resources=resources)
        self._deny_unclassified_api_route(path)
        return False

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        if int(status) == int(HTTPStatus.OK):
            status_scope = getattr(self, "_security_status_scope", None)
            if status_scope is not None:
                principal, facility_id, ppu_id = status_scope
                payload = self._filtered_status_payload(payload, principal, facility_id, ppu_id)
            if getattr(self, "_security_filter_engineering_catalog", False):
                payload = self._filtered_engineering_catalog(payload, self._principal())

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
                if exc.code is ErrorCode.AUTHENTICATION_REQUIRED:
                    base._gateway_diagnostic(
                        "security_authentication_failed",
                        method=self.command,
                        path=urlparse(self.path).path,
                    )
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
