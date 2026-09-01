from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "scripts" / "mock-cd-browser-stack.py"
WORKFLOW = ROOT / ".github" / "workflows" / "mock-cd-browser.yml"
CONFIG = ROOT / "software" / "web" / "e2e" / "playwright.mock-cd.config.ts"
DEFAULT_CONFIG = ROOT / "software" / "web" / "e2e" / "playwright.config.ts"
SPEC = ROOT / "software" / "web" / "e2e" / "tests" / "mock-cd-runtime.spec.ts"
ASSET_CACHE_SPEC = ROOT / "software" / "web" / "e2e" / "tests" / "engineering-programming-asset-cache-runtime.spec.ts"


def test_browser_stack_reuses_canonical_mock_cd_harness() -> None:
    source = STACK.read_text(encoding="utf-8")
    compile(source, str(STACK), "exec")
    assert 'BASELINE_HARNESS = ROOT / "scripts" / "mock-cd.py"' in source
    assert "load_baseline_harness()" in source
    assert "cd.PPUS" in source
    assert "cd.validate_manager_fleet" in source
    assert "cd.validate_web_fleet" in source
    assert 'output_root = work / f"{item[\'ppu_id\']}-output"' in source
    assert '"--output-root"' in source
    assert "str(output_root)" in source
    assert '"state": "ready"' in source


def test_browser_workflow_is_mock_only_and_fail_closed() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Mock CD Browser Runtime Acceptance" in source
    assert "scripts/mock-cd-browser-stack.py" in source
    assert "playwright.mock-cd.config.ts" in source
    assert "runtime.json" in source
    assert "engineering_1mib_programming_asset_cache_reuse_and_reconnect" in source
    assert "continue-on-error: true" in source
    assert "Enforce browser acceptance result" in source
    assert "mock-cd-browser-acceptance" in source
    for forbidden in ("ssh ", "systemctl", "plasmactl deploy", "self-hosted"):
        assert forbidden not in source


def test_browser_spec_moves_real_runtime_acceptance_to_emode_without_api_route_mocking() -> None:
    source = SPEC.read_text(encoding="utf-8")
    assert "page.route(" not in source
    assert "MOCK_CD_GATEWAY_URL" in source
    assert "MOCK_CD_UNREACHABLE_GATEWAY_URL" in source
    assert "MOCK_CD_ENGINEERING_FACILITY_ID" in source
    assert "MOCK_CD_ENGINEERING_PPU_ID" in source
    assert 'page.goto("/")' in source
    assert 'page.goto("/ppu")' in source
    assert "/\\/demo$/" in source
    assert "/\\/engineering$/" in source
    assert 'getByText("SITE MATRIX"' in source
    assert 'getByText("PPU CONTROL"' in source
    assert 'getByLabel("Engineering Gateway URL")' in source
    assert ".engineeringGateway" in source
    assert "openEngineeringProgramming" in source
    assert "Engineering Programming Image Asset file" in source
    for operation in ("erase", "program", "verify", "read"):
        assert f'"{operation}"' in source
    assert "waitForEvent(\"download\")" in source
    assert "read_SITE${siteId}_main_flash.bin" in source
    assert 'url.pathname !== "/api/batches"' in source
    assert "setEngineeringBatchSites" in source
    assert "setEngineeringBatchOperations" in source
    assert "[BATCH] SUCCESS" in source
    assert "BatchLifecycle" not in source
    assert "representativeSelections" not in source


def test_engineering_asset_cache_spec_uses_real_gateway_without_route_mocking() -> None:
    source = ASSET_CACHE_SPEC.read_text(encoding="utf-8")
    assert "page.route(" not in source
    assert "1024 * 1024" in source

    # Engineering programming now submits its Image through the server-owned Batch API.
    assert 'url.pathname === "/api/batches"' in source
    assert "counters.batches" in source

    # Legacy asset endpoints are observed only to prove that the active path does not use them.
    assert "api/programming-assets/check" in source
    assert "counters.legacyAssetChecks" in source
    assert "counters.legacyAssetUploads" in source
    assert "expect(counters.legacyAssetChecks).toBe(0)" in source
    assert "expect(counters.legacyAssetUploads).toBe(0)" in source

    # Reconnect must retain the Engineering session contract.
    assert "previous_session_id" in source

    # The Programming Image is carried as the Batch asset, using canonical asset fields.
    assert "const firstAsset = firstBatch.asset" in source
    assert 'expect(typeof firstAsset.asset_base64).toBe("string")' in source
    assert 'expect(typeof firstAsset.asset_sha256).toBe("string")' in source
    assert 'expect(Object.hasOwn(firstAsset, "image_sha256")).toBe(false)' in source

    # The active Engineering path must not fall back to direct per-site jobs.
    assert "expect(counters.directJobs).toBe(0)" in source


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
