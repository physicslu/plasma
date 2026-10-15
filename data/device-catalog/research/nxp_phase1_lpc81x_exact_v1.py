#!/usr/bin/env python3
"""ADR-0002 NXP Phase 1 LPC811/LPC812 eight material sources, research only.

Vendor original PDF and live HTML byte custody remain explicitly unverified.
No software support, production admission, Site/Socket/HIL is qualified.
"""
from __future__ import annotations

import csv
import hashlib
import io
from collections import Counter
from pathlib import Path

import nxp_65_discovery_gates_v1 as prev

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "nxp-8-lpc81x-phase1-official-material-v1.csv"
SOURCE_GIT_BLOB = "2d94cdc9506b336dc580a178d3309dea6c1d8c63"
URL = "https://www.nxp.com/products/LPC81X_LPC83X?tab=Package_Quality_Tab"
DATASHEET = "https://www.nxp.com/docs/en/data-sheet/LPC81XM.pdf"
REV = "Rev 4.7 2021-03-19"
IO = "Single VDD core and external rail; independent VDDIO not established"
ANA = "Single VDD; comparator analog supply via VDD; separate VDDA not established"
SCOPE = "EXACT_MATERIAL_PHASE1_SOURCE_CROSSWALK_NOT_SOFTWARE_QUALIFIED"
EXPECTED = {
    "LPC811M001JDH16FP": ("LPC811M001JDH16", "TSSOP16", 16, "935302397129", 8, 2),
    "LPC811M001JDH16J":  ("LPC811M001JDH16", "TSSOP16", 16, "935302397118", 8, 2),
    "LPC812M101JD20J":  ("LPC812M101JD20", "SO20", 20, "935302399118", 16, 4),
    "LPC812M101JDH16FP":("LPC812M101JDH16", "TSSOP16", 16, "935302398129", 16, 4),
    "LPC812M101JDH16J": ("LPC812M101JDH16", "TSSOP16", 16, "935302398118", 16, 4),
    "LPC812M101JDH20FP":("LPC812M101JDH20", "TSSOP20", 20, "935302401129", 16, 4),
    "LPC812M101JDH20J": ("LPC812M101JDH20", "TSSOP20", 20, "935302401118", 16, 4),
    "LPC812M101JTB16X": ("LPC812M101JTB16", "XSON16", 16, "935301584115", 16, 4),
}
FALSE_FLAGS = ("original_pdf_bytes_archived",
               "original_manufacturer_html_bytes_archived",
               "exact_silicon_revision_verified",
               "programming_qualified", "production_admitted",
               "physical_hil_verified")

def need(test, reason):
    if not test:
        raise ValueError("NXP LPC81x: " + reason)

def blob(content):
    return hashlib.sha1(b"blob " + str(len(content)).encode()
                        + b"\0" + content).hexdigest()

def read():
    raw = SOURCE.read_bytes()
    need(blob(raw) == SOURCE_GIT_BLOB, "transcribed source CSV changed")
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))

def check(r, old):
    sku = r["icpn"]
    need(sku in EXPECTED, "unknown exact NXP material")
    base, pkg, pins, part12nc, flash, ram = EXPECTED[sku]
    family = "LPC811" if sku.startswith("LPC811") else "LPC812"
    driver = "LPC811_001" if family == "LPC811" else "LPC812_101_VARIANTS"
    need((r["manufacturer_base"], r["package"], int(r["terminal_count"]),
          r["manufacturer_12nc"], int(r["flash_kb"]), int(r["sram_kb"]))
         == (base, pkg, pins, part12nc, flash, ram),
         "exact manufacturer 12NC/base/package/memory source drift")
    need((r["manufacturer_status"], r["working_vdd_min_v"],
          r["working_vdd_max_v"], r["temperature_min_c"],
          r["temperature_max_c"], r["core"], r["debug_transport"]) ==
         ("Active", "1.8", "3.6", "-40", "105", "Cortex-M0+", "SWD"),
         "operation voltage/temperature/core/debug evidence drift")
    need((r["io_supply_evidence"], r["analog_supply_evidence"],
          r["datasheet_id"], r["datasheet_revision"], r["datasheet_url"],
          r["datasheet_ordering_locator"], r["datasheet_power_locator"],
          r["material_url"], r["pinned_openocd_part_id_lead"])
         == (IO, ANA, "LPC81XM", REV, DATASHEET,
             "Table 1 and Table 2 printed p3 of 78",
             "Table 9 Static characteristics printed p33 of 78", URL, driver),
         "source context / supply-domain inference drift")
    need(r["evidence_scope"] == SCOPE, "research scope upgraded")
    need(all(r[field] == "false" for field in FALSE_FLAGS),
         "false original-vendor custody / software / production / HIL claim")
    need((old["wave"], old["priority_lead"],
          old["manufacturer_status_observed"],
          old["manufacturer_evidence_scope"], old["target_config"],
          old["flash_driver"], old["manufacturer_url"]) ==
         ("4", "P0", "Active", "MATERIAL_ACTIVE",
          "tcl/target/lpc8xx.cfg", "src/flash/nor/lpc2000.c", URL),
         "previous pinned OpenOCD-first Wave4 identity/driver lead changed")
    need(all(old[f] == "false" for f in (
        "orderable_identity_qualified", "flash_programming_qualified",
        "production_admitted", "hardware_validation_qualified",
        "manufacturer_original_bytes_archived")),
        "previous wave prematurely promoted software/production")

def build():
    prev.verify()
    previous = {r["icpn_observation"]: r for r in prev.build()}
    rows = read()
    need(len(rows) == 8 and {r["icpn"] for r in rows} == set(EXPECTED),
         "expected exactly eight already-discovered material part strings")
    need(len({r["manufacturer_12nc"] for r in rows}) == 8,
         "manufacturer 12NC uniqueness changed")
    for row in rows:
        need(row["icpn"] in previous, "not in Wave4 OpenOCD-first P0 discovery")
        check(row, previous[row["icpn"]])
    need(Counter("LPC811" if r["icpn"].startswith("LPC811") else "LPC812"
                 for r in rows) == {"LPC811": 2, "LPC812": 6},
         "LPC811/812 population changed")
    return rows

def verify():
    build()
    print("NXP_LPC81X_PHASE1_PASS existing_p0_leads=60 "
          "LPC811=2 LPC812=6 source_rows=8 "
          "vdd=1.8-3.6 original_vendor_bytes_archived=0 "
          "new_software_supported=0 new_production_admission=0")

if __name__ == "__main__":
    verify()
