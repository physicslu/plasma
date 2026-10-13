#!/usr/bin/env python3
"""Durable all-NXP 353 exact-source gap queue, research-only.

Uses SHA-locked #835 per-SKU status index and eleven independently replayed
BGA source exceptions; never guesses 85 unresolvable vendor /part URLs.
"""
from __future__ import annotations
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from nxp_metadata_status_index_v2 import materialize as frozen_index
from nxp_metadata_gap_resolution_v3 import GATE, require

HERE = Path(__file__).resolve().parent
FROZEN = HERE / "nxp-353-metadata-gap-review-queue-v3.csv"
FIELDS = [
    "icpn","segment","exception_class","manufacturer_evidence_route",
    "catalog_admission_authorized","production_write_authorized",
]
ROUTES = {
    "http_non200": "official_datasheet_exact_ordering_table_required",
    "flash_multi_value": "official_KW45_datasheet_exact_table_pdf_binary_replay_required",
    "imx_rt_flash_temperature": "imx_RT_internal_external_flash_and_ambient_semantics_review_required",
    "mcx_flash_ambient": "official_MCX_flash_and_ambient_source_review_required",
    "wireless_ambient": "official_KW45_ambient_temperature_document_needed",
}


def queue() -> tuple[list[dict],dict]:
    original,_=frozen_index()
    lock=json.loads(GATE.read_text(encoding="utf-8"))
    promoted=set(lock["original_missing_bump_exact_skus"])
    require(len(promoted)==11 and len(original)==353 and
            lock["production_write_authorized"] is False,
            "NXP manufacturer bump source and full identity lock drift")
    counts=Counter()
    by_segment=Counter()
    results=[]
    for row in original:
        sku=row["icpn"]
        state=row["review_state"]
        cause=row["blocked_root_cause"]
        if sku in promoted:
            require(state=="PARTIAL_SOURCE_FIELDS_REVIEW_REQUIRED" and not cause,
                    f"BGA evidence status contradiction: {sku}")
            continue
        if state=="PARTIAL_SOURCE_FIELDS_REVIEW_REQUIRED":
            if row["segment"]=="imx-rt":
                kind="imx_rt_flash_temperature"
            elif row["segment"]=="mcx":
                kind="mcx_flash_ambient"
            elif row["segment"]=="wireless":
                kind="wireless_ambient"
            else:
                raise ValueError(f"unexpected unresolved partial source: {sku}")
        elif state=="OFFICIAL_PART_SOURCE_BLOCKED_REVIEW_REQUIRED":
            if cause=="official_exact_part_http_non200":
                kind="http_non200"
            elif cause=="manufacturer_flash_format_requires_review":
                kind="flash_multi_value"
            else:
                raise ValueError(f"unexpected blocked exact SKU cause: {sku}")
        else:
            continue
        counts[kind]+=1
        by_segment[row["segment"]]+=1
        results.append({
            "icpn":sku,
            "segment":row["segment"],
            "exception_class":kind,
            "manufacturer_evidence_route":ROUTES[kind],
            "catalog_admission_authorized":"false",
            "production_write_authorized":"false",
        })
    require(len(results)==129 and len({x["icpn"] for x in results})==129 and
            dict(counts)=={
                "http_non200":85,
                "flash_multi_value":8,
                "imx_rt_flash_temperature":23,
                "mcx_flash_ambient":5,
                "wireless_ambient":8,
            }, "reconciled 129 metadata exceptions do not match original evidence")
    require(all(x["catalog_admission_authorized"]=="false" for x in results),
            "unreviewed metadata incorrectly automatically admitted")
    summary={
        "schema_version":3,
        "manufacturer":"NXP",
        "active_exact_total":353,
        "prior_KL25_research_reviewed":12,
        "four_source_fields_original":201,
        "additional_bga_bump_evidence_verified":11,
        "four_source_fields_total_REVIEW_REQUIRED":212,
        "outstanding_metadata_exact_total":129,
        "exception_counts":dict(sorted(counts.items())),
        "exception_counts_by_source_lane":dict(sorted(by_segment.items())),
        "global_nxp_active_denominator":None,
        "catalog_admission_authorized":False,
        "production_write_authorized":False,
        "programming_backend_qualified":False,
    }
    return results,summary


def render(rows:list[dict])->str:
    import io
    stream=io.StringIO(newline="")
    writer=csv.DictWriter(stream,fieldnames=FIELDS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def main()->None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    rows,report=queue()
    require(FROZEN.read_text(encoding="utf-8")==render(rows),
            "durable 129 exact metadata review queue drift from source index")
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/"nxp-129-unresolved-metadata-queue-v3.csv").write_text(
        render(rows),encoding="utf-8")
    (args.output/"nxp-129-unresolved-metadata-queue-summary-v3.json").write_text(
        json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,sort_keys=True))


if __name__=="__main__":
    main()
