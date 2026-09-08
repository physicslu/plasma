#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32f3_foundation import DEFAULT_CATALOG, TARGET_CONFIG, read_catalog
from stm32f3_phase4_4b_discovery import (
    DEFAULT_MANIFEST,
    discovery_is_clean,
    read_manifest,
    run_discovery,
)

SYNTHETIC = {
    "STM32F301C6": ["STM32F301C6T6"],
    "STM32F302C6": ["STM32F302C6T6"],
    "STM32F303C6": ["STM32F303C6T6"],
    "STM32F373C8": ["STM32F373C8T6"],
    "STM32F334C4": ["STM32F334C4T6"],
    "STM32F318C8": ["STM32F318C8T6"],
}
EXPECTED = [
    ("STM32F301", "STM32F301C6"),
    ("STM32F302", "STM32F302C6"),
    ("STM32F303", "STM32F303C6"),
    ("STM32F373", "STM32F373C8"),
    ("STM32F3x4", "STM32F334C4"),
    ("STM32F3x8", "STM32F318C8"),
]


def _fetcher(source_url: str, timeout_seconds: float):
    assert timeout_seconds > 0
    return b"synthetic rendered DOM", source_url, None, None


def _evidence_builder(**kwargs: object) -> dict[str, object]:
    base = str(kwargs["base_device"])
    exact = SYNTHETIC[base]
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
            {"icpn": value, "marketing_status": "Active", "active": True}
            for value in exact
        ],
        "excluded_non_active_part_numbers": [],
        "exact_icpns": exact,
    }


def main() -> int:
    catalog = read_catalog(DEFAULT_CATALOG)
    pilot_id, targets = read_manifest(DEFAULT_MANIFEST, catalog)
    assert pilot_id == "stm32f3-phase4.4b-official-st-discovery-2026-09-08"
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
    assert summary["canonical_mapping"] == {
        "unique": 6,
        "ambiguous": 0,
        "unmapped": 0,
    }
    assert summary["manual_intervention_required"] == 0
    assert set(summary["claims"].values()) == {False}
    for result in summary["results"]:
        assert result["canonical_mapping"]["status"] == "unique"
        assert result["canonical_mapping"]["target_configs"] == [TARGET_CONFIG]

    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temporary_directory:
        mutated = copy.deepcopy(manifest)
        mutated["targets"][0]["base_device"] = "STM32F301C8"
        mutated["targets"][0]["source_url"] = (
            "https://www.st.com/en/microcontrollers-microprocessors/stm32f301c8.html"
        )
        path = Path(temporary_directory) / "mutated-manifest.json"
        path.write_text(json.dumps(mutated), encoding="utf-8")
        try:
            read_manifest(path, catalog)
        except AcquisitionError:
            pass
        else:
            raise AssertionError("non-deterministic STM32F3 target selection must fail closed")

    def foreign_evidence(**kwargs: object) -> dict[str, object]:
        evidence = _evidence_builder(**kwargs)
        evidence["exact_icpns"] = ["STM32F303C6T6"]
        return evidence

    bad = run_discovery(
        pilot_id=pilot_id,
        targets=targets[:1],
        catalog_rows=catalog,
        fetcher=_fetcher,
        evidence_builder=foreign_evidence,
    )
    assert not discovery_is_clean(bad)
    assert bad["acquisition_failure"] == 1

    print("Phase 4.4B STM32F3 discovery contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
