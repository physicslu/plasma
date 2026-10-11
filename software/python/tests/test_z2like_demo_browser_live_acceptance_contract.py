from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"
HANDOVER = ROOT / "handover" / "H021-z2like-demo-browser-runtime-deployment-plan-2026-09-14.md"


def test_live_gate_is_manual_post_deployment_swpc_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch: {}" in workflow
    assert "\n  push:\n" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow
    assert "github.event_name != 'pull_request'" not in workflow
    assert "github.repository == 'physicslu/plasma'" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert 'test "$GITHUB_EVENT_NAME" = "workflow_dispatch"' in workflow
    assert "runs-on: [self-hosted, linux, x64, plasma-integration]" in workflow
    assert "persist-credentials: false" in workflow
    assert "group: z2like-demo-browser-runtime-live-acceptance-${{ github.ref }}" in workflow
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in workflow
    assert "--expected-commit \"$GITHUB_SHA\"" in workflow


def test_live_gate_reconciles_user_owned_maintenance_manager_without_root_ingress_mutation() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "Reconcile canonical SWPC managed ingress" not in workflow
    assert "sudo -n" not in workflow
    assert "scripts/plasmactl-z2like-demo-managed-ingress install" not in workflow
    reconcile = workflow.index("Reconcile exact-commit QEMU control plane")
    maintenance = workflow.index("Reconcile exact-commit SWPC-local maintenance Manager")
    preflight = workflow.index("Preflight canonical SWPC/QEMU target")
    assert reconcile < maintenance < preflight
    assert "scripts/z2like-demo-qemu.py" in workflow
    assert "configure-control-station" in workflow
    assert "http://127.0.0.1:18082/__plasma/bootstrap/v1/status" in workflow
    assert "curl -4 --http1.1 --fail --silent --show-error" in workflow
    assert "--retry 3 --retry-all-errors --retry-delay 2 --retry-max-time 70" in workflow
    assert "--connect-timeout 5 --max-time 20" in workflow
    assert "https://z2like-demo.open4th.com/deployment.json" in workflow
    assert "Run ./scripts/plasmactl update z2like-demo as an operator before rerunning this gate." in workflow


def test_live_gate_keeps_pairing_secret_and_capability_out_of_evidence() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "/var/lib/plasma-bootstrap/control-token" in source
    assert 'token = ""' in source
    assert 'CAPABILITY_COOKIE = "plasma-manager-maintenance"' in source
    assert '"wrong_pairing_token": "BLOCKED_NO_CREDENTIAL_CHANGE"' in source
    assert '"maintenance_capability_cookie_contract": "PASS"' in source
    assert '"kit_sha256": kit_sha' in source
    assert '"token": token' in source
    assert '"capability": capability' not in source
    assert '"pairing_token"' not in source


def test_negative_lifecycle_authorization_probes_are_state_preserving() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    negative_region = source[
        source.index("lifecycle PATCH without capability") - 300:
        source.index("bootstrap_root =", source.index("lifecycle PATCH without capability"))
    ]
    assert negative_region.count('body={"lifecycle": "commissioned"}') == 3
    assert 'body={"lifecycle": "disabled"}' not in negative_region
    assert '_set_lifecycle(session, args.alias, "disabled", timeout_s=30.0)' in source


def test_live_gate_does_not_use_programming_registration_as_platform_maintenance_lock() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "commissioned Bootstrap upload" not in source
    assert "commissioned Bootstrap deployment" not in source
    assert "ppu_maintenance_required" not in source
    disable = source.index('_set_lifecycle(session, args.alias, "disabled", timeout_s=30.0)')
    deploy = source.index("_upload_and_deploy(", disable)
    assert disable < deploy


def test_live_gate_qualifies_openocd_managed_path_and_eight_site_isolation() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "_managed_openocd_acceptance(" in source
    assert "alias=args.alias" in source
    assert '"/api/manager/ppu/api/engineering/diagnostics/openocd-control-plane"' in source
    assert "for site_id in range(1, EXPECTED_SITE_COUNT + 1)" in source
    assert 'architecture not in {"armv7", "armv7l"}' in source
    assert '"execution_capability": "openocd-control-plane-only"' in source
    assert '"hardware_runtime_ready": False' in source
    assert "_eight_site_openocd_isolation(args.container)" in source
    assert '"/sim/openocd-control-plane-armv7-acceptance.py"' in source
    assert '"failure_injected_site_id": 5' in source
    assert '"surviving_sites_after_failure": 7' in source
    assert '"failed_site_restart": "PASS"' in source
    assert '"evidence_level": "live-swpc-render-qemu-openocd-control-plane"' in source
    assert '"openocd_control_plane_live"' in source
    for path in (
        "scripts/openocd-control-plane-armv7-acceptance.py",
        "scripts/openocd-runtime.py",
        "software/python/plasma_interfaces/openocd_rpc.py",
        "software/python/plasma_interfaces/openocd_worker.py",
        "software/python/plasma_manager/server.py",
        "software/python/plasma_web/gateway_base.py",
        "software/web/app/api/manager/ppu/**",
    ):
        assert path in workflow


def test_live_gate_preserves_fail_closed_qualification_boundary() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    handover = HANDOVER.read_text(encoding="utf-8")
    for boundary in (
        "active-Site-Job disable rejection",
        "forced stale/non-idle maintenance proof rejection",
        "15-minute capability expiry wall-clock rejection",
        "real PYNQ-Z2 deployment/reboot/rollback",
        "PL/FPGA behavior",
        "real IC programming",
    ):
        assert boundary in source
    assert "Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED" in handover
    assert "H021 is not fully closed" in handover


def test_live_gate_covers_public_and_local_bootstrap_boundaries() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "https://z2like-demo.open4th.com" in source
    assert "https://ppu-managed-lab.open4th.com" in source
    assert "http://127.0.0.1:18082" in source
    assert "http://127.0.0.1:18380" in source
    assert "http://172.30.77.2:18080" in source
    assert "/__plasma/bootstrap/v1/not-allowlisted" in source
    assert "wrong Browser Bootstrap method" in source
    assert "/api/manager/ppu/api/engineering/targets" in source
    assert "payload.get(\"storage\") != \"config\"" in source
    assert "payload.get(\"mutable\") is not False" in source
    assert '"maintenance_registry": maintenance_registry' in source
    assert '"programming_registration_owner": "public-production-control-plane"' in source
    assert "EXPECTED_SITE_COUNT = 8" in source
    assert "172.30.77.2:18081" not in source
