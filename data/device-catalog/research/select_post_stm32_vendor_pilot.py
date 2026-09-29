#!/usr/bin/env python3
"""Choose a bounded, cross-vendor ICPN research pilot after STM32 wireless publication.

This is a sequencing-only gate, not catalog admission or programming support.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE / "openocd-parts-canonical.csv"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
NXP_SOURCE_LOCK = ROOT / "data/ic-support/benchmarks/nxp-kl25/source-lock.json"

EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_PRODUCTION_BLOB = "c8012b211a28b0a7811bfe978e7e697bc169c6f3"
EXPECTED_NXP_SOURCE_LOCK_BLOB = "4927139f202bee1ee3e813ef57e3cfdfd3333ba6"

EXPECTED_NXP_PATTERNS = (
    "MKL25Z128xxx4",
    "MKL25Z32xxx4",
    "MKL25Z64xxx4",
)
EXEMPLAR = "MKL25Z128VLK4"
EXPECTED_ST_WIRELESS = {
    "STM32WBA2X": 14,
    "STM32WLX": 31,
    "STM32WBX": 50,
    "STM32WBA5X": 40,
    "STM32WBA6X": 39,
}

def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)

def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()

def match_pattern(pattern: str, part: str) -> bool:
    return len(pattern) == len(part) and all(
        p == "x" or p == c for p, c in zip(pattern, part)
    )

def render() -> dict[str, Any]:
    source_bytes = SOURCE.read_bytes()
    production_bytes = PRODUCTION.read_bytes()
    lock_bytes = NXP_SOURCE_LOCK.read_bytes()
    require(hashlib.sha256(source_bytes).hexdigest() == EXPECTED_SOURCE_SHA256,
            "frozen OpenOCD canonical research inventory drifted")
    require(git_blob_sha(production_bytes) == EXPECTED_PRODUCTION_BLOB,
            "Production prestate drifted; reselect from current main")
    require(git_blob_sha(lock_bytes) == EXPECTED_NXP_SOURCE_LOCK_BLOB,
            "NXP manufacturer document source lock drifted")
    production = json.loads(production_bytes)
    lock = json.loads(lock_bytes)
    require(production.get("status") == "production" and
            production.get("selection_policy") == "admitted_exact_manufacturer_part_number_only",
            "Production contract drifted")
    sources = production.get("sources")
    require(isinstance(sources, list) and len(sources) == 23, "Production family boundary drifted")
    require(sum(int(s["row_count"]) for s in sources) == 2683, "Production exact ICPN boundary drifted")
    require({s["manufacturer"] for s in sources} == {"STMicroelectronics"},
            "cross-vendor Production prestate changed")
    by_family = {s["family"]: int(s["row_count"]) for s in sources}
    require(all(by_family.get(k) == v for k, v in EXPECTED_ST_WIRELESS.items()),
            "already-published STM32 wireless frontier drifted")
    require("STM32W108" not in by_family and "KL25" not in by_family,
            "deferred/selected candidate already in Production")

    require(lock.get("source_lock_id") == "nxp-kl25-source-lock-v0", "NXP source lock ID drifted")
    require(lock.get("targets") == [EXEMPLAR], "reviewed exact exemplar drifted")
    docs = lock.get("sources")
    require(isinstance(docs, list) and len(docs) == 2, "NXP source evidence set drifted")
    require({(d["source_id"], d["document_number"], str(d["revision"])) for d in docs} == {
        ("nxp_kl25_ds_rev5", "KL25P80M48SF0", "5"),
        ("nxp_kl25_rm_rev3", "KL25P80M48SF0RM", "3"),
    }, "reviewed NXP official document identities drifted")
    require(all(d.get("authority") == "manufacturer_official" and
                d.get("integrity", {}).get("algorithm") == "sha256" and
                len(d.get("integrity", {}).get("digest", "")) == 64 for d in docs),
            "NXP manufacturer source provenance incomplete")
    require(lock.get("trust_boundary", {}).get("production_admission") is False,
            "previous source lock trust boundary changed")

    rows = list(csv.DictReader(source_bytes.decode("utf-8").splitlines()))
    w108 = [r for r in rows if r["vendor"] == "STMicroelectronics" and
            r["plasma_series"] == "STM32W108"]
    require(len(w108) == 1 and
            w108[0]["part_number"] == "STM32W108C8" and
            w108[0]["identifier_kind"] == "cmsis_device_name" and
            w108[0]["target_config"] == "tcl/target/stm32w108xx.cfg",
            "historical STM32W108 structural exception drifted")

    nxp = [r for r in rows if r["vendor"] == "NXP"]
    require(len(nxp) == 380, "frozen NXP research surface drifted")
    kl25 = [r for r in nxp if r["plasma_series"] == "KL25"]
    patterns = tuple(sorted(r["part_number"] for r in kl25))
    require(patterns == EXPECTED_NXP_PATTERNS, "bounded KL25 pattern set drifted")
    require(len(kl25) == 3 and all(
        r["identifier_kind"] == "ordering_pattern" and
        r["target_config"] == "tcl/target/kl25.cfg" and
        r["openocd_distribution"] == "upstream-openocd" and
        r["mapping_status"] == "mapping_candidate" and
        r["validation_status"] == "not_verified"
        for r in kl25), "KL25 candidate route/validation surface drifted")
    matching = [p for p in patterns if match_pattern(p, EXEMPLAR)]
    require(matching == ["MKL25Z128xxx4"],
            "manufacturer-reviewed exact exemplar is not uniquely covered by frozen KL25 pattern")

    return {
        "schema_version": 1,
        "selection_id": "post-stm32-nxp-kl25-bounded-cross-vendor-pilot-v1",
        "scope": "research_only_cross_vendor_sequencing",
        "status": "selected_for_official_manufacturer_evidence_accessibility_only",
        "policy": {
            "type": "explicit_bounded_cross_vendor_pilot",
            "not_a_global_vendor_ranking": True,
            "criteria": [
                "not already included in Production manifest",
                "one pinned authoritative manufacturer source lock for an exact commercial identity",
                "exact identity matches precisely one frozen canonical ordering pattern",
                "one declared OpenOCD target configuration",
                "legacy software execution evidence does not grant catalog or runtime permission",
            ],
        },
        "production_prestate": {
            "exact_icpns": 2683,
            "families": 23,
            "manifest_git_blob_sha": EXPECTED_PRODUCTION_BLOB,
            "manufacturer_scope": ["STMicroelectronics"],
            "already_published_wireless": EXPECTED_ST_WIRELESS,
        },
        "stm32_residual_exception": {
            "plasma_series": "STM32W108",
            "frozen_identifier": "STM32W108C8",
            "kind": "cmsis_device_name",
            "disposition": "deferred_structural_gate_not_an_active_exact_icpn",
            "reasons": ["no_ordering_pattern_rows", "no_bounded_subfamilies",
                        "no_retained_current_active_commercial_identity_evidence"],
            "historical_candidate_preserved": True,
        },
        "selected": {
            "manufacturer": "NXP",
            "family": "KL25",
            "target_config": "tcl/target/kl25.cfg",
            "candidate_kind": "ordering_pattern",
            "frozen_manufacturer_rows": 380,
            "selected_rows": 3,
            "ordering_patterns": list(EXPECTED_NXP_PATTERNS),
            "source_lock": "data/ic-support/benchmarks/nxp-kl25/source-lock.json",
            "source_lock_git_blob_sha": EXPECTED_NXP_SOURCE_LOCK_BLOB,
            "reviewed_exact_representative": EXEMPLAR,
            "matching_pattern": "MKL25Z128xxx4",
            "manufacturer_source_documents": [
                {"document": "KL25P80M48SF0", "revision": "5", "role": "datasheet"},
                {"document": "KL25P80M48SF0RM", "revision": "3", "role": "reference_manual"},
            ],
            "current_public_product_reference": {
                "url": "https://www.nxp.com/products/KL2x?tab=Package_Quality_Tab",
                "reference_identity": EXEMPLAR,
                "reference_status": "Active",
                "retained_live_acquisition_completed": False,
                "note": "External manufacturer product listing is an accessibility lead, not retained exact-family admission evidence.",
            },
        },
        "next_gate": "nxp-kl25-bounded-official-manufacturer-current-commercial-evidence-accessibility-gate",
        "claims": {
            "full_exact_icpn_discovery_completed": False,
            "identity_admission_ready": False,
            "catalog_admission_ready": False,
            "production_write_authorized": False,
            "production_publication_authorized": False,
            "software_executor_admission_implies_catalog_admission": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "target_execution_authorized": False,
            "physical_validation_claimed": False,
            "hil_required_for_catalog_admission": False,
            "stm32w108_rejected": False,
        },
    }

def main() -> int:
    print(json.dumps(render(), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
