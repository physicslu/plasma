from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "scripts" / "mock-cd-browser-stack.py"
WORKFLOW = ROOT / ".github" / "workflows" / "mock-cd-browser.yml"
CONFIG = ROOT / "software" / "web" / "e2e" / "playwright.mock-cd.config.ts"
DEFAULT_CONFIG = ROOT / "software" / "web" / "e2e" / "playwright.config.ts"
SPEC = ROOT / "software" / "web" / "e2e" / "tests" / "mock-cd-runtime.spec.ts"
TESTS = ROOT / "software" / "web" / "e2e" / "tests"
ASSET_CACHE_SPEC = TESTS / "engineering-programming-asset-cache-runtime.spec.ts"
MULTI_PPU_SPEC = TESTS / "production-multi-ppu-runtime.spec.ts"
SETTINGS_SPEC = TESTS / "mock-runtime-settings-runtime.spec.ts"
PARITY_SPEC = TESTS / "programming-job-real-stack-parity.spec.ts"
HELPERS = TESTS / "mock-cd-managed-helpers.ts"
REAL_STACK_SPECS = (SPEC, ASSET_CACHE_SPEC, MULTI_PPU_SPEC, SETTINGS_SPEC, PARITY_SPEC)


def test_browser_stack_reuses_canonical_mock_cd_harness() -> None:
    source = STACK.read_text(encoding="utf-8")
    compile(source, str(STACK), "exec")
    assert 'BASELINE_HARNESS = ROOT / "scripts" / "mock-cd.py"' in source
    assert "load_baseline_harness()" in source
    assert "cd.PPUS" in source
    assert "cd.validate_web_fleet" in source
    # U10: the Mock PPUs (Runtime + real Bootstrap + G13 Gateway) and the
    # Manager Programming Engine come from the canonical harness.
    assert "cd.start_managed_ppus(" in source
    assert "cd.start_manager(" in source
    assert "cd.enroll_mock_ppus(" in source
    assert '"state": "ready"' in source
    # Read downloads are served from the Job output directory the Runtime writes.
    harness = (ROOT / "scripts" / "mock-cd.py").read_text(encoding="utf-8")
    assert '"output": root / f"{item[\'ppu_id\']}-output"' in harness
    assert '"--output-root", str(paths["output"])' in harness
    # start_manager still validates the two-PPU Fleet before anything else.
    assert "validate_manager_fleet(manager_fleet)" in harness


def test_browser_workflow_is_mock_only_and_fail_closed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Mock CD Browser Runtime Acceptance" in source
    assert "scripts/mock-cd-browser-stack.py" in source
    assert "playwright.mock-cd.config.ts" in source
    assert "runtime.json" in source
    # U10: the managed scenarios and the env the managed specs read.
    assert '"schema_version": 4' in source
    for scenario in (
        "managed_ppu_offline_recovery",
        "emode_managed_per_site_erase_program_verify_read_download",
        "emode_managed_batch_noncontiguous_sites_x_operations",
        "emode_1mib_image_once_per_batch_resource_set_activated_once_reused",
        "pmode_multi_ppu_batch_shared_image_epv",
        "pmode_abort_is_stop_queuing_started_jobs_complete",
        "mock_runtime_settings_via_manager_relay",
        "pmode_emode_programming_job_parity_1200_1680",
    ):
        assert scenario in source
    assert "engineering_1mib_programming_asset_cache_reuse_and_reconnect" not in source
    for env in ("MOCK_CD_HARNESS_CONTROL_URL", "MOCK_CD_PPU_A_ALIAS", "MOCK_CD_PPU_B_ALIAS",
                "MOCK_CD_ROUTE_ICPN", "MOCK_CD_FLASH_BASE", "MOCK_CD_FLASH_SIZE"):
        assert f"{env}=" in source
    for spec in REAL_STACK_SPECS + (HELPERS,):
        assert f"software/web/e2e/tests/{spec.name}" in source
    assert "continue-on-error: true" in source
    assert "Enforce browser acceptance result" in source
    assert "mock-cd-browser-acceptance" in source
    for forbidden in ("ssh ", "systemctl", "plasmactl deploy", "self-hosted"):
        assert forbidden not in source


def test_real_stack_specs_never_fake_or_bypass_plasma_apis() -> None:
    for spec in REAL_STACK_SPECS + (HELPERS,):
        source = spec.read_text(encoding="utf-8")
        assert "page.route(" not in source, spec.name
        # The retired Browser-owned Engineering / Batch / asset paths are only
        # ever observed to prove they are unused, never called.
        assert 'request.post("/api/batches' not in source, spec.name
        assert "Engineering Gateway URL\")).fill" not in source, spec.name


def test_managed_runtime_spec_covers_offline_recovery_per_site_epvr_and_batch_subset() -> None:
    source = SPEC.read_text(encoding="utf-8")
    assert 'page.goto("/")' in source
    assert 'page.goto("/ppu")' in source
    assert "/\\/demo$/" in source
    assert "/\\/engineering$/" in source
    assert 'getByText("SITE MATRIX"' in source
    assert 'getByText("PPU CONTROL"' in source
    # Offline / recovery is Manager-managed, driven by the harness control.
    assert 'setHarnessPpu(request, alias, "offline")' in source
    assert 'setHarnessPpu(request, alias, "online")' in source
    assert "PPU OFFLINE" in source and "PPU ONLINE" in source
    # No Gateway URL / Connect: the managed Console owns no PPU endpoint.
    assert 'getByLabel("Engineering Gateway URL")).toHaveCount(0)' in source
    # Per-Site E / P / V as Manager Batches, then Read by address / length.
    for operation in ("erase", "program", "verify"):
        assert f'"{operation}"' in source
    assert 'operation: "read"' in source
    assert "address: managed.flashBase" in source
    assert "length: managed.flashSize" in source
    assert 'waitForEvent("download")' in source
    assert "toBe(output!.filename)" in source
    assert "read_SITE" not in source
    # A non-contiguous Site subset × operations in one Manager Batch.
    assert "selectedSites = [1, 3, managed.ppuASites]" in source
    assert "settledManagerBatch(" in source and "batchRuns(" in source
    assert "/api/batches" not in source
    assert "BatchLifecycle" not in source


def test_asset_cache_spec_proves_one_image_per_batch_and_activation_once_from_manager_evidence() -> None:
    source = ASSET_CACHE_SPEC.read_text(encoding="utf-8")
    assert "1024 * 1024" in source
    assert "image_base64" in source
    assert "resource_activation" in source
    assert '"B1_UPLOAD", "B2_ADMIT", "B3_ACTIVATE"' in source
    assert "resource_reuse" in source
    assert "generation: 1" in source
    assert "page.reload()" in source
    assert "expect(traffic.legacy).toEqual([])" in source
    # Never the retired asset or Batch endpoints.
    assert "/api/programming-assets" not in source
    assert "/api/batches" not in source
    helpers = HELPERS.read_text(encoding="utf-8")
    assert 'BATCHES_PATH = "/api/manager/programming/batches"' in helpers
    assert '"/api/programming-assets"' in helpers  # observed as legacy only


def test_multi_ppu_spec_covers_shared_image_and_stop_queuing() -> None:
    source = MULTI_PPU_SPEC.read_text(encoding="utf-8")
    assert "managed.ppuA, managed.ppuB" in source
    assert "programmingJobAction(job, \"abort\")" in source
    assert "stop_requested" in source
    assert "cycles.pass).toBe(cycles.settled)" in source
    assert "/api/mock/runtime" not in source
    assert "/api/batches" not in source


def test_settings_spec_writes_through_the_manager_relay_not_the_gateway() -> None:
    source = SETTINGS_SPEC.read_text(encoding="utf-8")
    assert 'const mockRuntime = "/api/manager/ppu/api/mock/runtime"' in source
    assert "request.post(mockRuntime" in source
    assert "expect(direct.status()).toBe(401)" in source
    assert "REV ${applied.revision}" in source


def test_parity_spec_keeps_both_widths() -> None:
    source = PARITY_SPEC.read_text(encoding="utf-8")
    assert "[1200, 1680]" in source
    assert "programmingJobPresentation" in source


def test_browser_playwright_configs_keep_real_stack_suite_isolated() -> None:
    source = CONFIG.read_text(encoding="utf-8")
    assert "playwright.mock-cd.config.ts" not in source
    assert "webServer:" not in source
    assert "MOCK_CD_WEB_URL" in source
    assert "mock-cd-runtime.spec.ts" in source
    assert "engineering-programming-asset-cache-runtime.spec.ts" in source
    assert 'trace: "retain-on-failure"' in source
    assert 'video: "retain-on-failure"' in source

    default_source = DEFAULT_CONFIG.read_text(encoding="utf-8")
    assert '"mock-cd-runtime.spec.ts"' in default_source
    assert '"engineering-programming-asset-cache-runtime.spec.ts"' in default_source
