#!/usr/bin/env python3
"""ADR-0002 NXP Phase 1 v26: exact MCXN Table 1 to Table 9 operating-rail evidence.

Source-only manufacturer IC Information. Not a programming, PPU/PL,
HIL, fixture-power, Production, or OpenOCD software qualification.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

import nxp_phase1_k32l2b_vdd_v25 as prev
import nxp_phase1_mcxa_rails_v23 as csvfmt
from nxp_phase1_information_v13 import blob

DIR = Path(__file__).resolve().parent
SOURCE = DIR / "nxp-31-mcxn-operating-rails-official-source-v26.csv"
SOURCE_OLD_EXACT = DIR / "nxp-54-exact-ordering-rows-v21.csv"
LOCK = DIR / "nxp-phase1-mcxn-operating-rails-lock-v26.json"
LEDGER = DIR / "nxp-501-phase1-mcxn-operating-rails-v26.csv"
METRICS = DIR / "nxp-phase1-mcxn-operating-rails-coverage-v26.json"

EXTRA = (
    "mcxn_source_doc_v26",
    "mcxn_source_uri_v26",
    "mcxn_source_revision_v26",
    "mcxn_ordering_page_v26",
    "mcxn_operating_locator_v26",
    "mcxn_vdd_sys_mode_v26",
    "mcxn_io_rail_mode_v26",
    "mcxn_vdda_constraint_v26",
    "mcxn_por_sequence_v26",
    "mcxn_power_pin_package_caveat_v26",
    "mcxn_source_pdf_sha256_v26",
    "mcxn_source_scope_v26",
    "mcxn_evidence_limit_v26",
)
CHANGED = (
    "working_vdd", "working_vdd_unit", "working_vdd_state",
    "io_supply", "io_supply_state", "vdda", "vdda_state",
)
OPERATING_VDD = "1.71 to 3.6"
IO = (
    "VDD(P0/P1/Flash) 1.71–3.6 V; VDD_P2/P3 1.71–3.6 V or "
    "1.14–1.32 V restricted mode; VDD_P4 1.71–3.6 V"
)
ANA = (
    "VDD_ANA follows VDD_P4 nominal (1.71–3.6 V), tolerates ±0.1 V; "
    "VDD_P4 & VDD_ANA same nominal at POR"
)
SYS = (
    "VDD_SYS normal mode 1.71–1.98 V; fuse programming 2.25–2.75 V "
    "is separate not normal mode"
)
LIMIT = (
    "Original NXP datasheet binary NOT archived or SHA-256 verified; "
    "transcribed official table evidence only; no "
    "SWD/PPU/fixture/Programming/Production admission claim"
)
SOURCE_SCOPE = "EXACT_ORDERING_TABLE_PLUS_APPLICABLE_FAMILY_ELECTRICAL_TABLE"


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError("NXP Phase1 v26: " + reason)


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


@lru_cache(maxsize=1)
def baseline_rows() -> list[dict]:
    return prev.build()


def load() -> dict:
    lk = json.loads(LOCK.read_text(encoding="utf-8"))
    require((lk["schema_version"], lk["adr"], lk["phase"], lk["manufacturer"]) ==
            (26, "ADR-0002", "IC_INFORMATION", "NXP"),
            "scope/schema changed")
    require((lk["expected_501"], lk["expected_admitted"],
             lk["expected_research_only"], lk["expected_exact_mcxn_existing"],
             lk["expected_new_exact_identifiers"]) == (501, 224, 277, 31, 0),
            "identity, research, or admission cohort changed")
    require(lk["document_exact_count"] == {
        "MCXN23x": 6, "MCXNP184M150F70": 25
    }, "document cohort changed")
    require(lk["expected_field_state"] == "VERIFIED"
            and lk["approved_normal_vdd"] == OPERATING_VDD
            and lk["approved_voltage_unit"] == "V"
            and lk["allowed_changes"] == list(CHANGED),
            "unreviewed field promoted or normal supply range changed")
    require(lk["original_official_pdf_archive"] is False
            and lk["original_official_pdf_sha256"] is None
            and lk["software_supported_promoted"] is False
            and lk["production_or_hardware_changed"] is False,
            "false original vendor source or support/HIL claim")
    require(blob(prev.LEDGER.read_bytes()) == lk["frozen_prior_501_v25_git_blob"]
            and prev.LEDGER.read_bytes() ==
            csvfmt.dump(baseline_rows(), csvfmt.header(prev.LEDGER)),
            "v25 source baseline has drifted or cannot replay")
    require(blob(SOURCE_OLD_EXACT.read_bytes()) == lk["frozen_v21_exact_54_git_blob"],
            "upstream exact ordering evidence drifted")
    require(blob(SOURCE.read_bytes()) == lk["official_31_source_git_blob"],
            "new exact manufacturer electric source transcription drifted")
    return lk


def build() -> list[dict]:
    lk = load()
    src = read(SOURCE)
    prior_source = read(SOURCE_OLD_EXACT)
    original = {r["icpn"]: r for r in prior_source
                if r["source_id"] in lk["docs"]}
    require(len(original) == len(src) == 31
            and len({r["icpn"] for r in src}) == 31
            and {r["icpn"] for r in src} == set(original),
            "31 exact device ordering-code crosswalk not complete")
    by = {}
    doc_counts = Counter()
    for ev in src:
        icpn, doc = ev["icpn"], ev["source_document"]
        require(doc in lk["docs"] and icpn.startswith("MCXN"),
                "unreviewed manufacturer device/source")
        meta = lk["docs"][doc]
        old = original[icpn]
        require(ev["source_official_pdf_url"] == meta["url"]
                and ev["source_revision"] == meta["rev"]
                and ev["rail_operating_table_locator"] == meta["normal_electrical"]
                and ev["por_and_sequence_description"] == meta["por"],
                "manufacturer normal-operating source version or locator drift")
        require(ev["exact_ordering_source_page"] ==
                "Table 1, original PDF physical page " + old["pdf_physical_page"]
                and old["pdf_physical_page"] in
                ([meta["ordering_page"]] if "ordering_page" in meta
                 else meta["ordering_pages"])
                and old["source_id"] == doc
                and old["manufacturer_uri"] == ev["source_official_pdf_url"]
                and old["flash_kb"] == ev["existing_flash_kb"]
                and old["exact_ordering_table_seen"] == "true"
                and old["original_pdf_binary_archived"] == "false"
                and not old["original_pdf_sha256"],
                "exact commercial ordering table or flash identity mismatch")
        require(ev["exact_manufacturer_part_page"] ==
                "https://www.nxp.com/part/" + icpn
                and (ev["working_vdd_min_v"], ev["working_vdd_max_v"]) ==
                    ("1.71", "3.6")
                and ev["io_rail_description"] == IO
                and ev["analog_rail_description"] == ANA
                and ev["vdd_sys_mode_description"] == SYS,
                "VDD/VDD_SYS, low-voltage GPIO or VDDA supply field drift")
        require(ev["evidence_state"] == "VERIFIED"
                and ev["source_scope"] == SOURCE_SCOPE
                and not ev["original_vendor_pdf_sha256"]
                and ev["document_limit"] == LIMIT,
                "scope, original vendor byte custody or software authority drift")
        by[icpn] = ev
        doc_counts[doc] += 1
    require(dict(doc_counts) == lk["document_exact_count"],
            "source document count changed")
    out, matched = [], set()
    for old in baseline_rows():
        row = dict(old)
        for key in EXTRA:
            row[key] = ""
        ev = by.get(old["icpn"])
        if ev is not None:
            require(old["identity_state"] == "ADMITTED"
                    and old["manufacturer_uri"] == ev["exact_manufacturer_part_page"]
                    and old["manufacturer_exact_source_v21"] == ev["source_document"]
                    and old["manufacturer_official_source_url_v21"] ==
                        ev["source_official_pdf_url"]
                    and int(old["flash"].split()[0]) == int(ev["existing_flash_kb"])
                    and all(old[x + "_state"] == "UNKNOWN"
                            for x in ("working_vdd", "io_supply", "vdda"))
                    and not any(old[x] for x in
                                ("working_vdd", "io_supply", "vdda")),
                    "existing exact ICPN/Flash or previous evidence state drift")
            row.update(
                working_vdd=OPERATING_VDD,
                working_vdd_unit="V",
                working_vdd_state="VERIFIED",
                io_supply=IO +
                    "; alternate 1.2-V rail and power sequencing are conditional, NOT socket-ready",
                io_supply_state="VERIFIED",
                vdda=ANA,
                vdda_state="VERIFIED",
                mcxn_source_doc_v26=ev["source_document"],
                mcxn_source_uri_v26=ev["source_official_pdf_url"],
                mcxn_source_revision_v26=ev["source_revision"],
                mcxn_ordering_page_v26=ev["exact_ordering_source_page"],
                mcxn_operating_locator_v26=ev["rail_operating_table_locator"],
                mcxn_vdd_sys_mode_v26=ev["vdd_sys_mode_description"],
                mcxn_io_rail_mode_v26=ev["io_rail_description"],
                mcxn_vdda_constraint_v26=ev["analog_rail_description"],
                mcxn_por_sequence_v26=ev["por_and_sequence_description"],
                mcxn_power_pin_package_caveat_v26=(
                    "Package-specific power pins require exact original datasheet "
                    "pin-table review before hardware design" if ev["source_document"] ==
                    "MCXN23x" else (
                        "100HLQFP: VDD_DCDC must remain powered even if DCDC "
                        "unused; DCDC_LX floating" if old["package"] == "HLQFP100" else
                        "184VFBGA/172HDQFP: dedicated VDD_DCDC; unused regulator "
                        "requires GND via 10 kΩ"
                    )
                ),
                mcxn_source_pdf_sha256_v26="NOT_ARCHIVED",
                mcxn_source_scope_v26=ev["source_scope"],
                mcxn_evidence_limit_v26=ev["document_limit"],
            )
            matched.add(old["icpn"])
        require(old["icpn"] == row["icpn"]
                and old["identity_state"] == row["identity_state"]
                and row["phase"] == "1"
                and all(row[k] == v for k, v in old.items() if k not in CHANGED),
                "unapproved Phase 1 field, core, admission or Phase 2/3 claim")
        if ev is None:
            require(all(row[k] == old[k] for k in CHANGED),
                    "unreviewed exact ICPN fields changed")
        out.append(row)
    require(len(out) == 501 and matched == set(by)
            and sum(r["identity_state"] == "ADMITTED" for r in out) == 224
            and sum(r["identity_state"] == "RESEARCH_ONLY" for r in out) == 277,
            "exact 501 population or 31-ICPN changed cohort")
    return out


def stats(rows: list[dict]) -> dict:
    lk = load()
    return {
        "schema_version": 26,
        "adr": "ADR-0002",
        "phase": "IC_INFORMATION",
        "manufacturer": "NXP",
        "frozen_prior_501_v25_git_blob": lk["frozen_prior_501_v25_git_blob"],
        "frozen_v21_exact_54_git_blob": lk["frozen_v21_exact_54_git_blob"],
        "official_31_source_git_blob": lk["official_31_source_git_blob"],
        "exact_official_ordering_rail_joins": 31,
        "document_exact_counts": lk["document_exact_count"],
        "before_admitted": prev.prev.summary([
            r for r in baseline_rows() if r["identity_state"] == "ADMITTED"]),
        "after_admitted": prev.prev.summary([
            r for r in rows if r["identity_state"] == "ADMITTED"]),
        "all_501": prev.prev.summary(rows),
        "source_scope":
            "Official Table 1 exact ordering code + same datasheet Table 9 normal supply/electrical applicability",
        "vdd_ana_conditions":
            "VDD_ANA relative to VDD_P4 nominal same, ±0.1V within 1.71–3.6 V; not a generic independent supply",
        "io_mode_conditions":
            "VDD Px 1.71–3.6 V except P2/P3 1.14–1.32 V restriction; POR sequencing; package-specific DCDC pin",
        "source_pdf_original_bytes_archived": False,
        "software_supported_promotions": 0,
        "production_or_hil_promotions": 0,
    }


def verify() -> None:
    rows = build()
    columns = csvfmt.header(prev.LEDGER) + list(EXTRA)
    require(LEDGER.read_bytes() == csvfmt.dump(rows, columns),
            "output CSV is not deterministic 501-row replay")
    require(json.loads(METRICS.read_text(encoding="utf-8")) == stats(rows),
            "field coverage differs from replay")
    coverage = stats(rows)["after_admitted"]["fields"]
    for field, expected in (
        ("working_vdd", (166, 39, 19)),
        ("io_supply", (150, 16, 58)),
        ("vdda", (166, 0, 58)),
    ):
        got = coverage[field]
        require((got["VERIFIED"], got["PARTIAL"], got["UNKNOWN"]) == expected
                and got["CONFLICT"] == 0,
                "admitted source-evidence denominator mismatch: " + field)
    print("NXP_PHASE1_V26_PASS exact_MCXN=31, 501 unchanged, VDD/IO/ANA "
          "verified via two official Table 1+9 documents; no Software/HIL")


if __name__ == "__main__":
    verify()
