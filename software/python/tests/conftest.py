"""Offline SQLite authority for legacy Phase 42/43 REST Catalog regression tests.

Only the REST tests get a qualified, explicit Catalog. Missing-DB/fail-closed
tests outside these legacy modules remain unconfigured by design.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def _phase_rest_qualified_catalog(tmp_path_factory: pytest.TempPathFactory) -> Path:
    from plasma_web.catalog_sqlite_repository import CatalogSqliteShadowRepository
    from plasma_web.device_catalog import default_catalog_manifest_path
    from plasma_web.programming_qualification import get_default_programming_qualification_registry

    database = tmp_path_factory.mktemp("phase-rest-qualified-catalog") / "catalog.db"
    CatalogSqliteShadowRepository(database).import_verified_manifest(
        default_catalog_manifest_path(),
        qualification_registry=get_default_programming_qualification_registry(),
    )
    return database


@pytest.fixture(autouse=True)
def _provision_legacy_phase_rest_catalog(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = request.module.__name__.rsplit(".", 1)[-1]
    if not module.startswith(("test_device_catalog_phase42", "test_device_catalog_phase43")):
        return
    if "rest_catalog" not in request.node.name:
        return
    database = request.getfixturevalue("_phase_rest_qualified_catalog")
    monkeypatch.setenv("PLASMA_CATALOG_SQLITE_DB", str(database))


# CI routing keeps slow packaging and ICPN/SQLite qualification out of the
# ordinary SW/PPU regression. Local pytest (no --plasma-ci-suite) still runs all
# tests. The categories are disjoint and own the test selection in one place.
from fnmatch import fnmatchcase

_CI_PACKAGING_FILES = frozenset({
    "test_control_station_runtime.py",
    "test_control_station_release.py",
    "test_macos_control_station_installer.py",
    "test_windows_control_station_installer.py",
    "test_product_release.py",
    "test_product_release_canonical_paths.py",
})
# Dedicated long-session Batch Coordinator / Journal stress cases; ordinary
# programming CI still covers short Repeat/Retry/Stop/SAFE_OFF regressions.
_CI_BATCH_STRESS_CASES = frozenset({
    "test_t04_repeat_100_accumulates_every_cycle",
    "test_long_session_keeps_every_cycle_with_bounded_memory_and_journal",
    "test_t21_status_and_history_reads_stay_bounded",
})
_CI_PACKAGING_MANAGER_CASES = frozenset({
    "test_packaged_manager_serves_selector_from_its_own_catalog",
    "test_catalog_export_is_raw_git_blob_bytes_even_with_autocrlf",
})
_CI_ICPN_SQLITE_PATTERNS = (
    "test_catalog_*.py",
    "test_device_catalog*.py",
    "test_ic_selector_*.py",
    "test_icpn_*.py",
    "test_manager_sqlite_selector.py",
    "test_manager_device_selector.py",
    "test_manufacturer_device_basic.py",
    "test_microchip_*.py",
    "test_nxp_*.py",
    "test_programming_qualification.py",
    "test_route_evidence_admission.py",
    "test_physical_compatibility_l3.py",
)


def _plasma_ci_test_suite(item: pytest.Item) -> str:
    filename = item.path.name
    test_name = getattr(item, "originalname", None) or item.name.split("[", 1)[0]
    if filename == "test_programming_batch_repeat.py" and test_name in _CI_BATCH_STRESS_CASES:
        return "batch-stress"
    if filename in _CI_PACKAGING_FILES or (
        filename == "test_manager_device_selector.py"
        and test_name in _CI_PACKAGING_MANAGER_CASES
    ):
        return "packaging"
    if any(fnmatchcase(filename, pattern) for pattern in _CI_ICPN_SQLITE_PATTERNS):
        return "icpn-sqlite"
    return "general"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--plasma-ci-suite",
        choices=("general", "icpn-sqlite", "packaging", "batch-stress"),
        default=None,
        help="Select a disjoint PLASMA CI test suite; absent means all tests",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    suite = config.getoption("--plasma-ci-suite")
    if suite is None:
        return
    selected = [item for item in items if _plasma_ci_test_suite(item) == suite]
    deselected = [item for item in items if _plasma_ci_test_suite(item) != suite]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected
