#!/usr/bin/env python3
"""Research-only reconciliation of independently acquired NXP product pages.

All results are *observed bounded pages*, never a global NXP Active denominator.
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
SOURCE_REGISTRY = HERE / "nxp-official-pilot-products-v1.json"
KL25_SOURCE = HERE / "nxp-kl25-commercial-icpn.csv"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
HASH = re.compile(r"[0-9a-f]{64}\Z")
CODE = re.compile(r"[A-Z0-9][A-Z0-9._/-]{3,63}\Z")
LIFECYCLE = {"Active", "Qualification", "NRND", "Obsolete",
             "Discontinued", "No Longer Manufactured"}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def nxp_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname in {"nxp.com", "www.nxp.com"}


def load(path: Path) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(result, dict), "invalid evidence JSON")
    return result


def set_hash(values: set[str]) -> str:
    return sha256("".join(v + "\n" for v in sorted(values)))


def reconcile(root: Path) -> dict:
    registry = load(SOURCE_REGISTRY)
    require(registry["global_active_denominator_claimed"] is False
            and registry["production_write_authorized"] is False,
            "research-only scope changed")
    products = registry["products"]
    require(len(products) >= 7 and len({p["id"] for p in products}) == len(products),
            "fixed official product set drift")
    require({"mcx-c04x", "mcx-n23x", "kl25", "lpc55s6x", "k32-l2", "imx-rt1060", "kw45"}.issubset({p["id"] for p in products}),
            "retained seven-page manufacturer pilot changed")
    production = load(PRODUCTION_MANIFEST)
    require(production.get("status") == "production", "bad Production manifest")
    require(all(s["manufacturer"] != "NXP" for s in production["sources"]),
            "NXP Production sources exist: revise reconciliation first")
    production_nxp: set[str] = set()
    with KL25_SOURCE.open(encoding="utf-8", newline="") as fh:
        frozen_kl25 = {r["icpn"] for r in csv.DictReader(fh)}
    require(len(frozen_kl25) == 12, "KL25 frozen pilot source changed")
    observations: dict[str, list[dict]] = defaultdict(list)
    sources = []
    for product in products:
        folder = root / ("nxp-official-v1-" + product["id"])
        evidence = load(folder / "acquisition.json")
        html = (folder / "rendered-page.html").read_text(encoding="utf-8")
        require(evidence.get("status") == "bounded_official_product_page_observed",
                "missing successful acquisition")
        require(evidence.get("manufacturer") == "NXP"
                and evidence.get("acquisition_id") == product["id"]
                and evidence.get("segment") == product["segment"], "source identity mismatch")
        require(evidence.get("source_population_complete") is False
                and evidence.get("global_active_denominator_claimed") is False,
                "pilot cannot claim manufacturer-wide source completeness")
        require(nxp_url(evidence.get("source_url", "")), "non-official evidence URL")
        require(urlsplit(evidence["source_url"]).path.lower() ==
                urlsplit(product["url"]).path.lower(), "unpinned NXP product route")
        require(sha256(html) == evidence.get("rendered_dom_sha256"), "raw DOM evidence drift")
        rows = evidence.get("rows")
        require(isinstance(rows, list) and len(rows) > 0, "no official product rows")
        require(evidence.get("source_product_row_count") == len(rows), "source row count drift")
        seen_in_product = set()
        for row in rows:
            name = row.get("icpn")
            require(isinstance(name, str) and bool(CODE.fullmatch(name))
                    and name.startswith(product["prefix"]), "invalid manufacturer ordering code")
            require(name not in seen_in_product, "duplicate exact code in normalized product rows")
            seen_in_product.add(name)
            require(row.get("lifecycle") in LIFECYCLE, "invalid manufacturer lifecycle")
            require(nxp_url(row.get("source_url", "")), "non-official row evidence URL")
            require(bool(HASH.fullmatch(row.get("evidence_sha256", "")))
                    and bool(HASH.fullmatch(row.get("row_markup_sha256", ""))),
                    "missing row digest")
            for key in ("row_evidence_sha256s", "row_markup_sha256s"):
                hashes = row.get(key)
                require(isinstance(hashes, list) and len(hashes) > 0
                        and all(isinstance(h, str) and HASH.fullmatch(h) for h in hashes),
                        "missing repeated-row provenance")
            require(row["official_lifecycle_row_occurrences"] >=
                    len(row["row_evidence_sha256s"]), "invalid source occurrence count")
            observations[name].append({
                "lifecycle": row["lifecycle"], "product": product["id"],
                "evidence_sha256": row["evidence_sha256"]})
        require(product["must_include"] in seen_in_product,
                "frozen exact representative absent")
        actual_active = sum(r["lifecycle"] == "Active" for r in rows)
        actual_qual = sum(r["lifecycle"] == "Qualification" for r in rows)
        require(actual_active == evidence["active_exact_count"]
                and actual_qual == evidence["qualification_exact_count"],
                "lifecycle counts mismatch")
        if product["id"] == "kl25":
            require(seen_in_product == frozen_kl25,
                    "live KL25 exact-set drift from retained twelve-row official snapshot")
        sources.append({
            "product": product["id"],
            "segment": product["segment"],
            "page_exact_count": len(rows),
            "page_active_count": actual_active,
            "page_qualification_count": actual_qual,
            "raw_dom_sha256": evidence["rendered_dom_sha256"],
            "complete_manufacturer_denominator": False,
        })
    for name, records in observations.items():
        require(len({r["lifecycle"] for r in records}) == 1,
                "cross-product exact MPN lifecycle conflict")
    active = {name for name, records in observations.items()
              if records[0]["lifecycle"] == "Active"}
    qualification = {name for name, records in observations.items()
                     if records[0]["lifecycle"] == "Qualification"}
    other = sorted(
        ({"icpn": name, "lifecycle": records[0]["lifecycle"]}
         for name, records in observations.items()
         if records[0]["lifecycle"] not in {"Active", "Qualification"}),
        key=lambda row: row["icpn"],
    )
    require(len(active) + len(qualification) + len(other) == len(observations),
            "NXP lifecycle partition incomplete")
    return {
        "schema_version": 1,
        "status": "bounded_official_pilot_reconciled",
        "manufacturer": "NXP",
        "official_product_page_count": len(products),
        "observed_unique_exact": len(observations),
        "observed_active_exact": len(active),
        "observed_qualification_exact": len(qualification),
        "observed_other_lifecycle_exact": len(other),
        "observed_other_lifecycle_icpns": other,
        "observed_active_missing_from_production": len(active - production_nxp),
        "observed_active_exact_set_sha256": set_hash(active),
        "locked_kl25_exact_pilot": len(frozen_kl25),
        "global_active_denominator": None,
        "global_active_coverage": None,
        "global_portfolio_complete": False,
        "source_pages": sources,
        "observed_active_icpns": sorted(active),
        "observed_qualification_icpns": sorted(qualification),
        "claims": {"production_write_authorized": False,
                   "runtime_programming_support_claimed": False,
                   "physical_validation_claimed": False},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    result = reconcile(args.evidence_root)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "bounded-pilot-gap.json").write_text(
        json.dumps(result, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    (args.output / "observed-active-icpns.txt").write_text(
        "".join(x+"\n" for x in result["observed_active_icpns"]), encoding="utf-8")
    (args.output / "observed-qualification-icpns.txt").write_text(
        "".join(x+"\n" for x in result["observed_qualification_icpns"]), encoding="utf-8")
    (args.output / "observed-other-lifecycle-icpns.json").write_text(
        json.dumps(result["observed_other_lifecycle_icpns"], indent=2, sort_keys=True)+"\n",
        encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in {
        "observed_active_icpns","observed_qualification_icpns",
        "observed_other_lifecycle_icpns","source_pages"}},
        sort_keys=True))


if __name__ == "__main__":
    main()
