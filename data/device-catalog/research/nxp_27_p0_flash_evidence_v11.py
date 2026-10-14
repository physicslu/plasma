#!/usr/bin/env python3
"""NXP P0 exact 27: immutable OpenOCD source geometry and security gap ledger.

Research ONLY. Does not qualify individual target operation or authorize Catalog.
"""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from nxp_adr0002_core_qual_v10 import (
    build as build_v10,
    LEDGER as V10_LEDGER,
    LOCK as V10_LOCK,
    to_csv as v10_csv,
)
from nxp_adr0002_openocd_triage_v9 import (
    blob,
    upstream_source as upstream_v9,
    LOCK as V9_LOCK,
)
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LOCK=HERE/"nxp-27-p0-openocd-source-evidence-v11.json"
LEDGER=HERE/"nxp-27-p0-exact-flash-review-v11.csv"
KL25=HERE/"nxp-kl25-commercial-icpn.csv"
FIELDS=("icpn family core_model openocd_version openocd_source_commit "
        "target_config flash_driver identity_scope manufacturer_exact_flash_kib "
        "manufacturer_metadata_state openocd_flash_geometry_model driver_flash_capacity_kib_candidate "
        "driver_part_id_family_candidates driver_erase_write_source driver_probe_source "
        "requested_read_verify_qualified silicon_id_observed silicon_revision_observed "
        "flash_geometry_runtime_verified exact_icpn_driver_id_match_verified "
        "source_safety_blocker software_support_state public_catalog_authorized "
        "physical_hil_evidence next_required_evidence").split()
EXPECTED={"KL25":12,"LPC844":7,"LPC845":8}
LPC={
"LPC844":"LPC844_201|LPC844_201_1|LPC844_201_2",
"LPC845":"LPC845_301|LPC845_301_1|LPC845_301_2|LPC845_301_3",
}
COMMIT="9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"

def require(ok, msg):
    if not ok:raise ValueError(msg)

def read(path):
    with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def pinned():
    p=json.loads(LOCK.read_text(encoding="utf-8"))
    require(p["schema_version"]==11 and p["adr"]=="ADR-0002"
            and p["source_commit"]==COMMIT,
            "ADR-0002 / OpenOCD source scope drift")
    require(blob(V10_LEDGER.read_bytes())==p["source_v10_501_core_ledger_git_blob"]
            and V10_LEDGER.read_bytes()==v10_csv(build_v10()),
            "v10 501 Core/Target/Driver original source changed")
    require(blob(KL25.read_bytes())==p["source_kl25_12_canonical_git_blob"],
            "KL25 original exact manufacturer CSV changed")
    require(blob(V10_LOCK.read_bytes())==p["source_v10_family_lock_git_blob"]
            and blob(V9_LOCK.read_bytes())==p["source_v9_pinned_openocd_lock_git_blob"],
            "OpenOCD Core/Target upstream version SHA drift")
    require(p["review_cohorts"]==EXPECTED,"P0 cohort scope modified")
    require(p["upstream_source_blobs"]==json.loads(V9_LOCK.read_text())["upstream_git_blobs"],
            "pinned source file SHA mismatch")
    return p

def upstream(root):
    e=pinned()
    upstream_v9(root,json.loads(V9_LOCK.read_text(encoding="utf-8")))
    def source(path):
        return (root/path).read_text(encoding="utf-8")
    klcfg=source("tcl/target/kl25.cfg")
    klx=source("tcl/target/klx.cfg")
    kin=source("src/flash/nor/kinetis.c")
    lpcCfg=source("tcl/target/lpc84x.cfg")
    lpcBase=source("tcl/target/lpc1xxx.cfg")
    lpcDriver=source("src/flash/nor/lpc2000.c")
    for name,haystack,markers in [
        ("kl25.cfg",klcfg,("set CHIPNAME kl25","source [find target/klx.cfg]")),
        ("klx.cfg",klx,("flash bank $_FLASHNAME kinetis","kinetis create_banks")),
        ("kinetis.c",kin,("case KINETIS_SDID_SERIESID_KL:","k_chip->pflash_sector_size = 1<<10;",
                        "k_chip->flash_support = FS_PROGRAM_LONGWORD;",
                        "SIM_FCFG1_OFFSET","SIM_FCFG2_OFFSET","kinetis_erase","kinetis_write",
                        "FCF_ADDRESS","Device security requested in the programmed file! Write denied.")),
        ("lpc84x.cfg",lpcCfg,("set CHIPSERIES lpc800","set WORKAREASIZE 0x1fe0",
                             "set IAP_ENTRY 0x0F001FF1","source [find target/lpc1xxx.cfg]")),
        ("lpc1xxx.cfg",lpcBase,("flash bank $_FLASHNAME lpc2000","calc_checksum $_IAP_ENTRY")),
        ("lpc2000.c",lpcDriver,("case LPC844_201:","case LPC845_301:",
                                 "bank->size = 64 * 1024;","bank->sectors[i].size = 1 * 1024;",
                                 'LOG_ERROR("BUG: unknown Part ID encountered:',
                                 "exit(-1);","lpc2000_auto_probe_flash","lpc2000_write","lpc2000_erase"))
    ]:
        for marker in markers:
            require(marker in haystack,"Pinned upstream "+name+" missing "+marker)
    # Critical: we preserve the unknown-ID process abort risk as a blocker.
    unknown=lpcDriver.index('LOG_ERROR("BUG: unknown Part ID encountered:')
    require("exit(-1);" in lpcDriver[unknown:unknown+160],"unknown ID path changed")
    require(e["source_observations"]["LPC84x"]["driver_error_process_exit_risk"],
            "LPC unknown-id safety gate silently relaxed")

def build():
    pinned()
    kl={r["icpn"]:r for r in read(KL25)}
    require(len(kl)==12,"KL25 exact manufacturer input incomplete")
    src=[r for r in build_v10() if r["research_priority"]=="P0"]
    require(len(src)==27,"P0 full cohort mismatch")
    out=[]
    for r in src:
        sku=r["icpn"]
        fam=("KL25" if sku.startswith("MKL25") else
             "LPC844" if sku.startswith("LPC844") else
             "LPC845" if sku.startswith("LPC845") else None)
        require(bool(fam),"unknown P0 SKU "+sku)
        iskl=fam=="KL25"
        man=kl.get(sku) if iskl else None
        if iskl:
            require(man is not None and man["openocd_target_config"]=="tcl/target/kl25.cfg"
                    and man["flash_size"] in ("32 KiB","64 KiB","128 KiB")
                    and r["production_identity_admitted"]=="true","unverified KL manufacturer identity")
        else:
            require(r["identity_scope"]=="research_277" and
                    r["production_identity_admitted"]=="false","LPC exact source not yet verified")
        out.append({
            "icpn":sku,"family":fam,"core_model":r["core_model"],
            "openocd_version":r["openocd_version"],
            "openocd_source_commit":r["openocd_source_commit"],
            "target_config":r["target_config"],"flash_driver":r["flash_bank_driver"],
            "identity_scope":r["identity_scope"],
            "manufacturer_exact_flash_kib":man["flash_size"].split()[0] if man else "",
            "manufacturer_metadata_state":"SOURCE_LOCKED_KL25_EXACT_IDENTITY" if man
                else "LPC84X_EXACT_PART_HTML_BLOCKED",
            "openocd_flash_geometry_model":"KL_SERIES_BRANCH_FCFG1_FCFG2_RUNTIME_DETECTED" if iskl
                else "LPC84X_AUTO_PART_ID_64K_AND_1K_SECTORS",
            "driver_flash_capacity_kib_candidate":"RUNTIME_REGISTER_DETECTED" if iskl else "64",
            "driver_part_id_family_candidates":LPC.get(fam,""),
            "driver_erase_write_source":"IMPLEMENTED_IN_PINNED_DRIVER",
            "driver_probe_source":"IMPLEMENTED_IN_PINNED_DRIVER",
            "requested_read_verify_qualified":"UNKNOWN",
            "silicon_id_observed":"UNKNOWN","silicon_revision_observed":"UNKNOWN",
            "flash_geometry_runtime_verified":"false",
            "exact_icpn_driver_id_match_verified":"false",
            "source_safety_blocker":"FLASH_CONFIGURATION_FIELD_SECURITY_FCF_GUARD_REVIEW_REQUIRED" if iskl
                else "UNKNOWN_PART_ID_EXIT_MINUS_ONE_REQUIRES_FAIL_CLOSED",
            "software_support_state":"CANDIDATE",
            "public_catalog_authorized":"false",
            "physical_hil_evidence":"NOT_TESTED_IN_THIS_RESEARCH",
            "next_required_evidence":"MANUFACTURER_EXACT_DEVICE_SDID_MAPPING_FCFG_SECTORS_FCF_POLICY_AND_PROGRAM_VERIFY_TEST" if iskl
                else "MANUFACTURER_EXACT_ORDERING_TO_PART_ID_ROM_IAP_GEOMETRY_RESET_ERA_PROGRAM_VERIFY"
        })
    require(Counter(r["family"] for r in out)==EXPECTED,"P0 12+7+8 membership changed")
    require(sum(bool(r["manufacturer_exact_flash_kib"]) for r in out)==12,
            "exact manufacturer metadata boundary was crossed")
    require(all(r["software_support_state"]=="CANDIDATE"
                and r["requested_read_verify_qualified"]=="UNKNOWN"
                and r["exact_icpn_driver_id_match_verified"]=="false"
                and r["public_catalog_authorized"]=="false" for r in out),
            "Core/driver evidence promoted unsupported exact software qualification")
    return out

def render(rows):
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return buf.getvalue().encode("utf-8")

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--upstream-root",type=Path)
    options=parser.parse_args()
    if options.upstream_root: upstream(options.upstream_root)
    require(LEDGER.read_bytes()==render(build()),"P0 27-row source-bound audit CSV differs")
    print("NXP_P0_27_V11_PASS KL25=12 LPC844=7 LPC845=8; exact silicon ID=0; new SUPPORTED=0",flush=True)

if __name__=="__main__":
    main()
