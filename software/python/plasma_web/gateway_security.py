from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

import yaml

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_core.models import iso_now


SECURITY_CONFIG_VERSION = 1
SECURITY_STATE_SCHEMA_VERSION = 1
_TOKEN_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COMMAND_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class Permission(StrEnum):
    STATUS_READ = "status.read"
    BATCH_READ = "batch.read"
    CATALOG_READ = "catalog.read"
    SETTINGS_READ = "settings.read"
    PROGRAMMING_ASSET_READ = "programming_asset.read"
    JOB_OUTPUT_READ = "job.output.read"

    BATCH_START = "batch.start"
    BATCH_CANCEL = "batch.cancel"
    JOB_CANCEL = "job.cancel"
    PPU_ERASE = "ppu.erase"
    PPU_PROGRAM = "ppu.program"
    PPU_VERIFY = "ppu.verify"
    PPU_READ = "ppu.read"
    PROGRAMMING_ASSET_WRITE = "programming_asset.write"
    ENGINEERING_SESSION_WRITE = "engineering.session.write"
    GATEWAY_SETTINGS_WRITE = "settings.gateway.write"
    PPU_NETWORK_SETTINGS_WRITE = "settings.ppu_network.write"
    MOCK_SETTINGS_WRITE = "settings.mock.write"


VIEWER_PERMISSIONS = frozenset(
    {
        Permission.STATUS_READ,
        Permission.BATCH_READ,
        Permission.CATALOG_READ,
        Permission.SETTINGS_READ,
        Permission.PROGRAMMING_ASSET_READ,
    }
)
OPERATOR_PERMISSIONS = VIEWER_PERMISSIONS | frozenset(
    {
        Permission.BATCH_START,
        Permission.BATCH_CANCEL,
        Permission.JOB_CANCEL,
        Permission.PPU_ERASE,
        Permission.PPU_PROGRAM,
        Permission.PPU_VERIFY,
        Permission.PPU_READ,
        Permission.PROGRAMMING_ASSET_WRITE,
        Permission.ENGINEERING_SESSION_WRITE,
        Permission.JOB_OUTPUT_READ,
    }
)
ENGINEER_PERMISSIONS = OPERATOR_PERMISSIONS | frozenset({Permission.MOCK_SETTINGS_WRITE})
ADMIN_PERMISSIONS = ENGINEER_PERMISSIONS | frozenset(
    {
        Permission.GATEWAY_SETTINGS_WRITE,
        Permission.PPU_NETWORK_SETTINGS_WRITE,
    }
)
SERVICE_PERMISSIONS = frozenset(
    {
        Permission.STATUS_READ,
        Permission.BATCH_READ,
        Permission.BATCH_START,
        Permission.BATCH_CANCEL,
        Permission.PPU_ERASE,
        Permission.PPU_PROGRAM,
        Permission.PPU_VERIFY,
        Permission.PPU_READ,
        Permission.PROGRAMMING_ASSET_READ,
        Permission.PROGRAMMING_ASSET_WRITE,
    }
)
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    "viewer": VIEWER_PERMISSIONS,
    "operator": OPERATOR_PERMISSIONS,
    "engineer": ENGINEER_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
    "service": SERVICE_PERMISSIONS,
}


@dataclass(frozen=True, slots=True)
class ResourceRef:
    facility_id: str | None = None
    ppu_id: str | None = None
    site_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "facility_id": self.facility_id,
                "ppu_id": self.ppu_id,
                "site_id": self.site_id,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class ResourceScope:
    facility_id: str = "*"
    ppu_id: str = "*"
    site_ids: frozenset[int] | None = None

    def matches(self, resource: ResourceRef) -> bool:
        if resource.facility_id is not None and self.facility_id not in {"*", resource.facility_id}:
            return False
        if resource.ppu_id is not None and self.ppu_id not in {"*", resource.ppu_id}:
            return False
        if resource.site_id is not None and self.site_ids is not None and resource.site_id not in self.site_ids:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "facility_id": self.facility_id,
            "ppu_id": self.ppu_id,
            "site_ids": "*" if self.site_ids is None else sorted(self.site_ids),
        }


@dataclass(frozen=True, slots=True)
class Principal:
    principal_id: str
    roles: tuple[str, ...]
    permissions: frozenset[Permission]
    scopes: tuple[ResourceScope, ...]
    token_sha256: str

    def allows(self, permission: Permission, resource: ResourceRef | None = None) -> bool:
        if permission not in self.permissions:
            return False
        return resource is None or any(scope.matches(resource) for scope in self.scopes)


@dataclass(frozen=True, slots=True)
class CommandAdmission:
    principal_id: str
    command_id: str
    request_sha256: str
    replay_status: int | None = None
    replay_payload: dict[str, Any] | None = None

    @property
    def replay(self) -> bool:
        return self.replay_status is not None and self.replay_payload is not None


class GatewaySecurityConfig:
    def __init__(self, principals: Iterable[Principal]) -> None:
        normalized = tuple(principals)
        if not normalized:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security config requires at least one principal")
        if len({p.principal_id for p in normalized}) != len(normalized):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security principal IDs must be unique")
        if len({p.token_sha256 for p in normalized}) != len(normalized):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security token digests must be unique")
        self.principals = normalized

    @classmethod
    def load(cls, path: str | Path) -> "GatewaySecurityConfig":
        source = Path(path).expanduser().resolve()
        try:
            raw = yaml.safe_load(source.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"cannot load Gateway security config: {source}",
                original_exception=exc,
            ) from exc
        if not isinstance(raw, dict) or set(raw) != {"version", "principals"}:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security config fields are invalid")
        if raw["version"] != SECURITY_CONFIG_VERSION:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "Unsupported Gateway security config version",
                context={"expected": SECURITY_CONFIG_VERSION, "actual": raw["version"]},
            )
        entries = raw["principals"]
        if not isinstance(entries, list) or not entries:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security principals must be a non-empty array")
        return cls(cls._principal(entry, index) for index, entry in enumerate(entries))

    @staticmethod
    def _principal(raw: Any, index: int) -> Principal:
        if not isinstance(raw, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {index} must be an object")
        allowed = {"id", "token_sha256", "roles", "permissions", "scopes"}
        required = {"id", "token_sha256", "scopes"}
        if not required <= set(raw) or set(raw) - allowed:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {index} fields are invalid")
        principal_id = raw["id"]
        token_sha256 = raw["token_sha256"]
        if not isinstance(principal_id, str) or not principal_id or len(principal_id) > 128:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {index} id is invalid")
        if not isinstance(token_sha256, str) or not _TOKEN_SHA256_PATTERN.fullmatch(token_sha256.lower()):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {index} token_sha256 is invalid")

        roles_raw = raw.get("roles", [])
        if not isinstance(roles_raw, list) or any(not isinstance(role, str) for role in roles_raw):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {index} roles are invalid")
        unknown_roles = sorted(set(roles_raw) - set(ROLE_PERMISSIONS))
        if unknown_roles:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"security principal {index} has unknown roles",
                context={"unknown_roles": unknown_roles},
            )
        permissions: set[Permission] = set()
        for role in roles_raw:
            permissions.update(ROLE_PERMISSIONS[role])

        explicit = raw.get("permissions", [])
        if not isinstance(explicit, list) or any(not isinstance(value, str) for value in explicit):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {index} permissions are invalid")
        try:
            permissions.update(Permission(value) for value in explicit)
        except ValueError as exc:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                f"security principal {index} contains an unknown permission",
                original_exception=exc,
            ) from exc
        if not permissions:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {index} has no permissions")

        scopes_raw = raw["scopes"]
        if not isinstance(scopes_raw, list) or not scopes_raw:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {index} scopes are invalid")
        scopes = tuple(GatewaySecurityConfig._scope(scope, index) for scope in scopes_raw)
        return Principal(
            principal_id=principal_id,
            roles=tuple(roles_raw),
            permissions=frozenset(permissions),
            scopes=scopes,
            token_sha256=token_sha256.lower(),
        )

    @staticmethod
    def _scope(raw: Any, principal_index: int) -> ResourceScope:
        required = {"facility_id", "ppu_id", "site_ids"}
        if not isinstance(raw, dict) or set(raw) != required:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {principal_index} scope fields are invalid")
        facility_id = raw["facility_id"]
        ppu_id = raw["ppu_id"]
        if not isinstance(facility_id, str) or not facility_id or not isinstance(ppu_id, str) or not ppu_id:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {principal_index} scope IDs are invalid")
        raw_sites = raw["site_ids"]
        if raw_sites == "*":
            site_ids = None
        elif (
            isinstance(raw_sites, list)
            and raw_sites
            and all(not isinstance(site, bool) and isinstance(site, int) and site >= 1 for site in raw_sites)
        ):
            site_ids = frozenset(raw_sites)
        else:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security principal {principal_index} scope site_ids are invalid")
        return ResourceScope(facility_id=facility_id, ppu_id=ppu_id, site_ids=site_ids)


class GatewaySecurityStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._connection.execute("PRAGMA synchronous=FULL")
            self._connection.execute("PRAGMA foreign_keys=ON")
            self._migrate()

    def _migrate(self) -> None:
        version = int(self._connection.execute("PRAGMA user_version").fetchone()[0])
        if version == 0:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS security_commands (
                    principal_id TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    request_sha256 TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    http_status INTEGER,
                    response_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (principal_id, command_id)
                );

                CREATE TABLE IF NOT EXISTS security_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    action TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    resource_json TEXT NOT NULL,
                    command_id TEXT,
                    detail_json TEXT NOT NULL
                );
                """
            )
            self._connection.execute(f"PRAGMA user_version={SECURITY_STATE_SCHEMA_VERSION}")
            self._connection.commit()
            version = SECURITY_STATE_SCHEMA_VERSION
        if version != SECURITY_STATE_SCHEMA_VERSION:
            raise PlasmaError(
                ErrorCode.CONFIG_INVALID,
                "Unsupported Gateway security state schema version",
                context={"expected": SECURITY_STATE_SCHEMA_VERSION, "actual": version},
            )

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    def audit(
        self,
        *,
        principal_id: str,
        decision: str,
        action: str,
        method: str,
        path: str,
        resource: ResourceRef | None,
        command_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not principal_id:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Durable security audit requires an authenticated principal")
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO security_audit (
                    timestamp, principal_id, decision, action, method, path,
                    resource_json, command_id, detail_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    iso_now(),
                    principal_id,
                    decision,
                    action,
                    method,
                    path,
                    self._json(resource.to_dict() if resource else {}),
                    command_id,
                    self._json(detail or {}),
                ),
            )
            self._connection.commit()

    def audit_count(self) -> int:
        with self._lock:
            return int(self._connection.execute("SELECT COUNT(*) FROM security_audit").fetchone()[0])

    def begin_command(
        self,
        *,
        principal_id: str,
        command_id: str,
        request_sha256: str,
        method: str,
        path: str,
        action: str,
        resource: ResourceRef | None,
    ) -> CommandAdmission:
        now = iso_now()
        resource_json = self._json(resource.to_dict() if resource else {})
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM security_commands WHERE principal_id = ? AND command_id = ?",
                (principal_id, command_id),
            ).fetchone()
            if row is not None:
                if (
                    row["request_sha256"] != request_sha256
                    or row["method"] != method
                    or row["path"] != path
                    or row["action"] != action
                    or row["resource_json"] != resource_json
                ):
                    raise PlasmaError(
                        ErrorCode.COMMAND_REPLAY_CONFLICT,
                        "Idempotency key was already used for a different command",
                        context={"command_id": command_id},
                    )
                if row["state"] == "completed" and row["http_status"] is not None and row["response_json"] is not None:
                    payload = json.loads(str(row["response_json"]))
                    if not isinstance(payload, dict):
                        raise PlasmaError(ErrorCode.CONFIG_INVALID, "Persisted command response must be an object")
                    return CommandAdmission(
                        principal_id=principal_id,
                        command_id=command_id,
                        request_sha256=request_sha256,
                        replay_status=int(row["http_status"]),
                        replay_payload=payload,
                    )
                raise PlasmaError(
                    ErrorCode.COMMAND_IN_PROGRESS,
                    "Command with this idempotency key is already in progress or requires reconciliation",
                    recoverable=True,
                    context={"command_id": command_id},
                )

            self._connection.execute(
                """
                INSERT INTO security_commands (
                    principal_id, command_id, request_sha256, method, path, action,
                    resource_json, state, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'started', ?, ?)
                """,
                (
                    principal_id,
                    command_id,
                    request_sha256,
                    method,
                    path,
                    action,
                    resource_json,
                    now,
                    now,
                ),
            )
            self._connection.commit()
        return CommandAdmission(principal_id, command_id, request_sha256)

    def complete_command(self, admission: CommandAdmission, *, http_status: int, response: dict[str, Any]) -> None:
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE security_commands
                SET state = 'completed', http_status = ?, response_json = ?, updated_at = ?
                WHERE principal_id = ? AND command_id = ? AND state = 'started'
                """,
                (
                    int(http_status),
                    self._json(response),
                    iso_now(),
                    admission.principal_id,
                    admission.command_id,
                ),
            )
            if cursor.rowcount != 1:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Command admission row is not completable")
            self._connection.commit()

    def close(self) -> None:
        with self._lock:
            self._connection.commit()
            self._connection.close()


class GatewaySecurityController:
    def __init__(self, config: GatewaySecurityConfig, store: GatewaySecurityStore) -> None:
        self.config = config
        self.store = store

    @classmethod
    def from_paths(cls, config_path: str | Path, state_path: str | Path) -> "GatewaySecurityController":
        return cls(GatewaySecurityConfig.load(config_path), GatewaySecurityStore(state_path))

    def authenticate(self, authorization: str | None, *, method: str, path: str) -> Principal:
        # Unauthenticated traffic is intentionally not written to the durable
        # SQLite audit ledger. A hostile caller must not be able to turn bad
        # credentials into synchronous microSD writes. The HTTP handler emits
        # non-durable runtime diagnostics for E4101 instead.
        if not isinstance(authorization, str) or not authorization.startswith("Bearer "):
            raise PlasmaError(ErrorCode.AUTHENTICATION_REQUIRED, "Bearer authentication is required")
        token = authorization[7:]
        if len(token) < 32 or len(token) > 512:
            raise PlasmaError(ErrorCode.AUTHENTICATION_REQUIRED, "Bearer authentication is required")
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        matched: Principal | None = None
        for principal in self.config.principals:
            if hmac.compare_digest(digest, principal.token_sha256):
                matched = principal
        if matched is None:
            raise PlasmaError(ErrorCode.AUTHENTICATION_REQUIRED, "Bearer authentication is required")
        return matched

    def authorize(
        self,
        principal: Principal,
        permission: Permission,
        *,
        method: str,
        path: str,
        resource: ResourceRef | None = None,
    ) -> None:
        if principal.allows(permission, resource):
            return
        self.store.audit(
            principal_id=principal.principal_id,
            decision="denied",
            action=permission.value,
            method=method,
            path=path,
            resource=resource,
        )
        raise PlasmaError(
            ErrorCode.AUTHORIZATION_DENIED,
            "Principal is not authorized for this Plasma action or resource",
            context={
                "principal_id": principal.principal_id,
                "permission": permission.value,
                "resource": resource.to_dict() if resource else {},
            },
        )

    def admit_command(
        self,
        principal: Principal,
        *,
        permission: Permission,
        command_id: str | None,
        request_sha256: str,
        method: str,
        path: str,
        resource: ResourceRef | None = None,
    ) -> CommandAdmission:
        self.authorize(principal, permission, method=method, path=path, resource=resource)
        if not isinstance(command_id, str) or not _COMMAND_ID_PATTERN.fullmatch(command_id):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "State-changing requests require an Idempotency-Key of 8..128 safe characters",
            )
        admission = self.store.begin_command(
            principal_id=principal.principal_id,
            command_id=command_id,
            request_sha256=request_sha256,
            method=method,
            path=path,
            action=permission.value,
            resource=resource,
        )
        self.store.audit(
            principal_id=principal.principal_id,
            decision="replay" if admission.replay else "accepted",
            action=permission.value,
            method=method,
            path=path,
            resource=resource,
            command_id=command_id,
        )
        return admission

    def close(self) -> None:
        self.store.close()
