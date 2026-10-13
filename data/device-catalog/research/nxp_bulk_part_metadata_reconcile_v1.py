#!/usr/bin/env python3
"""NXP single-batch 341 missing metadata reconciliation, research-only."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
CANDIDATES = HERE / "nxp-active-353-bulk-candidates-v1.csv"
SNAPSHOT = HERE / "nxp-official-bounded-snapshot-2026-10-13-v1.json"
SHARDS = 8
PROVENANCE = re.compile(r"[a-f0-9]{64}\Z")


def require(value, message: str) -> None:
    if not value:
        raise ValueError(message)


def normalized(root: Path) -> tuple[list[dict], dict]:
    with CANDIDATES.open(newline="", encoding="utf-8") as stream:
        records = list(csv.DictReader(stream))
    frozen = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["reconciliation"]
    require(len(records) == len(frozen["observed_active_icpns"]) == 353,
            "full NXP Active identity prestate drift")
    require([x["icpn"] for x in records] == frozen["observed_active_icpns"],
            "frozen NXP exact identity ordering drift")
    missing = [x for x in records if x["metadata_gate"] ==
               "manufacturer_metadata_missing"]
    require(len(missing) == 341, "341 official metadata acquisition rows drift")
    observed = {}
    for shard in range(SHARDS):
        folder = root / f"nxp-part-metadata-shard-{shard}"
        path = folder / "metadata-shard.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        require(doc["shard"] == shard and doc["shard_count"] == 8
                and doc["manufacturer"] == "NXP"
                and doc["production_write_authorized"] is False,
                "wrong shard identity/authority")
        expected = [row["icpn"] for i, row in enumerate(missing) if i % 8 == shard]
        got = [row["icpn"] for row in doc["results"]]
        require(got == expected and doc["requested"] == len(expected),
                "wrong, absent, duplicate or reordered official SKU shard")
        require(doc["observed"] + doc["blocked"] == len(expected),
                "silent missing part-page acquisition")
        for row in doc["results"]:
            name, status = row["icpn"], row["status"]
            require(name not in observed and status in {
                "official_nxp_part_metadata_observed", "blocked_source_or_schema"},
                "duplicate or invalid part metadata state")
            require(row["canonical_metadata_admission_authorized"] is False,
                    "unexpected metadata Production permission")
            target = urlsplit(row["source_url"])
            require(target.scheme == "https" and
                    target.hostname in {"nxp.com", "www.nxp.com"} and
                    target.path.lower() == f"/part/{name}".lower(),
                    "untrusted or aliased part-page source")
            if status == "official_nxp_part_metadata_observed":
                digest = row["source_sha256"]
                require(isinstance(digest, str) and bool(PROVENANCE.fullmatch(digest)),
                        "unverified vendor HTML digest")
                raw = gzip.decompress((folder / f"{name}.html.gz").read_bytes())
                require(hashlib.sha256(raw).hexdigest() == digest,
                        f"manufacturer HTML changed: {name}")
                require(row["heading_matches_exact_sku"] is True,
                        "aliased NXP part heading entered verified metadata")
                assert row["programming_backend_qualified"] is False
                for key in ("package_raw", "package_terminals", "flash_kb_raw",
                            "ambient_temperature_raw", "junction_temperature_raw"):
                    require(key in row, f"lost manufacturer source metadata key: {key}")
            observed[name] = row
    require(len(observed) == 341, "incomplete 341 manufacturer metadata partition")

    result = []
    gates = Counter()
    field_counts = Counter()
    for row in records:
        name = row["icpn"]
        if name not in observed:
            require(row["metadata_gate"] == "manufacturer_metadata_reviewed_KL25",
                    "NXP identity has no official metadata provenance")
            status = "previously_reviewed_KL25"
            info = {"package_raw": row["package"], "package_terminals": int(row["pin_count"]),
                    "flash_kb_raw": int(row["flash_size"].split()[0]),
                    "ambient_temperature_raw": row["temperature_grade"],
                    "junction_temperature_raw": None, "source_url": "",
                    "source_sha256": ""}
        else:
            info = observed[name]
            full = (info["status"] == "official_nxp_part_metadata_observed" and
                    info.get("package_raw") and info.get("package_terminals") and
                    info.get("flash_kb_raw") and info.get("ambient_temperature_raw"))
            status = ("official_part_fields_complete_REVIEW_REQUIRED" if full else
                      "official_part_partial_REVIEW_REQUIRED" if info["status"] ==
                      "official_nxp_part_metadata_observed" else
                      "official_part_blocked_REVIEW_REQUIRED")
        gates[status] += 1
        for attr in ("package_raw", "package_terminals", "flash_kb_raw",
                     "ambient_temperature_raw", "junction_temperature_raw"):
            if info.get(attr) is not None:
                field_counts[attr] += 1
        result.append({
            "manufacturer": "NXP", "icpn": name, "segment": row["segment"],
            "lifecycle": "Active", "metadata_review_state": status,
            "package_raw": info.get("package_raw") or "",
            "pin_count_observed": info.get("package_terminals") or "",
            "flash_kb_observed": info.get("flash_kb_raw") or "",
            "ambient_temperature_raw": info.get("ambient_temperature_raw") or "",
            "junction_temperature_raw": info.get("junction_temperature_raw") or "",
            "official_part_url": info.get("source_url") or "",
            "official_part_html_sha256": info.get("source_sha256") or "",
            "production_publication_authorized": "false",
            "programming_backend_qualified": "false",
        })
    require(len(result) == 353 and sum(gates.values()) == 353,
            "bulk metadata result incomplete")
    summary = {
        "schema_version": 1,
        "status": "READ_ONLY_BULK_METADATA_ENRICHMENT",
        "manufacturer": "NXP",
        "identity_total": 353,
        "prior_reviewed_KL25": 12,
        "acquired_official_part_metadata": 341 - gates["official_part_blocked_REVIEW_REQUIRED"],
        "blocked_exact_part_pages": gates["official_part_blocked_REVIEW_REQUIRED"],
        "source_fields_complete_but_review_required":
            gates["official_part_fields_complete_REVIEW_REQUIRED"],
        "partial_source_fields_review_required":
            gates["official_part_partial_REVIEW_REQUIRED"],
        "metadata_review_states": dict(sorted(gates.items())),
        "field_observed_counts": dict(sorted(field_counts.items())),
        "no_nxp_wide_denominator_claimed": True,
        "automatic_canonical_metadata_admission_authorized": False,
        "production_write_authorized": False,
        "programming_backend_qualified": False,
    }
    return result, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    entries, report = normalized(args.root)
    args.output.mkdir(parents=True, exist_ok=True)
    fields = list(entries[0])
    with (args.output / "nxp-active-353-official-part-metadata-research.csv").open(
            "w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(entries)
    (args.output / "nxp-bulk-341-part-metadata-coverage.json").write_text(
        json.dumps(report, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
