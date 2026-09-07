#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
import tempfile
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32f2_phase4_3b_discovery import TARGET_CONFIG, resolve_mapping
from stm32f2_phase4_3e_discovery import (
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
    ("STM32F205", "STM32F205RC"),
    ("STM32F207", "STM32F207IE"),
    ("STM32F215", "STM32F215RG"),
    ("STM32F217", "STM32F217IG"),
]
SYNTHETIC = {
    "STM32F205RC": ["STM32F205RCT6"],
    "STM32F207IE": ["STM32F207IEH6", "STM32F207IET6"],
    "STM32F215RG": ["STM32F215RGT6"],
    "STM32F217IG": ["STM32F217IGH6", "STM32F217IGT6"],
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
    assert resolve_mapping("STM32F217IGH6", catalog)["status"] == "unique"

    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temporary_directory:
        wrong = copy.deepcopy(manifest)
        wrong["targets"][0]["base_device"] = "STM32F205RE"
        wrong["targets"][0]["source_url"] = "https://www.st.com/en/microcontrollers-microprocessors/stm32f205re.html"
        path = Path(temporary_directory) / "wrong.json"
        path.write_text(json.dumps(wrong), encoding="utf-8")
        try:
            read_manifest(path, catalog, production_bases)
        except AcquisitionError:
            pass
        else:
            raise AssertionError("non-deterministic Phase 4.3E selection must fail closed")

        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames
            rows = list(reader)
        assert fields is not None
        rows.append({**rows[0], "base_device": "STM32F205RC", "icpn": "STM32F205RCT6"})
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

    print("Phase 4.3E STM32F2 discovery contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
