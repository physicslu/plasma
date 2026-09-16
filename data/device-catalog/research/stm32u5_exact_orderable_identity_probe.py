#!/usr/bin/env python3
"""Bounded STM32U5 exact orderable identity acquisition from official ST pages.

Quality & Reliability is exact Part Number identity authority. Sample & Buy is
Marketing Status authority. The two exact Part Number sets must join exactly.
No ordering suffix or commercial identity is synthesized by Plasma.

This is a temporary research/live-acquisition tool. Its output must be frozen
into repository evidence and validated offline before this gate can become
merge-ready.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
from collections import Counter
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from st_dual_surface_browser_acquisition import STDualSurfaceBrowserAcquirer
from st_dual_surface_evidence import build_dual_surface_browser_evidence_record
from st_product_page_acquisition import AcquisitionError, validate_source_url

HERE = Path(__file__).resolve().parent
BASE_CSV = HERE / "stm32u5-base-device-discovery.csv"
EXPECTED_BASE_DEVICES = 74
MIN_DELAY_SECONDS = 1.0
PARSER_PROFILE = "stm32u5_exact_orderable_identity_v1"
AUTHORITY = "official_st_quality_and_reliability_identity_plus_sample_and_buy_lifecycle_exact_set_join"
OBSERVATION_SCOPE = "official_st_dual_surface_exact_part_number_observation"


def _playwright_version() -> str:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return "unknown"


def _set_sha(values: set[str]) -> str:
    canonical = "\n".join(sorted(values)) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _read_bases() -> list[dict[str, str]]:
    with BASE_CSV.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != EXPECTED_BASE_DEVICES:
        raise AcquisitionError(
            f"expected {EXPECTED_BASE_DEVICES} Base Devices, got {len(rows)}"
        )

    seen: set[str] = set()
    for row in rows:
        base = row.get("base_device", "").strip().upper()
        subfamily = row.get("subfamily", "").strip().upper()
        url = row.get("manufacturer_url", "").strip()
        if not base or not subfamily or not url:
            raise AcquisitionError("STM32U5 Base Device discovery row is incomplete")
        if base in seen:
            raise AcquisitionError(f"duplicate STM32U5 Base Device: {base}")
        if not base.startswith(subfamily):
            raise AcquisitionError(f"{base}: subfamily mismatch ({subfamily})")
        validate_source_url(url)
        seen.add(base)
        row["base_device"] = base
        row["subfamily"] = subfamily
        row["manufacturer_url"] = url
    return rows


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = [
        "exact_icpn",
        "base_device",
        "subfamily",
        "marketing_status_observed",
        "active_observed",
        "manufacturer_url",
        "final_url",
        "observation_scope",
        "retrieved_at_utc",
        "rendered_dom_sha256",
        "evidence_section_sha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda item: str(item["exact_icpn"])))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive")
    if args.delay < MIN_DELAY_SECONDS:
        raise SystemExit(f"--delay must be at least {MIN_DELAY_SECONDS:.1f}s")

    bases = _read_bases()
    base_by_url = {row["manufacturer_url"]: row["base_device"] for row in bases}
    if len(base_by_url) != EXPECTED_BASE_DEVICES:
        raise SystemExit("STM32U5 manufacturer URL set is not one-to-one with Base Devices")

    exact_rows: list[dict[str, object]] = []
    evidence_records: list[dict[str, object]] = []
    failures: list[dict[str, str]] = []
    per_base: dict[str, int] = {}
    status_counts: Counter[str] = Counter()
    owners: dict[str, str] = {}
    duplicate_exact: set[str] = set()

    with STDualSurfaceBrowserAcquirer(
        base_by_url=base_by_url,
        family_label="STM32U5 exact orderable identity enumeration",
        headless=args.headless,
        reuse_browser=True,
        global_deadline=True,
    ) as acquirer:
        for index, row in enumerate(bases, start=1):
            if index > 1:
                time.sleep(args.delay)
            base = row["base_device"]
            subfamily = row["subfamily"]
            source_url = row["manufacturer_url"]
            print(f"[{index:02d}/{EXPECTED_BASE_DEVICES}] {base}: acquiring", flush=True)
            try:
                body, final_url, etag, last_modified = acquirer.fetch(
                    source_url, args.timeout
                )
                retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                evidence = build_dual_surface_browser_evidence_record(
                    body=body,
                    source_url=source_url,
                    final_url=final_url,
                    base_device=base,
                    retrieved_at_utc=retrieved_at,
                    parser_profile=PARSER_PROFILE,
                    http_etag=etag,
                    http_last_modified=last_modified,
                )
                records = evidence.get("part_number_records")
                if not isinstance(records, list) or not records:
                    raise AcquisitionError(f"{base}: no exact Part Number records")

                per_base[base] = len(records)
                for record in records:
                    if not isinstance(record, dict):
                        raise AcquisitionError(f"{base}: invalid Part Number record")
                    icpn = record.get("icpn")
                    status = record.get("marketing_status")
                    active = record.get("active")
                    if not isinstance(icpn, str) or not icpn.startswith(base):
                        raise AcquisitionError(f"{base}: invalid/foreign exact Part Number")
                    if not isinstance(status, str) or not status.strip():
                        raise AcquisitionError(f"{icpn}: missing observed Marketing Status")
                    if not isinstance(active, bool):
                        raise AcquisitionError(f"{icpn}: invalid active observation")
                    prior = owners.setdefault(icpn, base)
                    if prior != base:
                        duplicate_exact.add(icpn)
                    status_counts[status] += 1
                    exact_rows.append(
                        {
                            "exact_icpn": icpn,
                            "base_device": base,
                            "subfamily": subfamily,
                            "marketing_status_observed": status,
                            "active_observed": active,
                            "manufacturer_url": source_url,
                            "final_url": final_url,
                            "observation_scope": OBSERVATION_SCOPE,
                            "retrieved_at_utc": retrieved_at,
                            "rendered_dom_sha256": evidence["rendered_dom_sha256"],
                            "evidence_section_sha256": evidence["evidence_section_sha256"],
                        }
                    )

                evidence_records.append(
                    {
                        "subfamily": subfamily,
                        "base_device": base,
                        "evidence": evidence,
                    }
                )
                if args.evidence_dir is not None:
                    _write_json(
                        args.evidence_dir / f"{base.lower()}.json",
                        evidence_records[-1],
                    )
                print(f"[{index:02d}/{EXPECTED_BASE_DEVICES}] {base}: {len(records)} exact Part Numbers", flush=True)
            except (AcquisitionError, OSError) as exc:
                failures.append(
                    {
                        "base_device": base,
                        "subfamily": subfamily,
                        "manufacturer_url": source_url,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
                print(
                    f"[{index:02d}/{EXPECTED_BASE_DEVICES}] {base}: acquisition failure: {exc}",
                    flush=True,
                )

        browser = {
            "headless": args.headless,
            "browser_version": acquirer.browser_version,
            "playwright_version": _playwright_version(),
            "reuse_browser": acquirer.reuse_browser,
            "per_device_global_deadline": acquirer.global_deadline,
            "per_device_timeout_seconds": args.timeout,
            "inter_device_delay_seconds": args.delay,
        }

    identities = set(owners)
    complete = (
        len(per_base) == EXPECTED_BASE_DEVICES
        and not failures
        and not duplicate_exact
        and len(exact_rows) == len(identities)
        and all(per_base.get(row["base_device"], 0) > 0 for row in bases)
    )

    _write_csv(args.output_csv, exact_rows)
    summary: dict[str, object] = {
        "schema_version": 1,
        "transaction": "stm32u5-exact-orderable-identity-enumeration",
        "authority": AUTHORITY,
        "acquisition_transport": BROWSER_TRANSPORT,
        "parser_profile": PARSER_PROFILE,
        "observed_base_devices": EXPECTED_BASE_DEVICES,
        "successful_base_devices": len(per_base),
        "base_devices_with_exact_identity": len(per_base),
        "acquisition_failures": len(failures),
        "exact_icpn_count": len(identities),
        "exact_icpn_set_sha256": _set_sha(identities),
        "marketing_status_counts": dict(sorted(status_counts.items())),
        "per_base_counts": dict(sorted(per_base.items())),
        "duplicate_exact_icpns": sorted(duplicate_exact),
        "failures": failures,
        "synthesized_exact_icpns": 0,
        "complete_exact_identity_observation": complete,
        "browser": browser,
        "claims": {
            "catalog_admission_authorized": False,
            "physical_validation_claimed": False,
            "runtime_programming_support_claimed": False,
            "security_mutation_support_claimed": False,
            "debug_attach_support_claimed": False,
        },
    }
    _write_json(args.output_json, summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
