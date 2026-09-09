from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "z2-ps-release.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_cache_key_is_architecture_source_and_recipe_bound() -> None:
    text = workflow_text()
    assert 'Z2_PYTHON_CACHE_SCHEMA: "v1"' in text
    assert "armv7-ubuntu22.04" in text
    assert "env.Z2_PYTHON_VERSION" in text
    assert "env.Z2_PYTHON_SOURCE_SHA256" in text
    assert "hashFiles('.github/workflows/z2-ps-release.yml', 'scripts/z2-python-runtime.py')" in text
    assert "restore-keys:" not in text


def test_pull_requests_restore_but_cannot_publish_executable_cache() -> None:
    text = workflow_text()
    assert "uses: actions/cache/restore@v4" in text
    assert "uses: actions/cache/save@v4" in text
    assert "github.event_name == 'push'" in text
    assert "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" in text
    assert "push:\n    branches:\n      - main" in text


def test_cache_hit_skips_only_build_not_verification() -> None:
    text = workflow_text()
    restore = text.index("Restore verified ARMv7 Python build cache")
    build = text.index("Build CPython against Ubuntu 22.04 ARMv7 userspace")
    verify = text.index("Verify Python artifact without executing ARM code on x86 host")
    fresh_install = text.index("Install Python artifact on fresh Ubuntu 22.04 ARMv7 userspace")
    save = text.index("Save verified ARMv7 Python build cache")
    upload = text.index("Upload qualified Plasma Python runtime candidate")

    assert restore < build < verify < fresh_install < save < upload
    assert "if: steps.z2-python-cache.outputs.cache-hit != 'true'" in text
    assert 'test -f "$artifact"' in text
    assert 'test -f "$artifact.sha256"' in text
    assert 'python scripts/z2-python-runtime.py verify "$artifact" --sidecar "$artifact.sha256"' in text
    assert '"/opt/plasma/python/${PYTHON_VERSION}/bin/python3" -c' in text


def test_cache_is_not_the_release_distribution_boundary() -> None:
    text = workflow_text()
    assert "actions/upload-artifact@v4" in text
    assert "plasma-z2-python-${{ env.Z2_PYTHON_VERSION }}-linux-armv7l-${{ github.sha }}" in text
    assert "actions/download-artifact@v4" in text
    assert "Build canonical PPU release" in text
