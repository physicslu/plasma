from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
STACK = ROOT / "scripts" / "mock-cd-browser-stack.py"
WORKFLOW = ROOT / ".github" / "workflows" / "mock-cd-browser.yml"
CONFIG = ROOT / "software" / "web" / "e2e" / "playwright.mock-cd.config.ts"
DEFAULT_CONFIG = ROOT / "software" / "web" / "e2e" / "playwright.config.ts"
SPEC = ROOT / "software" / "web" / "e2e" / "tests" / "mock-cd-runtime.spec.ts"
CACHE_SPEC = ROOT / "software" / "web" / "e2e" / "tests" / "engineering-firmware-cache-runtime.spec.ts"


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
    assert 'stream.write(f"MOCK_CD_EXPECTED_SITES={payload[\'enabled_sites\']}\\n")' in source
    assert "engineering_1mib_firmware_cache_reuse_and_reconnect" in source
    assert "continue-on-error: true" in source
    assert "Enforce browser acceptance result" in source
    assert "mock-cd-browser-acceptance" in source
    for forbidden in ("ssh ", "systemctl", "plasmactl deploy", "self-hosted"):
        assert forbidden not in source


def test_browser_spec_uses_real_gateway_without_api_route_mocking() -> None:
    source = SPEC.read_text(encoding="utf-8")
    assert "page.route(" not in source
    assert "MOCK_CD_GATEWAY_URL" in source
    assert "MOCK_CD_UNREACHABLE_GATEWAY_URL" in source
    assert "MOCK_CD_EXPECTED_PPU_ID" in source
    assert "Plasma Web REST Gateway offline" in source
    assert "Plasma Web REST Gateway connected" in source
    assert 'for (let siteId = 1; siteId <= expectedSites; siteId += 1)' in source
    for operation in ("erase", "program", "verify", "read"):
        assert f'"{operation}"' in source
    assert "waitForEvent(\"download\")" in source
    assert "read_SITE${siteId}_flash.bin" in source
    assert "bytes.equals(firmware)" in source
    assert "representativeSelections(expectedSites)" in source
    assert "runBatchAndAssert" in source
    assert "selectedSites.length * operations.length" in source
    assert "starts.slice(before)" in source
    assert "expectedSummary" in source
    assert "expectedCompleteCount" not in source
    assert "siteId % 2" not in source


def test_engineering_cache_spec_uses_real_gateway_without_route_mocking() -> None:
    source = CACHE_SPEC.read_text(encoding="utf-8")
    assert "page.route(" not in source
    assert "1024 * 1024" in source
    assert "api/firmware/check" in source
    assert "counters.uploads" in source
    assert "previous_session_id" in source
    assert 'Object.hasOwn(body, "firmware_base64")' in source


def test_browser_playwright_configs_keep_real_stack_suite_isolated() -> None:
    source = CONFIG.read_text(encoding="utf-8")
    assert "playwright.mock-cd.config.ts" not in source
    assert "webServer:" not in source
    assert "MOCK_CD_WEB_URL" in source
    assert "mock-cd-runtime.spec.ts" in source
    assert "engineering-firmware-cache-runtime.spec.ts" in source
    assert 'trace: "retain-on-failure"' in source
    assert 'video: "retain-on-failure"' in source

    default_source = DEFAULT_CONFIG.read_text(encoding="utf-8")
    assert '"mock-cd-runtime.spec.ts"' in default_source
    assert '"engineering-firmware-cache-runtime.spec.ts"' in default_source
