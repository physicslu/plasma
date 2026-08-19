from __future__ import annotations

import py_compile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "mock-cd.py"
WORKFLOW = ROOT / ".github" / "workflows" / "mock-cd.yml"


def test_mock_cd_harness_compiles() -> None:
    py_compile.compile(str(SCRIPT), doraise=True)


def test_mock_cd_is_ephemeral_and_does_not_deploy_real_hosts() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    forbidden = (
        "systemctl",
        "plasmactl deploy",
        "ssh ",
        "tailscale",
        "sudo ",
        "git clean",
        "git reset --hard",
    )
    for token in forbidden:
        assert token not in source

    assert '"mock-ppu-a"' in source
    assert '"mock-ppu-b"' in source
    assert '"sites": 8' in source
    assert '"sites": 4' in source
    assert '"reported_sites": 12' in source
    assert '"worker_binding"' in source
    assert '"browser_contract_sanitization"' in source
    assert "RESULT: PASS" in source


def test_mock_cd_workflow_is_isolated_and_publishes_artifact() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "name: Mock CD" in workflow
    assert "runs-on: ubuntu-latest" in workflow
    assert "python scripts/mock-cd.py" in workflow
    assert "mock-cd-acceptance" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "workflow_dispatch:" in workflow

    # Mock CD must not become a hidden real deployment path.
    assert "self-hosted" not in workflow
    assert "secrets." not in workflow
    assert "plasmactl deploy" not in workflow
    assert "ssh" not in workflow.lower()
