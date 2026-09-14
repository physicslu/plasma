from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/z2like-demo-qemu.yml"
E2E = ROOT / "scripts/z2like-demo-qemu-e2e.py"
DOC = ROOT / "docs/deployment/z2like-demo-qemu.md"


def test_workflow_runs_armv7_qemu_and_manager_bootstrap_e2e():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "docker/setup-qemu-action@v4" in source
    assert "python scripts/z2like-demo-qemu.py up" in source
    assert "python scripts/z2like-demo-qemu-e2e.py" in source
    assert "test -z \"$(docker port plasma-z2like-demo-qemu)\"" in source
    assert "simulation-only Z2 kit fixture" in source


def test_e2e_never_mutates_bootstrap_directly():
    source = E2E.read_text(encoding="utf-8")
    assert "/api/registry/{args.alias}/bootstrap" in source
    assert 'method="POST"' in source
    assert "/v1/uploads" not in source
    assert "/v1/deployments" not in source
    assert "runtime_absent" in source
    assert "runtime_active" in source
    assert "lifecycle\") != \"pending\"" in source


def test_public_boundary_is_console_only():
    source = DOC.read_text(encoding="utf-8")
    assert "127.0.0.1:18390" in source
    assert "QEMU container publishes **no host ports**" in source
    assert "Never expose QEMU `:18080`, QEMU `:18081`" in source
    assert "swpc-z2like" in source
    assert "engineering surrogate only" in source
    assert "Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED" in source
