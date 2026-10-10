from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github/workflows/z2like-demo-qemu.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_cache_key_is_pinned_to_architecture_release_and_build_recipe() -> None:
    text = workflow_text()
    assert 'OPENOCD_ARMV7_CACHE_SCHEMA: "v1"' in text
    assert "armv7-ubuntu22.04-" in text
    assert "hashFiles('release/openocd.json', 'scripts/build-openocd-runtime.sh', 'scripts/openocd-runtime.py')" in text
    assert "restore-keys:" not in text
    assert "hashFiles('.github/workflows/z2like-demo-qemu.yml'" not in text
    assert "path: ${{ runner.temp }}/openocd-armv7l-cached" in text


def test_prs_may_restore_but_only_main_can_save_cache() -> None:
    text = workflow_text()
    assert "uses: actions/cache/restore@v4" in text
    assert "uses: actions/cache/save@v4" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "(github.event_name == 'push' || github.event_name == 'workflow_dispatch')" in text
    save_section = text.split("Save qualified ARMv7 OpenOCD build cache on main only", 1)[1]
    assert "github.event_name == 'pull_request'" not in save_section
    assert "steps.openocd-cache.outputs.cache-hit != 'true'" in save_section


def test_cache_hit_skips_only_openocd_compile_never_integrity_gate() -> None:
    text = workflow_text()
    restore = text.index("Restore pinned ARMv7 OpenOCD build cache")
    build = text.index("Build pinned ARMv7 OpenOCD only on cache miss")
    verify = text.index("Verify cached or freshly built ARMv7 OpenOCD and pinned source identity")
    kit = text.index("Build real canonical ARMv7 PPU release and simulation-only Z2 kit fixture")
    e2e = text.index("Drive Manager to Bootstrap to QEMU deployment E2E")
    run_arm = text.index("Verify kit-deployed OpenOCD inside QEMU ARMv7 target")
    eight_sites = text.index("Qualify eight isolated OpenOCD workers inside deployed ARMv7 PPU")
    matrix = text.index("Prove Platform and Managed PS loopback lifecycle matrix")
    save = text.index("Save qualified ARMv7 OpenOCD build cache on main only")
    assert restore < build < verify < kit < e2e < run_arm < eight_sites < matrix < save
    build_part = text[build:verify]
    assert "if: steps.openocd-cache.outputs.cache-hit != 'true'" in build_part
    assert 'bash scripts/build-openocd-runtime.sh "$RUNNER_TEMP/openocd-armv7l-cached" armv7l' in build_part
    verify_part = text[verify:kit]
    assert "if: steps.openocd-cache.outputs.cache-hit" not in verify_part
    assert 'test -f "$artifact"' in verify_part
    assert 'test -f "$artifact.sha256"' in verify_part
    assert 'scripts/openocd-runtime.py verify "$artifact" --sidecar "$artifact.sha256"' in verify_part
    assert 'evidence["source_commit"] == release["source_commit"]' in verify_part
    assert 'evidence["runtime_id"] == release["runtime_id"]' in verify_part
    assert 'evidence["architecture"] == "armv7l"' in verify_part
    assert 'evidence["hardware_runtime_ready"] is False' in verify_part


def test_fresh_commit_specific_kit_and_e2e_remain_unconditional() -> None:
    text = workflow_text()
    kit = text.split("Build real canonical ARMv7 PPU release and simulation-only Z2 kit fixture", 1)[1].split(
        "Drive Manager to Bootstrap to QEMU deployment E2E", 1
    )[0]
    assert 'sha="$(git rev-parse HEAD)"' in kit
    assert 'python scripts/ppu-runtime.py build --output-dir "$runtime"' in kit
    assert 'python scripts/ppu-release.py' in kit
    assert 'openocd_out="$RUNNER_TEMP/openocd-armv7l-cached"' in kit
    assert 'python scripts/openocd-runtime.py verify "$openocd" --sidecar "$openocd.sha256"' in kit
    assert "if: steps.openocd-cache" not in kit
    assert "if: steps.openocd-cache" not in text.split("Drive Manager to Bootstrap to QEMU deployment E2E", 1)[1].split(
        "Capture diagnostics on failure", 1
    )[0]
    assert 'assert p["starts_openocd_service"] is False' in text


def test_cache_metrics_and_evidence_distinguish_hit_from_miss() -> None:
    text = workflow_text()
    assert 'start="$(date +%s)"' in text
    assert 'echo "OpenOCD cache MISS: build duration' in text
    assert "OpenOCD ARMv7 cache: " in text
    assert 'echo "OpenOCD ARMv7 cache:' in text
    assert "Cache MISS" not in text  # Log is a measurement, not a silent behavioral fallback.
