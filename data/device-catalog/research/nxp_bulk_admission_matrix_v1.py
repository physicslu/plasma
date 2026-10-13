#!/usr/bin/env python3
"""NXP 353 exact Active ordering-code bulk admission *preparation*, read-only.

ST-style exact-set intersection/difference and evidence gates. No production
writes, no guessed family metadata, no backend or device programming.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "nxp-official-bounded-snapshot-2026-10-13-v1.json"
PRODUCTS = HERE / "nxp-official-pilot-products-v1.json"
KL25 = HERE / "nxp-kl25-commercial-icpn.csv"
PRODUCTION = HERE.parent / "production" / "icpn-v1-manifest.json"
ACTIVE_HASH = "8d25ee58d833b69d9d6b6bc68bd20d11090c33c543e606507b95ce667267eb24"
HEX = re.compile(r"[0-9a-f]{64}\Z")
CODE = re.compile(r"[A-Z0-9][A-Z0-9._/-]{3,63}\Z")
FIELDS = [
    "manufacturer", "icpn", "segment", "lifecycle", "metadata_gate",
    "package", "pin_count", "flash_size", "temperature_grade",
    "official_product_pages", "source_row_sha256s", "source_dom_sha256s",
    "identity_evidence_level", "production_publication_authorized",
    "programming_backend_qualified",
]


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"invalid JSON object: {path}")
    return value


def exact_set_hash(names: set[str]) -> str:
    return hashlib.sha256(
        "".join(s + "\n" for s in sorted(names)).encode("utf-8")
    ).hexdigest()


def official(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname in {"nxp.com", "www.nxp.com"}


def segment_for(icpn: str) -> str:
    # Classification of the six *research acquisition lanes*, not an NXP
    # part-number decoding rule for flash/package/temperature or backend.
    if icpn.startswith("MCX"):
        return "mcx"
    for prefix, lane in (
        ("MKL25Z", "kinetis"), ("LPC55", "lpc"), ("K32L", "k32"),
        ("MIMXRT", "imx-rt"), ("KW45", "wireless")
    ):
        if icpn.startswith(prefix):
            return lane
    raise ValueError(f"unclassified manufacturer Active identity: {icpn}")


def metadata_kl25() -> dict[str, dict]:
    with KL25.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_id = {row["icpn"]: row for row in rows}
    require(len(rows) == 12 and len(by_id) == 12, "frozen KL25 metadata count drift")
    require(all(row["manufacturer"] == "NXP" and row["family"] == "KL25"
                and row["package"] and row["pin_count"] and row["flash_size"]
                and row["temperature_grade"] for row in rows),
            "KL25 research metadata incomplete")
    return by_id


def validate_snapshot() -> tuple[dict, dict, dict[str, dict]]:
    s, sources = read(SNAPSHOT), read(PRODUCTS)
    p = s["reconciliation"]
    policy = s["scope_limits"]
    require(s["authority"] == "read_only_manufacturer_evidence_observation"
            and policy["source_population_complete"] is False
            and policy["global_nxp_active_denominator"] is None
            and policy["global_nxp_active_coverage"] is None
            and policy["production_admission_ready"] is False
            and policy["production_publication_authorized"] is False
            and policy["runtime_programming_qualified"] is False,
            "attempt to upgrade bounded research source authority")
    require(p["manufacturer"] == "NXP" and p["global_portfolio_complete"] is False
            and p["global_active_denominator"] is None
            and p["global_active_coverage"] is None
            and p["claims"]["production_write_authorized"] is False,
            "unverified NXP whole-vendor or write-authority claim")
    active = p["observed_active_icpns"]
    other = p["observed_other_lifecycle_icpns"]
    qualification = p["observed_qualification_icpns"]
    require(len(active) == len(set(active)) == p["observed_active_exact"] == 353,
            "353 exact Active cardinality drift")
    require(active == sorted(active) and all(CODE.fullmatch(x) for x in active),
            "unsorted or malformed exact Active MPN list")
    require(exact_set_hash(set(active)) == p["observed_active_exact_set_sha256"]
            == ACTIVE_HASH, "official exact Active set SHA-256 changed")
    require(len(qualification) == 2 and len(other) == 13
            and len(set(qualification)) == 2
            and len({x["icpn"] for x in other}) == 13
            and set(active).isdisjoint(qualification)
            and set(active).isdisjoint(x["icpn"] for x in other)
            and set(qualification).isdisjoint(x["icpn"] for x in other)
            and all(x["lifecycle"] in {"NRND", "No Longer Manufactured"} for x in other)
            and len(active) + len(qualification) + len(other) == p["observed_unique_exact"] == 368,
            "non-Active lifecycle exclusion partition drift")
    require(sources["global_active_denominator_claimed"] is False
            and sources["production_write_authorized"] is False,
            "NXP product source registry policy changed")
    products = sources["products"]
    by_product = {r["id"]: r for r in products}
    require(len(products) == len(by_product) == p["official_product_page_count"] == 23,
            "23 source pin drift")
    page_by_id = {r["product"]: r for r in p["source_pages"]}
    require(set(by_product) == set(page_by_id), "source page reconciliation drift")
    for key, source in by_product.items():
        page = page_by_id[key]
        require(source["segment"] == page["segment"]
                and bool(HEX.fullmatch(page["raw_dom_sha256"]))
                and page["complete_manufacturer_denominator"] is False
                and official(source["url"]),
                f"unverified NXP official product evidence: {key}")
    metadata = metadata_kl25()
    require(set(metadata).issubset(active), "KL25 12 candidates not all Active")
    production = read(PRODUCTION)
    require(production["status"] == "production"
            and not any(x["manufacturer"] == "NXP" for x in production["sources"]),
            "NXP Production state changed: rebaseline before any proposal")
    return s, sources, metadata


def row_evidence(evidence_root: Path, s: dict, sources: dict) -> dict[str, list[dict]]:
    """Read only after existing independent HTML/row reconciliation passes."""
    # Reuse the stricter bounded offline cross-check rather than replicating
    # its DOM hash, source URL, exact-set and lifecycle validators.
    from nxp_official_pilot_reconcile_v1 import reconcile

    verified = reconcile(evidence_root)
    pinned = s["reconciliation"]
    require(verified["observed_active_exact_set_sha256"] ==
            pinned["observed_active_exact_set_sha256"]
            and verified["observed_active_icpns"] == pinned["observed_active_icpns"]
            and verified["observed_qualification_icpns"] == pinned["observed_qualification_icpns"]
            and verified["observed_other_lifecycle_icpns"] == pinned["observed_other_lifecycle_icpns"]
            and verified["official_product_page_count"] == 23,
            "fresh official source evidence is not frozen exact identity set")
    provenance: dict[str, list[dict]] = defaultdict(list)
    for product in sources["products"]:
        d = read(evidence_root / ("nxp-official-v1-" + product["id"]) / "acquisition.json")
        require(d["status"] == "bounded_official_product_page_observed",
                "unverified official acquisition")
        require(d["acquisition_id"] == product["id"] and d["segment"] == product["segment"],
                "source product or segment mismatched")
        require(official(d["source_url"]), "non-NXP source URL")
        require(HEX.fullmatch(d["rendered_dom_sha256"]) is not None,
                "invalid source DOM digest")
        for row in d["rows"]:
            require(HEX.fullmatch(row["evidence_sha256"]) is not None
                    and HEX.fullmatch(row["row_markup_sha256"]) is not None,
                    "missing per-SKU row digest")
            provenance[row["icpn"]].append({
                "lifecycle": row["lifecycle"],
                "source_url": d["source_url"],
                "row_sha256": row["row_markup_sha256"],
                "dom_sha256": d["rendered_dom_sha256"],
            })
    for icpn in pinned["observed_active_icpns"]:
        records = provenance.get(icpn, [])
        require(bool(records) and all(r["lifecycle"] == "Active" for r in records),
                f"Active manufacturer row absent: {icpn}")
        require(all(segment_for(icpn) == next(
            p["segment"] for p in sources["products"]
            if p["url"].split("?")[0].lower() == record["source_url"].split("?")[0].lower())
                    for record in records),
                f"source segment classification contradiction: {icpn}")
    return provenance


def build(evidence_root: Path | None = None) -> tuple[list[dict], dict]:
    snapshot, sources, metadata = validate_snapshot()
    observed = snapshot["reconciliation"]
    records = row_evidence(evidence_root, snapshot, sources) if evidence_root else {}
    candidates = []
    for icpn in observed["observed_active_icpns"]:
        m = metadata.get(icpn)
        docs = sorted(records.get(icpn, []), key=lambda r: (r["source_url"], r["row_sha256"]))
        candidates.append({
            "manufacturer": "NXP", "icpn": icpn, "segment": segment_for(icpn),
            "lifecycle": "Active",
            "metadata_gate": "manufacturer_metadata_reviewed_KL25" if m else "manufacturer_metadata_missing",
            "package": m["package"] if m else "",
            "pin_count": m["pin_count"] if m else "",
            "flash_size": m["flash_size"] if m else "",
            "temperature_grade": m["temperature_grade"] if m else "",
            "official_product_pages": ";".join(sorted({x["source_url"] for x in docs})),
            "source_row_sha256s": ";".join(sorted({x["row_sha256"] for x in docs})),
            "source_dom_sha256s": ";".join(sorted({x["dom_sha256"] for x in docs})),
            "identity_evidence_level": "official_per_sku_row_reconciled" if docs else "frozen_official_exact_set_only",
            "production_publication_authorized": "false",
            "programming_backend_qualified": "false",
        })
    require(len(candidates) == 353 and
            sum(row["metadata_gate"] == "manufacturer_metadata_reviewed_KL25"
                for row in candidates) == 12 and
            sum(row["metadata_gate"] == "manufacturer_metadata_missing"
                for row in candidates) == 341, "metadata readiness partition drift")
    if evidence_root:
        require(all(x["identity_evidence_level"] == "official_per_sku_row_reconciled"
                    and x["official_product_pages"] and x["source_row_sha256s"]
                    for x in candidates), "incomplete per-SKU manufacturer evidence")
    counts: dict[str, int] = defaultdict(int)
    for row in candidates:
        counts[row["segment"]] += 1
    return candidates, {
        "schema_version": 1,
        "transaction": "NXP_353_BULK_RESEARCH_ADMISSION_PREFLIGHT_V1",
        "status": "DRY_RUN_METADATA_INCOMPLETE_OWNER_APPROVAL_NOT_YET_REQUESTED",
        "manufacturer": "NXP",
        "scope": "23 bounded official NXP product pages, not entire NXP portfolio",
        "active_candidates_exact": 353,
        "active_set_sha256": ACTIVE_HASH,
        "non_active_excluded_exact": 15,
        "active_metadata_reviewed_kl25": 12,
        "active_metadata_missing": 341,
        "production_nxp_exact_before": 0,
        "active_missing_from_production": 353,
        "candidate_counts_by_research_segment": dict(sorted(counts.items())),
        "per_sku_raw_source_evidence_locked": bool(evidence_root),
        "full_portfolio_active_denominator": None,
        "full_portfolio_active_coverage": None,
        "production_write_authorized": False,
        "catalog_automatic_admission_authorized": False,
        "programming_backend_qualified": False,
        "physical_validation_claimed": False,
        "required_next_gate": "bulk manufacturer metadata enrichment for all 341 incomplete exact Active SKUs; then bounded owner-approved Production transaction",
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--evidence-root", type=Path)
    ap.add_argument("--require-row-evidence", action="store_true")
    args = ap.parse_args()
    require(not args.require_row_evidence or args.evidence_root is not None,
            "full row evidence requested but no manufacturer acquisition supplied")
    rows, summary = build(args.evidence_root)
    args.output.mkdir(parents=True, exist_ok=True)
    write_csv(args.output / "nxp-active-353-bulk-candidates.csv", rows, FIELDS)
    write_csv(args.output / "nxp-active-metadata-341-gap.csv",
              [r for r in rows if r["metadata_gate"] == "manufacturer_metadata_missing"], FIELDS)
    snapshot = read(SNAPSHOT)["reconciliation"]
    excluded = ([{"icpn": x, "lifecycle": "Qualification"}
                 for x in snapshot["observed_qualification_icpns"]] +
                snapshot["observed_other_lifecycle_icpns"])
    write_csv(args.output / "nxp-excluded-nonactive-15.csv",
              sorted(excluded, key=lambda row: row["icpn"]), ["icpn", "lifecycle"])
    (args.output / "nxp-bulk-353-admission-preflight.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
