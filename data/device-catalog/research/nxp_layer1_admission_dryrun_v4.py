#!/usr/bin/env python3
"""Read-only bounded NXP 353 snapshot + 12-row KL25 Layer-1 proposal.

Evidence/status are independent of target programming: this produces an
unpublished hypothetical manifest, never changes Production or authorizes
a PLASMA programming job. Original NXP SKU Active universe is bounded to
23 product pages, not an entire vendor denominator.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

from nxp_metadata_status_index_v2 import materialize as frozen_index
from nxp_metadata_gap_queue_v3 import queue as unresolved_queue
from nxp_metadata_gap_resolution_v3 import GATE as BUMP_LOCK

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
KL25 = HERE / "nxp-kl25-commercial-icpn.csv"
KL25_GATE = HERE / "nxp-kl25-admission-readiness.json"
SOURCE_CANDIDATES = HERE / "nxp-active-353-bulk-candidates-v1.csv"
ORIGINAL_353 = "8d25ee58d833b69d9d6b6bc68bd20d11090c33c543e606507b95ce667267eb24"
KL25_SOURCE_SHA = "73876af1a6344c298dd98559f2ea824362b8ce4935308e7b598d842d537bab95"
KL25_BLOB_SHA = "53087e9082445e7948f88e688ecd890b0454d788"
KL25_EXACT_SHA = "dd2c3cee83552a9875ee84c7bdea2cc6bc9c671f528b4bde02bed02b753755d5"
EXPECTED_PRODUCTION_MANIFEST_BLOB = "3f66a14212fbf82aa9faa16e9434892f649f736d"
EXPECTED_PRODUCTION_ROWS = 4629
EXPECTED_PRODUCTION_SOURCES = 28
FIELDS = (
    "icpn","manufacturer","segment","lifecycle","candidate_class",
    "research_metadata_status","independent_qualifying_source",
    "existing_exact_peer","peer_frozen_metadata_status","source_exception",
    "requested_next_evidence","canonical_metadata_admission_authorized",
    "production_write_authorized","programming_backend_qualified",
    "physical_programming_verified",
)


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def gitblob(data: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()


def read_manifest() -> tuple[dict, int]:
    raw = MANIFEST.read_bytes()
    require(gitblob(raw) == EXPECTED_PRODUCTION_MANIFEST_BLOB,
            "Production manifest changed: new owner-reviewed dry-run baseline required")
    doc = json.loads(raw)
    src = doc["sources"]
    total = sum(int(s["row_count"]) for s in src)
    require(doc["status"] == "production" and
            doc["selection_policy"] == "admitted_exact_manufacturer_part_number_only"
            and len(src) == EXPECTED_PRODUCTION_SOURCES and
            total == EXPECTED_PRODUCTION_ROWS,
            "Production prestate count/version changed")
    require(all(s["manufacturer"] != "NXP" for s in src),
            "NXP already exists in Production; refuse duplicate admission")
    require(all(s["manufacturer"] == "STMicroelectronics" for s in src),
            "unexpected existing manufacturer state")
    return doc, total


def kl25_rows() -> tuple[list[dict], bytes]:
    raw = KL25.read_bytes()
    require(sha256(raw) == KL25_SOURCE_SHA and gitblob(raw) == KL25_BLOB_SHA,
            "NXP 12-row manufacturer-reviewed canonical KL25 CSV drift")
    gate = json.loads(KL25_GATE.read_text(encoding="utf-8"))
    require(gate["catalog_admission_ready"] is True and
            gate["frozen_exact_icpn_count"] == 12 and
            gate["frozen_exact_icpn_set_sha256"] == KL25_EXACT_SHA and
            gate["canonical_candidate_sha256"] == KL25_SOURCE_SHA and
            gate["canonical_candidate_git_blob_sha"] == KL25_BLOB_SHA and
            gate["route_ready_count"] == 12 and
            gate["metadata_exception_count"] == 0 and
            gate["claims"]["production_write_authorized"] is False and
            gate["claims"]["runtime_programming_support_claimed"] is False,
            "KL25 source authority or approval boundary changed")
    with io.StringIO(raw.decode("utf-8"), newline="") as stream:
        rows = list(csv.DictReader(stream))
    ids = [r["icpn"] for r in rows]
    require(len(ids) == len(set(ids)) == 12 and
            sha256(("\n".join(sorted(ids))+"\n").encode()) == KL25_EXACT_SHA,
            "KL25 exact manufacturer SKU set differs from independently reviewed scope")
    require(all(r["manufacturer"] == "NXP"
                and r["family"] == r["series"] == "KL25"
                and r["mapping_status"] == "deterministic_ordering_pattern"
                and r["existing_identifier_kind"] == "ordering_pattern"
                and r["openocd_target_config"] == "tcl/target/kl25.cfg"
                and r["source_authority"].startswith("https://www.nxp.com/")
                and r["verification_status"].startswith("verified_nxp_manufacturer_")
                and r["pin_count"] and r["flash_size"] and r["temperature_grade"]
                for r in rows),
            "KL25 mandatory manufacturer metadata or route evidence missing")
    return rows, raw


def proposal() -> tuple[list[dict], dict, dict, bytes]:
    production, total = read_manifest()
    ready, kl25_csv = kl25_rows()
    original, orig_summary = frozen_index()
    gaps, gap_summary = unresolved_queue()
    ids = {r["icpn"] for r in original}
    require(len(ids) == len(original) == 353 and
            orig_summary["official_active_exact_count"] == 353 and
            gap_summary["active_exact_total"] == 353,
            "full 353 manufacturer identity scope drift")
    actual_set_sha = sha256(("\n".join(sorted(ids))+"\n").encode())
    require(actual_set_sha == ORIGINAL_353,
            "frozen NXP Active exact set SHA256 drift")
    kl_ids = {r["icpn"] for r in ready}
    require(kl_ids <= ids and len(kl_ids) == 12,
            "KL25 independently documented Exact identities differ from global 353 set")
    bump = json.loads(BUMP_LOCK.read_text(encoding="utf-8"))
    bga = set(bump["original_missing_bump_exact_skus"])
    require(len(bga) == 11 and not bga & kl_ids and
            bump["production_write_authorized"] is False,
            "replayed BGA manufacturer evidence / authority drift")
    gaps_by = {r["icpn"]: r for r in gaps}
    require(len(gaps) == len(gaps_by) == 129 and
            not (set(gaps_by) & kl_ids) and
            not (set(gaps_by) & bga),
            "129 unresolved exact SKUs overlap verified KL25/BGA sources")

    statuses = {r["icpn"]: r["review_state"] for r in original}
    counts = Counter()
    paired = Counter()
    output = []
    for row in original:
        sku = row["icpn"]
        case = gaps_by.get(sku)
        peer = ""
        peer_status = ""
        if sku in kl_ids:
            klass = "KL25_BOUNDED_LAYER1_PROPOSAL_REQUIRES_OWNER_APPROVAL"
            evidence = "manufacturer_document_reviewed_canonical_route_still_no_HIL"
            gap_type = ""
            next_step = "separately_approve_12_layer1_production_write"
        elif case is not None:
            klass = "RESEARCH_SOURCE_OR_METADATA_GAP_NOT_ADMISSIBLE"
            evidence = "bounded_official_active_identity_only"
            gap_type = case["exception_class"]
            next_step = case["manufacturer_evidence_route"]
            if gap_type == "http_non200":
                if sku.endswith("R"):
                    base = sku[:-1]
                    if base in ids:
                        peer = base
                        peer_status = statuses[base]
                        paired["R_with_active_exact_minus_R_peer"] += 1
                    else:
                        paired["R_without_active_exact_minus_R_peer"] += 1
                else:
                    paired["non_R_http_non200"] += 1
        elif sku in bga:
            require(row["review_state"] == "PARTIAL_SOURCE_FIELDS_REVIEW_REQUIRED",
                    f"11 BGA original part state drift: {sku}")
            klass = "FOUR_FIELD_HTML_EVIDENCE_ONLY_REVIEW_REQUIRED"
            evidence = "11_explicit_LFBGA64_bumps_SHA_locked_original_HTML"
            gap_type = ""
            next_step = "complete_datasheet_canonical_semantics_and_backend_review"
        else:
            require(row["review_state"] == "FOUR_SOURCE_FIELDS_VERIFIED_REVIEW_REQUIRED",
                    f"unexplained research metadata status: {sku}")
            klass = "FOUR_FIELD_HTML_EVIDENCE_ONLY_REVIEW_REQUIRED"
            evidence = "manufacturer_exact_part_original_HTML_verified"
            gap_type = ""
            next_step = "complete_datasheet_canonical_semantics_and_backend_review"
        counts[klass] += 1
        output.append({
            "icpn":sku,"manufacturer":"NXP","segment":row["segment"],
            "lifecycle":"Active","candidate_class":klass,
            "research_metadata_status":row["review_state"],
            "independent_qualifying_source":evidence,
            "existing_exact_peer":peer,"peer_frozen_metadata_status":peer_status,
            "source_exception":gap_type,"requested_next_evidence":next_step,
            "canonical_metadata_admission_authorized":"false",
            "production_write_authorized":"false",
            "programming_backend_qualified":"false",
            "physical_programming_verified":"false",
        })
    require(counts == {
        "KL25_BOUNDED_LAYER1_PROPOSAL_REQUIRES_OWNER_APPROVAL":12,
        "FOUR_FIELD_HTML_EVIDENCE_ONLY_REVIEW_REQUIRED":212,
        "RESEARCH_SOURCE_OR_METADATA_GAP_NOT_ADMISSIBLE":129,
    }, "NXP full 353 research/admission proposal partition drift")
    require(paired == {
        "R_with_active_exact_minus_R_peer":22,
        "R_without_active_exact_minus_R_peer":32,
        "non_R_http_non200":31,
    }, "NXP 85 manufacturer non-200 exact peer-source triage drift")
    require(all(r["production_write_authorized"] == "false" for r in output),
            "unauthorized candidate Production publication")
    projected = json.loads(json.dumps(production))
    projected["sources"].append({
        "manufacturer":"NXP","family":"KL25",
        "path":"../research/nxp-kl25-commercial-icpn.csv",
        "row_count":12,
        "git_blob_sha":KL25_BLOB_SHA,
        "sha256":KL25_SOURCE_SHA,
    })
    require(len(projected["sources"]) == EXPECTED_PRODUCTION_SOURCES + 1 and
            sum(int(s["row_count"]) for s in projected["sources"]) == total + 12 and
            projected["sources"][-1]["manufacturer"] == "NXP",
            "hypothetical 12-row manifest incorrect")
    report = {
        "schema_version":4,
        "status":"RESEARCH_ONLY_UNPUBLISHED_LAYER1_DRY_RUN",
        "manufacturer":"NXP","bounded_active_exact_count":353,
        "active_set_sha256":ORIGINAL_353,
        "no_global_nxp_active_denominator":True,
        "research_partition":dict(sorted(counts.items())),
        "unresolved_source_gap_counts":gap_summary["exception_counts"],
        "eighty_five_http_non200_peer_triage":dict(sorted(paired.items())),
        "kl25_exact_metadata_ready":12,
        "kl25_canonical_source_sha256":KL25_SOURCE_SHA,
        "kl25_canonical_source_git_blob_sha":KL25_BLOB_SHA,
        "kl25_route_config_only":"tcl/target/kl25.cfg",
        "production_prestate_manifest_blob":EXPECTED_PRODUCTION_MANIFEST_BLOB,
        "production_exact_prestate":total,
        "production_source_prestate":EXPECTED_PRODUCTION_SOURCES,
        "production_nxp_exact_prestate":0,
        "hypothetical_kl25_additions_if_separately_approved":12,
        "hypothetical_production_exact_after_if_approved":total+12,
        "hypothetical_production_sources_after_if_approved":EXPECTED_PRODUCTION_SOURCES+1,
        "proposal_requires_owner_approval":True,
        "production_write_authorized":False,
        "runtime_programming_qualified":False,
        "physical_programming_verified":False,
        "publication_performed":False,
    }
    return output, report, projected, kl25_csv


def as_csv(rows: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    records, summary, hypothetical, kl25_csv = proposal()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "nxp-353-bounded-layer1-qualification-review-v4.csv").write_text(
        as_csv(records), encoding="utf-8")
    (args.output / "nxp-kl25-12-proposed-canonical-rows-v4.csv").write_bytes(kl25_csv)
    (args.output / "nxp-kl25-hypothetical-manifest-NOT-PRODUCTION-v4.json").write_text(
        json.dumps(hypothetical, indent=2)+"\n", encoding="utf-8")
    (args.output / "nxp-353-layer1-admission-dryrun-v4.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
