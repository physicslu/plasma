#!/usr/bin/env python3
"""NXP bounded 353 exact-ICPN manufacturer-device-only bulk admission v5.

Replays the ORIGINAL 8 SHA-locked NXP manufacturer HTML shards. It creates
new, exact, source-bound Canonical Layer-1 rows ONLY for the 212 records
with unambiguous package/contact, on-chip Flash, and ambient temperature.
This does not invent Base Device family grouping, Programming Profiles,
I/O supply, analog supply, or physical hardware programming qualification.

A canonical row has NO OpenOCD mapping; target config and identifier
mapping remain empty. Exact source evidence is retained per SKU.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup
from nxp_metadata_gap_resolution_v3 import resolve as original_replay
from nxp_metadata_qualification_v2 import LOCK as SOURCE_LOCK, verify_shard_lock
from nxp_metadata_gap_queue_v3 import queue as unresolved_queue
from nxp_bulk_admission_matrix_v1 import ACTIVE_HASH, exact_set_hash

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PRODUCTION=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
EVIDENCE_LABELS={
    "ram_kb":("SRAM (kB)", "RAM (kB)", "Memory - SRAM (kB)"),
    "vdd_range":("Supply Voltage [Min to Max] (V)", "Supply Voltage [min to max] (V)"),
    "vdd_min":("Supply Voltage [min] (V)", "Supply Voltage [Min] (V)"),
    "vdd_max":("Supply Voltage [max] (V)", "Supply Voltage [Max] (V)"),
}
ALLOWED_SEGMENTS={"k32":"K32L2","mcx":"MCX","lpc":"LPC55","wireless":"KW45","imx-rt":"i.MX RT"}
CANONICAL_FIELDS=[
    "manufacturer","icpn","family","series","base_device","package",
    "pin_count","flash_size","temperature_grade","option_suffix",
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config","source_type",
    "source_reference","source_authority","verification_status",
]
DEVICE_FIELDS=[
    "icpn","base_device","base_device_evidence_state","package",
    "pin_count","flash","ram","operating_vdd","io_supply","vdda",
    "operating_temperature","source_url","source_html_sha256",
    "ram_evidence_state","vdd_evidence_state","io_supply_evidence_state",
    "vdda_evidence_state","production_layer1_only",
    "programming_profile_qualified",
]
NUM=re.compile(r"\d{1,7}(?:\.\d+)?\Z")
TEMP=re.compile(r"(-?\d+(?:\.\d+)?)\s+to\s+(-?\d+(?:\.\d+)?)\Z")
VOLT=re.compile(r"(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)\Z")


def require(ok:bool, why:str)->None:
    if not ok: raise ValueError(why)


def digest(value:bytes)->str:
    return hashlib.sha256(value).hexdigest()


def source_cells(soup:BeautifulSoup)->dict[str,set[str]]:
    out:dict[str,set[str]]={}
    for tr in soup.select("tr"):
        cols=tr.find_all("td",recursive=False)
        if len(cols)!=2:continue
        k=" ".join(cols[0].get_text(" ",strip=True).split())
        v=" ".join(cols[1].get_text(" ",strip=True).split())
        if k and v:out.setdefault(k,set()).add(v)
    return out


def field(cells:dict[str,set[str]],keys:tuple[str,...])->tuple[str,str]:
    found=set().union(*(cells.get(k,set()) for k in keys))
    if not found:return "", "not_on_exact_product_page"
    if len(found)!=1:return "", "conflicting_manufacturer_parametric_cells"
    value=next(iter(found))
    if value in {"—","-","N/A","NA"}:return "", "not_provided_for_exact_sku"
    return value,"independently_replayed_exact_manufacturer_html"


def family_series(sku:str,segment:str)->tuple[str,str]:
    require(segment in ALLOWED_SEGMENTS,f"unknown NXP product group: {sku}")
    family=ALLOWED_SEGMENTS[segment]
    if segment=="mcx":
        require(re.fullmatch(r"MCX[A-Z0-9]+",sku) is not None,"malformed MCX SKU")
        return family, "MCX "+sku[3]
    if segment=="k32":
        require(sku.startswith("K32L2"),"non-K32L2 identity")
        return family,"K32 L2"
    if segment=="lpc":
        require(sku.startswith("LPC55"),"non-LPC55 identity")
        return family,"LPC55"
    if segment=="wireless":
        require(sku.startswith("KW45"),"non-KW45 identity")
        return family,"KW45"
    require(sku.startswith("MIMXRT"),"non-i.MX RT identity")
    return family,"i.MX RT"


def render(rows:list[dict],fields:list[str])->str:
    out=io.StringIO(newline="")
    writer=csv.DictWriter(out,fieldnames=fields,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    return out.getvalue()


def build(root:Path)->tuple[list[dict],list[dict],dict]:
    replay,report=original_replay(root)
    locked=verify_shard_lock(root,json.loads(SOURCE_LOCK.read_text(encoding="utf-8")))
    gaps,_=unresolved_queue()
    blocked={x["icpn"] for x in gaps}
    official={r["icpn"] for r in replay}
    require(len(official)==len(replay)==353 and
            exact_set_hash(official)==ACTIVE_HASH,"353 exact manufacturer set drift")
    require(len(blocked)==129,"NXP metadata exceptions changed")
    existing=json.loads(PRODUCTION.read_text(encoding="utf-8"))
    source_rows=existing["sources"]
    require(len(source_rows) in {29,31},"unexpected Production source count")
    previous=source_rows[:29]
    kl=[x for x in previous if x["manufacturer"]=="NXP"]
    require(len(kl)==1 and kl[0]["family"]=="KL25" and
            kl[0]["row_count"]==12 and
            sum(x["row_count"] for x in previous)==4641 and
            all(x["manufacturer"]=="STMicroelectronics" for x in previous[:28]),
            "original Production 4629 ST + 12 KL25 prestate drift")
    old_doc=json.loads(json.dumps(existing))
    old_doc["sources"]=previous
    old_raw=(json.dumps(old_doc,indent=2)+"\\n").encode("utf-8")
    old_blob=hashlib.sha1(b"blob "+str(len(old_raw)).encode("ascii")+
                          b"\\0"+old_raw).hexdigest()
    require(old_blob=="02affa52402a23628c971e58b5bb2e5b3528c511",
            "previous verified 4641-ICPN Production manifest prestate changed")
    if len(source_rows)==31:
        require(sum(x["row_count"] for x in source_rows)==4853 and
                [(x["manufacturer"],x["family"],x["row_count"],x["path"])
                 for x in source_rows[29:]]==[
                    ("NXP","MCX",196,"../research/nxp-mcx-196-commercial-v5.csv"),
                    ("NXP","K32L2",16,"../research/nxp-k32l2-16-commercial-v5.csv"),
                ],
                "new Production scope must be strictly MCX 196 + K32L2 16")
    out=[]
    device=[]
    fields=Counter()
    for row in replay:
        sku=row["icpn"]
        state=row["independent_html_replay_state"]
        if state not in {
            "FOUR_FIELDS_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED",
            "FOUR_FIELDS_BGA_BUMP_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED",
        }:continue
        require(sku not in blocked, f"source-exception SKU cannot be admitted: {sku}")
        original,folder=locked[sku]
        require(original["status"]=="official_nxp_part_metadata_observed" and
                original["heading_matches_exact_sku"] is True and
                original["source_url"]==f"https://www.nxp.com/part/{sku}",
                f"exact NXP official source identity mismatch: {sku}")
        raw=gzip.decompress((folder/f"{sku}.html.gz").read_bytes())
        require(digest(raw)==original["source_sha256"]==
                row["official_part_html_sha256"],
                f"original manufacturer HTML SHA mismatch: {sku}")
        soup=BeautifulSoup(raw,"html.parser")
        require(sku in [h.get_text(" ",strip=True) for h in soup.select("h1")],
                f"manufacturer exact SKU heading absent: {sku}")
        cells=source_cells(soup)
        flash_raw=str(original["flash_kb_raw"])
        pin_raw=str(row["pin_count_observed"])
        temp_raw=str(original["ambient_temperature_raw"])
        package=original["package_raw"]
        require(NUM.fullmatch(flash_raw) is not None and int(float(flash_raw))>0
                and re.fullmatch(r"\d{2,4}",pin_raw) is not None and
                int(pin_raw)>0 and TEMP.fullmatch(temp_raw) is not None and
                isinstance(package,str) and package,
                f"mandatory unambiguous four-field original proof missing: {sku}")
        require(package==row["package_raw"] and
                flash_raw==str(row["flash_kb_observed"]) and
                temp_raw==row["ambient_temperature_raw"],
                f"independent replay result differs from source: {sku}")
        ram,ram_state=field(cells,EVIDENCE_LABELS["ram_kb"])
        if ram and NUM.fullmatch(ram) is None:
            ram,ram_state="","ambiguous_non_numeric_ram_parametric"
        vdd,vdd_state=field(cells,EVIDENCE_LABELS["vdd_range"])
        if not vdd:
            lo,lo_state=field(cells,EVIDENCE_LABELS["vdd_min"])
            hi,hi_state=field(cells,EVIDENCE_LABELS["vdd_max"])
            if lo and hi and NUM.fullmatch(lo) and NUM.fullmatch(hi):
                vdd,vdd_state=f"{lo} to {hi}","independently_replayed_two_manufacturer_voltage_cells"
        if vdd and (m:=VOLT.fullmatch(vdd)) is None:
            vdd,vdd_state="","unsupported_official_voltage_format"
        if vdd and float(VOLT.fullmatch(vdd).group(1))>float(VOLT.fullmatch(vdd).group(2)):
            vdd,vdd_state="","contradictory_voltage_range"
        family,series=family_series(sku,row["segment"])
        # NO suffix-to-base-device inference; conservative singleton prevents
        # cross-orderable grouping until an official manufacturer bridge exists.
        canonical={
            "manufacturer":"NXP","icpn":sku,"family":family,
            "series":series,"base_device":sku,"package":package,
            "pin_count":pin_raw,"flash_size":f"{flash_raw} kB",
            "temperature_grade":temp_raw+" C","option_suffix":"",
            "cmsis_device_name":"","existing_identifier":"",
            "existing_identifier_kind":"","mapping_status":"no_mapping",
            "openocd_target_config":"",
            "source_type":"official_nxp_independent_exact_part_html_replay",
            "source_reference":f"manufacturer HTML SHA256 {digest(raw)}; page /part/{sku}; frozen run 38337377867",
            "source_authority":original["source_url"],
            "verification_status":"verified_nxp_exact_part_identity_package_pin_flash_ambient_only",
        }
        device.append({
            "icpn":sku,"base_device":sku,
            "base_device_evidence_state":"exact_sku_singleton_not_manufacturer_base_verified",
            "package":package,"pin_count":pin_raw,"flash":f"{flash_raw} kB",
            "ram":f"{ram} kB" if ram else "",
            "operating_vdd":f"{vdd} V" if vdd else "",
            "io_supply":"","vdda":"","operating_temperature":temp_raw+" C",
            "source_url":original["source_url"],"source_html_sha256":digest(raw),
            "ram_evidence_state":ram_state,"vdd_evidence_state":vdd_state,
            "io_supply_evidence_state":"not_individually_sourced",
            "vdda_evidence_state":"not_individually_sourced",
            "production_layer1_only":"true","programming_profile_qualified":"false",
        })
        fields[ram_state]+=1
        fields[vdd_state]+=1
        out.append(canonical)
    require(len(out)==len(device)==212 and len({r["icpn"] for r in out})==212,
            "212 manufacturer HTML exact canonical candidates drift")
    require(all(r["mapping_status"]=="no_mapping" and not r["openocd_target_config"]
                for r in out),"Programming Profile boundary crossed")
    if len(source_rows)==31:
        for x in source_rows[29:]:
            name=x["family"]
            family_rows=[r for r in out if r["family"]==name]
            raw=render(family_rows,CANONICAL_FIELDS).encode("utf-8")
            canonical_file=(PRODUCTION.parent/x["path"]).resolve().read_bytes()
            require(canonical_file==raw and
                    digest(raw)==x["sha256"] and
                    hashlib.sha1(b"blob "+str(len(raw)).encode("ascii")+
                                 b"\\0"+raw).hexdigest()==x["git_blob_sha"],
                    f"{name}: proposed production file is not byte-for-byte official HTML replay")
    require(set(x["icpn"] for x in out).isdisjoint(blocked) and
            set(x["icpn"] for x in out).isdisjoint(
                x["icpn"] for x in replay if x["independent_html_replay_state"]=="PRIOR_KL25_REVIEWED"),
            "unverified source or existing KL25 duplicate")
    counts=Counter(x["family"] for x in out)
    stats={
        "schema_version":5,"manufacturer":"NXP",
        "scope":"353 frozen Active exact NXP (23 official product pages, not vendor-wide)",
        "full_bounded_active_exact":353,
        "preexisting_production_kl25_exact":12,
        "new_source_bound_four_field_candidates":212,
        "unresolved_source_or_metadata_exact":129,
        "new_candidate_family_counts":dict(sorted(counts.items())),
        "ram_nonempty_exact_count":sum(bool(x["ram"]) for x in device),
        "vdd_nonempty_exact_count":sum(bool(x["operating_vdd"]) for x in device),
        "base_device_official_grouping_verified_count":0,
        "io_supply_nonempty_exact_count":0,
        "vdda_nonempty_exact_count":0,
        "new_candidate_target_config_nonempty_count":0,
        "producer_original_run":38337377867,
        "new_candidate_set_sha256":exact_set_hash({x["icpn"] for x in out}),
        "source_html_replay_required_for_admission":True,
        "manufacturer_device_full_profile_complete":False,
        "global_nxp_active_denominator":None,
        "production_publication_authorized":False,
        "programming_profile_qualified":False,
        "physical_programming_verified":False,
    }
    return out,device,stats


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--emit-marked-csv-stdout",action="store_true")
    args=ap.parse_args()
    rows,devices,report=build(args.root)
    args.output.mkdir(parents=True,exist_ok=True)
    content=render(rows,CANONICAL_FIELDS)
    (args.output/"nxp-212-canonical-source-unpublished-v5.csv").write_text(content,encoding="utf-8")
    (args.output/"nxp-212-manufacturer-device-evidence-v5.csv").write_text(
        render(devices,DEVICE_FIELDS),encoding="utf-8")
    (args.output/"nxp-212-evidence-summary-v5.json").write_text(
        json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,sort_keys=True),flush=True)
    if args.emit_marked_csv_stdout:
        # Output is GitHub action-log transport for accountable code review;
        # never automatically published into Production.
        print("NXP_212_CANONICAL_CSV_BEGIN",flush=True)
        print(content,end="",flush=True)
        print("NXP_212_CANONICAL_CSV_END",flush=True)
        print("NXP_212_DEVICE_CSV_BEGIN",flush=True)
        print(render(devices,DEVICE_FIELDS),end="",flush=True)
        print("NXP_212_DEVICE_CSV_END",flush=True)


if __name__=="__main__":
    main()
