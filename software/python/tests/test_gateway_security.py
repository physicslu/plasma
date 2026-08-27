from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.gateway_security import (
    GatewaySecurityConfig,
    GatewaySecurityController,
    Permission,
    ResourceRef,
)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _controller(tmp_path: Path) -> tuple[GatewaySecurityController, dict[str, str]]:
    tokens = {
        "viewer": "viewer-token-0123456789abcdef0123456789abcdef",
        "operator": "operator-token-0123456789abcdef0123456789abcdef",
        "admin": "admin-token-0123456789abcdef0123456789abcdef",
    }
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": [
                    {
                        "id": "remote-support",
                        "token_sha256": _token_digest(tokens["viewer"]),
                        "roles": ["viewer"],
                        "scopes": [
                            {
                                "facility_id": "mock-facility-01",
                                "ppu_id": "mock-facility-01-ppu-01",
                                "site_ids": "*",
                            }
                        ],
                    },
                    {
                        "id": "production-operator",
                        "token_sha256": _token_digest(tokens["operator"]),
                        "roles": ["operator"],
                        "scopes": [
                            {
                                "facility_id": "mock-facility-01",
                                "ppu_id": "mock-facility-01-ppu-01",
                                "site_ids": [1, 2],
                            }
                        ],
                    },
                    {
                        "id": "system-admin",
                        "token_sha256": _token_digest(tokens["admin"]),
                        "roles": ["admin"],
                        "scopes": [{"facility_id": "*", "ppu_id": "*", "site_ids": "*"}],
                    },
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    controller = GatewaySecurityController.from_paths(config_path, tmp_path / "security-state.sqlite3")
    return controller, tokens


def test_viewer_is_read_only_and_ic_read_remains_execution_permission(tmp_path: Path) -> None:
    controller, tokens = _controller(tmp_path)
    try:
        principal = controller.authenticate(
            f"Bearer {tokens['viewer']}",
            method="GET",
            path="/api/status",
        )
        target = ResourceRef(
            facility_id="mock-facility-01",
            ppu_id="mock-facility-01-ppu-01",
            site_id=1,
        )
        controller.authorize(
            principal,
            Permission.STATUS_READ,
            method="GET",
            path="/api/status",
            resource=target,
        )
        with pytest.raises(PlasmaError) as exc_info:
            controller.authorize(
                principal,
                Permission.PPU_READ,
                method="POST",
                path="/api/jobs",
                resource=target,
            )
        assert exc_info.value.code is ErrorCode.AUTHORIZATION_DENIED
        with pytest.raises(PlasmaError) as exc_info:
            controller.authorize(
                principal,
                Permission.PPU_PROGRAM,
                method="POST",
                path="/api/jobs",
                resource=target,
            )
        assert exc_info.value.code is ErrorCode.AUTHORIZATION_DENIED
    finally:
        controller.close()


def test_operator_scope_rejects_other_site_and_ppu(tmp_path: Path) -> None:
    controller, tokens = _controller(tmp_path)
    try:
        principal = controller.authenticate(
            f"Bearer {tokens['operator']}",
            method="POST",
            path="/api/jobs",
        )
        controller.authorize(
            principal,
            Permission.PPU_PROGRAM,
            method="POST",
            path="/api/jobs",
            resource=ResourceRef("mock-facility-01", "mock-facility-01-ppu-01", 2),
        )
        with pytest.raises(PlasmaError) as exc_info:
            controller.authorize(
                principal,
                Permission.PPU_PROGRAM,
                method="POST",
                path="/api/jobs",
                resource=ResourceRef("mock-facility-01", "mock-facility-01-ppu-01", 3),
            )
        assert exc_info.value.code is ErrorCode.AUTHORIZATION_DENIED
        with pytest.raises(PlasmaError) as exc_info:
            controller.authorize(
                principal,
                Permission.PPU_PROGRAM,
                method="POST",
                path="/api/jobs",
                resource=ResourceRef("mock-facility-01", "mock-facility-01-ppu-02", 1),
            )
        assert exc_info.value.code is ErrorCode.AUTHORIZATION_DENIED
    finally:
        controller.close()


def test_site_limited_scope_does_not_authorize_parent_ppu_resource(tmp_path: Path) -> None:
    controller, tokens = _controller(tmp_path)
    try:
        principal = controller.authenticate(
            f"Bearer {tokens['operator']}",
            method="GET",
            path="/api/status",
        )
        with pytest.raises(PlasmaError) as exc_info:
            controller.authorize(
                principal,
                Permission.STATUS_READ,
                method="GET",
                path="/api/status",
                resource=ResourceRef("mock-facility-01", "mock-facility-01-ppu-01"),
            )
        assert exc_info.value.code is ErrorCode.AUTHORIZATION_DENIED
    finally:
        controller.close()


def test_missing_or_invalid_bearer_token_is_unauthenticated_without_durable_writes(tmp_path: Path) -> None:
    controller, _ = _controller(tmp_path)
    try:
        before = controller.store.audit_count()
        for authorization in (None, "Basic abc", "Bearer short", "Bearer " + "x" * 48):
            with pytest.raises(PlasmaError) as exc_info:
                controller.authenticate(authorization, method="POST", path="/api/batches")
            assert exc_info.value.code is ErrorCode.AUTHENTICATION_REQUIRED
        assert controller.store.audit_count() == before
    finally:
        controller.close()


def test_same_idempotency_key_replays_completed_response_without_new_command(tmp_path: Path) -> None:
    controller, tokens = _controller(tmp_path)
    try:
        principal = controller.authenticate(
            f"Bearer {tokens['operator']}",
            method="POST",
            path="/api/batches",
        )
        resource = ResourceRef("mock-facility-01", "mock-facility-01-ppu-01", 1)
        admission = controller.admit_command(
            principal,
            permission=Permission.BATCH_START,
            command_id="cmd-batch-0001",
            request_sha256="a" * 64,
            method="POST",
            path="/api/batches",
            resource=resource,
        )
        assert admission.replay is False
        controller.store.complete_command(
            admission,
            http_status=202,
            response={"ok": True, "batch": {"batch_id": "batch-1"}},
        )
        replay = controller.admit_command(
            principal,
            permission=Permission.BATCH_START,
            command_id="cmd-batch-0001",
            request_sha256="a" * 64,
            method="POST",
            path="/api/batches",
            resource=resource,
        )
        assert replay.replay is True
        assert replay.replay_status == 202
        assert replay.replay_payload == {"ok": True, "batch": {"batch_id": "batch-1"}}
    finally:
        controller.close()


def test_same_idempotency_key_cannot_change_payload_or_duplicate_inflight_command(tmp_path: Path) -> None:
    controller, tokens = _controller(tmp_path)
    try:
        principal = controller.authenticate(
            f"Bearer {tokens['operator']}",
            method="POST",
            path="/api/jobs",
        )
        resource = ResourceRef("mock-facility-01", "mock-facility-01-ppu-01", 1)
        controller.admit_command(
            principal,
            permission=Permission.PPU_ERASE,
            command_id="cmd-job-0001",
            request_sha256="b" * 64,
            method="POST",
            path="/api/jobs",
            resource=resource,
        )
        with pytest.raises(PlasmaError) as exc_info:
            controller.admit_command(
                principal,
                permission=Permission.PPU_ERASE,
                command_id="cmd-job-0001",
                request_sha256="b" * 64,
                method="POST",
                path="/api/jobs",
                resource=resource,
            )
        assert exc_info.value.code is ErrorCode.COMMAND_IN_PROGRESS
        with pytest.raises(PlasmaError) as exc_info:
            controller.admit_command(
                principal,
                permission=Permission.PPU_ERASE,
                command_id="cmd-job-0001",
                request_sha256="c" * 64,
                method="POST",
                path="/api/jobs",
                resource=resource,
            )
        assert exc_info.value.code is ErrorCode.COMMAND_REPLAY_CONFLICT
    finally:
        controller.close()


def test_security_config_requires_explicit_resource_scopes(tmp_path: Path) -> None:
    token = "high-entropy-token-0123456789abcdef0123456789abcdef"
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": [
                    {
                        "id": "viewer",
                        "token_sha256": _token_digest(token),
                        "roles": ["viewer"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(PlasmaError) as exc_info:
        GatewaySecurityConfig.load(config_path)
    assert exc_info.value.code is ErrorCode.CONFIG_INVALID


def test_config_stores_only_token_hash_not_plaintext_token(tmp_path: Path) -> None:
    token = "high-entropy-token-0123456789abcdef0123456789abcdef"
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": [
                    {
                        "id": "viewer",
                        "token_sha256": _token_digest(token),
                        "roles": ["viewer"],
                        "scopes": [{"facility_id": "*", "ppu_id": "*", "site_ids": "*"}],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loaded = GatewaySecurityConfig.load(config_path)
    assert loaded.principals[0].token_sha256 == _token_digest(token)
    assert token not in config_path.read_text(encoding="utf-8")
