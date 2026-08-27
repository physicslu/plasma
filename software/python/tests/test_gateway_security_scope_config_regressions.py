from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from plasma_core.errors import ErrorCode, PlasmaError
from plasma_web.gateway_security import GatewaySecurityConfig


TOKEN = "scope-config-regression-token-0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(
    "scope",
    [
        {},
        {"facility_id": "*"},
        {"facility_id": "*", "ppu_id": "*"},
    ],
)
def test_security_scope_requires_all_fields_explicitly(tmp_path: Path, scope: dict[str, object]) -> None:
    config_path = tmp_path / "security.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "principals": [
                    {
                        "id": "viewer",
                        "token_sha256": hashlib.sha256(TOKEN.encode("utf-8")).hexdigest(),
                        "roles": ["viewer"],
                        "scopes": [scope],
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
