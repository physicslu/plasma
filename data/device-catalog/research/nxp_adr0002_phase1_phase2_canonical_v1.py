#!/usr/bin/env python3
"""NXP ADR-0002 historical-source projection under Catalog Levels.

Official manufacturer identity ledgers establish Level 0 DISCOVERED identity.
Archived OpenOCD 501 v10 is a source clue for Level 1 programming relevance,
not Programming Qualification authority. Historical filenames remain immutable,
but canonical output contains no phase-prefixed fields.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SUB = Path("data/device-catalog/research")
SRC = {
    "legacy": ("nxp-501-phase1-ic-information-v13.csv", "4a0fbad8fa5f57580ba28e92f71b0793e12faf07", 501),
    "81": ("nxp-8-lpc81x-phase1-official-material-v1.csv", "2d94cdc9506b336dc580a178d3309dea6c1d8c63", 8),
    "82": ("nxp-8-lpc82x-official-phase1-observations-v1.csv", "449a3a6cb5e98ff1edef8ea2bb6a065ef8482528", 8),
    "11": ("nxp-11-lpc11u-lpc83x-phase1-official-material-v1.csv", "0a90ceb12dde7e37fbee0e1ede0f230bea0891f5", 11),
    "25": ("nxp-25-lpc-exact-material-12nc-phase1-v1.csv", "31d3fd024c01ff21db0534a5522fc0fbedf88890", 25),
    "21": ("nxp-21-k40-k60-kl4x-official-materials-phase1-v1.csv", "d11788fb5b210bd3b3ed06807f922c3ac1e2f8a0", 21),
    "oldtech": ("nxp-501-adr0002-core-transport-qualification-v10.csv", "9f0397fe6062356fd04cd5eb73133969e75d9bfb", 501),
}
RELEASE_BLOB = "08c884b1bf6f5999c6d34c090992a8b59d85971d"
COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
STATES = ("UNKNOWN", "CANDIDATE", "SUPPORTED", "UNSUPPORTED")

def need(ok, reason):
    if not ok:
        raise ValueError("NXP ADR-0002 Catalog Level projection: " + reason)

def gitblob(blob):
    return hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest()

def read_source(key, root=ROOT):
    file, digest, count = SRC[key]
    raw = (root / SUB / file).read_bytes()
    need(gitblob(raw) == digest, "pinned source bytes changed: " + file)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    need(len(rows) == count and len({r["icpn"] for r in rows}) == count,
         "source row count / duplicate changed: " + file)
    return rows

def authority(root=ROOT):
    adr = (root / "docs/adr/0002-openocd-software-qualified-catalog-visibility.md").read_text(encoding="utf-8")
    for token in ("Level 0 — DISCOVERED",
                  "Level 1 — PROGRAMMING_CANDIDATE",
                  "Level 2 — PROGRAMMABLE",
                  "Level 3 — PLASMA_VERIFIED",
                  "INFORMATION_COMPLETE"):
        need(token in adr, "latest ADR-0002 semantic contract missing: " + token)
    release = (root / "release/openocd.json").read_bytes()
    need(gitblob(release) == RELEASE_BLOB, "pinned OpenOCD provider blob drift")
    r = json.loads(release)
    need(r["engine"] == "openocd" and r["version"] == "0.12.0"
         and r["source_commit"] == COMMIT, "pinned OpenOCD provider changed")
    return r

def identities(root=ROOT):
    old = read_source("legacy", root)
    admitted = [r for r in old if r["identity_state"] == "ADMITTED"]
    need(len(admitted) == 224 and
         len([r for r in old if r["identity_state"] == "RESEARCH_ONLY"]) == 277,
         "Level 0 identity gate must not silently promote the 277 Research-only identities")
    parts = {}
    for r in admitted:
        need(r["manufacturer_uri"].startswith("https://www.nxp.com/"),
             "existing manufacturer identity source missing")
        parts[r["icpn"]] = {
            "source":r["manufacturer_uri"], "base_device":r["base_device"],
            "base_relation":"UNRECONCILED_ALIAS" if r["base_device"] == r["icpn"] else "LEGACY_REVIEW",
            "original_bytes":"NOT_DEMONSTRATED"}
    specs = [
        ("81","material_url","manufacturer_base"),
        ("82","manufacturer_material_url","datasheet_base"),
        ("11","official_exact_material_page","manufacturer_base"),
        ("25","official_package_quality_url","manufacturer_model_lead"),
        ("21","official_material_product_url","base_device"),
    ]
    for name,uri,base in specs:
        for r in read_source(name,root):
            p = r["icpn"]
            need(p not in parts and r[uri].startswith("https://www.nxp.com/")
                 and bool(r[base]) and len(r["manufacturer_12nc"]) == 12
                 and r["manufacturer_12nc"].isascii() and r["manufacturer_12nc"].isdigit(),
                 "new Level 0 identity requires official exact material/Base/12NC: "+p)
            parts[p] = {"source":r[uri],"base_device":r[base],
                        "base_relation":"DATASHEET_CROSSWALK" if name in ("81","82","11") else "PRODUCT_MODEL",
                        "original_bytes":"NOT_ARCHIVED"}
    need(len(parts) == 297 and sum(x["base_relation"]=="UNRECONCILED_ALIAS" for x in parts.values())==212,
         "approved Level 0 297 identities / 212 alias gaps drifted")
    return parts

def validate(rows):
    need(len(rows)==297 and len({r["icpn"] for r in rows})==297,
         "Catalog Level projection must use distinct exact ICPNs")
    need(all(r["identity_state"] == "IDENTIFIED" and r["manufacturer"] == "NXP"
             and r["programming_state"] in STATES
             and r["catalog_level"] in (0, 1)
             and r["catalog_level_state"] in ("DISCOVERED", "PROGRAMMING_CANDIDATE")
             for r in rows),
         "illegal Catalog Level / Programming state")
    need(Counter(r["programming_state"] for r in rows)=={"CANDIDATE":28,"UNKNOWN":269},
         "old source-only research cannot promote PROGRAMMABLE")
    need(all(r["silicon_revision"] == "NOT_VERIFIED"
             and r["flash_geometry"] == "NOT_VERIFIED"
             and r["security"] == "NOT_VERIFIED"
             and not r["programming_profile_id"]
             and r["operations"] == {"erase":"NOT_QUALIFIED","program":"NOT_QUALIFIED",
                                    "read":"NOT_QUALIFIED","verify":"NOT_QUALIFIED"}
             and r["compatibility_state"] == "NOT_AUDITED"
             for r in rows), "fabricated software support, Programming Profile or HIL")
    need(sum(r["programming_state"]=="CANDIDATE" and r["target_cfg"]=="tcl/target/kl25.cfg"
             for r in rows)==12, "KL25 source-backed candidate count changed")
    need(sum(r["programming_state"]=="CANDIDATE" and not r["target_cfg"]
             and r["driver"]=="kinetis" for r in rows)==16,
         "K32L2 driver-only candidate count changed")
    need(all(not r["target_cfg"] and not r["driver"]
             for r in rows if r["programming_state"]=="UNKNOWN"),
         "unreviewed source guesses cannot become qualified routes")

def build(root=ROOT):
    # Read reviewed exact-material inputs independently. Historical P0/P1/P2
    # research-priority audit chains are not invoked by the canonical pipeline.
    provider = authority(root)
    parts = identities(root)
    tech = {r["icpn"]:r for r in read_source("oldtech",root)}
    rows=[]
    for part in sorted(parts):
        historic = tech.get(part)
        candidate = bool(historic and historic["identity_scope"]=="production_224"
                         and historic["software_support_qualification"]=="CANDIDATE")
        if candidate:
            need(historic["openocd_source_commit"] == COMMIT
                 and historic["exact_icpn_applicability"]=="UNVERIFIED"
                 and historic["exact_icpn_to_silicon_revision"]=="UNKNOWN"
                 and historic["operation_read_verify_qualification"]=="UNKNOWN"
                 and historic["flash_bank_driver"]=="kinetis",
                 "historical partial evidence is not independently qualified")
        target = historic["target_config"] if candidate else ""
        driver = historic["flash_bank_driver"] if candidate else ""
        missing = ["EXACT_SILICON_ID_REVISION","FLASH_GEOMETRY","SECURITY_POLICY",
                   "ERASE_PROGRAM_READ_VERIFY","REVIEWED_PROGRAMMING_PROFILE"]
        if not target: missing.append("TARGET_CONFIG")
        if not driver: missing.append("FLASH_DRIVER")
        rows.append({
            "manufacturer":"NXP","icpn":part,
            "identity_state":"IDENTIFIED",
            "information_complete":False, **parts[part],
            "catalog_level":1 if candidate else 0,
            "catalog_level_state":"PROGRAMMING_CANDIDATE" if candidate else "DISCOVERED",
            "programming_state":"CANDIDATE" if candidate else "UNKNOWN",
            "provider":"openocd-upstream" if candidate else None,
            "provider_version":provider["version"] if candidate else None,
            "provider_commit":COMMIT if candidate else None,
            "target_cfg":target,"driver":driver,
            "silicon_revision":"NOT_VERIFIED", "flash_geometry":"NOT_VERIFIED",
            "security":"NOT_VERIFIED","programming_profile_id":None,
            "operations":{op:"NOT_QUALIFIED" for op in ("erase","program","read","verify")},
            "missing_evidence":missing, "compatibility_state":"NOT_AUDITED"})
    validate(rows)
    return rows

def report(rows):
    states=Counter(r["programming_state"] for r in rows)
    levels=Counter(r["catalog_level"] for r in rows)
    return {
        "manufacturer":"NXP",
        "catalog_level_0_or_higher_discovered":len(rows),
        "catalog_level_0_only":levels[0],
        "catalog_level_1_programming_candidate":levels[1],
        "information_complete":0,
        "base_alias_pending":212,
        "new_original_vendor_bytes_not_archived":73,
        "programming_state_counts":{state:states[state] for state in STATES},
        "catalog_level_1_candidate_evidence":{
            "KL25_target_driver":12,
            "K32L2_driver_only":16,
        },
        "catalog_level_2_programmable_in_this_source_audit":0,
        "programming_scope":"no new software qualification; not all external support assessed",
        "catalog_level_3_state":"NOT_AUDITED",
        "execution_authorized":False,
        "canonical_catalog_levels_only":True,
        "historical_priorities_excluded":True,
        "openocd_source_commit":COMMIT,
    }

if __name__=="__main__":
    import sys
    rows=build()
    print("NXP_ADR0002_CATALOG_LEVEL_PASS L0PLUS=297 L0_ONLY=269 L1=28 L2=0_IN_AUDIT L3=NOT_AUDITED")
    print(json.dumps(report(rows),indent=2,ensure_ascii=False))
    if "--jsonl" in sys.argv:
        for row in rows:
            print(json.dumps(row,ensure_ascii=False,sort_keys=True))
