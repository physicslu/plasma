#!/usr/bin/env python3
"""NXP ADR-0002: consolidate three OpenOCD-first discovery waves, research only.

This is a source-locked identity/evidence gate, NOT an OpenOCD scanner, runtime
qualification, exact commercial admission, or automatic P0/P1 promotion.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = ("nxp-501-adr0002-core-transport-qualification-v10.csv",
            "9f0397fe6062356fd04cd5eb73133969e75d9bfb")
WAVES = (
    (2, "nxp-openocd-exact-active-discovery-v2.json", "13919603e288a89f53362076e75dbf4d0839a1fa", 27),
    (3, "nxp-openocd-source-first-wave3-v1.json", "3fd40854d4cbab17e5dcaa7019df385e33c6fbc0", 18),
    (4, "nxp-openocd-source-first-wave4-v1.json", "c2f76934edd9a1ab05761134887fe5aabbaa115c", 20),
)
UPSTREAM = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
LEDGER = HERE / "nxp-65-openocd-discovery-gates-v1.csv"
FIELDS = [
    "icpn_observation", "wave", "priority_lead", "manufacturer_url",
    "manufacturer_evidence_scope", "manufacturer_status_observed",
    "source_json", "openocd_source_commit", "target_config", "flash_driver",
    "orderable_identity_qualified", "exact_silicon_crosswalk_qualified",
    "manufacturer_original_bytes_archived", "flash_programming_qualified",
    "production_admitted", "hardware_validation_qualified",
    "transport_gate", "next_research_gate",
]

def require(test: bool, reason: str):
    if not test:
        raise ValueError("NXP65: " + reason)

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def locked_bytes(filename: str, sha: str) -> bytes:
    content = (HERE / filename).read_bytes()
    require(git_blob(content) == sha, "source Git blob changed: " + filename)
    return content

def read_json(filename: str, sha: str) -> dict:
    return json.loads(locked_bytes(filename, sha))

def priority(wave: int, record: dict) -> str:
    raw = (record["priority_proposal"] if wave == 2 else
           record["candidate_class"] if wave == 3 else record["priority"])
    require(raw.startswith(("P0_", "P1_")), "unexpected priority encoding")
    return raw[:2]

def classify(wave: int, record: dict, source: str) -> dict:
    sku = record["icpn"]
    pr = priority(wave, record)
    require(sku and record["manufacturer_url"].startswith("https://www.nxp.com/"),
            "missing NXP official source/identity")
    if wave == 2:
        require(record["manufacturer_page_bytes_archived"] is False,
                "wave2 original bytes unexpectedly archived") if "manufacturer_page_bytes_archived" in record else None
        require(record["exact_to_silicon_id"] == "UNVERIFIED"
                and record["flash_geometry_and_operations"] == "UNVERIFIED"
                and record["production_admission"] is False
                and record["openocd_software_supported"] is False,
                "wave2 prematurely promoted exact support")
        scope = record["manufacturer_observation"]
        lifecycle = record["manufacturer_active_status"]
        target = record["openocd_target"]
        driver = record["openocd_flash_driver"]
    elif wave == 3:
        require(record["software_supported"] is False
                and record["production_admitted"] is False
                and record["hardware_validated"] is False,
                "wave3 prematurely promoted support")
        scope = record["manufacturer_evidence_state"]
        lifecycle = record["manufacturer_status"]
        target = record["pinned_target_config"] or ""
        driver = record["pinned_flash_driver"] or ""
    else:
        require(record["manufacturer_original_bytes_archived"] is False
                and record["exact_material_to_silicon_part_id_verified"] is False
                and record["flash_programming_qualified"] is False
                and record["production_admitted"] is False
                and record["physical_hil_verified"] is False,
                "wave4 prematurely promoted support")
        scope = record["manufacturer_evidence_scope"]
        lifecycle = record["manufacturer_observed_lifecycle"]
        target = record["openocd_target"] or ""
        driver = record["openocd_flash_driver"] or ""

    require(bool(driver) and (pr == "P1" or bool(target)),
            "P0 lacks source-backed target + driver")
    require(lifecycle in ("Active", "NRND"),
            "unexpected lifecycle asserted as valid Active")
    if sku == "LPC1769FBD100":
        require(scope == "PRODUCT_ACTIVE_MATERIAL_LIFECYCLE_UNVERIFIED" and wave == 4,
                "product-level Active improperly upgraded")
        gate = "PRODUCT_ACTIVE_ONLY_MATERIAL_UNVERIFIED"
    elif sku == "LPC2148FBD64":
        require(wave == 3 and pr == "P1"
                and "118" in record["qualifying_gap"]
                and "151" in record["qualifying_gap"]
                and "157" in record["qualifying_gap"],
                "mixed-lifecycle LPC2148 evidence lost")
        gate = "MIXED_MATERIAL_LIFECYCLE_AND_JTAG"
    elif sku.startswith("LPC2378"):
        require(wave == 3 and pr == "P0",
                "JTAG-only LPC2378 discovery unexpectedly reclassified")
        gate = "JTAG_ARM7_NRND_NOT_SWD_QUALIFIED"
    elif "/" in sku:
        gate = "RAW_DISPLAY_CODE_ORDERING_NORMALIZATION"
    elif pr == "P1":
        gate = "INCOMPLETE_PINNED_TARGET_OR_DRIVER_ID"
    elif wave == 2:
        gate = "ORDERING_NORMALIZATION_AND_SILICON_ID_CROSSWALK"
    else:
        gate = "ORDERING_SILICON_CROSSWALK_AND_SOURCE_CAPTURE"

    return {
        "icpn_observation": sku, "wave": str(wave), "priority_lead": pr,
        "manufacturer_url": record["manufacturer_url"],
        "manufacturer_evidence_scope": scope,
        "manufacturer_status_observed": lifecycle,
        "source_json": source,
        "openocd_source_commit": UPSTREAM,
        "target_config": target, "flash_driver": driver,
        "orderable_identity_qualified": "false",
        "exact_silicon_crosswalk_qualified": "false",
        "manufacturer_original_bytes_archived": "false",
        "flash_programming_qualified": "false",
        "production_admitted": "false",
        "hardware_validation_qualified": "false",
        "transport_gate": "JTAG_ROUTE_NOT_SWD_VERIFIED" if
            sku.startswith("LPC2378") or sku == "LPC2148FBD64"
            else "NOT_PPU_HIL_QUALIFIED",
        "next_research_gate": gate,
    }

def build() -> list[dict]:
    source, sha = BASELINE
    original = list(csv.DictReader(io.StringIO(locked_bytes(source, sha).decode())))
    require(len(original) == 501 and len({r["icpn"] for r in original}) == 501,
            "historical 501 changed")
    require(Counter(r["research_priority"] for r in original) ==
            {"P0": 27, "P1": 38, "P2": 436}, "historical priority counts changed")
    existing = {r["icpn"] for r in original}
    rows = []
    for wave, filename, sha, expected in WAVES:
        doc = read_json(filename, sha)
        require(doc["source_commit"] == UPSTREAM,
                "unexpected OpenOCD source commit " + filename)
        require(len(doc["records"]) == expected,
                "wave scope changed " + filename)
        custody = (doc["manufacturer_page_bytes_archived"] if wave == 2 else
                   doc["manufacturer_original_html_archived"] if wave == 3 else
                   doc["official_page_original_html_byte_custody"])
        require(custody is False, "original web evidence custody fabricated")
        for record in doc["records"]:
            rows.append(classify(wave, record, filename))
    keys = [r["icpn_observation"] for r in rows]
    require(len(keys) == len(set(keys)) == 65
            and not (set(keys) & existing),
            "repeated or historical exact ICPN included")
    require(Counter(r["priority_lead"] for r in rows) == {"P0": 60, "P1": 5},
            "65 discovery priority lead counts changed")
    require(Counter(r["wave"] for r in rows) == {"2": 27, "3": 18, "4": 20},
            "wave source split changed")
    require(all(r["orderable_identity_qualified"] == "false"
                and r["flash_programming_qualified"] == "false"
                and r["production_admitted"] == "false" for r in rows),
            "candidate discovery upgraded into support")
    return sorted(rows, key=lambda r: (int(r["wave"]), r["icpn_observation"]))

def serialize(rows: list[dict]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")

def verify():
    rows = build()
    require(LEDGER.read_bytes() == serialize(rows),
            "65-row consolidated research ledger not reproducible")
    print("NXP_65_DISCOVERY_GATES_PASS existing=501 P0=27 P1=38 P2=436 "
          "new=65 P0_leads=60 P1_leads=5; supported=0 admitted=0")

if __name__ == "__main__":
    verify()
