#!/usr/bin/env python3
"""Replay the five bounded ST official commercial-row observations against frozen Production.

The CSV is a manually transcribed bounded research observation, NOT a downloaded,
raw-page-hash-bound full manufacturer export. This script checks local integrity
and the historical Production baseline, not remote ST page freshness.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import validate_st_multisource_structure as v04

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "st-bounded-active-commercial-gap-v0.5.csv"
REPORT = HERE / "st-bounded-active-commercial-gap-v0.5.json"
HEADER = ("family", "exact_icpn", "marketing_status", "source_surface", "source_url")
COHORTS = {
  "STM32C5": [
    "STM32C531CBT6"
  ],
  "STM32H5": [
    "STM32H503CBT6",
    "STM32H503CBT7",
    "STM32H503CBT7TR",
    "STM32H503CBU6",
    "STM32H503CBU6TR",
    "STM32H503CBU7"
  ],
  "STM32N6": [
    "STM32N657A0H3Q",
    "STM32N657A0H3QG",
    "STM32N657A0H3QTR"
  ],
  "STM32WB0": [
    "STM32WB05KZV6TR",
    "STM32WB05KZV7TR"
  ],
  "STM32WL3": [
    "STM32WL33CCV6",
    "STM32WL33CCV6A",
    "STM32WL33CCV6ATR",
    "STM32WL33CCV6TR",
    "STM32WL33CCV7",
    "STM32WL33CCV7A",
    "STM32WL33CCV7ATR",
    "STM32WL33CCV7TR"
  ]
}
OFFICIAL_URLS = {
  "STM32C5": "https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-mainstream-mcus/stm32c5-series/stm32c53x-542.html",
  "STM32H5": "https://www.st.com/en/microcontrollers-microprocessors/stm32h503cb.html",
  "STM32N6": "https://www.st.com/en/microcontrollers-microprocessors/stm32n657a0.html",
  "STM32WB0": "https://www.st.com/en/microcontrollers-microprocessors/stm32wb05kz.html",
  "STM32WL3": "https://www.st.com/en/microcontrollers-microprocessors/stm32wl33cc.html"
}
SURFACES = {
  "STM32C5": "ST official eStore Active exact part listing",
  "STM32H5": "Quality and Reliability exact-ICPN row",
  "STM32N6": "Quality and Reliability exact-ICPN row",
  "STM32WB0": "Quality and Reliability exact-ICPN row",
  "STM32WL3": "Quality and Reliability exact-ICPN row"
}
FIVE_V02_SENTINELS = {
    "STM32H503CBT6", "STM32C531CBT6", "STM32N657A0H3Q",
    "STM32WB05KZV6TR", "STM32WL33CCV6",
}

def require(condition: bool, why: str) -> None:
    if not condition:
        raise ValueError(why)

def parse_csv_text(raw: str) -> list[dict[str, str]]:
    reader = csv.DictReader(io.StringIO(raw))
    require(tuple(reader.fieldnames or ()) == HEADER, "commercial cohort CSV schema drift")
    observations: list[dict[str, str]] = []
    identities: set[str] = set()
    by_family: dict[str, set[str]] = {f: set() for f in COHORTS}
    for record in reader:
        require(None not in record and None not in record.values(), "malformed CSV record")
        require(set(record) == set(HEADER), "unexpected source column")
        family, exact = record["family"], record["exact_icpn"]
        require(family in COHORTS, f"unreviewed family: {family}")
        require(bool(re.fullmatch(r"STM32[A-Z0-9]+", exact)) and exact == exact.strip(),
                f"non-exact or unnormalized identity: {exact}")
        require(exact in COHORTS[family], f"unreviewed identity, never expand a pattern: {exact}")
        require(exact not in identities, f"duplicate commercial MPN: {exact}")
        require(record["marketing_status"] == "Active",
                f"status not same-row Active: {exact}")
        require(record["source_surface"] == SURFACES[family],
                f"source evidence surface drifted: {exact}")
        source_url = record["source_url"]
        require(source_url == OFFICIAL_URLS[family] and
                urlsplit(source_url).scheme == "https" and
                urlsplit(source_url).hostname in ("www.st.com", "estore.st.com"),
                f"source provenance drifted: {exact}")
        identities.add(exact)
        by_family[family].add(exact)
        observations.append({key: record[key] for key in HEADER})
    require({f: set(values) for f, values in COHORTS.items()} == by_family,
            "the reviewed bounded official cohort is incomplete or changed")
    require(FIVE_V02_SENTINELS.issubset(identities), "v0.2 sentinels lost")
    require(len(identities) == 20 and len(observations) == 20,
            "bounded 20-row commercial source drifted")
    return sorted(observations, key=lambda row: (row["family"], row["exact_icpn"]))

def render(source_text: str | None = None) -> dict:
    # v0.4 replays the original official Git tree object IDs and all 23
    # SHA256/Git-blob-pinned ST Production files, no Production mutation.
    baseline = v04.render()
    prod = baseline["production_st"]
    require(prod["exact_icpns"] == 2683 and prod["catalog_families"] == 23,
            "Production ST frozen baseline drifted")
    already = v04.st_v02.render()["production_baseline"]["family_counts"]
    require(not set(COHORTS).intersection(already),
            "a bounded missing family was subsequently published: refresh this research audit")
    source = SOURCE.read_text(encoding="utf-8") if source_text is None else source_text
    observations = parse_csv_text(source)
    counts = dict(sorted(Counter(r["family"] for r in observations).items()))
    require(counts == {name: len(rows) for name, rows in sorted(COHORTS.items())},
            "reviewed family counts drifted")
    return {
        "schema_version": 1,
        "audit_id": "st-stm32-bounded-official-active-commercial-gap-v0.5",
        "observation_date_utc": "2026-09-29",
        "record_state": "RESEARCH_ONLY_MANUALLY_TRANSCRIBED_OFFICIAL_PAGE_ROWS",
        "raw_official_page_bytes_retained": False,
        "source_cohort_count": len(COHORTS),
        "production_baseline": {
            "st_exact_icpns": prod["exact_icpns"],
            "st_catalog_families": prod["catalog_families"],
            "st_integrity_bound_sources": 23,
        },
        "bounded_unpublished_active_exact_mpn_minimum": len(observations),
        "per_missing_family_counts": counts,
        "observations": observations,
        "full_st_active_exact_mpn_denominator": None,
        "actual_active_coverage_percent": None,
        "actual_full_st_gap_count": None,
        "is_complete_st_official_portfolio_export": False,
        "production_write_authorized": False,
        "backend_programming_authorized": False,
        "physical_hil_validated": False,
        "next_gate": "Capture manufacturer raw exact-MPN and same-row lifecycle across all scoped MX1/MX2 families with replayable date, digest, pagination and completeness review.",
    }

def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    calculated = render()
    retained = json.loads(REPORT.read_text(encoding="utf-8"))
    require(calculated == retained, "v0.5 retained report differs from deterministic replay")
    print("ST bounded commercial gap v0.5: PASS")
    print("Official Active exact-MPN bounded cohort: 20 missing / 5 absent families")
    print("Frozen ST Production: 2683 exact ICPNs / 23 source families; no writes")
    print("Full actual ST Active coverage / missing count: UNKNOWN")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
