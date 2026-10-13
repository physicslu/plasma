#!/usr/bin/env python3
"""Fail-closed, research-only Microchip segment coverage reconciliation.

No live scraping, no Production mutation, and no inferred vendor-wide coverage.
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
REGISTRY = HERE / "microchip-bulk-source-registry-v1.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
SOURCE_STATES = {
    "Active", "In Production", "NRND", "Not Recommended for New Designs",
    "Obsolete", "Discontinued", "Preproduction", "Qualification", "Unknown",
}
SOURCE_STATE_KEYS = {state.casefold() for state in SOURCE_STATES}
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
    payload = "".join(value + "\n" for value in sorted(values))
    return hashlib.sha256(payload.encode()).hexdigest()


def official_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname in {"microchip.com", "www.microchip.com"}


def canonical_lifecycle(source_state: str) -> str:
    """Map Microchip's official product-page status into the catalog vocabulary."""
    normalized = source_state.strip().casefold()
    if normalized in {"active", "in production"}:
        return "Active"
    if normalized in {"nrnd", "not recommended for new designs"}:
        return "NRND"
    return {
        "obsolete": "Obsolete",
        "discontinued": "Discontinued",
        "preproduction": "Preproduction",
        "qualification": "Qualification",
        "unknown": "Unknown",
    }.get(normalized, "")



def verify_source_bytes(root: Path, filename: str, expected_sha256: str) -> None:
    """Verify actual local source bytes, not merely a 64-character digest field."""
    require(isinstance(filename, str) and filename not in (".", "..") and
            Path(filename).name == filename and "/" not in filename and
            "\\\\" not in filename, "invalid evidence capture filename")
    require(isinstance(expected_sha256, str) and bool(DIGEST.fullmatch(expected_sha256)),
            "missing source bytes digest")
    evidence = root / filename
    require(evidence.is_file() and not evidence.is_symlink(),
            "missing or symlinked source capture")
    hasher = hashlib.sha256()
    nbytes = 0
    with evidence.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            nbytes += len(chunk)
            hasher.update(chunk)
    require(nbytes > 0 and hasher.hexdigest() == expected_sha256,
            "source capture digest mismatch")


def production_microchip() -> set[str]:
    manifest = read_json(PRODUCTION)
    found: set[str] = set()
    for source in manifest.get("sources", []):
        if source.get("manufacturer", "").casefold() != "microchip":
            continue
        path = (PRODUCTION.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as handle:
            rows = csv.DictReader(handle)
            for row in rows:
                part = row.get("icpn") or row.get("manufacturer_part_number") or ""
                if part:
                    found.add(part)
    return found


def summarize(evidence_root: Path | None = None) -> dict:
    registry = read_json(REGISTRY)
    require(registry.get("schema_version") == 1 and registry.get("manufacturer") == "Microchip",
            "registry identity")
    require(registry.get("population_boundary_validated") is False and
            registry.get("production_write_authorized") is False and
            registry.get("global_active_denominator") is None,
            "unreviewed global coverage or publication claim")
    segments = registry.get("segments", [])
    ids = [segment.get("id") for segment in segments]
    require(len(ids) == len(set(ids)) and len(ids) == 5, "segment IDs must be five unique lanes")
    for segment in segments:
        require(official_url(segment.get("index_url", "")), "untrusted Microchip index URL")
        require(segment.get("population_complete") is False, "registry completeness must remain unproven")

    production = production_microchip()
    found: dict[str, str] = {}
    lane_reports = []
    if evidence_root:
        for segment in segments:
            path = evidence_root / f"{segment['id']}.json"
            if not path.exists():
                lane_reports.append({"segment": segment["id"], "state": "no_snapshot",
                                     "exact_rows": 0, "complete": False})
                continue
            snapshot = read_json(path)
            require(snapshot.get("manufacturer") == "Microchip", "snapshot manufacturer mismatch")
            require(snapshot.get("segment") == segment["id"], "snapshot segment mismatch")
            require(official_url(snapshot.get("source_url", "")), "snapshot source is not Microchip")
            rows = snapshot.get("rows")
            require(isinstance(rows, list), "snapshot rows must be a list")
            complete = snapshot.get("source_population_complete") is True
            if complete:
                require(snapshot.get("official_count") == len(rows),
                        "complete snapshot requires matching official count")
                verify_source_bytes(evidence_root, snapshot.get("source_capture_file"),
                                    snapshot.get("source_content_sha256"))
            lane_seen: set[str] = set()
            for row in rows:
                part, raw_state = row.get("icpn", ""), row.get("lifecycle", "")
                require(bool(PART.fullmatch(part)), "invalid exact Microchip ordering code")
                state = canonical_lifecycle(raw_state)
                require(raw_state.strip().casefold() in SOURCE_STATE_KEYS and state,
                        "unreviewed lifecycle token")
                require(part not in lane_seen, "duplicate exact part within segment")
                require(bool(DIGEST.fullmatch(row.get("evidence_sha256", ""))),
                        "manufacturer row evidence missing")
                if complete:
                    verify_source_bytes(evidence_root, row.get("evidence_file"),
                                        row.get("evidence_sha256"))
                require(official_url(row.get("source_url", "")), "row evidence is not Microchip")
                lane_seen.add(part)
                prior = found.get(part)
                require(prior is None or prior == state,
                        "conflicting Microchip lifecycle across segments")
                found[part] = state
            lane_reports.append({"segment": segment["id"],
                                 "state": "bytes_verified_scope_unreviewed" if complete else "partial_snapshot",
                                 "exact_rows": len(rows), "complete": complete})

    active = {part for part, state in found.items() if state == "Active"}
    unknown = {part for part, state in found.items() if state == "Unknown"}
    boundary_valid = registry.get("population_boundary_validated") is True
    complete = boundary_valid and len(lane_reports) == len(segments) and all(
        lane["complete"] for lane in lane_reports
    )
    return {
        "schema_version": 1,
        "manufacturer": "Microchip",
        "status": "full_population_verified" if complete else "partial_research_inventory",
        "observed_unique_exact": len(found),
        "observed_active_exact": len(active),
        "observed_unknown_lifecycle_exact": len(unknown),
        "observed_active_exact_set_sha256": digest_set(active),
        "production_microchip_exact": len(production),
        "active_missing_from_production": len(active - production),
        "complete_global_active_denominator": len(active) if complete else None,
        "global_active_identity_coverage": (
            len(active & production) / len(active) if complete and active else None
        ),
        "segments": lane_reports or [
            {"segment": segment["id"], "state": "not_acquired", "exact_rows": 0, "complete": False}
            for segment in segments
        ],
        "claims": {
            "production_write_authorized": False,
            "runtime_programming_support_claimed": False,
            "physical_validation_claimed": False,
            "openocd_or_cmsis_is_lifecycle_authority": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(summarize(args.evidence_root), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
