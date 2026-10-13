#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "manufacturer_enrichment_scope.py"


def load_module():
    spec = importlib.util.spec_from_file_location("manufacturer_enrichment_scope", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load manufacturer_enrichment_scope.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scope_artifact(*, exact_icpns: list[str] | None = None, flash_size: str = "64 KiB", value=2) -> dict:
    return {
        "schema_version": "1.0.0",
        "scope_id": "stm32f1-fpec-test",
        "status": "research_candidate",
        "authority": "manufacturer_official_only",
        "scope_kind": "flash_controller",
        "applicability": {
            "mode": "explicit_exact_icpns",
            "exact_icpns": exact_icpns or ["STM32F103C8T6"],
        },
        "catalog_constraints": {
            "manufacturer": "STMicroelectronics",
            "family": "STM32F1",
            "flash_size": flash_size,
        },
        "source_locks": [
            {
                "source_id": "st_pm0075_rev2",
                "revision": "Rev 2",
                "sha256": "a" * 64,
                "source_kind": "manufacturer_official",
            }
        ],
        "facts": [
            {
                "path": "programming.flash_geometry.program_unit_bytes",
                "value": value,
                "evidence_source_ids": ["st_pm0075_rev2"],
            }
        ],
    }


def target(icpn: str = "STM32F103C8T6", *, flash_size: str = "64 KiB") -> dict:
    return {
        "icpn": icpn,
        "manufacturer": "STMicroelectronics",
        "family": "STM32F1",
        "base_device": "STM32F103C8",
        "package": "LQFP",
        "flash_size": flash_size,
    }


def test_explicit_exact_applicability_composes() -> None:
    module = load_module()
    result = module.compose_manufacturer_facts(target(), [scope_artifact()])
    assert result["applied_scopes"] == ["stm32f1-fpec-test"]
    assert result["facts"]["programming.flash_geometry.program_unit_bytes"] == 2


def test_family_similarity_does_not_grant_applicability() -> None:
    module = load_module()
    other = target("STM32F103R8T6")
    result = module.compose_manufacturer_facts(other, [scope_artifact(exact_icpns=["STM32F103C8T6"])])
    assert result["applied_scopes"] == []
    assert result["facts"] == {}


def test_catalog_flash_size_constraint_fails_closed() -> None:
    module = load_module()
    try:
        module.compose_manufacturer_facts(target(flash_size="128 KiB"), [scope_artifact()])
    except module.ManufacturerEnrichmentError as exc:
        assert "flash_size" in str(exc)
    else:
        raise AssertionError("catalog Flash-size mismatch must fail closed")


def test_openocd_or_other_non_manufacturer_source_is_forbidden() -> None:
    module = load_module()
    artifact = scope_artifact()
    artifact["source_locks"][0]["source_kind"] = "openocd"
    try:
        module.validate_scope_artifact(artifact)
    except module.ManufacturerEnrichmentError as exc:
        assert "non-manufacturer source" in str(exc)
    else:
        raise AssertionError("OpenOCD must not establish manufacturer facts")


def test_conflicting_reusable_scope_facts_fail_closed() -> None:
    module = load_module()
    first = scope_artifact(value=2)
    second = scope_artifact(value=4)
    second["scope_id"] = "conflicting-scope"
    try:
        module.compose_manufacturer_facts(target(), [first, second])
    except module.ManufacturerEnrichmentError as exc:
        assert "conflicting manufacturer fact" in str(exc)
    else:
        raise AssertionError("conflicting reusable scope facts must fail closed")


def test_source_revision_and_digest_are_bound() -> None:
    module = load_module()
    expected = {
        "st_pm0075_rev2": {
            "revision": "Rev 2",
            "sha256": "a" * 64,
        }
    }
    result = module.compose_manufacturer_facts(
        target(),
        [scope_artifact()],
        expected_source_locks=expected,
    )
    assert result["applied_scopes"] == ["stm32f1-fpec-test"]

    wrong_revision = copy.deepcopy(expected)
    wrong_revision["st_pm0075_rev2"]["revision"] = "Rev 3"
    try:
        module.compose_manufacturer_facts(
            target(),
            [scope_artifact()],
            expected_source_locks=wrong_revision,
        )
    except module.ManufacturerEnrichmentError as exc:
        assert "revision drift" in str(exc)
    else:
        raise AssertionError("source revision drift must fail closed")

    wrong_digest = copy.deepcopy(expected)
    wrong_digest["st_pm0075_rev2"]["sha256"] = "b" * 64
    try:
        module.compose_manufacturer_facts(
            target(),
            [scope_artifact()],
            expected_source_locks=wrong_digest,
        )
    except module.ManufacturerEnrichmentError as exc:
        assert "digest drift" in str(exc)
    else:
        raise AssertionError("source digest drift must fail closed")


def test_implicit_or_empty_applicability_is_rejected() -> None:
    module = load_module()
    implicit = scope_artifact()
    implicit["applicability"]["mode"] = "family_match"
    try:
        module.validate_scope_artifact(implicit)
    except module.ManufacturerEnrichmentError as exc:
        assert "implicit applicability" in str(exc)
    else:
        raise AssertionError("implicit family matching must be rejected")

    empty = scope_artifact()
    empty["applicability"]["exact_icpns"] = []
    try:
        module.validate_scope_artifact(empty)
    except module.ManufacturerEnrichmentError as exc:
        assert "explicit exact_icpns" in str(exc)
    else:
        raise AssertionError("empty explicit applicability must be rejected")


def main() -> int:
    test_explicit_exact_applicability_composes()
    test_family_similarity_does_not_grant_applicability()
    test_catalog_flash_size_constraint_fails_closed()
    test_openocd_or_other_non_manufacturer_source_is_forbidden()
    test_conflicting_reusable_scope_facts_fail_closed()
    test_source_revision_and_digest_are_bound()
    test_implicit_or_empty_applicability_is_rejected()
    print("Manufacturer enrichment scope tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
