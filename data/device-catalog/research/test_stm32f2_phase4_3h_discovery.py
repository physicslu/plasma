#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
import tempfile
from pathlib import Path

from device_catalog_bounded_discovery import BoundedDiscoveryError, load_batch_spec
from st_product_page_acquisition import AcquisitionError
from stm32f2_bounded_discovery import DEFAULT_REGISTRY, load_spec
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

    print("Phase 4.3H STM32F2 discovery contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
