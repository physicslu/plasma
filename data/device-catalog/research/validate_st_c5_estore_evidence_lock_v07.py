#!/usr/bin/env python3
"""Replay frozen v0.7 C5 observed exact set and optionally the raw GitHub artifact.

An observed public eStore category is NOT a full-ST authoritative denominator.
No network, Production write or backend/runtime operation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import audit_st_portfolio_coverage_gap as v02
import acquire_st_c5_estore as acquisition

HERE = Path(__file__).resolve().parent
REPORT = HERE / "st-c5-estore-evidence-lock-v0.7.json"
CODES = HERE / "st-c5-estore-172-active-exact-mpn-v0.7.txt"
V05 = HERE / "st-bounded-active-commercial-gap-v0.5.json"
EXPECTED_SET_SHA = "32d81e2491f1c8973a778cf62828a0c76662f4fb1813bc611d8b8959607b36a3"
EXPECTED_ZIP_SHA = "b0b7349899864cbb5378603de17526532898e249be54d48a989c2c8b6b191861"
EXPECTED_CSV_SHA = "1c09edd86c7bfe12b38f6e22fea8626adced3ab964990ac6f61c1a9880abd85c"
MPN_RE = re.compile(r"STM32C5[A-Z0-9]{5,20}\Z")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_set(data: str) -> list[str]:
    require(data.endswith("\n") and "\r" not in data, "noncanonical line endings")
    rows = data.splitlines()
    require(len(rows) == 172 and len(set(rows)) == 172, "C5 exact identity count or uniqueness drift")
    require(rows == sorted(rows) and all(MPN_RE.fullmatch(row) for row in rows),
            "nonexact, wildcard or unsorted C5 identity")
    require("STM32C531CBT6" in rows, "original C5 sentinel missing")
    require(sha(("\n".join(rows) + "\n").encode()) == EXPECTED_SET_SHA,
            "officially observed set digest drift")
    return rows


def validate(report: dict | None = None, codes: str | None = None,
             artifact_zip: Path | None = None) -> dict:
    info = json.loads(REPORT.read_text(encoding="utf-8")) if report is None else report
    names = validate_set(CODES.read_text(encoding="utf-8") if codes is None else codes)
    require(info["audit_id"] == "st-c5-official-estore-raw-evidence-lock-v0.7" and
            info["observation_date_utc"] == "2026-09-29", "report identity drift")
    require(info["acquisition_status"] ==
            "OBSERVED_C5_CATEGORY_CANDIDATE_REQUIRES_INDEPENDENT_REVIEW",
            "source candidate incorrectly promoted to authoritative admission")
    require(info["observed_exact_set_sha256"] == EXPECTED_SET_SHA and
            info["observed_active_exact_mpn_count"] == len(names), "snapshot/set mismatch")
    require(info["source_url"] == acquisition.URL and
            info["vendor_displayed_active_facet"] == 172 and
            info["vendor_displayed_total_pages"] == 18, "official category scope drift")
    expected_pages = info["page_source_digests"]
    require(len(expected_pages) == 18 and
            [p["page"] for p in expected_pages] == list(range(1, 19)) and
            sum(p["exact_active_rows"] for p in expected_pages) == 172,
            "18-page acquisition ledger drift")
    require(all(re.fullmatch(r"[0-9a-f]{64}", p["sha256"]) and
                p["exact_active_rows"] == (2 if p["page"] == 18 else 10)
                for p in expected_pages), "bad page digest or row count")
    provenance = info["provenance"]
    require(provenance["pr_number"] == 677 and
            provenance["executed_pr_head_sha"] ==
            "b8457dc333b1526ea798ac609bf55be38ed18324" and
            provenance["workflow_run_id"] == 36537612073 and
            provenance["artifact_id"] == 11018802900 and
            provenance["artifact_zip_sha256"] == EXPECTED_ZIP_SHA and
            provenance["artifact_csv_sha256"] == EXPECTED_CSV_SHA,
            "source artifact provenance drift")
    base = v02.render()
    production = base["production_baseline"]
    require(production["unique_exact_icpns"] == 2683 and
            production["integrity_bound_source_count"] == 23 and
            "STM32C5" not in production["family_counts"], "frozen Production ST changed")
    legacy = json.loads(V05.read_text(encoding="utf-8"))
    fam = legacy["per_missing_family_counts"]
    require(legacy["bounded_unpublished_active_exact_mpn_minimum"] == 20 and
            fam == {"STM32C5": 1, "STM32H5": 6, "STM32N6": 3,
                    "STM32WB0": 2, "STM32WL3": 8},
            "v0.5 manually transcribed bounded observation changed")
    require(info["v05_remaining_observed_non_c5_sentinels"] == 19 and
            info["combined_bounded_official_active_observations_minimum"] == 191,
            "bounded no-overlap arithmetic drift")
    require(info["manufacturer_snapshot_atomicity_verified"] is False and
            info["product_category_equals_full_manufacturer_c5_commercial_portfolio_verified"] is False and
            info["whole_st_active_denominator"] is None and
            info["whole_st_actual_coverage_percent"] is None and
            info["whole_st_missing_exact_count"] is None and
            info["production_write_authorized"] is False and
            info["backend_route_or_hil_qualified"] is False,
            "unreviewed category snapshot incorrectly promoted to complete/admitted support")

    if artifact_zip is not None:
        raw_zip = artifact_zip.read_bytes()
        require(sha(raw_zip) == EXPECTED_ZIP_SHA, "GitHub artifact ZIP digest mismatch")
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as source:
            expected_entries = {"capture-manifest.json", "observed-active-exact-c5.csv"}
            expected_entries.update(f"raw/page-{page:02}.html" for page in range(1, 19))
            require(set(source.namelist()) == expected_entries and len(source.namelist()) == 20,
                    "raw evidence archive member drift")
            source_manifest = json.loads(source.read("capture-manifest.json"))
            require(source_manifest["status"] ==
                    "OBSERVED_C5_CATEGORY_CANDIDATE_REQUIRES_INDEPENDENT_REVIEW" and
                    source_manifest["observed_exact_active_mpn_count"] == 172 and
                    source_manifest["observed_exact_set_sha256"] == EXPECTED_SET_SHA and
                    len(source_manifest["pages"]) == 18,
                    "original capture manifest status/count drift")
            replay = set()
            for entry, pinned in zip(source_manifest["pages"], expected_pages):
                page = pinned["page"]
                require(entry["page"] == page and
                        entry["sha256"] == pinned["sha256"] and
                        entry["exact_active_rows"] == pinned["exact_active_rows"],
                        "raw source manifest / immutable ledger mismatch")
                content = source.read(f"raw/page-{page:02}.html")
                require(sha(content) == pinned["sha256"], "raw vendor HTML SHA mismatch")
                observed = acquisition.parse_html(content, page)
                require(len(observed) == pinned["exact_active_rows"] and
                        replay.isdisjoint(observed), "invalid page population or duplicate")
                replay.update(observed)
            csv_bytes = source.read("observed-active-exact-c5.csv")
            require(sha(csv_bytes) == EXPECTED_CSV_SHA, "original derived CSV byte SHA mismatch")
            csv_rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8"))))
            require(len(csv_rows) == 172 and
                    {row["exact_icpn"] for row in csv_rows} == replay == set(names) and
                    all(row["marketing_status"] == "Active" for row in csv_rows),
                    "raw archive exact set / durable research set mismatch")
    return {
        "status": "PASS", "observed_c5_category_exact_active_mpns": len(names),
        "non_c5_bounded_observed_other_four_series": 19,
        "combined_bounded_unpublished_minimum": 191,
        "frozen_st_production": 2683,
        "full_st_actual_coverage": None,
        "raw_zip_replayed": artifact_zip is not None,
        "production_changed": False,
    }


def main() -> int:
    args = argparse.ArgumentParser()
    args.add_argument("--artifact-zip", type=Path, default=None,
                      help="Optional original 7-day GitHub Actions artifact for full 18-page raw replay")
    options = args.parse_args()
    result = validate(artifact_zip=options.artifact_zip)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
