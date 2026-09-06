#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32f2_phase4_3b_discovery import (
    EXPECTED_SUBFAMILIES,
    TARGET_CONFIG,
    deterministic_targets,
    discovery_is_clean,
    read_catalog,
    read_manifest,
    resolve_mapping,
    run_discovery,
)

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "openocd-parts-canonical.csv"
MANIFEST = HERE / "stm32f2-phase4.3b-discovery-manifest.json"
SYNTHETIC = {
    "STM32F205RB": ["STM32F205RBT6"],
    "STM32F207IC": ["STM32F207ICH6", "STM32F207ICT6"],
    "STM32F215RE": ["STM32F215RET6"],
    "STM32F217IE": ["STM32F217IEH6", "STM32F217IET6"],
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


def _write_manifest(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    catalog = read_catalog(CATALOG)
    expected = [
        ("STM32F205", "STM32F205RB"),
        ("STM32F207", "STM32F207IC"),
        ("STM32F215", "STM32F215RE"),
        ("STM32F217", "STM32F217IE"),
    ]
    assert list(EXPECTED_SUBFAMILIES) == [item[0] for item in expected]
    assert deterministic_targets(catalog) == expected
    pilot_id, targets = read_manifest(MANIFEST, catalog)
    assert [(target.subfamily, target.base_device) for target in targets] == expected

    summary = run_discovery(
        pilot_id=pilot_id,
        targets=targets,
        catalog_rows=catalog,
        fetcher=_fetcher,
        evidence_builder=_evidence_builder,
    )
    assert discovery_is_clean(summary)
    assert summary["attempted"] == 4
    assert summary["active_exact_icpn_candidates"] == 6
    assert summary["canonical_mapping"] == {"unique": 4, "ambiguous": 0, "unmapped": 0}
    assert summary["manual_intervention_required"] == 0
    assert set(summary["claims"].values()) == {False}
    mappings = [item for result in summary["results"] for item in result["candidate_mappings"]]
    assert len(mappings) == 6
    assert all(item["status"] == "unique" for item in mappings)
    assert all(item["target_configs"] == [TARGET_CONFIG] for item in mappings)
    assert resolve_mapping("STM32F205RBT6TR", catalog)["status"] == "unique"
    assert resolve_mapping("STM32F205XXT6", catalog)["status"] == "unmapped"

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)

        wrong_url = copy.deepcopy(manifest)
        wrong_url["targets"][0]["source_url"] = (
            "https://www.st.com/en/microcontrollers-microprocessors/stm32f205rc.html"
        )
        wrong_url_path = root / "wrong-url.json"
        _write_manifest(wrong_url_path, wrong_url)
        try:
            read_manifest(wrong_url_path, catalog)
        except AcquisitionError:
            pass
        else:
            raise AssertionError("manifest URL slug drift must fail closed")

        wrong_selection = copy.deepcopy(manifest)
        wrong_selection["targets"][0]["base_device"] = "STM32F205RC"
        wrong_selection["targets"][0]["source_url"] = (
            "https://www.st.com/en/microcontrollers-microprocessors/stm32f205rc.html"
        )
        wrong_selection_path = root / "wrong-selection.json"
        _write_manifest(wrong_selection_path, wrong_selection)
        try:
            read_manifest(wrong_selection_path, catalog)
        except AcquisitionError:
            pass
        else:
            raise AssertionError("non-deterministic target selection must fail closed")

        drifted = copy.deepcopy(catalog)
        f2_row = next(row for row in drifted if row["plasma_series"] == "STM32F2")
        f2_row["validation_status"] = "verified"
        try:
            deterministic_targets(drifted)
        except AcquisitionError:
            pass
        else:
            raise AssertionError("OpenOCD candidate contract drift must fail closed")

    def no_active(**kwargs: object) -> dict[str, object]:
        evidence = _evidence_builder(**kwargs)
        evidence["part_number_records"] = []
        evidence["exact_icpns"] = []
        return evidence

    blocked = run_discovery(
        pilot_id=pilot_id,
        targets=targets,
        catalog_rows=catalog,
        fetcher=_fetcher,
        evidence_builder=no_active,
    )
    assert blocked["acquisition_failure"] == 4
    assert not discovery_is_clean(blocked)

    print("Phase 4.3B STM32F2 discovery contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
