#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import prepare_openocd_c0_route_inventory_v625 as v625

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "openocd-parts-canonical.csv"
TX = HERE / "openocd-c0-canonical-route-write-dry-run-v6.26.json"

FIELDS = (
    "vendor","family","subfamily","plasma_series","part_number","identifier_kind",
    "cpu_architectures","target_config","openocd_distribution","mapping_status",
    "validation_status","catalog_origin",
)


class DryRunError(RuntimeError):
    pass


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise DryRunError(msg)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def render(rows: list[dict[str,str]]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def parse(raw: bytes) -> list[dict[str,str]]:
    with io.StringIO(raw.decode("utf-8")) as stream:
        reader = csv.DictReader(stream)
        req(tuple(reader.fieldnames or ()) == FIELDS, f"canonical schema drift: {reader.fieldnames}")
        return list(reader)


def build() -> tuple[bytes, bytes, dict[str,Any]]:
    tx = json.loads(TX.read_text(encoding="utf-8"))
    proposal_rows, proposal_csv, p = v625.build()

    req(p["proposal_exact_set_sha256"] == tx["input"]["v625_proposal_exact_set_sha256"],
        "v6.25 exact-set hash drift")
    req(p["proposal_pattern_set_sha256"] == tx["input"]["v625_proposal_pattern_set_sha256"],
        "v6.25 pattern-set hash drift")
    req(p["proposal_binding_sha256"] == tx["input"]["v625_proposal_binding_sha256"],
        "v6.25 binding hash drift")
    req(p["proposal_csv_sha256"] == tx["input"]["v625_proposal_csv_sha256"],
        "v6.25 proposal CSV hash drift")
    req(hashlib.sha256(proposal_csv.encode()).hexdigest() == tx["source_delta"]["sha256"],
        "source delta hash drift")
    req(len(proposal_rows) == tx["source_delta"]["row_count"] == 4,
        "source delta row count drift")
    req(all(r["catalog_origin"] == Path(tx["source_delta"]["materialized_path"]).name
            for r in proposal_rows),
        "proposal catalog_origin does not match required materialized source filename")

    pre = CATALOG.read_bytes()
    req(git_blob_sha(pre) == tx["canonical_preimage"]["git_blob_sha"],
        "canonical preimage lease failed")
    rows = parse(pre)
    req(len(rows) == tx["canonical_preimage"]["row_count"] == 7657,
        "canonical preimage row count drift")
    req(render(rows) == pre,
        "canonical preimage cannot be byte-for-byte reproduced by canonical renderer")
    req(rows == sorted(rows, key=lambda r:(r["vendor"],r["part_number"])),
        "canonical preimage sort order drift")

    before_keys = [(r["vendor"],r["part_number"].upper()) for r in rows]
    req(len(before_keys) == len(set(before_keys)),
        "canonical preimage has duplicate vendor/identifier keys")
    delta_keys = [(r["vendor"],r["part_number"].upper()) for r in proposal_rows]
    req(len(delta_keys) == len(set(delta_keys)) == 4,
        "proposal delta has duplicate keys")
    req(set(before_keys).isdisjoint(delta_keys),
        "proposal delta collides with existing canonical identifiers")

    post_rows = sorted(rows + proposal_rows, key=lambda r:(r["vendor"],r["part_number"]))
    req(len(post_rows) == tx["canonical_postimage"]["row_count"] == 7661,
        "canonical postimage row count drift")

    post = render(post_rows)
    reparsed = parse(post)
    req(reparsed == post_rows, "canonical postimage parse/render roundtrip drift")

    before_by_key = {(r["vendor"],r["part_number"].upper()):r for r in rows}
    post_by_key = {(r["vendor"],r["part_number"].upper()):r for r in reparsed}
    req(set(post_by_key) - set(before_by_key) == set(delta_keys),
        "postimage added identifiers outside exact 4-row delta")
    req(set(before_by_key) <= set(post_by_key),
        "postimage deleted existing canonical identifiers")
    req(all(post_by_key[k] == v for k,v in before_by_key.items()),
        "postimage mutated pre-existing canonical rows")

    post_git = git_blob_sha(post)
    post_sha256 = hashlib.sha256(post).hexdigest()
    pre_sha256 = hashlib.sha256(pre).hexdigest()

    lock = tx["canonical_postimage"]
    if lock["lock_state"] == "FROZEN":
        req(lock["git_blob_sha"] == post_git, "frozen postimage Git blob SHA mismatch")
        req(lock["sha256"] == post_sha256, "frozen postimage SHA256 mismatch")
        req(lock["byte_count"] == len(post), "frozen postimage byte count mismatch")
    else:
        req(lock["lock_state"] == "DISCOVERY_PENDING",
            f"unknown postimage lock state: {lock['lock_state']}")
        req(lock["git_blob_sha"] is None and lock["sha256"] is None and lock["byte_count"] is None,
            "discovery transaction contains partial postimage lock")

    for key,value in tx["governance"].items():
        if key == "exact_set_only":
            req(value is True, "exact-set governance opened")
        else:
            req(value is False, f"dry-run overclaim/authorization: {key}")

    summary = {
        "schema_version":1,
        "transaction_id":tx["transaction_id"],
        "record_state":"DRY_RUN_ONLY",
        "postimage_lock_state":lock["lock_state"],
        "canonical_preimage":{
            "row_count":len(rows),
            "git_blob_sha":git_blob_sha(pre),
            "sha256":pre_sha256,
            "byte_count":len(pre),
        },
        "source_delta":{
            "path":tx["source_delta"]["materialized_path"],
            "row_count":len(proposal_rows),
            "sha256":hashlib.sha256(proposal_csv.encode()).hexdigest(),
            "patterns":[r["part_number"] for r in proposal_rows],
        },
        "canonical_postimage":{
            "row_count":len(post_rows),
            "git_blob_sha":post_git,
            "sha256":post_sha256,
            "byte_count":len(post),
        },
        "delta_invariants":{
            "added_rows":4,
            "removed_rows":0,
            "mutated_existing_rows":0,
            "duplicate_keys":0,
        },
        "production_state_unchanged":{
            "mapped":4054,
            "no_mapping":575,
            "active_openocd_route_exact_count":3975,
            "active_openocd_route_denominator":4550,
            "active_openocd_route_coverage_percent":87.3626,
        },
        "actual_write_requirements":{
            "expected_preimage_git_blob_sha":tx["canonical_preimage"]["git_blob_sha"],
            "write_exact_postimage_only":True,
            "materialize_source_delta_same_transaction":True,
            "source_delta_path":tx["source_delta"]["materialized_path"],
            "source_delta_sha256":tx["source_delta"]["sha256"],
            "owner_approval_required":True,
        },
        "claims":{
            "canonical_write_authorized":False,
            "source_delta_materialization_authorized":False,
            "production_mapping_write_authorized":False,
            "programming_profile_binding_claimed":False,
            "programming_verified_claimed":False,
            "engineering_verified_claimed":False,
            "hil_verified_claimed":False,
        },
    }
    return proposal_csv.encode("utf-8"), post, summary


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--delta-csv",type=Path)
    parser.add_argument("--postimage",type=Path)
    parser.add_argument("--summary",type=Path)
    args=parser.parse_args()

    delta,post,summary=build()
    if args.delta_csv:
        args.delta_csv.write_bytes(delta)
    if args.postimage:
        args.postimage.write_bytes(post)
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_C0_CANONICAL_WRITE_DRY_RUN_V626_PASS")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
