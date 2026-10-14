#!/usr/bin/env python3
"""ADR-0002 NXP OpenOCD-first source-only 501-row prioritization, fail closed."""
import csv, hashlib, json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LOCK=HERE/"nxp-adr0002-openocd-source-v9.json"
LEDGER=HERE/"nxp-501-adr0002-openocd-priority-v9.csv"
FIELDS="icpn identity_scope silicon_group research_priority openocd_software_state provider source_commit target_tcl_evidence driver_name driver_c_evidence driver_source_operations exact_variant_qualified adr_catalog_visibility_authorized production_identity_admitted physical_validation_claimed previous_review_state missing_next_evidence".split()
PATH_EXPECTED={"KL25":12,"LPC84x":15,"LPC80x":18,"K32L2":20,"MCX":241,"LPC55":97,"KW45":30,"MIMXRT":68}
ROUTES={
"KL25":("P0","CANDIDATE","tcl/target/kl25.cfg","kinetis","src/flash/nor/kinetis.c","exact_sdid_geometry_protection_erase_program_verify"),
"LPC84x":("P0","CANDIDATE","tcl/target/lpc84x.cfg","lpc2000","src/flash/nor/lpc2000.c","exact_part_ID_ROM_IAP_flash_geometry_and_verify"),
"LPC80x":("P1","CANDIDATE","tcl/target/lpc8xx.cfg","lpc2000","src/flash/nor/lpc2000.c","LPC802_LPC804_not_explicitly_supported_in_driver_IDs"),
"K32L2":("P1","CANDIDATE","","kinetis","src/flash/nor/kinetis.c","K32L2_exact_target_driver_SDI_D_and_flash_geometry")}
UNKNOWN=("P2","UNKNOWN","","","","pinned_openocd_route_not_established_archive_only")

def require(ok,reason):
    if not ok:raise ValueError(reason)

def blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+bytes([0])+data).hexdigest()

def read(path):
    with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def group(s):
    if s.startswith("MKL25"):return "KL25"
    if s.startswith(("LPC844","LPC845")):return "LPC84x"
    if s.startswith(("LPC802","LPC804")):return "LPC80x"
    if s.startswith("K32L2"):return "K32L2"
    for p in ("MCX","LPC55","KW45","MIMXRT"):
        if s.startswith(p):return p
    raise ValueError("unknown NXP exact device family "+s)

def upstream_source(root,lock):
    for name,sha in lock["upstream_git_blobs"].items():
        path=root/name
        require(path.is_file() and blob(path.read_bytes())==sha,"OpenOCD source Git blob mismatch: "+name)
    kl=(root/"tcl/target/klx.cfg").read_text()
    lpc=(root/"tcl/target/lpc1xxx.cfg").read_text()
    kd=(root/"src/flash/nor/kinetis.c").read_text()
    ld=(root/"src/flash/nor/lpc2000.c").read_text()
    require("flash bank" in kl and "kinetis" in kl and "flash bank" in lpc and "lpc2000" in lpc,"target flash driver linkage lost")
    for word in ("kinetis_erase","kinetis_write","kinetis_probe"):
        require(word in kd,"Kinetis operation evidence missing "+word)
    for word in ("lpc2000_erase","lpc2000_write","lpc2000_probe","LPC844_201","LPC845_301"):
        require(word in ld,"LPC operation or exact chipset evidence missing "+word)
    require("LPC802_" not in ld and "LPC804_" not in ld,"LPC802/804 evidence changed, re-review")
    require("K32L2" not in kd,"K32L2 evidence changed, re-review")

def build():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["adr"]=="ADR-0002" and lock["source_commit"]=="9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c","provider changed")
    rpath=ROOT/"release/openocd.json";r=json.loads(rpath.read_text())
    require(blob(rpath.read_bytes())==lock["release_openocd_json_git_blob"] and r["source_commit"]==lock["source_commit"] and r["version"]=="0.12.0","runtime provider source-lock drift")
    mpath=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
    require(blob(mpath.read_bytes())==lock["production_manifest_git_blob"],"Production baseline drift")
    m=json.loads(mpath.read_text())
    require(sum(int(x["row_count"]) for x in m["sources"])==4853 and sum(int(x["row_count"]) for x in m["sources"] if x["manufacturer"]=="NXP")==224,"Production row drift")
    result=[]
    for item in lock["input_files"]:
        path=ROOT/item["path"]
        require(blob(path.read_bytes())==item["git_blob"],"NXP source content drift: "+item["path"])
        source=read(path)
        require(len(source)==item["rows"],"NXP input count drift")
        is_pending=item["rows"]==277
        for x in source:
            icpn=x["icpn"];g=group(icpn)
            pr,state,target,driver,driver_path,gap=ROUTES.get(g,UNKNOWN)
            result.append({
                "icpn":icpn,"identity_scope":"research_277" if is_pending else "production_224",
                "silicon_group":g,"research_priority":pr,"openocd_software_state":state,
                "provider":"openocd-upstream","source_commit":lock["source_commit"],
                "target_tcl_evidence":target,"driver_name":driver,
                "driver_c_evidence":driver_path,"driver_source_operations":"erase|write|probe" if driver else "",
                "exact_variant_qualified":"false","adr_catalog_visibility_authorized":"false",
                "production_identity_admitted":"false" if is_pending else "true",
                "physical_validation_claimed":"false",
                "previous_review_state":x["review_decision"] if is_pending else "IDENTITY_ADMITTED_ONLY",
                "missing_next_evidence":gap})
    result.sort(key=lambda x:x["icpn"])
    require(len(result)==len({x["icpn"] for x in result})==501,"NXP 501 exact source mismatch")
    require(Counter(x["silicon_group"] for x in result)==PATH_EXPECTED,"NXP families drift")
    require(Counter(x["research_priority"] for x in result)=={"P0":27,"P1":38,"P2":436},"P0/P1/P2 drift")
    require(all(x["exact_variant_qualified"]=="false" and x["adr_catalog_visibility_authorized"]=="false" and x["physical_validation_claimed"]=="false" and x["openocd_software_state"]!="SUPPORTED" for x in result),"unapproved ICPN promotion")
    return result

def serialize(records):
    import io
    file=io.StringIO(newline="")
    w=csv.DictWriter(file,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader()
    w.writerows(records)
    return file.getvalue().encode()

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--upstream-root",type=Path)
    a=p.parse_args()
    lock=json.loads(LOCK.read_text())
    if a.upstream_root:upstream_source(a.upstream_root,lock)
    require(LEDGER.read_bytes()==serialize(build()),"501-row NXP OpenOCD-first ledger replay mismatch")
    print("NXP_ADR0002_PASS: 501 exact; P0=27, P1=38, P2=436; new SUPPORTED=0",flush=True)

if __name__=="__main__":main()
