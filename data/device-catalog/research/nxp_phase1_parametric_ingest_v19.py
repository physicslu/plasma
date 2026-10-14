#!/usr/bin/env python3
"""NXP Phase 1: inspect an operator-supplied official Buy/Parametrics CSV/XLSX export.

Read-only, no network, no device admission, no automatic source qualification.
Original export URL is a provenance *assertion*, not authenticated by this tool.
"""
import argparse
import csv
import hashlib
import io
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from nxp_phase1_mcxa1fs_v18 import build as existing_phase1

MAX_BYTES=20*1024*1024
MAX_XML_BYTES=30*1024*1024
NS="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL="http://schemas.openxmlformats.org/officeDocument/2006/relationships"

class ImportErrorSafe(ValueError):pass

def insist(p,msg):
    if not p:raise ImportErrorSafe(msg)

def provenance_url(url):
    x=urlsplit(url)
    insist(x.scheme=="https" and x.hostname in ("nxp.com","www.nxp.com",
        "nxp.com.cn","www.nxp.com.cn") and x.username is None and x.password is None
        and x.path.startswith("/products/"),"Source URL must be official NXP HTTPS /products/ page")
    return url

def norm(s):
    x=unicodedata.normalize("NFKC",str(s or "")).strip().lower()
    return re.sub(r"\s+"," ",x)

def fields(header):
    lower=[norm(x) for x in header]
    mapping={
      "icpn":("part","part number","orderable part number","ordering part number"),
      "flash":("flash (kb)","flash [kb]","flash kb"),
      "sram":("sram (kb)","sram [kb]","sram kb"),
      "vdd":("supply voltage [min to max] (v)","supply voltage (min to max) (v)",
             "supply voltage [min-max] (v)","supply voltage (v)"),
      "vdd_min":("supply voltage [min] (v)","supply voltage (min) (v)"),
      "vdd_max":("supply voltage [max] (v)","supply voltage (max) (v)"),
    }
    found={}
    for k,aliases in mapping.items():
        hits=[i for i,h in enumerate(lower) if h in aliases]
        insist(len(hits)<=1,"Ambiguous duplicate column: "+k)
        if hits:found[k]=hits[0]
    insist(all(k in found for k in ("icpn","flash","sram")),
           "Export must have exact Part, Flash (kB) and SRAM (kB) columns")
    return found

def spreadsheet_xlsx(p):
    with zipfile.ZipFile(p) as z:
        names=set(z.namelist())
        insist("[Content_Types].xml" in names and "xl/workbook.xml" in names,
            "File is not an OOXML workbook")
        def xml_file(name):
            insist(name in names,"Missing XLSX member: "+name)
            size=z.getinfo(name).file_size
            insist(size<=MAX_XML_BYTES,"XLSX member too large")
            return ET.fromstring(z.read(name))
        shared=[]
        if "xl/sharedStrings.xml" in names:
            root=xml_file("xl/sharedStrings.xml")
            for si in root.findall("{"+NS+"}si"):
                shared.append("".join(e.text or "" for e in si.iter("{"+NS+"}t")))
                insist(len(shared)<=100000,"Too many shared strings")
        # Only the first worksheet; explicit fail if formulas found.
        sheets=sorted(x for x in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml",x))
        insist(bool(sheets),"No worksheet in XLSX")
        root=xml_file(sheets[0])
        result=[]
        for row in root.findall(".//{"+NS+"}sheetData/{"+NS+"}row"):
            by_index={}
            for c in row.findall("{"+NS+"}c"):
                ref=c.attrib.get("r","")
                match=re.fullmatch(r"([A-Z]+)\d+",ref)
                insist(match is not None,"Unsupported XLSX cell reference")
                col=0
                for char in match.group(1):col=col*26+ord(char)-64
                idx=col-1
                insist(idx<=500,"XLSX too many columns")
                insist(c.find("{"+NS+"}f") is None,
                       "Formula cells require independently confirmed cached values; abort")
                v=c.find("{"+NS+"}v")
                typ=c.attrib.get("t")
                if typ=="s":
                    insist(v is not None and v.text is not None,"Invalid shared string")
                    si=int(v.text)
                    insist(0<=si<len(shared),"Shared string out of range")
                    value=shared[si]
                elif typ=="inlineStr":
                    value="".join(n.text or "" for n in c.findall(".//{"+NS+"}t"))
                else:value=v.text if v is not None and v.text else ""
                by_index[idx]=value
            if by_index:
                n=max(by_index)+1
                result.append([by_index.get(i,"") for i in range(n)])
                insist(len(result)<=20000,"XLSX too many rows")
        return result

def read_export(path):
    p=Path(path)
    insist(p.is_file() and 0<p.stat().st_size<=MAX_BYTES,"Export missing, empty or too large")
    suffix=p.suffix.lower()
    if suffix==".csv":
        raw=p.read_bytes()
        insist(not raw.lstrip().startswith((b"<",b"<!DOCTYPE",b"<html")),
            "HTML masquerading as CSV/XLS")
        try:s=raw.decode("utf-8-sig")
        except UnicodeError as e:raise ImportErrorSafe("CSV must be UTF-8; re-export from Excel as CSV UTF-8") from e
        rows=list(csv.reader(io.StringIO(s,newline="")))
    elif suffix==".xlsx":rows=spreadsheet_xlsx(p)
    elif suffix==".xls":raise ImportErrorSafe(
        "Legacy .xls not parsed: keep original, open it in Excel and save a CSV UTF-8 or XLSX copy")
    else:raise ImportErrorSafe("Only CSV UTF-8 and XLSX supported, not HTML or synthetic .xls")
    insist(bool(rows),"Empty export")
    # Accommodate one-row page caption above the headers.
    header_index=None; mapping=None
    for i,row in enumerate(rows[:15]):
        try:cols=fields(row)
        except ImportErrorSafe:continue
        header_index=i;mapping=cols;break
    insist(header_index is not None,"No authoritative NXP Part/Flash(kB)/SRAM(kB) header")
    return rows[header_index+1:],mapping,p

def positive_int(val):
    x=norm(val)
    if not re.fullmatch(r"\d{1,6}(?:\.0+)?",x):return None
    n=int(float(x))
    return n if n>0 else None

def supply(s):
    text=norm(s).replace("–","-").replace("—","-")
    m=re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:to|-)\s*(\d+(?:\.\d+)?)",text)
    if not m:return None
    a,b=float(m.group(1)),float(m.group(2))
    if not (0<a<=b<=20):return None
    return [a,b]

def inspect(path,source):
    provenance_url(source)
    data,cols,p=read_export(path)
    baseline={x["icpn"]:x for x in existing_phase1() if x["identity_state"]=="ADMITTED"}
    insist(len(baseline)==224,"Expected 224 previously admitted NXP exact ICPNs")
    output=[];seen=set()
    for raw in data:
        def get(k):return (raw[cols[k]] if k in cols and cols[k]<len(raw) else "").strip()
        sku=get("icpn").upper()
        if not sku:continue
        insist(re.fullmatch(r"[A-Z0-9]+",sku) is not None,"Invalid order code row")
        insist(sku not in seen,"Duplicate part in export: "+sku)
        seen.add(sku)
        r={"icpn":sku,"result":"NOT_IN_EXISTING_ADMITTED_SCOPE",
           "source_flash_kb":get("flash"),"source_sram_kb":get("sram"),
           "source_vdd":get("vdd"),"baseline_flash":"","baseline_ram_state":"",
           "baseline_vdd_state":"","suggested_ram":"","suggested_vdd":"",
           "source_confidence":"OPERATOR_SUPPLIED_UNAUTHENTICATED_EXPORT"}
        x=baseline.get(sku)
        if x:
            r["baseline_flash"]=x["flash"]
            r["baseline_ram_state"]=x["ram_state"]
            r["baseline_vdd_state"]=x["working_vdd_state"]
            flash=positive_int(get("flash"));ram=positive_int(get("sram"))
            expected=positive_int(x["flash"].split(" ")[0])
            if not flash or not expected or flash!=expected:r["result"]="BLOCK_FLASH_MISMATCH_OR_MISSING"
            elif not ram:r["result"]="BLOCK_INVALID_OR_MISSING_SRAM"
            else:
                r["result"]="EXACT_MATCH_REVIEW_ONLY"
                r["suggested_ram"]=str(ram)
                v=supply(get("vdd"))
                if not v and "vdd_min" in cols and "vdd_max" in cols:
                    v=supply(get("vdd_min")+" to "+get("vdd_max"))
                if v:r["suggested_vdd"]=f"{v[0]:g} to {v[1]:g}"
        output.append(r)
    count=Counter(r["result"] for r in output)
    result={
        "schema_version":19,"phase":"IC_INFORMATION","manufacturer":"NXP",
        "source_page_claim":source,"source_export_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),
        "source_file_type":p.suffix.lower(),"source_authenticity":"UNVERIFIED_OPERATOR_PROVIDED_FILE",
        "automatically_admitted_rows":0,"production_mutations":0,
        "scope_admitted_exact_total":224,"source_export_rows":len(output),
        "results":dict(sorted(count.items())),"rows":output,
        "note":"Candidate report only. Check original manufacturer export provenance and resolve discrepancies before independent Phase1 official-source acceptance; does not alter ICPN identities, Programming or HIL."
    }
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True,help="Original NXP Buy/Parametrics export CSV UTF-8 or XLSX")
    ap.add_argument("--source-page",required=True,help="Official https://www.nxp.com/products/... page")
    ap.add_argument("--output",help="JSON review report path; stdout if omitted")
    args=ap.parse_args()
    try:
        result=inspect(args.input,args.source_page)
        data=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
        if args.output:Path(args.output).write_text(data,encoding="utf-8")
        else:print(data,end="")
    except (ImportErrorSafe,ValueError,zipfile.BadZipFile,ET.ParseError) as e:
        print("NXP_PHASE1_EXPORT_REJECTED:",str(e),file=sys.stderr)
        return 2
    return 0

if __name__=="__main__":sys.exit(main())
