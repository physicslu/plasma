#!/usr/bin/env python3
"""Fail-closed, research-only NXP segment coverage reconciliation.

No live scraping, no implicit completeness claim, no Production mutation.
Segment evidence may be generated independently by manufacturer-source
acquirers; this script verifies its basic structure before set arithmetic.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REGISTRY = HERE / "nxp-bulk-source-registry-v1.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
READINESS = HERE / "nxp-kl25-admission-readiness.json"
KL25 = HERE / "nxp-kl25-commercial-icpn.csv"
STATES = {"Active", "NRND", "Obsolete", "No Longer Manufactured", "Preproduction", "Unknown"}
PART = re.compile(r"[A-Z0-9][A-Z0-9._/-]{3,63}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def require(test: bool, reason: str) -> None:
    if not test:
        raise ValueError(reason)


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"not an object: {path}")
    return data


def digest_set(values: set[str]) -> str:
    return hashlib.sha256(("".join(v + "\n" for v in sorted(values))).encode()).hexdigest()


def official_url(url: str) -> bool:
    u = urlsplit(url)
    return u.scheme == "https" and u.hostname in ("nxp.com", "www.nxp.com")


def baseline() -> tuple[dict, set[str], set[str]]:
    registry = read_json(REGISTRY)
    require(registry["schema_version"] == 1 and registry["manufacturer"] == "NXP", "registry identity")
    require(registry["population_boundary_validated"] is False, "v1 does not authorize full portfolio population claim")
    require(registry["global_active_denominator"] is None, "v1 cannot assert a global denominator")
    require(registry["production_write_authorized"] is False, "v1 cannot write Production")
    groups = registry["segments"]
    ids = [x["id"] for x in groups]
    require(len(ids) == len(set(ids)) and len(ids) == 6, "segment inventory drift")
    for group in groups:
        require(official_url(group["index_url"]), "non-official index")
        require(group["inventory_status"] == "pending" and group["population_complete"] is False,
                "unreviewed NXP segment marked complete")
    pilot = registry["retained_pilot"]
    gate = read_json(READINESS)
    require(pilot["discovered_active_exact_icpns"] == gate["frozen_exact_icpn_count"] == 12,
            "KL25 pilot cardinality drift")
    require(gate["catalog_admission_ready"] is True, "KL25 research gate changed")
    require(pilot["catalog_admission_ready"] is True and pilot["production_published"] is False,
            "KL25 admission boundary")
    require(hashlib.sha256(KL25.read_bytes()).hexdigest() == gate["canonical_candidate_sha256"],
            "KL25 source integrity drift")
    with KL25.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    names = [r["icpn"] for r in rows]
    require(len(names) == 12 and len(set(names)) == 12, "KL25 exact identity set changed")
    require(all(r["manufacturer"] == "NXP" and r["family"] == "KL25" for r in rows),
            "KL25 research manufacturer drift")
    manifest = read_json(PRODUCTION)
    require(manifest["status"] == "production", "Production manifest status")
    require(all(s["manufacturer"] != "NXP" for s in manifest["sources"]),
            "NXP already Production; update read-only portfolio baseline")
    return registry, set(names), set()


def summarize(evidence_root: Path | None) -> dict:
    registry, kl25, production_nxp = baseline()
    found: dict[str, tuple[str, str]] = {}
    segments: list[dict] = []
    for group in registry["segments"]:
        identifier = group["id"]
        path = evidence_root / (identifier + ".json") if evidence_root else None
        if path is None or not path.is_file():
            segments.append({"segment": identifier, "state": "not_acquired", "exact_rows": 0,
                             "complete": False})
            continue
        snapshot = read_json(path)
        require(snapshot.get("manufacturer") == "NXP" and snapshot.get("segment") == identifier,
                "snapshot segment/manufacturer mismatch")
        require(official_url(snapshot.get("source_url", "")), "snapshot non-manufacturer source")
        rows = snapshot.get("rows")
        require(isinstance(rows, list) and len(rows) > 0, "empty/invalid snapshot")
        complete = snapshot.get("source_population_complete") is True
        if complete:
            # A count taken from extracted rows is circular and insufficient.
            require(snapshot.get("official_count_authority") == "manufacturer_facet",
                    "complete segment requires independent manufacturer count facet")
            count = snapshot.get("official_visible_count")
            require(type(count) is int and count == len(rows), "manufacturer count mismatch")
            require(bool(DIGEST.fullmatch(snapshot.get("official_count_evidence_sha256", ""))),
                    "manufacturer count facet evidence missing")
            require(snapshot.get("family_enumeration_verified") is True,
                    "complete segment requires full official family enumeration")
        seen: set[str] = set()
        for row in rows:
            mpn, status = row.get("icpn"), row.get("lifecycle")
            require(isinstance(mpn, str) and bool(PART.fullmatch(mpn)), "invalid exact MPN")
            require(status in STATES, "unreviewed lifecycle token")
            require(mpn not in seen, "duplicate MPN within segment")
            require(bool(DIGEST.fullmatch(row.get("evidence_sha256", ""))),
                    "manufacturer row evidence missing")
            require(official_url(row.get("source_url", "")), "row evidence not NXP")
            seen.add(mpn)
            previous = found.get(mpn)
            require(previous is None or previous[0] == status,
                    "conflicting NXP lifecycle across segments")
            found[mpn] = (status, identifier)
        segments.append({"segment": identifier,
                         "state": "verified_snapshot" if complete else "partial_snapshot",
                         "exact_rows": len(rows), "complete": complete})
    active = {mpn for mpn, (state, _) in found.items() if state == "Active"}
    unresolved = {mpn for mpn, (state, _) in found.items() if state == "Unknown"}
    global_complete = registry["population_boundary_validated"] and all(s["complete"] for s in segments)
    return {
        "schema_version": 1,
        "manufacturer": "NXP",
        "status": "full_population_verified" if global_complete else "partial_research_inventory",
        "locked_kl25_pilot_exact": len(kl25),
        "locked_kl25_exact_set_sha256": digest_set(kl25),
        "observed_unique_exact": len(found),
        "observed_active_exact": len(active),
        "observed_unknown_lifecycle_exact": len(unresolved),
        "production_nxp_exact": len(production_nxp),
        "active_missing_from_production": len(active - production_nxp),
        "observed_active_exact_set_sha256": digest_set(active),
        "complete_global_active_denominator": len(active) if global_complete else None,
        "global_active_identity_coverage": (
            len(active & production_nxp) / len(active) if global_complete and active else None
        ),
        "segments": segments,
        "claims": {
            "production_write_authorized": False,
            "runtime_programming_support_claimed": False,
            "physical_validation_claimed": False,
            "kl25_12_are_full_nxp_denominator": False,
        },
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--evidence-root", type=Path)
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    result = summarize(args.evidence_root)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
