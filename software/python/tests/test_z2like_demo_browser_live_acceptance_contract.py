from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "z2like-demo-browser-live-acceptance.py"
WORKFLOW = ROOT / ".github" / "workflows" / "z2like-demo-browser-live-acceptance.yml"
HANDOVER = ROOT / "handover" / "H021-z2like-demo-browser-runtime-deployment-plan-2026-09-14.md"


def test_live_gate_is_post_merge_swpc_only() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "github.event_name != 'pull_request'" in workflow
    assert "github.repository == 'physicslu/plasma'" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert "runs-on: [self-hosted, linux, x64, plasma-integration]" in workflow
    assert "persist-credentials: false" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "--expected-commit \"$GITHUB_SHA\"" in workflow


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
    assert "/__plasma/bootstrap/v1/not-allowlisted" in source
    assert "wrong Browser Bootstrap method" in source
    assert "/api/manager/ppu/api/engineering/targets" in source
    assert "EXPECTED_SITE_COUNT = 8" in source
    assert "172.30.77.2:18081" not in source
