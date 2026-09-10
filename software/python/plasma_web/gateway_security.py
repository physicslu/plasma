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
    SITE_SETTINGS_WRITE = "settings.site.write"
    RUNTIME_ACTIVATION_WRITE = "settings.runtime_activation.write"
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
ENGINEER_PERMISSIONS = OPERATOR_PERMISSIONS | frozenset(
    {
        Permission.MOCK_SETTINGS_WRITE,
        Permission.SITE_SETTINGS_WRITE,
        Permission.RUNTIME_ACTIVATION_WRITE,
    }
)
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
        self.principals = normalized
        self.by_token_sha256 = {p.token_sha256: p for p in normalized}

    @staticmethod
    def _scope(raw: Any) -> ResourceScope:
        if not isinstance(raw, dict):
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "security scope must be an object")
        allowed = {"facility_id", "ppu_id", "site_ids"}
        unknown = sorted(set(raw) - allowed)
        if unknown:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"security scope contains unknown fields: {unknown}")
        facility_id = raw.get("facility_id", "*")
        ppu_id = raw.get("ppu_id", "*")
        if not isinstance(facility_id, str) or not facility_id:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "security scope facility_id must be a non-empty string")
        if not isinstance(ppu_id, str) or not ppu_id:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "security scope ppu_id must be a non-empty string")
        raw_sites = raw.get("site_ids", "*")
        if raw_sites == "*":
            site_ids = None
        elif isinstance(raw_sites, list) and raw_sites and all(isinstance(value, int) and not isinstance(value, bool) and value >= 1 for value in raw_sites):
            site_ids = frozenset(raw_sites)
        else:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "security scope site_ids must be '*' or a non-empty list of 1-based integers")
        return ResourceScope(facility_id=facility_id, ppu_id=ppu_id, site_ids=site_ids)

    @classmethod
    def from_yaml(cls, raw: Any) -> "GatewaySecurityConfig":
        if not isinstance(raw, dict) or raw.get("version") != SECURITY_CONFIG_VERSION:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security config version is invalid")
        principals = raw.get("principals")
        if not isinstance(principals, list) or not principals:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security config principals must be a non-empty list")
        parsed: list[Principal] = []
        for item in principals:
            if not isinstance(item, dict):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security principal must be an object")
            principal_id = item.get("id")
            token_sha256 = item.get("token_sha256")
            roles = item.get("roles")
            scopes = item.get("scopes")
            if not isinstance(principal_id, str) or not principal_id:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security principal id is invalid")
            if not isinstance(token_sha256, str) or not _TOKEN_SHA256_PATTERN.fullmatch(token_sha256):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security token_sha256 is invalid")
            if not isinstance(roles, list) or not roles or not all(isinstance(role, str) and role in ROLE_PERMISSIONS for role in roles):
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security principal roles are invalid")
            if not isinstance(scopes, list) or not scopes:
                raise PlasmaError(ErrorCode.CONFIG_INVALID, "Gateway security principal scopes are invalid")
            permissions = frozenset(permission for role in roles for permission in ROLE_PERMISSIONS[role])
            parsed.append(
                Principal(
                    principal_id=principal_id,
                    roles=tuple(roles),
                    permissions=permissions,
                    scopes=tuple(cls._scope(scope) for scope in scopes),
                    token_sha256=token_sha256,
                )
            )
        return cls(parsed)

    @classmethod
    def load(cls, path: Path) -> "GatewaySecurityConfig":
        try:
            return cls.from_yaml(yaml.safe_load(path.read_text(encoding="utf-8")))
        except OSError as exc:
            raise PlasmaError(ErrorCode.CONFIG_INVALID, f"cannot read Gateway security config: {path}", original_exception=exc) from exc


class GatewaySecurityController:
    def __init__(self, config: GatewaySecurityConfig, state_path: Path) -> None:
        self.config = config
        self.state_path = state_path
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(state_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS commands (principal_id TEXT NOT NULL, command_id TEXT NOT NULL, request_sha256 TEXT NOT NULL, status INTEGER, response_json TEXT, created_at TEXT NOT NULL, PRIMARY KEY (principal_id, command_id))"
        )
        self._connection.commit()

    @classmethod
    def from_paths(cls, config_path: Path, state_path: Path) -> "GatewaySecurityController":
        return cls(GatewaySecurityConfig.load(config_path), state_path)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def authenticate(self, token: str) -> Principal:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        for expected, principal in self.config.by_token_sha256.items():
            if hmac.compare_digest(digest, expected):
                return principal
        raise PlasmaError(ErrorCode.AUTHENTICATION_REQUIRED, "invalid Bearer token")

    def authorize(self, principal: Principal, permission: Permission, resources: Iterable[ResourceRef] = ()) -> None:
        required = tuple(resources)
        if permission not in principal.permissions or any(not principal.allows(permission, resource) for resource in required):
            raise PlasmaError(ErrorCode.PERMISSION_DENIED, f"permission denied: {permission.value}")

    def admit_command(self, principal: Principal, command_id: str, request_body: bytes) -> CommandAdmission:
        if not _COMMAND_ID_PATTERN.fullmatch(command_id):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Idempotency-Key is invalid")
        request_sha256 = hashlib.sha256(request_body).hexdigest()
        with self._lock:
            row = self._connection.execute(
                "SELECT request_sha256, status, response_json FROM commands WHERE principal_id=? AND command_id=?",
                (principal.principal_id, command_id),
            ).fetchone()
            if row is not None:
                if row["request_sha256"] != request_sha256:
                    raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "Idempotency-Key was already used for a different request")
                if row["status"] is None or row["response_json"] is None:
                    raise PlasmaError(ErrorCode.PPU_BUSY, "idempotent command is already in progress", recoverable=True)
                return CommandAdmission(
                    principal.principal_id,
                    command_id,
                    request_sha256,
                    replay_status=int(row["status"]),
                    replay_payload=json.loads(row["response_json"]),
                )
            self._connection.execute(
                "INSERT INTO commands(principal_id, command_id, request_sha256, created_at) VALUES (?, ?, ?, ?)",
                (principal.principal_id, command_id, request_sha256, iso_now()),
            )
            self._connection.commit()
        return CommandAdmission(principal.principal_id, command_id, request_sha256)

    def complete_command(self, admission: CommandAdmission, status: int, payload: dict[str, Any]) -> None:
        with self._lock:
            self._connection.execute(
                "UPDATE commands SET status=?, response_json=? WHERE principal_id=? AND command_id=? AND request_sha256=?",
                (
                    int(status),
                    json.dumps(payload, separators=(",", ":"), sort_keys=True),
                    admission.principal_id,
                    admission.command_id,
                    admission.request_sha256,
                ),
            )
            self._connection.commit()
