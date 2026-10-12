"""Contracts for content-bound, verified OpenOCD release cache.

No hardware, network or Docker needed. Actual hit/miss evidence comes from CI.
"""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/z2-ps-release.yml"
SCRIPT = ROOT / "scripts/build-openocd-runtime.sh"
METADATA = ROOT / "release/openocd.json"

CACHE_KEY = (
    "openocd-${{ env.OPENOCD_CACHE_SCHEMA }}-${{ runner.os }}-"
    "${{ matrix.architecture }}-ubuntu22.04-"
    "${{ env.OPENOCD_TOOLCHAIN_EPOCH }}-"
    "${{ hashFiles('release/openocd.json', "
    "'scripts/build-openocd-runtime.sh', 'scripts/openocd-runtime.py') }}"
)


def job() -> str:
    source = WORKFLOW.read_text(encoding="utf-8")
    return source.split("\n  openocd-runtime:\n", 1)[1].split("\n  z2-ps-kit:\n", 1)[0]


def step(job_text: str, name: str) -> str:
    marker = "      - name: " + name + "\n"
    after = job_text.split(marker, 1)[1]
    return after.split("\n      - name:", 1)[0].split("\n      - uses:", 1)[0]


def test_cache_key_is_separate_per_architecture_source_recipe_and_toolchain_epoch() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    body = job()
    assert 'OPENOCD_CACHE_SCHEMA: "v1"' in workflow
    assert 'OPENOCD_TOOLCHAIN_EPOCH: "jammy-build-deps-2026-10-v1"' in workflow
    assert "          - x86_64\n          - armv7l" in body
    assert body.count("key: " + CACHE_KEY) == 2
    assert "restore-keys:" not in body
    assert ".github/workflows/z2-ps-release.yml', 'scripts/build-openocd-runtime.sh'" not in body
    assert "release/openocd.json" in CACHE_KEY
    assert "scripts/build-openocd-runtime.sh" in CACHE_KEY
    assert "scripts/openocd-runtime.py" in CACHE_KEY
    assert "matrix.architecture" in CACHE_KEY
    assert "OPENOCD_TOOLCHAIN_EPOCH" in CACHE_KEY
    assert "ubuntu22.04" in CACHE_KEY


def test_cache_restore_skips_only_compile_and_never_skips_sha_or_runtime_smoke() -> None:
    body = job()
    restore = body.index("Restore verified OpenOCD runtime build cache")
    build = body.index("Build pinned OpenOCD runtime on cache miss")
    verify = body.index("Verify OpenOCD runtime on cache hit and cache miss")
    rpc = body.index("Qualify real OpenOCD Tcl RPC worker")
    install = body.index("Install and execute on fresh matching Ubuntu 22.04 userspace")
    save = body.index("Save verified OpenOCD runtime build cache")
    upload = body.index("Upload qualified OpenOCD runtime candidate")
    assert restore < build < verify < rpc < install < save < upload

    assert "uses: actions/cache/restore@v4" in step(body, "Restore verified OpenOCD runtime build cache")
    compile_step = step(body, "Build pinned OpenOCD runtime on cache miss")
    assert "if: steps.openocd-cache.outputs.cache-hit != 'true'" in compile_step
    assert 'bash scripts/build-openocd-runtime.sh "$RUNNER_TEMP/openocd-$ARCH" "$ARCH"' in compile_step
    verify_step = step(body, "Verify OpenOCD runtime on cache hit and cache miss")
    assert "if: steps.openocd-cache.outputs" not in verify_step
    assert "test -f \"$artifact\"" in verify_step
    assert "test -f \"$artifact.sha256\"" in verify_step
    assert 'python scripts/openocd-runtime.py verify "$artifact" --sidecar "$artifact.sha256"' in verify_step
    assert "id: runtime" in verify_step

    worker_step = step(body, "Qualify real OpenOCD Tcl RPC worker")
    assert "if: matrix.architecture == 'x86_64'" in worker_step
    assert 'ARTIFACT: ${{ steps.runtime.outputs.artifact }}' in worker_step
    install_step = step(body, "Install and execute on fresh matching Ubuntu 22.04 userspace")
    assert 'ARTIFACT: ${{ steps.runtime.outputs.artifact }}' in install_step
    assert 'python3 /repo/scripts/openocd-runtime.py install' in install_step
    assert '\"hardware_runtime_ready\"' in install_step or "hardware_runtime_ready" in install_step


def test_only_main_push_or_manual_main_can_write_cache_after_full_runtime_checks() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    body = job()
    save = step(body, "Save verified OpenOCD runtime build cache")
    assert "uses: actions/cache/save@v4" in save
    assert "steps.openocd-cache.outputs.cache-hit != 'true'" in save
    assert "github.event_name == 'push'" in save
    assert "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'" in save
    assert "key: " + CACHE_KEY in save
    assert "          path: ${{ runner.temp }}/openocd-${{ matrix.architecture }}" in save
    assert "on:\n  workflow_dispatch:\n  push:\n    branches:\n      - main" in workflow
    assert "actions/cache/save@v4" not in step(body, "Restore verified OpenOCD runtime build cache")


def test_openocd_cache_does_not_replace_release_and_kit_artifact_boundaries() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    body = job()
    assert 'plasma-openocd-${{ steps.runtime.outputs.runtime_id }}-linux-${{ matrix.architecture }}-${{ github.sha }}' in body
    assert 'steps.runtime.outputs.artifact' in body
    assert 'steps.build.outputs.artifact' not in body
    assert 'steps.build.outputs.runtime_id' not in body
    assert 'name: plasma-openocd-' in body
    assert "actions/upload-artifact@v4" in body
    assert "needs: [z2-python-runtime, openocd-runtime]" in workflow
    assert "actions/download-artifact@v4" in workflow
    script = SCRIPT.read_text(encoding="utf-8")
    assert "OPENOCD_SOURCE_COMMIT" in script
    assert "OPENOCD_RUNTIME_ID" in script
    assert "--architecture" in script
    assert METADATA.is_file()
