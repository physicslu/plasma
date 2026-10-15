#!/usr/bin/env python3
"""Source-first NXP wave 3: scope-locked offline research-only evidence replay.

OpenOCD source SHA locks are compared to the previously merged upstream
reverse inventory. Official public page observations are NOT original-byte
captured; this checker deliberately refuses to claim manufacturer replay.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LEDGER = HERE / "nxp-openocd-source-first-wave3-v1.json"
BASELINE = HERE / "nxp-501-adr0002-core-transport-qualification-v10.csv"
WAVE2 = HERE / "nxp-openocd-exact-active-discovery-v2.json"
PREVIOUS = HERE / "nxp-openocd-reverse-target-lock-v1.json"
RELEASE = ROOT / "release/openocd.json"
COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"

PARTS = {
    "LPC822": ("LPC822M101JHI33E", "LPC822M101JHI33K",
               "LPC822M101JHI33Y", "LPC822M101JDH20J"),
    "LPC824": ("LPC824M201JHI33E", "LPC824M201JHI33K",
               "LPC824M201JHI33Y", "LPC824M201JDH20J"),
    "LPC1778": ("LPC1778FBD208", "LPC1778FBD208K"),
    "LPC1788": ("LPC1788FBD208", "LPC1788FBD208K"),
    "LPC4078": ("LPC4078FBD208",),
    "LPC2378": ("LPC2378FBD144", "LPC2378FBD144K"),
    "LPC2148": ("LPC2148FBD64",),
    "LPC1549": ("LPC1549JBD100E", "LPC1549JBD100K"),
}
P0 = {"LPC822", "LPC824", "LPC1778", "LPC1788", "LPC4078", "LPC2378"}
ROUTES = {
    "LPC822": ("tcl/target/lpc8xx.cfg", "tcl/target/lpc1xxx.cfg"),
    "LPC824": ("tcl/target/lpc8xx.cfg", "tcl/target/lpc1xxx.cfg"),
    "LPC1778": ("tcl/target/lpc17xx.cfg", "tcl/target/lpc1xxx.cfg"),
    "LPC1788": ("tcl/target/lpc17xx.cfg", "tcl/target/lpc1xxx.cfg"),
    "LPC4078": ("tcl/target/lpc40xx.cfg", "tcl/target/lpc1xxx.cfg"),
    "LPC2378": ("tcl/target/lpc2378.cfg", "tcl/target/lpc2xxx.cfg"),
    "LPC2148": ("tcl/target/lpc2148.cfg", "tcl/target/lpc2xxx.cfg"),
    "LPC1549": (None, None),
}
SOURCE_LOCKS = {
    "tcl/target/lpc8xx.cfg": "4c54a2a6670d6186297306112deee8d25e2627e4",
    "tcl/target/lpc1xxx.cfg": "70d26d2673900b06c6d5eef8e55b4542103e9e42",
    "tcl/target/lpc17xx.cfg": "35d8badea416e641babe6ccad3fd8503f3de7cae",
    "tcl/target/lpc40xx.cfg": "f0be5a1e40979b2484f9f8edec0c4dfa49a65069",
    "tcl/target/lpc2148.cfg": "fda622f11d9e240cb46e3e43243ea14a8abd4246",
    "tcl/target/lpc2378.cfg": "59e41c9a10cfe92a3d57de91209dfcdf223599de",
    "tcl/target/lpc2xxx.cfg": "bc5e6009f88567471d8b9c2f6865d50f8bf132fb",
    "src/flash/nor/lpc2000.c": "f12eef7e4ce68fc8830773f6c57da57dfb87d6b8",
}
PAGES = {
    "LPC822": "https://www.nxp.com/products/LPC82X?tab=Package_Quality_Tab",
    "LPC824": "https://www.nxp.com/products/LPC82X?tab=Package_Quality_Tab",
    "LPC1778": "https://www.nxp.com/products/LPC1778FBD208?tab=Package_Quality_Tab",
    "LPC1788": "https://www.nxp.com/products/LPC1788FBD208?tab=Package_Quality_Tab",
    "LPC4078": "https://www.nxp.com/products/LPC4078FBD208?tab=Package_Quality_Tab",
    "LPC2378": "https://www.nxp.com/products/processors-and-microcontrollers/arm-microcontrollers/general-purpose-mcus/lpc2000-arm7/arm7-with-512kb-flash-58-kb-sram-ethernet-usb-2-0-device-can-and-10-bit-adc:LPC2378FBD144?tab=Package_Quality_Tab",
    "LPC2148": "https://www.nxp.com/products/processors-and-microcontrollers/arm-microcontrollers/general-purpose-mcus/lpc2000-arm7/single-chip-16-bit-32-bit-microcontrollers-up-to-512-kb-flash-with-isp-iap-usb-2-0-full-speed-device-10-bit-adc-and-dac:LPC2148FBD64?tab=Package_Quality_Tab",
    "LPC1549": "https://www.nxp.com/products/LPC1549JBD100?tab=Package_Quality_Tab",
}
CLASS = {
    family: ("P0_DISCOVERY_CANDIDATE" if family in P0 else
             "P1_ORDERING_VARIANT_AMBIGUITY" if family == "LPC2148" else
             "P1_DRIVER_ONLY_NO_PINNED_TARGET_CONFIG")
    for family in PARTS
}
SUPPORT = {
    "LPC822": "LPC822_101", "LPC824": "LPC824_201",
    "LPC1778": "LPC1778", "LPC1788": "LPC1788", "LPC4078": "LPC4078",
    "LPC2378": "LPC2000_V2", "LPC2148": "LPC2000_V2",
    "LPC1549": "LPC1500_DRIVER_VARIANT",
}


def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError("NXP source-first wave3: " + why)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(doc: dict | None = None, *, previous: dict | None = None,
             old: list[dict] | None = None, wave2: dict | None = None) -> dict:
    doc = doc if doc is not None else load(LEDGER)
    previous = previous if previous is not None else load(PREVIOUS)
    wave2 = wave2 if wave2 is not None else load(WAVE2)
    release = load(RELEASE)
    require(doc["schema_version"] == 1 and
            doc["scope"] == "NXP_PINNED_OPENOCD_SOURCE_FIRST_DISCOVERY_WAVE3_RESEARCH_ONLY" and
            doc["provider"] == "openocd-org/openocd" and
            doc["openocd_version"] == release["version"] == "0.12.0" and
            doc["source_commit"] == release["source_commit"] == previous["source_commit"] == COMMIT,
            "pinned version or research scope changed")
    require(doc["manufacturer_original_html_archived"] is False and
            doc["whole_vendor_active_denominator"] is None and
            doc["existing_review_501_not_modified"] is True and
            doc["first_discovery_wave2_27_not_modified"] is True,
            "false source custody or vendor-wide coverage claim")
    source_pins = {row["path"]: row["git_blob"] for row in previous["target_files"]}
    source_pins.update(previous["verified_baseline_driver_blobs"])
    require(doc["target_driver_git_blob_sha1"] == SOURCE_LOCKS and
            all(source_pins[k] == value for k, value in SOURCE_LOCKS.items()),
            "upstream source Git blob re-sealed without review")

    if old is None:
        with BASELINE.open(encoding="utf-8", newline="") as stream:
            old = list(csv.DictReader(stream))
    original = {row["icpn"] for row in old}
    old2 = {row["icpn"] for row in wave2["records"]}
    require(len(original) == len(old) == 501 and
            len(old2) == len(wave2["records"]) == 27,
            "historical 501/27 population changed")
    require(wave2["source_commit"] == COMMIT, "prior discovery provider drift")
    rows = doc["records"]
    expected = {sku for family_parts in PARTS.values() for sku in family_parts}
    parts = [row["icpn"] for row in rows]
    require(len(rows) == len(expected) == len(set(parts)) == 18 and
            set(parts) == expected and parts == sorted(parts),
            "exact candidate additions, deletion, or duplicate require explicit review")
    require(not set(parts).intersection(original | old2),
            "candidate overlaps previously reviewed 501 or wave2 27")

    counts = Counter()
    for row in rows:
        family = row["family"]
        require(family in PARTS and row["icpn"] in PARTS[family],
                "part/family authority drift")
        target, helper = ROUTES[family]
        require((row["pinned_target_config"], row["pinned_target_helper"],
                 row["pinned_flash_driver"]) ==
                (target, helper, "src/flash/nor/lpc2000.c") and
                row["pinned_driver_identity"] == SUPPORT[family],
                "Target/Helper/Driver/ID evidence mismatch")
        url = row["manufacturer_url"]
        require(url == PAGES[family] and
                urlparse(url).netloc == "www.nxp.com",
                "unapproved manufacturer source URL")
        require(row["candidate_class"] == CLASS[family] and
                row["manufacturer_evidence_state"] ==
                "PUBLIC_OFFICIAL_PACKAGE_QUALITY_OBSERVED_ORIGINAL_BYTES_NOT_SHA256_ARCHIVED" and
                row["software_supported"] is False and
                row["production_admitted"] is False and
                row["hardware_validated"] is False,
                "source-only candidate silently promoted")
        require(row["manufacturer_status"] ==
                ("MIXED_MATERIAL_LIFECYCLE_ACTIVE_151_157_NLM_118"
                 if family == "LPC2148" else "Active"),
                "cannot promote mixed lifecycle to unqualified Active")
        if family == "LPC2378":
            require("JTAG" in row["qualifying_gap"] and "NRND" in row["qualifying_gap"],
                    "LPC2378 JTAG/NRND restriction lost")
        if family == "LPC1549":
            require(target is None and helper is None,
                    "LPC1549 cannot borrow an invented pinned Target CFG")
        counts[CLASS[family]] += 1
    require(counts == {"P0_DISCOVERY_CANDIDATE": 15,
                       "P1_ORDERING_VARIANT_AMBIGUITY": 1,
                       "P1_DRIVER_ONLY_NO_PINNED_TARGET_CONFIG": 2},
            "priority counts drift")
    return {
        "new_official_source_observations":len(rows),
        "p0_discovery_candidates":counts["P0_DISCOVERY_CANDIDATE"],
        "p1_candidates":len(rows)-counts["P0_DISCOVERY_CANDIDATE"],
        "manufacturer_pages":len(set(PAGES.values())),
        "source_git_blobs":len(SOURCE_LOCKS),
        "new_software_supported":0,
        "new_production_admitted":0,
        "official_original_html_sha256_present":False,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
    print("NXP WAVE 3 SOURCE-FIRST RESEARCH: PASS; no programming qualification")
