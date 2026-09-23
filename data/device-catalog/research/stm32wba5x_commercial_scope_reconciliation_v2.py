#!/usr/bin/env python3
"""Reconcile STM32WBA5X current commercial scope after STM32WBA55HE discovery block."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from stm32_post_u0_evidence_probe import base_from_ordering_pattern

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "openocd-parts-canonical.csv"
PRIOR = HERE / "stm32wba5x-commercial-scope-reconciliation.json"
PRESTATE = HERE / "stm32wba5x-commercial-scope-reconciliation-v2-production-prestate.json"
EVIDENCE_DIR = HERE / "evidence" / "stm32wba5x-discovery-block-live-2026-09-23"
SUMMARY = EVIDENCE_DIR / "discovery-summary.json"
PROVENANCE = EVIDENCE_DIR / "provenance.json"
TARGETS = EVIDENCE_DIR / "targets.json"
HG_EVIDENCE = EVIDENCE_DIR / "stm32wba55hg.json"

EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_PRIOR_BLOB = "d1e354abb390e968e10e2723517747041c2a2439"
EXPECTED_PRODUCTION_BLOB = "6e0fc69bec067259a1c52e150a313591cf4523e8"
EXPECTED_SUMMARY_BLOB = "dafc09228f27df49da693c5c21860b48366bce5b"
EXPECTED_PROVENANCE_BLOB = "1de7f35c33e8da83078d0a69e857091c26b534d2"
EXPECTED_TARGETS_BLOB = "789a4fe0ab498057e91789d4039532104b5e505c"
EXPECTED_HG_BLOB = "09843e1c37e6f37b8dd1cef16eb1fea4e32bfe95"

EXCLUDED = {
    ("STM32WBA50KEUx", "ordering_pattern"),
    ("STM32WBA50KEUxT", "cmsis_device_name"),
    ("STM32WBA55HEFx", "ordering_pattern"),
}

EXPECTED_BASES = (
    "STM32WBA50KG",
    "STM32WBA52CE", "STM32WBA52CG", "STM32WBA52KE", "STM32WBA52KG",
    "STM32WBA54CE", "STM32WBA54CG", "STM32WBA54KE", "STM32WBA54KG",
    "STM32WBA55CE", "STM32WBA55CG", "STM32WBA55HG", "STM32WBA55UE", "STM32WBA55UG",
    "STM32WBA5MMG",
)

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()

def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value

def render() -> dict[str, Any]:
    req(sha256(SOURCE) == EXPECTED_SOURCE_SHA256, "candidate source digest drifted")
    req(git_blob_sha(PRIOR) == EXPECTED_PRIOR_BLOB, "prior reconciliation blob drifted")
    req(git_blob_sha(PRESTATE) == EXPECTED_PRODUCTION_BLOB, "Production prestate blob drifted")
    req(git_blob_sha(SUMMARY) == EXPECTED_SUMMARY_BLOB, "discovery summary blob drifted")
    req(git_blob_sha(PROVENANCE) == EXPECTED_PROVENANCE_BLOB, "discovery provenance blob drifted")
    req(git_blob_sha(TARGETS) == EXPECTED_TARGETS_BLOB, "discovery targets blob drifted")
    req(git_blob_sha(HG_EVIDENCE) == EXPECTED_HG_BLOB, "STM32WBA55HG evidence blob drifted")

    prior = load_json(PRIOR)
    req(prior.get("reconciliation_id") == "stm32wba5x-current-commercial-scope-reconciliation-v1", "prior reconciliation id drifted")
    prior_surface = prior.get("reconciled_surface") or {}
    req(
        prior_surface.get("retained_rows") == 32
        and prior_surface.get("ordering_pattern_rows") == 16
        and prior_surface.get("cmsis_device_name_rows") == 16
        and prior_surface.get("base_device_count") == 16,
        "prior reconciled surface drifted",
    )
    req("STM32WBA55HE" in prior_surface.get("base_devices", []), "prior STM32WBA55HE surface missing")

    prod = load_json(PRESTATE)
    sources = prod.get("sources")
    req(
        isinstance(sources, list)
        and sum(int(x["row_count"]) for x in sources) == 2604
        and len(sources) == 21,
        "Production boundary drifted",
    )
    req(all(x.get("family") != "STM32WBA5X" for x in sources), "STM32WBA5X unexpectedly in Production")

    summary = load_json(SUMMARY)
    req(summary.get("discovery_id") == "stm32wba5x-bounded-exact-icpn-discovery-v1", "discovery id drifted")
    req(summary.get("attempted_targets") == 16, "discovery target count drifted")
    req(summary.get("successful_targets") == 15, "discovery success count drifted")
    req(summary.get("manual_review_targets") == 1, "discovery manual review count drifted")
    req(summary.get("status") == "blocked_manual_review", "discovery block status drifted")
    results = summary.get("results")
    req(isinstance(results, list) and len(results) == 16, "discovery results drifted")
    observed = {row.get("base_device"): row for row in results if isinstance(row, dict)}
    he = observed.get("STM32WBA55HE") or {}
    req(
        he.get("acquisition_status") == "failure"
        and he.get("commercial_identity_status") == "unverified"
        and he.get("error") == "browser navigation returned HTTP 404"
        and he.get("manual_intervention_required") is True,
        "STM32WBA55HE live blocker drifted",
    )
    hg = observed.get("STM32WBA55HG") or {}
    req(
        hg.get("acquisition_status") == "success"
        and hg.get("active_exact_icpns") == ["STM32WBA55HGF6TR", "STM32WBA55HGF7TR"],
        "STM32WBA55HG active sibling evidence drifted",
    )
    req(load_json(HG_EVIDENCE) == hg.get("evidence"), "retained STM32WBA55HG evidence differs from summary")

    provenance = load_json(PROVENANCE)
    req(provenance.get("workflow_run_id") == 35815561803, "discovery run provenance drifted")
    req(provenance.get("executed_git_sha") == "20536418aa52dc244ca5353ec64264550a6605ac", "discovery executed head drifted")
    req(provenance.get("browser_version") == "151.0.7922.34", "browser version drifted")

    targets = load_json(TARGETS)
    req(targets.get("base_device_count") == 16, "retained target count drifted")
    target_rows = targets.get("targets")
    req(isinstance(target_rows, list), "retained targets missing")
    req(any(x.get("base_device") == "STM32WBA55HE" for x in target_rows), "STM32WBA55HE retained target missing")
    req(any(x.get("base_device") == "STM32WBA55HG" for x in target_rows), "STM32WBA55HG retained target missing")

    with SOURCE.open(newline="", encoding="utf-8") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row.get("vendor") == "STMicroelectronics"
            and row.get("plasma_series") == "STM32WBA5X"
        ]
    req(len(rows) == 34, "STM32WBA5X source row count drifted")
    req(Counter(row["identifier_kind"] for row in rows) == Counter({"ordering_pattern": 17, "cmsis_device_name": 17}), "source identifier mix drifted")

    found = {
        (row["part_number"], row["identifier_kind"])
        for row in rows
        if (row["part_number"], row["identifier_kind"]) in EXCLUDED
    }
    req(found == EXCLUDED, "expected excluded research candidates missing")
    retained = [
        row for row in rows
        if (row["part_number"], row["identifier_kind"]) not in EXCLUDED
    ]
    req(len(retained) == 31, "v2 retained row count drifted")
    req(Counter(row["identifier_kind"] for row in retained) == Counter({"ordering_pattern": 15, "cmsis_device_name": 16}), "v2 identifier mix drifted")
    bases = tuple(sorted(
        base_from_ordering_pattern(row)
        for row in retained
        if row["identifier_kind"] == "ordering_pattern"
    ))
    req(bases == EXPECTED_BASES, f"v2 Base Device set drifted: {bases}")
    req("STM32WBA55HE" not in bases, "STM32WBA55HE leaked into v2 exact-discovery surface")
    req("STM32WBA55HG" in bases, "STM32WBA55HG current commercial sibling missing")

    return json.loads(r'''{
  "claims": {
    "catalog_admission_ready": false,
    "debug_attach_supported": false,
    "excluded_candidates_never_existed": false,
    "full_exact_icpn_discovery_completed": false,
    "hil_required_for_catalog_admission": false,
    "icpn_admission_authorized": false,
    "physical_validation_claimed": false,
    "production_write_authorized": false,
    "programming_algorithm_equivalence_claimed": false,
    "runtime_programming_support_claimed": false,
    "security_mutation_authorized": false,
    "target_execution_authorized": false,
    "wireless_radio_operation_authorized": false,
    "wireless_security_operation_authorized": false
  },
  "decision": "current_commercial_scope_reconciled_v2",
  "excluded_research_candidates": [
    {
      "identifier_kind": "ordering_pattern",
      "part_number": "STM32WBA50KEUx",
      "reason": "not_supported_by_current_official_stm32wba50kg_ordering_information"
    },
    {
      "identifier_kind": "cmsis_device_name",
      "part_number": "STM32WBA50KEUxT",
      "reason": "not_supported_by_current_official_stm32wba50kg_ordering_information"
    },
    {
      "identifier_kind": "ordering_pattern",
      "part_number": "STM32WBA55HEFx",
      "reason": "canonical_official_st_product_url_http_404_while_sibling_stm32wba55hg_is_active"
    }
  ],
  "family": "STM32WBA5X",
  "manufacturer": "STMicroelectronics",
  "next_gate": "stm32wba5x-bounded-exact-icpn-discovery-gate",
  "official_manufacturer_evidence": {
    "active_sibling_product": {
      "base_device": "STM32WBA55HG",
      "observed_active_exact_icpns": [
        "STM32WBA55HGF6TR",
        "STM32WBA55HGF7TR"
      ],
      "product_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32wba55hg.html"
    },
    "blocked_product": {
      "base_device": "STM32WBA55HE",
      "live_discovery_result": "browser navigation returned HTTP 404",
      "product_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32wba55he.html"
    },
    "document": "DS14127",
    "interpretation": "ordering grammar can express HE, but current official commercial product evidence does not establish STM32WBA55HE as a discoverable current product",
    "ordering_semantics": {
      "device_subfamily": "A55 = Full set of features, SMPS",
      "flash_memory_size_E": "E = 512 Kbytes",
      "flash_memory_size_G": "G = 1 Mbyte",
      "package": "F = Thin WLCSP",
      "pin_count": "H = 41 balls"
    },
    "revision": "Rev 10"
  },
  "prior_reconciled_surface": {
    "base_device_count": 16,
    "cmsis_device_name_rows": 16,
    "ordering_pattern_rows": 16,
    "retained_rows": 32
  },
  "production_boundary": {
    "exact_icpns": 2604,
    "families": 21,
    "frozen_manifest_git_blob_sha": "6e0fc69bec067259a1c52e150a313591cf4523e8",
    "wba5x_published": false
  },
  "reconciled_surface": {
    "base_device_count": 15,
    "base_devices": [
      "STM32WBA50KG",
      "STM32WBA52CE",
      "STM32WBA52CG",
      "STM32WBA52KE",
      "STM32WBA52KG",
      "STM32WBA54CE",
      "STM32WBA54CG",
      "STM32WBA54KE",
      "STM32WBA54KG",
      "STM32WBA55CE",
      "STM32WBA55CG",
      "STM32WBA55HG",
      "STM32WBA55UE",
      "STM32WBA55UG",
      "STM32WBA5MMG"
    ],
    "cmsis_device_name_rows": 16,
    "ordering_pattern_rows": 15,
    "retained_rows": 31
  },
  "reconciliation_id": "stm32wba5x-current-commercial-scope-reconciliation-v2",
  "schema_version": 1,
  "scope": "research_only",
  "source_surface": {
    "cmsis_device_name_rows": 17,
    "ordering_pattern_rows": 17,
    "source_rows": 34,
    "source_sha256": "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
  },
  "upstream": {
    "discovery_block_artifact_id": 10731257927,
    "discovery_block_artifact_zip_sha256": "bd388bcd430363eb82eb886e9d1aa1a4040996fa937cfa03392d985c52ba8d1a",
    "discovery_block_executed_head": "20536418aa52dc244ca5353ec64264550a6605ac",
    "discovery_block_run_id": 35815561803,
    "discovery_provenance_git_blob_sha": "1de7f35c33e8da83078d0a69e857091c26b534d2",
    "discovery_summary_git_blob_sha": "dafc09228f27df49da693c5c21860b48366bce5b",
    "discovery_targets_git_blob_sha": "789a4fe0ab498057e91789d4039532104b5e505c",
    "prior_reconciliation_git_blob_sha": "d1e354abb390e968e10e2723517747041c2a2439",
    "prior_reconciliation_id": "stm32wba5x-current-commercial-scope-reconciliation-v1",
    "stm32wba55hg_evidence_git_blob_sha": "09843e1c37e6f37b8dd1cef16eb1fea4e32bfe95"
  }
}''')

def main() -> int:
    print(json.dumps(render(), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
