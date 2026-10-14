#!/usr/bin/env python3
"""Portable *copy* of original Microchip Phase 1 manufacturer evidence.

This is NOT an object store, retention policy, authenticity signature, or proof
of off-site/durable custody. Offline verification independently replays actual
original MicrochipDirect HTML and two full, dual-paginated MCP response sets.
Only the previously bounded #874 two-lead P0 cohort is accepted by this v1.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

import microchip_phase1_chart_html_source_v1 as html_source
import microchip_phase1_p0_chart_batch_v1 as chart_batch
import microchip_phase1_p0_second_cohort_v1 as second

VERSION = 1
MAX_FILES = 96
MAX_FILE_SIZE = 8 * 1024 * 1024
MAX_TOTAL_SIZE = 256 * 1024 * 1024
MAX_ZIP_BYTES = 320 * 1024 * 1024
ROOTS = ("chart", "mcp-e5", "mcp-pic32")
REQUIRED = ("chart/original-chart.html", "chart/manifest.json",
            "mcp-e5/manifest.json", "mcp-pic32/manifest.json",
            "plan.json", "report.json")
MCP_RE = re.compile(r"mcp-(?:e5|pic32)/(?:manifest\.json|summary\.json|response-[0-9]{2,3}\.txt)\Z")


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def safe_name(value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts:
        return False
    if value in ("plan.json", "report.json", "bundle-index.json"):
        return True
    if value in ("chart/original-chart.html", "chart/manifest.json"):
        return True
    return MCP_RE.fullmatch(value) is not None


def raw_entries(sources):
    require(set(sources) == set(ROOTS) | {"plan", "report"},
            "all original source roots and two reviewed research documents required")
    result = {}
    for group in ROOTS:
        root = Path(sources[group])
        require(root.is_dir() and not root.is_symlink(), "untrusted source directory")
        for f in root.iterdir():
            require(f.is_file() and not f.is_symlink(), "nested/nonregular original source prohibited")
            name = group + "/" + f.name
            require(safe_name(name) and name not in result, "unexpected original-source filename")
            require(f.stat().st_size <= MAX_FILE_SIZE, "original source file too large")
            result[name] = f.read_bytes()
    for name in ("plan", "report"):
        file = Path(sources[name])
        require(file.is_file() and not file.is_symlink(), "nonregular research report source")
        require(file.stat().st_size <= MAX_FILE_SIZE, "research report too large")
        result[name + ".json"] = file.read_bytes()
    require(set(REQUIRED) <= set(result), "original HTML/MCP manifest or reports missing")
    require(len(result) <= MAX_FILES and sum(map(len, result.values())) <= MAX_TOTAL_SIZE,
            "bundle file count or byte cap exceeded")
    return result


def validate_tree(root):
    """Recompute chart, plan, both complete MCP page walks, and derived report."""
    root = Path(root)
    chart_root = root / "chart"
    chart_integrity = html_source.replay(chart_root)
    manufacturer_chart = chart_batch.build_report(chart_root)
    selected = second.cohort(manufacturer_chart)
    expected_plan = {
        "schema_version": 1,
        "scope": "research_two_unapproved_p0_queries",
        "p0_chart_original_sha256": manufacturer_chart["source_original_sha256"],
        "selected": selected,
        "query_count_upper_bound": 2,
        "production_write_authorized": False,
    }
    supplied_plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    require(supplied_plan == expected_plan, "source-derived query plan modified/mismatched")
    current = second.report(manufacturer_chart, {
        "sam-e5-d5": ("REPLAYED", root / "mcp-e5"),
        "pic32mx": ("REPLAYED", root / "mcp-pic32"),
    })
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    require(current == report, "original MCP/chart crosswalk report changed")
    require(current["mcp_state_counts"]["CURRENT_REPLAYED_MATCH"] == 2
            and current["mcp_state_counts"]["PREVIOUS_REPLAYED_NOT_RECHECKED"] == 1
            and current["mcp_state_counts"]["NOT_QUERIED"] == 338
            and current["current_exact_icpn_admissions"] == 0
            and current["production_write_authorized"] is False,
            "unexpected source-locked Research evidence states")
    queries = {r["lead_id"]: r for r in current["query_results"]}
    require(set(queries) == set(second.LEADS)
            and all(queries[lead]["source_independent_pagination_replayed"] is True
                    for lead in second.LEADS),
            "missing official MCP dual pagination proof")
    return {
        "chart_original_sha256": chart_integrity["original_byte_sha256"],
        "original_chart_bytes": chart_integrity["size_bytes"],
        "pinned_openocd_commit": current["pinned_openocd_commit"],
        "mcp_exact_source_candidates": {
            lead: queries[lead]["source_exact_ordering_candidates_not_admitted"]
            for lead in second.LEADS
        },
        "observed_p0_chart_denominator": current["observed_chart_p0_base_device_denominator"],
    }


def create_index(payload, result):
    return {
        "schema_version": VERSION,
        "format": "plasma-microchip-phase1-raw-evidence-portable-bundle",
        "evidence_scope": "original_microchipdirect_chart_and_two_mcp_p0_queries",
        "files": [{"name": name, "byte_length": len(payload[name]),
                   "sha256": hashlib.sha256(payload[name]).hexdigest()}
                  for name in sorted(payload)],
        "validated_original_source_result": result,
        "offline_source_replay_required": True,
        "durable_storage_verified": False,
        "source_authenticity_signature_verified": False,
        "production_write_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
    }


def pack(sources, output):
    output = Path(output)
    require(not output.exists(), "archive destination already exists")
    require("production" not in {x.lower() for x in output.resolve().parts},
            "production destination prohibited")
    payload = raw_entries(sources)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for name, raw in payload.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        replayed = validate_tree(root)  # never pack a failing source capture
        index = create_index(payload, replayed)
        index_bytes = (json.dumps(index, sort_keys=True, indent=2) + "\n").encode()
        payload["bundle-index.json"] = index_bytes
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".phase1-",
                                         suffix=".zip", delete=False) as tmp:
            staging = Path(tmp.name)
        try:
            with zipfile.ZipFile(staging, "w", allowZip64=False) as archive:
                for name in sorted(payload):
                    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_STORED
                    info.external_attr = 0o100644 << 16
                    archive.writestr(info, payload[name])
            # Independently unpack and replay the newly created archive.
            receipt = verify(staging)
            os.replace(staging, output)
        finally:
            staging.unlink(missing_ok=True)
    return receipt


def verify(input_path):
    archive = Path(input_path)
    require(archive.is_file() and archive.stat().st_size <= MAX_ZIP_BYTES,
            "missing/oversized source bundle")
    with tempfile.TemporaryDirectory() as td, zipfile.ZipFile(archive) as z:
        names = z.namelist()
        require(names and len(names) <= MAX_FILES + 1 and
                len(set(names)) == len(names)
                and all(safe_name(name) for name in names)
                and set(REQUIRED) | {"bundle-index.json"} <= set(names),
                "unsafe/duplicate/incomplete source archive members")
        member_index = z.getinfo("bundle-index.json")
        require(member_index.file_size <= 1024 * 1024, "oversized index")
        index = json.loads(z.read("bundle-index.json"))
        require(index.get("schema_version") == VERSION
                and index.get("format") == "plasma-microchip-phase1-raw-evidence-portable-bundle"
                and index.get("offline_source_replay_required") is True
                and index.get("durable_storage_verified") is False
                and index.get("source_authenticity_signature_verified") is False
                and index.get("production_write_authorized") is False
                and index.get("phase2_programming_authorized") is False
                and index.get("phase3_compatibility_authorized") is False,
                "untrusted custody index or false durable/production claim")
        recorded = index.get("files")
        require(isinstance(recorded, list)
                and [f.get("name") for f in recorded] == sorted(
                    x for x in names if x != "bundle-index.json"),
                "archive member/index inventory mismatch")
        approved = {f["name"]: f for f in recorded}
        require(len(approved) == len(recorded), "duplicate inventory declaration")
        total = 0
        root = Path(td)
        for name in names:
            if name == "bundle-index.json":
                continue
            info = z.getinfo(name)
            require(info.compress_type == zipfile.ZIP_STORED
                    and not info.is_dir()
                    and info.file_size <= MAX_FILE_SIZE
                    and ((info.external_attr >> 16) & 0o170000) in (0, 0o100000),
                    "nonregular, compressed or oversized source archive entry")
            total += info.file_size
            require(total <= MAX_TOTAL_SIZE, "zip extraction byte cap exceeded")
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            count = 0
            with z.open(info) as src, path.open("wb") as dst:
                while True:
                    block = src.read(1024 * 1024)
                    if not block:
                        break
                    count += len(block)
                    require(count <= MAX_FILE_SIZE, "source stream exceeded cap")
                    h.update(block)
                    dst.write(block)
            require(count == approved[name]["byte_length"]
                    and h.hexdigest() == approved[name]["sha256"],
                    "original archive source byte digest mismatch")
        rechecked = validate_tree(root)
        require(rechecked == index["validated_original_source_result"],
                "archived manufacturer semantic evidence drift")
    return {
        "schema_version": VERSION,
        "bundle_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "source_file_count": len(recorded),
        "source_originals_sha256_replayed": True,
        "original_mcp_dual_pagination_replayed": True,
        "source_to_phase1_chart_report_replayed": True,
        "validated_original_source_result": rechecked,
        "offline_bundle_verification": "PASS",
        "durable_storage_verified": False,
        "independent_offsite_copy_verified": False,
        "source_authenticity_signature_verified": False,
        "production_write_authorized": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pack", type=Path, metavar="ARCHIVE")
    mode.add_argument("--verify", type=Path, metavar="ARCHIVE")
    p.add_argument("--chart-root", type=Path)
    p.add_argument("--e5-root", type=Path)
    p.add_argument("--pic32-root", type=Path)
    p.add_argument("--plan", type=Path)
    p.add_argument("--report", type=Path)
    p.add_argument("--receipt", type=Path)
    args = p.parse_args()
    if args.pack:
        require(all((args.chart_root, args.e5_root, args.pic32_root,
                     args.plan, args.report)), "all original input sources required")
        receipt = pack({
            "chart": args.chart_root, "mcp-e5": args.e5_root,
            "mcp-pic32": args.pic32_root, "plan": args.plan, "report": args.report,
        }, args.pack)
    else:
        receipt = verify(args.verify)
    if args.receipt:
        require("production" not in {x.lower() for x in args.receipt.resolve().parts},
                "Production receipt destination forbidden")
        require(not args.receipt.exists(), "receipt already exists")
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n",
                                encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
