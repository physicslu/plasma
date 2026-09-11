from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
Z2_BACKEND = ROOT / "scripts" / "plasmactl-z2-ps"
BOOTSTRAP_KIT = ROOT / "scripts" / "ppu-bootstrap-kit.py"
Z2_RELEASE = ROOT / ".github" / "workflows" / "z2-ps-release.yml"


def test_z2_backend_routes_activation_through_durable_coordinator():
    source = Z2_BACKEND.read_text(encoding="utf-8")
    assert "PLASMA_Z2_BOOTSTRAP_DEPLOYMENT" in source
    assert "ppu-bootstrap-deployment.py" in source
    assert 'python3 "$deployment_tool" "${args[@]}"' in source
    assert 'python3 "$ppu_installer" "${args[@]}"' not in source
    assert '--installer "$ppu_installer"' in source
    assert '--product-root "$product_root"' in source


def test_bootstrap_kit_requires_durable_coordinator():
    source = BOOTSTRAP_KIT.read_text(encoding="utf-8")
    assert 'scripts / "ppu-bootstrap-deployment.py"' in source
    assert "missing required deployment tooling" in source


def test_z2_release_candidate_packages_and_tests_durable_coordinator():
    source = Z2_RELEASE.read_text(encoding="utf-8")
    assert source.count('"scripts/ppu-bootstrap-deployment.py"') >= 2
    assert "python -m py_compile" in source
    assert "scripts/ppu-bootstrap-deployment.py" in source
    assert "software/python/tests/test_ppu_bootstrap_deployment.py" in source
    assert "software/python/tests/test_z2_bootstrap_deployment_call_graph.py" in source
    assert 'cp scripts/ppu-bootstrap-deployment.py "$root/scripts/ppu-bootstrap-deployment.py"' in source
    assert '"$root/scripts/ppu-bootstrap-deployment.py"' in source
