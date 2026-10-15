#!/usr/bin/env python3
"""NXP ADR-0002 Phase1 exact identity to Phase2 evidence-only transition.

Official manufacturer identity ledgers are the Phase1 authority.
Archived OpenOCD 501 v10 is a source clue, not Phase2 state authority.
No historical P0/P1/P2 research priority enters the canonical output.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

import nxp_phase1_kinetis_21_official_v1 as approved_phase1

ROOT = Path(__file__).resolve().parents[2]
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
        raise ValueError("NXP ADR-0002 Phase1/Phase2: " + reason)

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
    for token in ("Phase 1 — IC Information", "Phase 2 — Programming",
                  "Phase 3 — PLASMA Compatibility", "INFORMATION_COMPLETE",
                  "不得再建立或依賴另一套數字型研究狀態"):
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
         "Phase1 277 Research-only identities must not be silently promoted")
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
                 "new Phase1 requires official exact material/Base/12NC: "+p)
            parts[p] = {"source":r[uri],"base_device":r[base],
                        "base_relation":"DATASHEET_CROSSWALK" if name in ("81","82","11") else "PRODUCT_MODEL",
                        "original_bytes":"NOT_ARCHIVED"}
    need(len(parts) == 297 and sum(x["base_relation"]=="UNRECONCILED_ALIAS" for x in parts.values())==212,
         "approved Phase1 297 identities / 212 alias gaps drifted")
    return parts

def validate(rows):
    need(len(rows)==297 and len({r["icpn"] for r in rows})==297,
         "Phase2 must be subset of distinct exact Phase1 ICPNs")
    need(all(r["phase1"] == "IDENTIFIED" and r["manufacturer"] == "NXP"
             and r["phase2"] in STATES for r in rows),
         "illegal Phase1/Phase2 state")
    need(Counter(r["phase2"] for r in rows)=={"CANDIDATE":28,"UNKNOWN":269},
         "old source-only research cannot promote SUPPORTED or UNSUPPORTED")
    need(all(r["silicon_revision"] == "NOT_VERIFIED"
             and r["flash_geometry"] == "NOT_VERIFIED"
             and r["security"] == "NOT_VERIFIED"
             and not r["programming_profile_id"]
             and r["operations"] == {"erase":"NOT_QUALIFIED","program":"NOT_QUALIFIED",
                                    "read":"NOT_QUALIFIED","verify":"NOT_QUALIFIED"}
             and r["phase3"] == "NOT_AUDITED"
             for r in rows), "fabricated software support, Programming Profile or HIL")
    need(sum(r["phase2"]=="CANDIDATE" and r["target_cfg"]=="tcl/target/kl25.cfg"
             for r in rows)==12, "KL25 source-backed candidate count changed")
    need(sum(r["phase2"]=="CANDIDATE" and not r["target_cfg"]
             and r["driver"]=="kinetis" for r in rows)==16,
         "K32L2 driver-only candidate count changed")
    need(all(not r["target_cfg"] and not r["driver"]
             for r in rows if r["phase2"]=="UNKNOWN"),
         "unreviewed source guesses cannot become qualified routes")

def build(root=ROOT):
    # Independent approved source-funnel verifier; never import the old v10
    # generator that pins obsolete ADR revision or P0/P1/P2 methodology.
    if root == ROOT:
        current = approved_phase1.build()
        need(current["phase1_identified_s1"] == 297, "approved Phase1 snapshot changed")
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
            "manufacturer":"NXP","icpn":part,"phase1":"IDENTIFIED",
            "information_complete":False, **parts[part],
            "phase2":"CANDIDATE" if candidate else "UNKNOWN",
            "provider":"openocd-upstream","provider_version":provider["version"],
            "provider_commit":COMMIT,"target_cfg":target,"driver":driver,
            "silicon_revision":"NOT_VERIFIED", "flash_geometry":"NOT_VERIFIED",
            "security":"NOT_VERIFIED","programming_profile_id":None,
            "operations":{op:"NOT_QUALIFIED" for op in ("erase","program","read","verify")},
            "missing_evidence":missing, "phase3":"NOT_AUDITED"})
    validate(rows)
    return rows

def report(rows):
    c=Counter(r["phase2"] for r in rows)
    return {"manufacturer":"NXP","phase1_identified":len(rows),
            "phase1_information_complete":0,
            "phase1_base_alias_pending":212,"phase1_new_original_vendor_bytes_not_archived":73,
            "phase2_states":{state:c[state] for state in STATES},
            "phase2_candidate_family_evidence":{"KL25_target_driver":12,"K32L2_driver_only":16},
            "phase2_supported_in_this_source_audit":0,
            "phase2_scope":"no new software qualification; not all external support assessed",
            "phase3":"NOT_AUDITED","execution_authorized":False,
            "canonical_phases_only":True,"historical_priorities_excluded":True,
            "openocd_source_commit":COMMIT}

if __name__=="__main__":
    import sys
    rows=build()
    print("NXP_ADR0002_PHASE1_PHASE2_PASS S1=297 S1_COMPLETE=0 S2_CANDIDATE=28 S2_UNKNOWN=269 S2_SUPPORTED=0_IN_AUDIT S3=NOT_AUDITED")
    print(json.dumps(report(rows),indent=2,ensure_ascii=False))
    if "--jsonl" in sys.argv:
        for row in rows:
            print(json.dumps(row,ensure_ascii=False,sort_keys=True))
