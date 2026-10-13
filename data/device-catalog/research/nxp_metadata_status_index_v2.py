#!/usr/bin/env python3
"""NXP 353 per-SKU metadata status lookup from durable frozen research records.

No browser, API, Production write, device programming, or expired Actions
artifact required to reproduce the 353-row *review-state* index.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ACTIVE = HERE / "nxp-active-353-bulk-candidates-v1.csv"
SNAPSHOT = HERE / "nxp-official-bounded-snapshot-2026-10-13-v1.json"
STATUS_MAP = HERE / "nxp-bulk-353-status-map-v2.json"
CODES = {
    "K": "KL25_METADATA_REVIEWED_RESEARCH_ONLY",
    "C": "FOUR_SOURCE_FIELDS_VERIFIED_REVIEW_REQUIRED",
    "P": "PARTIAL_SOURCE_FIELDS_REVIEW_REQUIRED",
    "B": "OFFICIAL_PART_SOURCE_BLOCKED_REVIEW_REQUIRED",
}
CAUSES = {"-": "", "H": "official_exact_part_http_non200",
          "F": "manufacturer_flash_format_requires_review"}


def require(value: bool, reason: str) -> None:
    if not value:
        raise ValueError(reason)


def sha(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def materialize() -> tuple[list[dict], dict]:
    lock = json.loads(STATUS_MAP.read_text(encoding="utf-8"))
    frozen = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["reconciliation"]
    with ACTIVE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 353 and len({r["icpn"] for r in rows}) == 353,
            "NXP 353 exact membership drift")
    ids = [r["icpn"] for r in rows]
    require(ids == frozen["observed_active_icpns"],
            "status map no longer aligns to frozen sorted Active exact set")
    require(lock["active_set_sha256"] == frozen["observed_active_exact_set_sha256"] and
            lock["claims"]["production_write_authorized"] is False and
            lock["claims"]["canonical_metadata_admission_authorized"] is False and
            lock["claims"]["global_nxp_active_denominator"] is None,
            "NXP per-SKU metadata lock changed authority")
    a, b = lock["status_map"], lock["blocked_reason_map"]
    require(len(a) == len(b) == 353 and
            set(a) <= set(CODES) and set(b) <= set(CAUSES),
            "NXP status/blocked reason map is invalid")
    require(sha(a+"\n") == lock["status_map_sha256"] and
            sha(b+"\n") == lock["blocked_reason_map_sha256"],
            "per-SKU SHA256 status map drift")
    require(all((s == "B") == (reason in "HF") for s, reason in zip(a,b)),
            "blocked source flag inconsistent with metadata status")
    status_counts = dict(Counter(a))
    reason_counts = dict(Counter(b))
    require(status_counts == lock["counts"]["status"] and
            reason_counts == lock["counts"]["blocked_reason"] and
            status_counts == {"C":201,"P":47,"B":93,"K":12} and
            reason_counts == {"-":260,"H":85,"F":8},
            "frozen 353 review partition changed")
    entries=[]
    for source, status, reason in zip(rows,a,b):
        entries.append({
            "icpn":source["icpn"],"manufacturer":"NXP","segment":source["segment"],
            "marketing_lifecycle":"Active",
            "review_state":CODES[status],
            "blocked_root_cause":CAUSES[reason],
            "canonical_metadata_admission_authorized":"false",
            "production_write_authorized":"false",
            "programming_backend_qualified":"false",
        })
    return entries, {
        "schema_version":2,
        "source":"frozen_nxp_353_exact_metadata_status_index",
        "official_active_exact_count":353,
        "status_counts":dict(sorted(status_counts.items())),
        "blocked_reason_counts":dict(sorted(reason_counts.items())),
        "global_nxp_active_denominator":None,
        "production_write_authorized":False,
        "runtime_programming_qualified":False,
    }


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    entries, summary=materialize()
    args.output.mkdir(parents=True,exist_ok=True)
    with (args.output/"nxp-353-review-status-index.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(entries[0]),lineterminator="\n")
        writer.writeheader()
        writer.writerows(entries)
    (args.output/"nxp-353-review-status-index.json").write_text(
        json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,sort_keys=True))


if __name__ == "__main__":
    main()
