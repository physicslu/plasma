#!/usr/bin/env python3
"""Read-only eight-shard re-acquisition of all 277 NXP exact Active evidence gaps.

Never authorizes Production Catalog admission or a Programming Profile.
Original HTML is preserved in per-SKU compressed artifacts; reconciliation
requires exact official /part/<ICPN> identity and a SHA-256 byte replay.
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
from nxp_bulk_part_metadata_v1 import capture
from nxp_manufacturer_device_bulk_v5 import EVIDENCE_LABELS, field, source_cells

HERE = Path(__file__).resolve().parent
QUEUE = HERE / "nxp-277-manufacturer-gap-review-v6.csv"
SUMMARY = HERE / "nxp-277-gap-summary-v6.json"
QUEUE_BLOB = "6480f04e57dd29d7bd45441c38552dad89107f51"
SHARDS = 8
OUTPUT_FIELDS = [
    "icpn", "discovery_cohort", "prior_source_state", "refresh_state",
    "package", "pin_count", "flash_kb", "ram_kb", "operating_vdd",
    "ambient_temperature", "ram_evidence_state", "vdd_evidence_state",
    "official_exact_part_url", "source_html_sha256", "failure_type",
    "catalog_admission_qualified", "production_publication_authorized",
    "programming_profile_qualified",
]


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def source_queue() -> list[dict[str, str]]:
    require(blob(QUEUE) == QUEUE_BLOB, "original 277 source queue drift")
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    require(summary["bounded_active_exact_501"] == 501 and
            summary["pending_active_exact"] == 277 and
            summary["main_production_nxp_exact"] == 224 and
            summary["manufacturer_global_denominator"] is None and
            summary["production_catalog_authorized"] is False,
            "source summary or Production authority drift")
    with QUEUE.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == 277 and len({r["icpn"] for r in rows}) == 277,
            "incomplete or duplicated manufacturer source queue")
    require(Counter(r["discovery_cohort"] for r in rows) ==
            {"original_353_active": 129, "expanded_148_active": 148},
            "original/new cohort partition drift")
    for r in rows:
        sku = r["icpn"]
        require(re.fullmatch(r"[A-Z0-9]{6,64}", sku) is not None and
                r["official_exact_part_url"] == f"https://www.nxp.com/part/{sku}" and
                r["production_catalog_authorized"] == "false" and
                r["programming_profile_qualified"] == "false",
                f"unsafe source identity or authorization: {sku}")
    return rows


def selected(rows: list[dict], index: int) -> list[dict]:
    require(0 <= index < SHARDS, "unexpected acquisition shard index")
    return [r for i, r in enumerate(rows) if i % SHARDS == index]


def acquire(index: int, output: Path) -> None:
    from playwright.sync_api import sync_playwright

    rows = selected(source_queue(), index)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(locale="en-US")
            page = context.new_page()
            for row in rows:
                sku = row["icpn"]
                try:
                    record = capture(page, sku, output)
                except Exception as exc:
                    record = {
                        "icpn": sku, "status": "blocked_source_or_schema",
                        "source_url": f"https://www.nxp.com/part/{sku}",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:400],
                        "canonical_metadata_admission_authorized": False,
                        "programming_backend_qualified": False,
                    }
                require(record["icpn"] == sku, "capture changed requested SKU")
                results.append(record)
                print(json.dumps({"shard": index, "icpn": sku,
                                  "status": record["status"]}), flush=True)
            context.close()
        finally:
            browser.close()
    report = {
        "schema_version": 7, "manufacturer": "NXP",
        "queue_git_blob": QUEUE_BLOB, "shard": index,
        "requested": len(rows), "exact_skus": [r["icpn"] for r in rows],
        "production_publication_authorized": False,
        "programming_profile_qualified": False, "results": results,
    }
    (output / "shard.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def reconcile(root: Path, destination: Path) -> dict:
    rows = source_queue()
    observed: dict[str, tuple[dict, Path]] = {}
    for i in range(SHARDS):
        folder = root / f"nxp-277-refresh-shard-{i}"
        report = json.loads((folder / "shard.json").read_text(encoding="utf-8"))
        want = [r["icpn"] for r in selected(rows, i)]
        require(report["schema_version"] == 7 and
                report["manufacturer"] == "NXP" and
                report["queue_git_blob"] == QUEUE_BLOB and
                report["shard"] == i and report["requested"] == len(want) and
                report["exact_skus"] == want and
                [r["icpn"] for r in report["results"]] == want and
                report["production_publication_authorized"] is False and
                report["programming_profile_qualified"] is False,
                f"shard {i} source manifest mismatch")
        for record in report["results"]:
            sku = record["icpn"]
            require(sku not in observed, f"duplicate source SKU: {sku}")
            observed[sku] = (record, folder)
    require(len(observed) == 277, "partial NXP source refresh rejected")

    output_rows = []
    counts = Counter()
    for row in rows:
        sku = row["icpn"]
        item, folder = observed[sku]
        require(item.get("source_url") == f"https://www.nxp.com/part/{sku}" and
                item["status"] in {"official_nxp_part_metadata_observed",
                                   "blocked_source_or_schema"} and
                item.get("canonical_metadata_admission_authorized") is False,
                f"untrusted official-source status: {sku}")
        state = "SOURCE_BLOCKED_OR_SCHEMA"
        package = pins = flash = ram = vdd = ambient = sha = ""
        ram_state = vdd_state = failure = ""
        if item["status"] == "blocked_source_or_schema":
            failure = item.get("error_type") or "unknown_blocked_source"
            require(not (folder / f"{sku}.html.gz").exists(),
                    f"blocked SKU incorrectly supplies HTML: {sku}")
        else:
            require(item.get("heading_matches_exact_sku") is True and
                    item.get("programming_backend_qualified") is False,
                    f"unqualified official part capture: {sku}")
            compressed = folder / f"{sku}.html.gz"
            raw = gzip.decompress(compressed.read_bytes())
            sha = hashlib.sha256(raw).hexdigest()
            require(sha == item.get("source_sha256"), f"HTML digest drift: {sku}")
            soup = BeautifulSoup(raw, "html.parser")
            headings = [h.get_text(" ", strip=True) for h in soup.select("h1")]
            require(sku in headings, f"wrong /part HTML heading for {sku}")
            cells = source_cells(soup)
            ram, ram_state = field(cells, EVIDENCE_LABELS["ram_kb"])
            if ram and re.fullmatch(r"[0-9]{1,7}(?:[.][0-9]+)?", ram) is None:
                ram, ram_state = "", "unsupported_ram_value"
            vdd, vdd_state = field(cells, EVIDENCE_LABELS["vdd_range"])
            package = str(item.get("package_raw") or "")
            pins = str(item.get("package_terminals") or "")
            flash = str(item.get("flash_kb_raw") or "")
            ambient = str(item.get("ambient_temperature_raw") or "")
            four = bool(package and pins and flash and ambient)
            if four and ram:
                state = "FOUR_BASIC_FIELDS_AND_RAM_SOURCE_REPLAYED"
            elif four:
                state = "FOUR_BASIC_FIELDS_RAM_NOT_VERIFIED"
            else:
                state = "PARTIAL_EXACT_HTML_REPLAYED"
        counts[state] += 1
        output_rows.append({
            "icpn": sku, "discovery_cohort": row["discovery_cohort"],
            "prior_source_state": row["source_state"], "refresh_state": state,
            "package": package, "pin_count": pins, "flash_kb": flash,
            "ram_kb": ram, "operating_vdd": vdd, "ambient_temperature": ambient,
            "ram_evidence_state": ram_state, "vdd_evidence_state": vdd_state,
            "official_exact_part_url": f"https://www.nxp.com/part/{sku}",
            "source_html_sha256": sha, "failure_type": failure,
            "catalog_admission_qualified": "false",
            "production_publication_authorized": "false",
            "programming_profile_qualified": "false",
        })
    require(sum(counts.values()) == 277, "missing NXP source decisions")
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "nxp-277-refreshed-source-review-v7.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)
    summary = {
        "schema_version": 7, "manufacturer": "NXP",
        "scope": "bounded_501_active_only",
        "refreshed_exact_active_277": 277,
        "prior_production_nxp_exact": 224,
        "original_129": 129, "new_148": 148,
        "refresh_states": dict(sorted(counts.items())),
        "source_queue_git_blob": QUEUE_BLOB,
        "global_active_denominator": None,
        "catalog_admission_qualified": False,
        "production_publication_authorized": False,
        "programming_profile_qualified": False,
        "physical_programming_qualified": False,
    }
    (destination / "nxp-277-refreshed-source-summary-v7.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("NXP_277_REFRESH=" + json.dumps(summary, sort_keys=True), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--shard", type=int)
    group.add_argument("--aggregate-root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.shard is not None:
        acquire(args.shard, args.output)
    else:
        reconcile(args.aggregate_root, args.output)


if __name__ == "__main__":
    main()
