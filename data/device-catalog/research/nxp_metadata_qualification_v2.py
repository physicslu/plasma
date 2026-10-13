#!/usr/bin/env python3
"""Offline manufacturer-HTML replay for all 353 NXP research identities.

Read-only and fail-closed: this is evidence consistency, NOT canonical
metadata admission, Programming Backend qualification, or Production write.
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
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from nxp_bulk_part_metadata_reconcile_v1 import normalized
from nxp_bulk_admission_matrix_v1 import ACTIVE_HASH, exact_set_hash

HERE = Path(__file__).resolve().parent
LOCK = HERE / "nxp-bulk-353-metadata-evidence-lock-v2.json"
STATE_MAP = HERE / "nxp-bulk-353-status-map-v2.json"
HEX = re.compile(r"[a-f0-9]{64}\Z")
PKG_TERM = re.compile(r"\b(\d{2,4})\s+(terminals?|pins?|balls?|leads?)\b", re.I)
EVIDENCE_FIELDS = ("package_raw", "package_terminals", "flash_kb_raw",
                   "ambient_temperature_raw", "junction_temperature_raw")


def require(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def table_values(soup: BeautifulSoup, label: str) -> list[str]:
    result = []
    for tr in soup.select("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) == 2 and cells[0].get_text(" ", strip=True) == label:
            result.append(cells[1].get_text(" ", strip=True))
    return result


def verify_html_exact_sku(sku: str, raw: bytes, fields: dict) -> None:
    """Re-extract from retained manufacturer HTML without using saved fields."""
    soup = BeautifulSoup(raw, "html.parser")
    heads = [x.get_text(" ", strip=True) for x in soup.select("h1")]
    require(sku in heads, f"manufacturer exact part heading missing: {sku}")
    document_text = soup.get_text("\n", strip=True)
    pkg = fields.get("package_raw")
    if pkg is not None:
        first = document_text.find("Package\n")
        last = document_text.find("Buy Options", first) if first >= 0 else -1
        require(first >= 0 and last > first, f"official package section missing: {sku}")
        section = document_text[first:last]
        require(pkg + ":" in section, f"package source mismatch: {sku}")
        pins = fields.get("package_terminals")
        if pins is not None:
            require(any(int(m.group(1)) == int(pins) for m in PKG_TERM.finditer(section)),
                    f"terminal/ball count not independently reproducible: {sku}")
    if fields.get("flash_kb_raw") is not None:
        values = table_values(soup, "Flash (kB)")
        require(str(fields["flash_kb_raw"]) in values,
                f"flash value mismatch: {sku}")
    if fields.get("ambient_temperature_raw") is not None:
        a = table_values(soup, "Ambient Operating Temperature (Min to Max) (℃)")
        b = table_values(soup, "Ambient Operating Temperature (Min to Max) (°C)")
        require(fields["ambient_temperature_raw"] in a + b,
                f"ambient temperature source mismatch: {sku}")
    if fields.get("junction_temperature_raw") is not None:
        a = table_values(soup, "Junction Temperature (Min to Max) (℃)")
        b = table_values(soup, "Junction Temperature (Min to Max) (°C)")
        require(fields["junction_temperature_raw"] in a + b,
                f"junction temperature source mismatch: {sku}")


def verify_shard_lock(root: Path, lock: dict) -> dict[str, dict]:
    require(lock["schema_version"] == 2 and
            lock["source_workflow_run_id"] == 38337377867 and
            lock["active_exact"] == 353 and lock["metadata_source_exact_skus"] == 341
            and lock["frozen_active_exact_set_sha256"] == ACTIVE_HASH and
            lock["claims"]["production_write_authorized"] is False and
            lock["claims"]["all_353_canonical_metadata_admitted"] is False and
            lock["claims"]["global_nxp_active_denominator"] is None,
            "NXP evidence lock scope/authority drift")
    shards = lock["source_shards"]
    require(len(shards) == 8 and {x["shard"] for x in shards} == set(range(8)),
            "source shard identity drift")
    all_skus = {}
    for x in shards:
        folder = root / f"nxp-part-metadata-shard-{x['shard']}"
        path = folder / "metadata-shard.json"
        raw = path.read_bytes()
        require(digest(raw) == x["metadata_json_sha256"],
                f"frozen official source metadata JSON digest changed: shard {x['shard']}")
        doc = json.loads(raw)
        require(doc["shard"] == x["shard"] and doc["shard_count"] == 8 and
                doc["manufacturer"] == "NXP" and
                doc["production_write_authorized"] is False,
                "unexpected source acquisition shard")
        for row in doc["results"]:
            sku = row["icpn"]
            require(sku not in all_skus, f"duplicate manufacturer exact SKU: {sku}")
            all_skus[sku] = (row, folder)
    require(len(all_skus) == 341, "missing or duplicated official SKU metadata sources")
    return all_skus


def audit(root: Path) -> tuple[list[dict], list[dict], dict]:
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    by_sku = verify_shard_lock(root, lock)
    rows, upstream = normalized(root)  # official URL + gzip SHA and 341 partition
    require(len(rows) == 353 and upstream["identity_total"] == 353 and
            upstream["blocked_exact_part_pages"] == lock["source_blocked"] == 93 and
            upstream["acquired_official_part_metadata"] == lock["observed_part_pages"] == 248,
            "bounded official metadata source count drift")
    require(exact_set_hash({r["icpn"] for r in rows}) == ACTIVE_HASH,
            "original official Active exact set changed")

    annotated, exceptions = [], []
    reasons = Counter()
    states = Counter()
    lanes = Counter()
    for record in rows:
        sku = record["icpn"]
        lane = record["segment"]
        lanes[lane] += 1
        if sku not in by_sku:
            require(record["metadata_review_state"] == "previously_reviewed_KL25",
                    "unattributed NXP source/metadata record")
            status, reason = "PRIOR_KL25_REVIEWED", "existing_manufacturer_metadata_gate"
        else:
            source, folder = by_sku[sku]
            require(source["source_url"] == f"https://www.nxp.com/part/{sku}" and
                    source["canonical_metadata_admission_authorized"] is False,
                    "NXP exact /part identity or production permission drift")
            if source["status"] == "blocked_source_or_schema":
                err = source.get("error", "")
                if err == "NXP exact part not HTTP 200":
                    reason = "official_exact_part_http_non200"
                elif err == "official flash parameter is not an exact numeric kB value":
                    reason = "manufacturer_flash_format_requires_review"
                else:
                    raise ValueError(f"unrecognized blocked source reason: {sku}: {err}")
                status = "SOURCE_BLOCKED_REVIEW_REQUIRED"
            else:
                require(source["status"] == "official_nxp_part_metadata_observed"
                        and source["heading_matches_exact_sku"] is True
                        and source["programming_backend_qualified"] is False,
                        f"nonofficial exact SKU metadata source: {sku}")
                compressed = (folder / f"{sku}.html.gz").read_bytes()
                raw = gzip.decompress(compressed)
                require(digest(raw) == source["source_sha256"] ==
                        record["official_part_html_sha256"],
                        f"source HTML evidence checksum contradiction: {sku}")
                verify_html_exact_sku(sku, raw, source)
                incomplete = [field for field in EVIDENCE_FIELDS[:4]
                              if source.get(field) is None]
                if incomplete:
                    status = "PARTIAL_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"
                    reason = "missing_" + "_".join(incomplete)
                else:
                    status = "FOUR_FIELDS_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"
                    reason = "still_requires_canonical_field_and_datasheet_review"
        reasons[reason] += 1
        states[status] += 1
        entry = dict(record)
        entry.update({
            "independent_html_replay_state": status,
            "gap_or_review_reason": reason,
            "catalog_admission_authorized": "false",
            "programming_backend_authorized": "false",
        })
        annotated.append(entry)
        if status not in {"PRIOR_KL25_REVIEWED"}:
            exceptions.append({
                "icpn": sku, "segment": lane,
                "qualification_state": status,
                "review_reason": reason,
                "official_part_url": record["official_part_url"],
                "official_part_html_sha256": record["official_part_html_sha256"],
            })
    require(sum(states.values()) == 353 and states["PRIOR_KL25_REVIEWED"] == 12
            and states["FOUR_FIELDS_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"] == 201
            and states["PARTIAL_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED"] == 47
            and states["SOURCE_BLOCKED_REVIEW_REQUIRED"] == 93,
            "independent HTML field-replay partition contradicts original source run")
    require(reasons["official_exact_part_http_non200"] == 85 and
            reasons["manufacturer_flash_format_requires_review"] == 8,
            "blocked root-cause partition drift")
    # Persist per-SKU classification, not merely aggregate counts.
    # Indexed by the frozen sorted 353-identity matrix, it remains useful
    # after the original GitHub Actions raw HTML artifacts expire.
    state_code = {
        "PRIOR_KL25_REVIEWED": "K",
        "FOUR_FIELDS_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED": "C",
        "PARTIAL_HTML_REPLAY_VERIFIED_REVIEW_REQUIRED": "P",
        "SOURCE_BLOCKED_REVIEW_REQUIRED": "B",
    }
    reason_code = {
        "official_exact_part_http_non200": "H",
        "manufacturer_flash_format_requires_review": "F",
    }
    joined_states = "".join(state_code[r["independent_html_replay_state"]]
                            for r in annotated)
    joined_reasons = "".join(reason_code.get(r["gap_or_review_reason"], "-")
                             for r in annotated)
    frozen_states = json.loads(STATE_MAP.read_text(encoding="utf-8"))
    require(frozen_states["active_set_sha256"] == ACTIVE_HASH and
            frozen_states["claims"]["production_write_authorized"] is False and
            frozen_states["claims"]["canonical_metadata_admission_authorized"] is False and
            frozen_states["claims"]["global_nxp_active_denominator"] is None,
            "frozen per-SKU metadata map authority drift")
    require(joined_states == frozen_states["status_map"] and
            joined_reasons == frozen_states["blocked_reason_map"],
            "per-SKU manufacturer metadata qualification map drift")
    require(digest((joined_states+"\\n").encode()) == frozen_states["status_map_sha256"] and
            digest((joined_reasons+"\\n").encode()) ==
                frozen_states["blocked_reason_map_sha256"],
            "per-SKU manufacturer metadata map SHA-256 mismatch")

    summary = {
        "schema_version": 2,
        "manufacturer": "NXP",
        "status": "OFFICIAL_BULK_METADATA_EVIDENCE_REPLAY_PASSED_REVIEW_REQUIRED",
        "source_workflow_run_id": lock["source_workflow_run_id"],
        "source_lock_sha256": digest(LOCK.read_bytes()),
        "official_active_exact_count": 353,
        "active_exact_set_sha256": ACTIVE_HASH,
        "source_metadata_exact_sku_count": 341,
        "metadata_state_counts": dict(sorted(states.items())),
        "root_cause_counts": dict(sorted(reasons.items())),
        "segment_counts": dict(sorted(lanes.items())),
        "global_nxp_active_denominator": None,
        "canonical_catalog_admission_authorized": False,
        "production_write_authorized": False,
        "runtime_programming_qualified": False,
    }
    return annotated, exceptions, summary


def save_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    annotated, exceptions, summary = audit(args.root)
    args.output.mkdir(parents=True, exist_ok=True)
    save_csv(args.output / "nxp-353-evidence-replay-review.csv", annotated)
    save_csv(args.output / "nxp-341-review-queue.csv", exceptions)
    (args.output / "nxp-metadata-qualification-v2.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
