from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_factory_bootstrap_can_be_rebuilt_for_exact_main_commit() -> None:
    workflow = (ROOT / ".github/workflows/ppu-bootstrap.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert '"git_sha": git_sha' in workflow
    assert 'name: ppu-bootstrap-factory-bundle' in workflow


def test_real_z2_hil_requires_same_commit_artifact_provenance() -> None:
    bootstrap = (ROOT / ".github/workflows/ppu-bootstrap.yml").read_text(encoding="utf-8")
    z2_release = (ROOT / ".github/workflows/z2-ps-release.yml").read_text(encoding="utf-8")
    handoff = (ROOT / "docs/deployment/ppu-bootstrap-factory-and-hil.md").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in bootstrap
    assert "workflow_dispatch:" in z2_release
    assert "same `main` commit" in handoff
    assert "PPU bootstrap regression" in handoff
    assert "Z2 PS release candidate" in handoff
    assert "workflow run IDs" in handoff
    assert "artifact SHA-256" in handoff
