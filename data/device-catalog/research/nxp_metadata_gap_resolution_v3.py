#!/usr/bin/env python3
"""NXP one-batch 353 exact SKU metadata evidence improvements (research only).

Replays SHA-locked 248 original manufacturer HTML pages, independently
recovers *explicit* 64-bump BGA contact counts for 11 variants, and preserves
all unresolved source/Flash/temperature gaps. No Production writes.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from bs4 import BeautifulSoup
from nxp_metadata_qualification_v2 import audit as prior_audit, verify_shard_lock, LOCK
from nxp_metadata_status_index_v2 import materialize as prior_index

HERE = Path(__file__).resolve().parent
GATE = HERE / "nxp-metadata-bump-evidence-v3.json"
BUMP = re.compile(r"\b(\d{2,4})\s+(?:bumps?|solder\s+bumps?)\b", re.I)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_bga_contacts(sku: str, html: bytes, package: str) -> int:
    """Only exact manufacturer package section; no suffix-derived pin counts."""
    doc = BeautifulSoup(html, "html.parser")
    heads = [h.get_text(" ", strip=True) for h in doc.select("h1")]
    require(sku in heads, f"exact manufacturer SKU H1 mismatch: {sku}")
    txt = doc.get_text("\n", strip=True)
    begin = txt.find("Package\n")
    end = txt.find("Buy Options", begin)
    require(begin >= 0 and end > begin, f"manufacturer package section not found: {sku}")
    section = txt[begin:end]
    require(package + ":" in section, f"official package name mismatch: {sku}")
    require(package.startswith("LFBGA") and package[5:].isdigit(),
            f"no supported explicit LFBGA package gate: {sku}")
    values = {int(m.group(1)) for m in BUMP.finditer(section)}
    require(len(values) == 1, f"ambiguous or missing manufacturer bump count: {sku}")
    count = values.pop()
    require(count == int(package[5:]),
            f"official package and bump evidence disagree: {sku}")
    return count


def resolve(root: Path) -> tuple[list[dict], dict]:
    before, _, prior_summary = prior_audit(root)
    recorded, _ = prior_index()
    require(len(before) == len(recorded) == 353 and
            [r["icpn"] for r in before] == [r["icpn"] for r in recorded],
            "353 Active exact identity order changed")
    source = verify_shard_lock(root, json.loads(LOCK.read_text(encoding="utf-8")))
    gate = json.loads(GATE.read_text(encoding="utf-8"))
    expected = gate["original_missing_bump_exact_skus"]
    require(gate["source_workflow_run_id"] == 38337377867 and
            gate["production_write_authorized"] is False and
            gate["runtime_programming_qualified"] is False and
            len(expected) == len(set(expected)) == 11,
            "11-bump manufacturer evidence gate changed")
    locked={x["icpn"]:x for x in gate["qualified_source_evidence"]}
    require(set(locked)==set(expected) and
            all(x["original_package_name"]=="LFBGA64" and
                x["explicit_original_package_contact"]=="64 bumps" and
                x["official_source_sha_locked"] is True and
                x["canonical_production_admission_authorized"] is False
                for x in locked.values()),
            "per-SKU manufacturer BGA evidence lock drift")
    recovered = []
    output = []
    counts = Counter()
    reasons = Counter()
    for record, index in zip(before, recorded):
        sku = record["icpn"]
        item = dict(record)
        state = record["independent_html_replay_state"]
        old_pins = record["pin_count_observed"]
        if sku in expected:
            require(index["review_state"] == "PARTIAL_SOURCE_FIELDS_REVIEW_REQUIRED"
                    and state == "PARTIAL_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"
                    and record["gap_or_review_reason"] == "missing_package_terminals"
                    and old_pins == "",
                    f"cannot escalate unverified BGA source: {sku}")
            rawrow, folder = source[sku]
            require(rawrow["status"] == "official_nxp_part_metadata_observed"
                    and rawrow.get("package_raw") == "LFBGA64"
                    and rawrow.get("package_terminals") is None,
                    f"wrong raw official BGA source state: {sku}")
            raw = gzip.decompress((folder / f"{sku}.html.gz").read_bytes())
            require(sha_bytes(raw) == rawrow["source_sha256"] ==
                    record["official_part_html_sha256"] ==
                    locked[sku]["original_rendered_html_sha256"],
                    f"original manufacturer HTML SHA drift: {sku}")
            require(locked[sku]["manufacturer_part_url"] == rawrow["source_url"],
                    f"official NXP exact source route drift: {sku}")
            n = read_bga_contacts(sku, raw, rawrow["package_raw"])
            require(n == 64, f"unexpected manufacturer BGA count: {sku}")
            item["pin_count_observed"] = str(n)
            item["independent_html_replay_state"] = (
                "FOUR_FIELDS_BGA_BUMP_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"
            )
            item["gap_or_review_reason"] = "explicit_manufacturer_LFBGA64_bumps"
            recovered.append(sku)
        else:
            require(index["review_state"].startswith(("KL25_", "FOUR_", "PARTIAL_", "OFFICIAL_")),
                    f"noncanonical source index: {sku}")
        require(item["catalog_admission_authorized"] == "false" and
                item["programming_backend_authorized"] == "false",
                "research-only permission changed")
        counts[item["independent_html_replay_state"]] += 1
        reasons[item["gap_or_review_reason"]] += 1
        output.append(item)
    require(set(recovered) == set(expected),
            "exact BGA manufacturer source evidence subset drift")
    require(counts["FOUR_FIELDS_BGA_BUMP_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"] == 11 and
            counts["FOUR_FIELDS_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"] == 201 and
            counts["PARTIAL_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"] == 36 and
            counts["SOURCE_BLOCKED_REVIEW_REQUIRED"] == 93 and
            counts["PRIOR_KL25_REVIEWED"] == 12,
            "353-source original evidence reconciliation cardinality changed")
    return output, {
        "schema_version": 3,
        "manufacturer": "NXP",
        "status": "EXACT_SOURCE_BUMP_EVIDENCE_UPGRADED_CATALOG_REVIEW_REQUIRED",
        "original_source_run_id": gate["source_workflow_run_id"],
        "original_353_identity_count": len(output),
        "four_source_field_replay_verified_count": 201,
        "bump_contact_evidence_upgraded_count": len(recovered),
        "four_source_field_combined_review_queue_count": 212,
        "prior_KL25_research_metadata_ready": 12,
        "partial_source_evidence_remaining": 36,
        "blocked_source_evidence_remaining": 93,
        "unresolved_exact_metadata_count_excluding_KL25": 36 + 93,
        "source_85_http_non200_still_unresolved": 85,
        "source_8_ambiguous_flash_still_unresolved": 8,
        "recovered_exact_skus": sorted(recovered),
        "metadata_state_counts": dict(sorted(counts.items())),
        "no_nxp_vendor_wide_denominator": True,
        "canonical_metadata_admission_authorized": False,
        "production_write_authorized": False,
        "runtime_programming_qualified": False,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows, report = resolve(args.root)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "nxp-353-replayed-metadata-v3.csv").open(
            "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    (args.output / "nxp-353-metadata-gap-resolution-v3.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
