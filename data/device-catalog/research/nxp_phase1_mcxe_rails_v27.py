#!/usr/bin/env python3
"""ADR-0002 NXP Phase 1 v27: exact MCXE24/31 VDD, IO, analog, SRAM conflict.

Research-only official information. It neither runs OpenOCD nor qualifies
Production, PPU, power sequencing, Socket, Site, HIL or an exact IC program.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

import nxp_phase1_mcxn_rails_v26 as prev
from nxp_phase1_kl25_k32l2a_io_v24 import summary
from nxp_phase1_information_v13 import blob

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "nxp-15-mcxe-normal-voltage-exact-source-v27.csv"
LOCK = HERE / "nxp-phase1-mcxe-operating-source-lock-v27.json"
PREV_EXACT = HERE / "nxp-54-exact-ordering-rows-v21.csv"
LEDGER = HERE / "nxp-501-phase1-mcxe-normal-voltage-v27.csv"
METRICS = HERE / "nxp-phase1-mcxe-normal-voltage-coverage-v27.json"
EXTRA = (
    "mcxe_source_doc_v27", "mcxe_source_uri_v27", "mcxe_source_revision_v27",
    "mcxe_source_order_table_v27", "mcxe_source_operating_table_v27",
    "mcxe_electrical_mode_constraint_v27", "mcxe_electrical_scope_v27",
    "mcxe_original_pdf_sha256_v27", "mcxe_io_rail_inference_limit_v27",
    "mcxe_analog_rail_inference_limit_v27", "mcxe_prior_ram_source_v27",
    "mcxe_new_ram_value_v27", "mcxe_ram_source_disposition_v27",
)
CHANGED = {
    "working_vdd", "working_vdd_unit", "working_vdd_state",
    "io_supply", "io_supply_state", "vdda", "vdda_state", "ram_state",
}
EXACT = {
    "MCXE245VLF": 512, "MCXE245VLH": 512, "MCXE245VLL": 512,
    "MCXE246VLH": 1024, "MCXE246VLL": 1024, "MCXE246VLQ": 1024,
    "MCXE247VLL": 2048, "MCXE247VLQ": 2048,
    "MCXE315MLF": 512, "MCXE315MPA": 512,
    "MCXE316MLF": 1024, "MCXE316MPA": 1024,
    "MCXE317MPA": 2048, "MCXE317MPB": 2048, "MCXE31BMPB": 4096,
}
RAM_CONFLICTS = {"MCXE315MLF", "MCXE315MPA"}
E24_IO = (
    "GPIO supplied by VDD 2.7–5.5 V; open-drain external pullup to VDD; "
    "independent VDDIO NOT established"
)
E31_IO = (
    "VDD_HV_A main I/O and analog 2.97–5.5 V; VDD_HV_B secondary I/O "
    "where pin physically present (MCXE31B); exact package pinout required"
)
E24_ANALOG = (
    "VDDA 2.7–5.5 V; VDDA and VDD must share same PCB source; "
    "|VDD−VDDA| ≤0.1V RF-AC only"
)
E31_ANALOG = (
    "Analog domain uses VDD_HV_A 2.97–5.5 V; no separately evidenced "
    "VDDA pin; VREFH is ADC reference not VDDA"
)
E24_MODES = (
    "MCXE247 with PLL engaged ≥2.97V; 2.7V requires internal FIRC; "
    "MCXE245/246 2.7V all modes"
)
E31_MODES = (
    "V25 internal flash rail ~2.5 V; V11 internal core rail ~1.14 V; "
    "neither is external high voltage I/O rail"
)
NONCLAIM = (
    "Manufacturer data only; not socket voltage programming or HIL; "
    "original manufacturer PDF binary not archived"
)
SOURCE_SCOPE = "EXACT_NXP_DATASHEET_ORDERING_TABLE_PLUS_NORMAL_ELECTRICAL"


def need(v: bool, reason: str) -> None:
    if not v:
        raise ValueError("NXP Phase1 v27: " + reason)


def read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@lru_cache(maxsize=1)
def baseline_rows() -> list[dict]:
    return prev.build()


def load() -> dict:
    lk = json.loads(LOCK.read_text(encoding="utf-8"))
    need((lk["schema_version"], lk["adr"], lk["phase"], lk["manufacturer"]) ==
         (27, "ADR-0002", "IC_INFORMATION", "NXP"), "schema/phase changed")
    need((lk["expected_501"], lk["expected_admitted"], lk["expected_research"],
          lk["new_identities"]) == (501, 224, 277, 0), "population/admission changed")
    need(lk["expected_15"] == {"MCXE24": 8, "MCXE31": 7}
         and lk["ram_conflict_exact"] == sorted(RAM_CONFLICTS)
         and set(lk["allowed_changes"]) == CHANGED, "reviewed field authority changed")
    need(lk["mode_restriction"] ==
         "MCXE247 uses FIRC for minimum 2.7V, PLL needs 2.97V minimum",
         "MCXE247 mode restriction lost")
    need("NOT" in lk["e31_analog"] and "same PCB" in lk["e24_vdda"],
         "supply-domain evidence misrepresented")
    need(lk["ram_conflict_old"] == "MCXE31FS Rev 1 2025-10-23 RAM 64 KB"
         and lk["ram_conflict_new"] ==
         "MCXEP172M160FB0 Rev 4 2026-04-06 RAM 112 KB",
         "RAM contradiction evidence changed")
    need(lk["vendor_original_pdf_bytes_archived"] is False
         and lk["vendor_original_pdf_sha256"] is None
         and lk["source_byte_replay_verified"] is False
         and lk["production_catalog_changed"] is False
         and lk["software_programming_qualified"] is False
         and lk["physical_hil_verified"] is False,
         "false PDF custody or Production/Programming/HIL claim")
    need(blob(prev.LEDGER.read_bytes()) == lk["baseline_501_v26_git_blob"]
         and prev.LEDGER.read_bytes() ==
         prev.csvfmt.dump(baseline_rows(), prev.csvfmt.header(prev.LEDGER)),
         "v26 source baseline drift or not reproducible")
    need(blob(PREV_EXACT.read_bytes()) == lk["prior_54_exact_v21_git_blob"],
         "v21 original exact material evidence drift")
    need(blob(SOURCE.read_bytes()) == lk["source_15_git_blob"],
         "v27 original official evidence transcription changed")
    return lk


def build() -> list[dict]:
    lk = load()
    src = read(SOURCE)
    need(len(src) == 15 and len({x["icpn"] for x in src}) == 15
         and {x["icpn"] for x in src} == set(EXACT), "unreviewed exact MCXE identities")
    exact_old = {r["icpn"]: r for r in read(PREV_EXACT)
                 if r["source_id"] == "MCXE31FS"}
    need(len(exact_old) == 7, "earlier exact E31 source scope changed")
    by, family_count = {}, Counter()
    for ev in src:
        sku, family = ev["icpn"], ev["source_family"]
        doc = lk["documents"].get(family)
        need(doc is not None, "unknown MCX E document")
        need(ev["source_document"] == doc["id"]
             and ev["source_revision"] == doc["rev"]
             and ev["source_official_pdf_url"] == doc["url"]
             and ev["source_normal_electrical_locator"] == doc["normal"]
             and ev["working_vdd_range"] == doc["range"],
             "manufacturer PDF/normal operating table/version/range drift")
        need(int(ev["previous_flash_kb"]) == EXACT[sku]
             and ev["manufacturer_exact_part_uri"] ==
             "https://www.nxp.com/part/" + sku
             and ev["confidence"] == "VERIFIED"
             and ev["exact_source_scope"] == SOURCE_SCOPE
             and ev["source_original_pdf_archived"] == "false"
             and ev["source_original_pdf_sha256"] == ""
             and ev["nonclaim"] == NONCLAIM,
             "exact SKU/Flash/verified source or original PDF claim changed")
        if family == "MCXE24":
            need(sku.startswith("MCXE24")
                 and ev["io_supply_evidence"] == E24_IO
                 and ev["analog_supply_evidence"] == E24_ANALOG
                 and ev["operating_mode_constraints"] == E24_MODES
                 and ev["source_exact_ordering_locator"] in (
                     "§3.2 Ordering information Table, PDF physical page 8/75",
                     "§3.2 Ordering information Table, PDF physical page 9/75",
                 )
                 and ev["ram_disposition"] == "UNCHANGED"
                 and not ev["ram_new_datasheet_table2_kb"],
                 "E24 mode, common VDD/VDDA or SKU evidence drift")
        else:
            o = exact_old.get(sku)
            need(sku.startswith("MCXE31") and o is not None
                 and o["flash_kb"] == ev["previous_flash_kb"]
                 and int(o["sram_kb"]) == int(ev["previous_ram_kb"])
                 and o["exact_ordering_table_seen"] == "true"
                 and ev["source_exact_ordering_locator"] ==
                 "Table 2 Ordering information, PDF physical page 6/81"
                 and ev["io_supply_evidence"] == E31_IO
                 and ev["analog_supply_evidence"] == E31_ANALOG
                 and ev["operating_mode_constraints"] == E31_MODES,
                 "E31 exact family source/analog supply discrepancy")
            if sku in RAM_CONFLICTS:
                need(ev["previous_ram_kb"] == "64"
                     and ev["ram_new_datasheet_table2_kb"] == "112"
                     and "RAM64KB" in ev["ram_prior_v21_source"]
                     and ev["ram_disposition"] ==
                     "OPEN_CONFLICT_NEW_REV4_112KB_OLD_FACTSHEET_64KB",
                     "E315 genuine 64/112KB contradiction ignored")
            else:
                need(ev["ram_disposition"] == "UNCHANGED"
                     and not ev["ram_new_datasheet_table2_kb"],
                     "spurious E31 memory conflict")
        by[sku] = ev
        family_count[family] += 1
    need(dict(family_count) == lk["expected_15"], "NXP family split changed")
    output, modified, ram_conflicts = [], set(), set()
    for old in baseline_rows():
        row = dict(old)
        row.update({field: "" for field in EXTRA})
        ev = by.get(old["icpn"])
        if ev:
            need(old["identity_state"] == "ADMITTED"
                 and old["working_vdd_state"] == "UNKNOWN"
                 and old["io_supply_state"] == "UNKNOWN"
                 and old["vdda_state"] == "UNKNOWN"
                 and not any(old[k] for k in ("working_vdd", "io_supply", "vdda"))
                 and int(old["flash"].split()[0]) ==
                 int(ev["previous_flash_kb"])
                 and int(old["ram"].split()[0]) == int(ev["previous_ram_kb"])
                 and old["manufacturer_uri"] == ev["manufacturer_exact_part_uri"],
                 "prior VDD, exact identity, Flash or RAM unexpectedly changed")
            f = ev["source_family"]
            row.update(
                working_vdd=ev["working_vdd_range"], working_vdd_unit="V",
                working_vdd_state="VERIFIED",
                io_supply=ev["io_supply_evidence"] +
                    "; electrical scope only, no independent hardware power readiness",
                io_supply_state="PARTIAL" if f == "MCXE24" else "VERIFIED",
                vdda=ev["analog_supply_evidence"], vdda_state="VERIFIED",
                mcxe_source_doc_v27=ev["source_document"],
                mcxe_source_uri_v27=ev["source_official_pdf_url"],
                mcxe_source_revision_v27=ev["source_revision"],
                mcxe_source_order_table_v27=ev["source_exact_ordering_locator"],
                mcxe_source_operating_table_v27=
                    ev["source_normal_electrical_locator"],
                mcxe_electrical_mode_constraint_v27=
                    ev["operating_mode_constraints"],
                mcxe_electrical_scope_v27=ev["exact_source_scope"],
                mcxe_original_pdf_sha256_v27="NOT_ARCHIVED",
                mcxe_io_rail_inference_limit_v27=(
                    "VDDA+VDD together; GPIO VDD reference verified; independent "
                    "VDDIO NOT established, remain PARTIAL" if f == "MCXE24" else
                    "VDD_HV_B only where physical second I/O rail exists; "
                    "VREFH is not GPIO I/O power"),
                mcxe_analog_rail_inference_limit_v27=(
                    "VDD and VDDA one PCB source; differential ±0.1V RF-AC only"
                    if f == "MCXE24" else
                    "Analog via VDD_HV_A; no separate independent VDDA pin evidenced"),
                mcxe_prior_ram_source_v27=ev["ram_prior_v21_source"],
                mcxe_new_ram_value_v27=ev["ram_new_datasheet_table2_kb"],
                mcxe_ram_source_disposition_v27=ev["ram_disposition"],
            )
            if old["icpn"] in RAM_CONFLICTS:
                need(old["ram_state"] == "VERIFIED",
                     "RAM source conflict old value is not independently verified")
                row["ram_state"] = "CONFLICT"
                ram_conflicts.add(old["icpn"])
            modified.add(old["icpn"])
        need(all(row[k] == v for k, v in old.items() if k not in CHANGED)
             and row["phase"] == "1"
             and row["identity_state"] == old["identity_state"],
             "unreviewed Phase 1/identity/prog/hardware field changed")
        if not ev:
            need(all(row[k] == old[k] for k in CHANGED),
                 "unreviewed exact ICPN parameter changed")
        output.append(row)
    need(len(output) == 501 and modified == set(EXACT)
         and ram_conflicts == RAM_CONFLICTS
         and sum(r["identity_state"] == "ADMITTED" for r in output) == 224
         and sum(r["identity_state"] == "RESEARCH_ONLY" for r in output) == 277,
         "cohort, exact 15 or 2 source RAM conflicts changed")
    return output


def stats(rows: list[dict]) -> dict:
    lk = load()
    return {
        "schema_version": 27, "adr": "ADR-0002",
        "phase": "IC_INFORMATION", "manufacturer": "NXP",
        "source_15_git_blob": lk["source_15_git_blob"],
        "baseline_501_v26_git_blob": lk["baseline_501_v26_git_blob"],
        "prior_54_exact_v21_git_blob": lk["prior_54_exact_v21_git_blob"],
        "exact_mcx_e24": 8, "exact_mcx_e31": 7,
        "ram_source_discrepancies": {
            k: "Rev1 Factsheet 64KB vs Rev4 Datasheet 112KB"
            for k in sorted(RAM_CONFLICTS)
        },
        "before_admitted": summary([r for r in baseline_rows()
                                   if r["identity_state"] == "ADMITTED"]),
        "after_admitted": summary([r for r in rows
                                  if r["identity_state"] == "ADMITTED"]),
        "all_501": summary(rows),
        "e24_vdd_mode": "MCXE247 2.7V FIRC vs >=2.97V PLL",
        "e24_io": "VDD referenced but independent VDDIO unestablished: PARTIAL",
        "e31_analog": "VDD_HV_A analog main rail; no dedicated VDDA pin",
        "original_vendor_pdf_sha256_archived": False,
        "new_production_admitted": 0,
        "new_programming_supported": 0,
        "new_physical_hil_passed": 0,
    }


def verify() -> None:
    rows = build()
    keys = prev.csvfmt.header(prev.LEDGER) + list(EXTRA)
    need(LEDGER.read_bytes() == prev.csvfmt.dump(rows, keys),
         "501-row Phase 1 ledger not deterministically replayable")
    need(json.loads(METRICS.read_text(encoding="utf-8")) == stats(rows),
         "admitted/all-501 coverage report not replayable")
    fields = stats(rows)["after_admitted"]["fields"]
    for field, expectation in (
        ("working_vdd", (181, 39, 4, 0)),
        ("io_supply", (157, 24, 43, 0)),
        ("vdda", (181, 0, 43, 0)),
        ("ram", (197, 25, 0, 2)),
    ):
        c = fields[field]
        need(tuple(c[x] for x in ("VERIFIED", "PARTIAL", "UNKNOWN", "CONFLICT"))
             == expectation, "unexpected Phase 1 evidence states: " + field)
    print("NXP_PHASE1_V27_PASS exact=15 E24=8 E31=7 RAM_CONFLICT=2; "
          "no Production/Selector/Programming/HIL")


if __name__ == "__main__":
    verify()
