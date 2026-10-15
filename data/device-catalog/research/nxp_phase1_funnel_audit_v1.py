#!/usr/bin/env python3
"""NXP-only ADR-0002 Phase 1 exact-ICPN funnel evidence inventory.

Offline research snapshot; not Production admission, OpenOCD SUPPORTED, public
Catalog migration or physical HIL. The S1 policy count derives official identity
observations, with source custody/completeness separate from identity.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = {
    "legacy": ("nxp-501-phase1-ic-information-v13.csv",
               "4a0fbad8fa5f57580ba28e92f71b0793e12faf07"),
    "reverse": ("nxp-65-openocd-discovery-gates-v1.csv",
                "fa428f58d351122d19fd1e70769f40d4e83b098e"),
    "lpc82x": ("nxp-8-lpc82x-official-phase1-observations-v1.csv",
               "449a3a6cb5e98ff1edef8ea2bb6a065ef8482528"),
    "lpc81x": ("nxp-8-lpc81x-phase1-official-material-v1.csv",
               "2d94cdc9506b336dc580a178d3309dea6c1d8c63"),
}
SPEC_FIELDS = ("base_device", "package", "pin_count", "flash", "ram",
               "working_vdd", "io_supply", "vdda", "temperature")

def need(ok, why):
    if not ok:
        raise ValueError("NXP Phase1 funnel: " + why)

def git_blob(raw: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode() + b"\0" + raw
    ).hexdigest()

def read(name: str) -> list[dict[str, str]]:
    filename, sha = SOURCE[name]
    raw = (HERE / filename).read_bytes()
    need(git_blob(raw) == sha, "source Git blob drift: " + filename)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    need(rows and not any(None in r for r in rows), "invalid CSV: " + filename)
    return rows

def audit_from(legacy, reverse, lpc82, lpc81):
    # Existing identity admission and manufacturer source are grandfathered as
    # original exact identity observations, NOT software/field completeness.
    need(len(legacy) == 501 and len({r["icpn"] for r in legacy}) == 501,
         "legacy 501 exact observations or uniqueness drift")
    admitted = [r for r in legacy if r["identity_state"] == "ADMITTED"]
    research = [r for r in legacy if r["identity_state"] == "RESEARCH_ONLY"]
    need(len(admitted) == 224 and len(research) == 277,
         "legacy 224 admitted / 277 research-only split changed")
    need(all(r["cohort"] == "existing_production_identity"
                 and r["field_source_scope"] == "EXACT_MANUFACTURER_EXISTING_ADMISSION"
                 and r["manufacturer_uri"].startswith("https://www.nxp.com/")
                 and r["base_device_state"] == "VERIFIED"
                 and r["phase"] == "1"
             for r in admitted),
         "legacy admitted official exact identity / provenance changed")
    need(all(r["cohort"] == "pending_manufacturer_research"
                 and r["base_device_state"] == "UNKNOWN"
                 and r["phase"] == "1"
             for r in research),
         "legacy research-only cannot silently enter S1")
    partial_html = [r for r in research
                    if r["field_source_scope"] == "EXACT_PART_HTML_PARTIAL_REVIEW"]
    blocked = [r for r in research
               if r["field_source_scope"] == "NO_EXACT_HTML_SOURCE_BYTES"]
    need(len(partial_html) == 70 and len(blocked) == 207,
         "70 partial / 207 source-blocked legacy cases changed")
    need(all(len(r["source_observation_sha256"]) == 64 for r in partial_html)
         and all(not r["source_observation_sha256"] for r in blocked),
         "legacy evidence custody tier changed")
    need(all(r["base_device"] == "" for r in research),
         "unverified research family link erroneously populated")
    need(all(r["io_supply_state"] == "UNKNOWN"
                 and r["vdda_state"] == "UNKNOWN"
             for r in legacy),
         "legacy Phase1 information-complete conclusion needs reevaluation")
    base_alias_gap = sum(r["base_device"] == r["icpn"] for r in admitted)
    need(base_alias_gap == 212,
         "legacy 212 base-device alias normalization gap changed")
    existing_raw_html_sha = sum(len(r["source_observation_sha256"]) == 64
                            for r in admitted)
    need(existing_raw_html_sha == 212,
         "existing admitted HTML SHA vs official-document subset drift")

    need(len(reverse) == 65
         and len({r["icpn_observation"] for r in reverse}) == 65,
         "OpenOCD reverse wave observations changed")
    priority = Counter(r["priority_lead"] for r in reverse)
    need(priority == {"P0": 60, "P1": 5},
         "historical research priority evidence drift (NOT Phase counts)")
    need(all(r["manufacturer_url"].startswith("https://www.nxp.com/")
                 and r["orderable_identity_qualified"] == "false"
                 and r["production_admitted"] == "false"
                 and r["flash_programming_qualified"] == "false"
                 and r["hardware_validation_qualified"] == "false"
             for r in reverse),
         "research wave promoted identity/software/production/hardware")
    old_names = {r["icpn"] for r in legacy}
    discovery_names = {r["icpn_observation"] for r in reverse}
    need(not (old_names & discovery_names),
         "legacy and reverse-coverage populations unexpectedly overlap")

    need(len(lpc82) == 8 and len(lpc81) == 8,
         "source-observed manufacturer crosswalk count drift")
    enriched = {}
    for row in lpc82:
        part = row["icpn"]
        need(part and part not in enriched and len(row["manufacturer_12nc"]) == 12
             and row["manufacturer_12nc"].isdigit()
             and row["manufacturer_material_url"].startswith("https://www.nxp.com/")
             and row["manufacturer_material_status"] == "Active"
             and row["original_datasheet_pdf_binary_archived"] == "false"
             and row["original_material_html_binary_archived"] == "false"
             and row["openocd_programming_qualified"] == "false"
             and row["production_admitted"] == "false"
             and row["physical_hil_verified"] == "false"
             and row["ordering_to_silicon_part_id_verified"] == "false",
             "LPC82x exact-material identity or Phase boundary drift")
        need(row["datasheet_base"] and row["datasheet_revision"],
             "LPC82x base/device relationship missing")
        enriched[part] = "LPC82x"
    for row in lpc81:
        part = row["icpn"]
        need(part and part not in enriched and len(row["manufacturer_12nc"]) == 12
             and row["manufacturer_12nc"].isdigit()
             and row["material_url"].startswith("https://www.nxp.com/")
             and row["manufacturer_status"] == "Active"
             and row["original_pdf_bytes_archived"] == "false"
             and row["original_manufacturer_html_bytes_archived"] == "false"
             and row["programming_qualified"] == "false"
             and row["production_admitted"] == "false"
             and row["physical_hil_verified"] == "false"
             and row["exact_silicon_revision_verified"] == "false",
             "LPC81x exact-material identity or Phase boundary drift")
        need(row["manufacturer_base"] and row["datasheet_revision"],
             "LPC81x base/device relationship missing")
        enriched[part] = "LPC81x"
    need(len(enriched) == 16
         and set(enriched).issubset(discovery_names)
         and set(enriched).isdisjoint(old_names),
         "new 16 official exact material observations not a disjoint wave subset")
    outstanding_reverse = discovery_names - set(enriched)
    need(len(outstanding_reverse) == 49, "reverse waves residual changed")
    original_byte_custody_unavailable = 16
    complete_legacy = sum(all(r[f + "_state"] == "VERIFIED" for f in SPEC_FIELDS)
                          for r in legacy)
    need(complete_legacy == 0,
         "S1 information complete requires reassessment")
    # The 16 new sources explicitly say VDDIO/VDDA cannot be independently
    # established, not proof that an absent pin is NOT_APPLICABLE.
    need(all("no independent VDDIO evidenced" in r["io_supply_domain"]
                 and "separate VDDA not evidenced" in r["analog_supply_domain"]
             for r in lpc82), "LPC82x unresolved supply rails changed")
    need(all("independent VDDIO not established" in r["io_supply_evidence"]
                 and "separate VDDA not established" in r["analog_supply_evidence"]
             for r in lpc81), "LPC81x unresolved supply rails changed")

    s1 = {r["icpn"] for r in admitted} | set(enriched)
    need(len(s1) == 240, "Phase1 manufacturer-identification count drift")
    phase1_backlog = (old_names | discovery_names) - s1
    need(len(phase1_backlog) == 326
         and phase1_backlog ==
             {r["icpn"] for r in research} | outstanding_reverse,
         "Phase1 research backlog partition/dedupe drift")
    return {
        "policy": "ADR-0002_S1_IDENTIFIED_VS_S1_COMPLETE",
        "manufacturer": "NXP",
        "dataset_scope": "bounded historical 501 + disjoint OpenOCD reverse 65",
        "source_git_blobs": {k: {"path": v[0], "git_blob": v[1]}
                             for k, v in SOURCE.items()},
        "unique_exact_icpn_observations_or_candidates": 566,
        "phase1_identified_s1": len(s1),
        "phase1_identified_components": {
            "legacy_official_internal_identity_admitted": len(admitted),
            "new_official_exact_material_observed_lpc81x_lpc82x": len(enriched),
        },
        "phase1_information_complete_s1_complete": 0,
        "phase1_information_completeness_scope":
            "strict required fields on pinned old v13 plus LPC81x/82x crosswalks",
        "phase1_identity_review_backlog": len(phase1_backlog),
        "backlog_components": {
            "original_277_exact_html_partial_fields_base_link_unknown": len(partial_html),
            "original_277_source_blocked_or_schema": len(blocked),
            "reverse_discovery_without_exact_material_crosswalk": len(outstanding_reverse),
        },
        "provenance_quality_gaps": {
            "legacy_admitted_base_device_is_exact_icpn_alias": base_alias_gap,
            "legacy_admitted_html_sha_present_not_proof_original_bytes_archived": existing_raw_html_sha,
            "new_identified_original_manufacturer_binary_bytes_not_archived": original_byte_custody_unavailable,
            "legacy_501_io_supply_unknown": 501,
            "legacy_501_vdda_unknown": 501,
        },
        "historical_research_priority_not_phase_counts": {
            "reverse_p0": priority["P0"], "reverse_p1": priority["P1"],
        },
        "phase2_software_qualified_s2": None,
        "phase3_hil_validated_s3": None,
        "phase2_phase3_note":
            "NOT AUDITED by this Phase1 source inventory; null is not zero",
        "no_runtime_catalog_production_or_hil_change": True,
    }

def build():
    return audit_from(read("legacy"), read("reverse"),
                      read("lpc82x"), read("lpc81x"))

def verify():
    x = build()
    print("NXP_PHASE1_FUNNEL_AUDIT_PASS unique=566 S1_identified=240 "
          "legacy=224 lpc81x82x=16 S1_complete=0 "
          "backlog=326 legacy_html_partial=70 source_blocked=207 "
          "reverse_uncrosswalked=49 S2=NOT_AUDITED S3=NOT_AUDITED")
    return x

if __name__ == "__main__":
    print(json.dumps(verify(), ensure_ascii=False, indent=2, sort_keys=True))
