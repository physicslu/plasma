#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
import shutil
import tempfile
from pathlib import Path

from device_catalog_bounded_discovery import BoundedDiscoveryError, load_batch_spec
from device_catalog_bounded_planning import BoundedPlanningError
from st_product_page_acquisition import AcquisitionError
from stm32f2_bounded_discovery import (
    DEFAULT_REGISTRY,
    build_next_batch_plan,
    load_spec,
    materialize_next_batch_plan,
)
from stm32f2_phase4_3b_discovery import TARGET_CONFIG, resolve_mapping
from stm32f2_phase4_3h_discovery import (
    DEFAULT_CANONICAL,
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    deterministic_targets,
    discovery_is_clean,
    read_catalog,
    read_manifest,
    read_production_bases,
    run_discovery,
)

EXPECTED = [
    ("STM32F205", "STM32F205RE"),
    ("STM32F207", "STM32F207IF"),
    ("STM32F215", "STM32F215VE"),
    ("STM32F217", "STM32F217VE"),
]
SYNTHETIC = {
    "STM32F205RE": ["STM32F205RET6", "STM32F205REY6"],
    "STM32F207IF": ["STM32F207IFH6", "STM32F207IFT6"],
    "STM32F215VE": ["STM32F215VET6"],
    "STM32F217VE": ["STM32F217VET6"],
}


def _fetcher(source_url: str, timeout_seconds: float) -> tuple[bytes, str, None, None]:
    assert timeout_seconds > 0
    return b"synthetic rendered DOM", source_url, None, None


def _evidence_builder(**kwargs: object) -> dict[str, object]:
    base = str(kwargs["base_device"])
    return {
        "schema_version": 1,
        "parser_version": 2,
        "acquisition_transport": "chromium_rendered_dom",
        "source_url": str(kwargs["source_url"]),
        "final_url": str(kwargs["final_url"]),
        "base_device": base,
        "retrieved_at_utc": str(kwargs["retrieved_at_utc"]),
        "rendered_dom_sha256": "a" * 64,
        "evidence_section_sha256": "b" * 64,
        "evidence_surface": "quality_and_reliability_part_number",
        "part_number_records": [
            {"icpn": icpn, "marketing_status": "Active", "active": True}
            for icpn in SYNTHETIC[base]
        ],
        "excluded_non_active_part_numbers": [],
        "exact_icpns": list(SYNTHETIC[base]),
    }


def _assert_next_batch_planning() -> None:
    phase = "4.3Z"
    acquisition_date = "2026-09-08"
    plan = build_next_batch_plan(
        phase=phase,
        acquisition_date=acquisition_date,
    )
    assert plan["family"] == "STM32F2"
    assert plan["phase"] == phase
    assert plan["inputs"]["production_exact_icpn_count"] == 22
    assert plan["inputs"]["production_base_device_count"] == 8
    assert (
        plan["registry_entry"]["expected_production_sha256"]
        == "1706ab65dccb112a7ff907d82cf07c5ef6a46110097746aaeb5f3f9aed17c5cb"
    )
    assert [
        (target["subfamily"], target["base_device"])
        for target in plan["manifest"]["targets"]
    ] == EXPECTED
    assert (
        plan["manifest"]["pilot_id"]
        == "stm32f2-phase4.3z-official-st-discovery-2026-09-08"
    )
    assert (
        plan["registry_entry"]["manifest"]
        == "stm32f2-phase4.3z-discovery-manifest.json"
    )
    assert (
        plan["registry_entry"]["baseline"]
        == "stm32f2-phase4.3z-discovery-baseline.json"
    )
    assert plan["registry_entry"]["evidence_dir"].endswith(
        "stm32f2-phase4.3z-official-st-discovery-live-2026-09-08"
    )

    try:
        build_next_batch_plan(phase="4.3H", acquisition_date=acquisition_date)
    except BoundedPlanningError:
        pass
    else:
        raise AssertionError("planner must refuse an already registered phase")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        registry_path = root / DEFAULT_REGISTRY.name
        shutil.copyfile(DEFAULT_REGISTRY, registry_path)

        materializable = build_next_batch_plan(
            phase=phase,
            acquisition_date=acquisition_date,
            registry_path=registry_path,
        )
        plan_path = root / "next-batch-plan.json"
        plan_path.write_text(
            json.dumps(materializable, indent=2) + "\n",
            encoding="utf-8",
        )
        report = materialize_next_batch_plan(
            plan_path=plan_path,
            registry_path=registry_path,
            root=root,
        )
        assert report["status"] == "materialized"
        assert report["canonical_dataset_admission"] is False

        registry_after = json.loads(registry_path.read_text(encoding="utf-8"))
        assert registry_after["batches"][phase] == materializable["registry_entry"]
        manifest_path = root / materializable["registry_entry"]["manifest"]
        assert json.loads(manifest_path.read_text(encoding="utf-8")) == materializable["manifest"]

        try:
            materialize_next_batch_plan(
                plan_path=plan_path,
                registry_path=registry_path,
                root=root,
            )
        except BoundedPlanningError:
            pass
        else:
            raise AssertionError("materializer must refuse an already registered phase")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        registry_path = root / DEFAULT_REGISTRY.name
        shutil.copyfile(DEFAULT_REGISTRY, registry_path)
        clean_plan = build_next_batch_plan(
            phase=phase,
            acquisition_date=acquisition_date,
            registry_path=registry_path,
        )
        mutated = copy.deepcopy(clean_plan)
        mutated["manifest"]["targets"][0]["base_device"] = "STM32F205RF"
        plan_path = root / "mutated-plan.json"
        plan_path.write_text(json.dumps(mutated), encoding="utf-8")
        try:
            materialize_next_batch_plan(
                plan_path=plan_path,
                registry_path=registry_path,
                root=root,
            )
        except BoundedPlanningError:
            pass
        else:
            raise AssertionError("materializer must fail closed on plan target drift")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        registry_path = root / DEFAULT_REGISTRY.name
        canonical_path = root / DEFAULT_CANONICAL.name
        shutil.copyfile(DEFAULT_REGISTRY, registry_path)
        shutil.copyfile(DEFAULT_CANONICAL, canonical_path)

        stale_plan = build_next_batch_plan(
            phase=phase,
            acquisition_date=acquisition_date,
            registry_path=registry_path,
            canonical_path=canonical_path,
        )
        plan_path = root / "stale-plan.json"
        plan_path.write_text(json.dumps(stale_plan), encoding="utf-8")

        with canonical_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            rows = list(reader)
        assert fields is not None
        rows[0]["icpn"] = "STM32F205RBT8"
        with canonical_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

        try:
            materialize_next_batch_plan(
                plan_path=plan_path,
                registry_path=registry_path,
                canonical_path=canonical_path,
                root=root,
            )
        except BoundedPlanningError:
            pass
        else:
            raise AssertionError("stale Production-bound plan must fail closed")


def main() -> int:
    catalog = read_catalog(DEFAULT_CATALOG)
    production_bases = read_production_bases(DEFAULT_CANONICAL)
    assert deterministic_targets(catalog, production_bases) == EXPECTED
    pilot_id, targets = read_manifest(DEFAULT_MANIFEST, catalog, production_bases)
    assert [(target.subfamily, target.base_device) for target in targets] == EXPECTED

    summary = run_discovery(
        pilot_id=pilot_id,
        targets=targets,
        catalog_rows=catalog,
        fetcher=_fetcher,
        evidence_builder=_evidence_builder,
    )
    assert discovery_is_clean(summary)
    assert summary["active_exact_icpn_candidates"] == 6
    assert summary["canonical_mapping"] == {"unique": 4, "ambiguous": 0, "unmapped": 0}
    assert set(summary["claims"].values()) == {False}
    mappings = [item for result in summary["results"] for item in result["candidate_mappings"]]
    assert len(mappings) == 6
    assert all(item["status"] == "unique" for item in mappings)
    assert all(item["target_configs"] == [TARGET_CONFIG] for item in mappings)
    assert resolve_mapping("STM32F217VET6", catalog)["status"] == "unique"

    # The generic registry must preserve both historical bounded batches without
    # requiring another phase-specific implementation.
    assert load_spec("4.3E").phase == "4.3E"
    assert load_spec("4.3H").manifest_path == DEFAULT_MANIFEST

    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    registry = json.loads(DEFAULT_REGISTRY.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temporary_directory:
        wrong = copy.deepcopy(manifest)
        wrong["targets"][0]["base_device"] = "STM32F205RF"
        wrong["targets"][0]["source_url"] = "https://www.st.com/en/microcontrollers-microprocessors/stm32f205rf.html"
        path = Path(temporary_directory) / "wrong.json"
        path.write_text(json.dumps(wrong), encoding="utf-8")
        try:
            read_manifest(path, catalog, production_bases)
        except AcquisitionError:
            pass
        else:
            raise AssertionError("non-deterministic Phase 4.3H selection must fail closed")

        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            rows = list(reader)
        assert fields is not None
        rows[0]["icpn"] = "STM32F205RBT8"
        drifted = Path(temporary_directory) / "drifted.csv"
        with drifted.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        try:
            read_production_bases(drifted)
        except AcquisitionError:
            pass
        else:
            raise AssertionError("Production boundary drift must fail closed")

        registry_drift = copy.deepcopy(registry)
        registry_drift["batches"]["4.3H"]["expected_production_sha256"] = "0" * 64
        registry_path = Path(temporary_directory) / "registry.json"
        registry_path.write_text(json.dumps(registry_drift), encoding="utf-8")
        spec = load_batch_spec(
            registry_path=registry_path,
            family="STM32F2",
            phase="4.3H",
            root=DEFAULT_REGISTRY.parent,
        )
        try:
            from stm32f2_bounded_discovery import read_production_bases as generic_read_production_bases

            generic_read_production_bases(DEFAULT_CANONICAL, spec=spec)
        except AcquisitionError:
            pass
        else:
            raise AssertionError("registry Production boundary drift must fail closed")

        wrong_family = copy.deepcopy(registry)
        wrong_family["family"] = "STM32F3"
        registry_path.write_text(json.dumps(wrong_family), encoding="utf-8")
        try:
            load_batch_spec(
                registry_path=registry_path,
                family="STM32F2",
                phase="4.3H",
                root=DEFAULT_REGISTRY.parent,
            )
        except BoundedDiscoveryError:
            pass
        else:
            raise AssertionError("registry family drift must fail closed")

    _assert_next_batch_planning()

    print("Phase 4.3H STM32F2 discovery contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
