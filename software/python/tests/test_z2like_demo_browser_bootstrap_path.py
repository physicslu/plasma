from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INGRESS = ROOT / "scripts" / "plasmactl-z2like-demo-managed-ingress"
RENDER = ROOT / "scripts" / "render-control-station-start.sh"
BLUEPRINT = ROOT / "render.yaml"


def test_swpc_managed_ingress_projects_only_allowlisted_qemu_bootstrap_routes() -> None:
    source = INGRESS.read_text(encoding="utf-8")
    assert 'qemu_gateway_root="${PLASMA_Z2LIKE_DEMO_GATEWAY_ROOT:-http://172.30.77.2:18080}"' in source
    assert 'qemu_bootstrap_root="${PLASMA_Z2LIKE_DEMO_BOOTSTRAP_ROOT:-http://172.30.77.2:18081}"' in source
    assert 'bootstrap_prefix="/__plasma/bootstrap"' in source
    assert 'bootstrap_route_profile="managed-bootstrap-v1"' in source

    for route in (
        "location = $bootstrap_prefix/v1/status {",
        "location = $bootstrap_prefix/v1/uploads {",
        "location ~ ^$bootstrap_prefix/v1/uploads/[0-9a-f]{32}/chunks$ {",
        "location ~ ^$bootstrap_prefix/v1/uploads/[0-9a-f]{32}/commit$ {",
        "location = $bootstrap_prefix/v1/deployments {",
    ):
        assert route in source

    assert "fixed prefix/method allowlist only" in source
    assert "arbitrary Bootstrap /v1/* paths" in source
    assert "direct public access to QEMU/SWPC :18081" in source
    assert 'location / { return 404; }' in source
    assert "must not target the SWPC host diagnostics :18081" in source


def test_swpc_ingress_verifies_bootstrap_readiness_and_negative_security_cases() -> None:
    source = INGRESS.read_text(encoding="utf-8")
    assert "verify_bootstrap_ready" in source
    assert "$bootstrap_prefix/v1/not-allowlisted" in source
    assert "unexpectedly exposed an unknown Bootstrap path" in source
    assert "did not reject POST Bootstrap status" in source
    assert '"bootstrap_route_profile": "$bootstrap_route_profile"' in source
    assert '"bootstrap_public_prefix": "$bootstrap_prefix"' in source


def test_render_manager_owns_bootstrap_transport_and_device_runtime_bind_host() -> None:
    source = RENDER.read_text(encoding="utf-8")
    assert "python -m plasma_manager.bootstrap_server" in source
    assert 'PLASMA_MANAGER_BOOTSTRAP_TRANSPORT="managed-gateway-prefix-v1"' in source
    assert 'PLASMA_MANAGER_BOOTSTRAP_RUNTIME_GATEWAY_HOST="${runtime_gateway_host}"' in source
    assert 'PLASMA_MANAGER_REGISTRY_POLICY="fixed-lifecycle"' in source
    assert '"registry_state_path": registry_state' in source
    assert "Browser Runtime Deployment must never learn a direct Bootstrap endpoint" in source

    blueprint = BLUEPRINT.read_text(encoding="utf-8")
    assert "PLASMA_RENDER_PPU_RUNTIME_GATEWAY_HOST" in blueprint
    assert "value: 172.30.77.2" in blueprint
