#!/usr/bin/env python3
"""NXP Phase 1: 8 LPC82x exact-material evidence crosswalk, research only.

Manufacturer material rows + LPC82X Rev1.5 original base datasheet are the
evidence sources; raw manufacturer PDF/HTML binary custody is NOT claimed.
This neither qualifies the OpenOCD installed runtime nor any physical Site.
"""
from __future__ import annotations
import csv
import hashlib
import io
from collections import Counter
from pathlib import Path

import nxp_65_discovery_gates_v1 as baseline

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "nxp-8-lpc82x-official-phase1-observations-v1.csv"
SOURCE_GIT_BLOB = "449a3a6cb5e98ff1edef8ea2bb6a065ef8482528"
LPC822 = {
    "LPC822M101JDH20J": ("LPC822M101JDH20", "TSSOP20", "TSSOP20", 20, "935304005118"),
    "LPC822M101JHI33E": ("LPC822M101JHI33", "HVQFN32", "HVQFN33", 33, "935304007551"),
    "LPC822M101JHI33K": ("LPC822M101JHI33", "HVQFN32", "HVQFN33", 33, "935304007557"),
    "LPC822M101JHI33Y": ("LPC822M101JHI33", "HVQFN32", "HVQFN33", 33, "935304007518"),
}
LPC824 = {
    "LPC824M201JDH20J": ("LPC824M201JDH20", "TSSOP20", "TSSOP20", 20, "935304006118"),
    "LPC824M201JHI33E": ("LPC824M201JHI33", "HVQFN32", "HVQFN33", 33, "935304008551"),
    "LPC824M201JHI33K": ("LPC824M201JHI33", "HVQFN32", "HVQFN33", 33, "935304008557"),
    "LPC824M201JHI33Y": ("LPC824M201JHI33", "HVQFN32", "HVQFN33", 33, "935304008518"),
}
EXACT = {**LPC822, **LPC824}
VENDOR = "https://www.nxp.com/products/LPC82X?tab=Package_Quality_Tab"
DOC = "LPC82X"
DOC_REV = "Rev 1.5 2023-02-07"
SCOPE = "RESEARCH_EXACT_MATERIAL_OBSERVED_PHASE1_BASE_DATASHEET_CROSSWALK"
IO_NOTE = "VDD pad ring 1.8-3.6V; no independent VDDIO evidenced"
ANA_NOTE = "VDD supplies analog peripherals; separate VDDA not evidenced"
VREF_NOTE = "VREFP is an ADC reference (2.4V to VDD), not an analog supply"
ORDER_LOCATOR = "Table 1 and Table 2 printed p3/82"
SUPPLY_LOCATOR = (
    "Table 3 VDD pad/analog printed p9/82; "
    "Table 7 normal VDD printed p33/82"
)

def need(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError("NXP LPC82X Phase1: " + reason)

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def read() -> list[dict[str, str]]:
    data = SOURCE.read_bytes()
    need(git_blob(data) == SOURCE_GIT_BLOB, "8-row project-side source Git SHA mismatch")
    rows = list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
    need(len(rows) == 8, "unexpected source row count")
    return rows

def check_one(r: dict[str, str], original: dict[str, str]) -> None:
    sku = r["icpn"]
    need(sku in EXACT, "out-of-scope material observation")
    base, product_pkg, datasheet_pkg, terminals, nc = EXACT[sku]
    family = "LPC822" if sku in LPC822 else "LPC824"
    flash, ram, driver = (16, 4, "LPC822_101") if family == "LPC822" else (32, 8, "LPC824_201")
    need(original["icpn_observation"] == sku
         and original["wave"] == "3"
         and original["priority_lead"] == "P0"
         and original["manufacturer_status_observed"] == "Active"
         and original["manufacturer_original_bytes_archived"] == "false"
         and original["flash_programming_qualified"] == "false"
         and original["orderable_identity_qualified"] == "false"
         and original["production_admitted"] == "false",
         "Wave3 observation falsely promoted or changed")
    need(original["target_config"] == "tcl/target/lpc8xx.cfg"
         and original["flash_driver"] == "src/flash/nor/lpc2000.c"
         and original["manufacturer_url"] == VENDOR,
         "pinned OpenOCD/official NXP lead changed")
    need(
        (r["datasheet_base"], r["nxp_product_package_alias"],
         r["datasheet_package"], int(r["datasheet_electrical_terminals"]),
         r["manufacturer_12nc"])
        == (base, product_pkg, datasheet_pkg, terminals, nc),
        "exact material/order/package/12NC crosswalk drift")
    need(
        (int(r["flash_kb"]), int(r["sram_kb"]),
         r["openocd_family_part_id_case"]) == (flash, ram, driver),
        "LPC822/824 source-backed memory/driver family identification changed")
    need(
        (r["manufacturer_material_status"], r["normal_vdd_min_v"],
         r["normal_vdd_max_v"], r["temperature_min_c"],
         r["temperature_max_c"]) == ("Active", "1.8", "3.6", "-40", "105"),
        "official manufacturer material or normal voltage/temperature drift")
    need(
        r["io_supply_domain"] == IO_NOTE
        and r["analog_supply_domain"] == ANA_NOTE
        and r["vrefp_scope"] == VREF_NOTE
        and r["datasheet_document"] == DOC
        and r["datasheet_revision"] == DOC_REV
        and r["datasheet_ordering_locator"] == ORDER_LOCATOR
        and r["datasheet_supply_locator"] == SUPPLY_LOCATOR
        and r["manufacturer_material_url"] == VENDOR,
        "official original NXP Table 1/2/3/7 domain or scope changed")
    for field in (
        "original_datasheet_pdf_binary_archived",
        "original_material_html_binary_archived",
        "ordering_to_silicon_part_id_verified",
        "openocd_programming_qualified",
        "production_admitted",
        "physical_hil_verified",
    ):
        need(r[field] == "false", "false original source/qualification claim: " + field)
    need(r["qualification_scope"] == SCOPE,
         "Phase1 material evidence promoted to software or physical support")

def build() -> list[dict[str, str]]:
    baseline.verify()
    old = {r["icpn_observation"]: r for r in baseline.build()}
    rows = read()
    need({r["icpn"] for r in rows} == set(EXACT),
         "not precisely the eight prior Wave3 P0 ICPNs")
    need(len({r["icpn"] for r in rows}) == 8
         and len({r["manufacturer_12nc"] for r in rows}) == 8,
         "duplicated exact material / 12NC")
    for r in rows:
        need(r["icpn"] in old, "not in prior source-locked P0 lead queue")
        check_one(r, old[r["icpn"]])
    need(Counter(r["openocd_family_part_id_case"] for r in rows)
         == {"LPC822_101": 4, "LPC824_201": 4},
         "incorrect base device group counts")
    return rows

def verify() -> None:
    rows = build()
    print("NXP_LPC82X_PHASE1_V1_PASS exact_source_materials=8 "
          "LPC822=4 LPC824=4; VDD=1.8-3.6; "
          "original_vendor_bytes_archived=0; "
          "exact_software_supported=0 production_admitted=0")

if __name__ == "__main__":
    verify()
