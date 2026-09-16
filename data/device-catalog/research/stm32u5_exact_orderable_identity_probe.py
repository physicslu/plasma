#!/usr/bin/env python3
"""Bounded STM32U5 exact orderable identity acquisition from official ST pages.

The admission question in this gate is exact commercial identity, not lifecycle
qualification. ST Quality & Reliability is therefore the authority surface for
exact Part Number identity. The first pass additionally required a Sample & Buy
exact-set join for 63 Base Devices; those stronger observations are retained as a
frozen seed. Retry acquisition is limited to the 11 unresolved Base Devices and
uses the Q&R authority surface directly.

No ordering suffix or commercial identity is synthesized by Plasma. Output from
live acquisition must be frozen and validated offline before Gate 2.
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

from st_browser_acquisition import (
    BROWSER_TRANSPORT,
    STBrowserAcquirer,
    build_browser_evidence_record,
)
from st_product_page_acquisition import AcquisitionError, validate_source_url

HERE = Path(__file__).resolve().parent
BASE_CSV = HERE / "stm32u5-base-device-discovery.csv"
DEFAULT_SEED = HERE / "stm32u5-exact-orderable-first-pass-seed.json"
EXPECTED_BASE_DEVICES = 74
EXPECTED_FIRST_PASS_SUCCESSES = 63
EXPECTED_RETRY_BASE_DEVICES = 11
MIN_DELAY_SECONDS = 1.0
PARSER_PROFILE = "stm32u5_exact_orderable_identity_qr_v1"
AUTHORITY = "official_st_quality_and_reliability_exact_part_number_identity"
OBSERVATION_SCOPE = "official_st_quality_and_reliability_exact_part_number_observation"
FIRST_PASS_TRANSACTION = "stm32u5-exact-orderable-first-pass-seed"
FIRST_PASS_RUN_ID = 35041196885
FIRST_PASS_ARTIFACT_ID = 10426086086
FIRST_PASS_ARTIFACT_SHA256 = "92dd546e14da115aab06abfe403b58bf53123f4af2158c9388a3b8a6494d31a2"

OUTPUT_COLUMNS = [
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda item: str(item["exact_icpn"])))


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _seed_rows(
    seed_path: Path,
    base_by_name: dict[str, dict[str, str]],
) -> tuple[list[dict[str, object]], set[str], dict[str, int], Counter[str], set[str], dict[str, object]]:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    if not isinstance(seed, dict) or seed.get("transaction") != FIRST_PASS_TRANSACTION:
        raise AcquisitionError("unexpected STM32U5 first-pass seed transaction")
    source = seed.get("source")
    if source != [
        FIRST_PASS_RUN_ID,
        FIRST_PASS_ARTIFACT_ID,
        FIRST_PASS_ARTIFACT_SHA256,
        "d25c4337a0ef7a16bd7c2e69b1ffee673b181d99",
    ]:
        raise AcquisitionError("STM32U5 first-pass seed provenance drifted")
    if seed.get("successful_base_devices") != EXPECTED_FIRST_PASS_SUCCESSES:
        raise AcquisitionError("STM32U5 first-pass successful Base Device count drifted")
    if seed.get("exact_icpn_count") != 211 or seed.get("synthesized_exact_icpns") != 0:
        raise AcquisitionError("STM32U5 first-pass exact identity boundary drifted")

    retry_bases = seed.get("failed_base_devices")
    if not isinstance(retry_bases, list) or len(retry_bases) != EXPECTED_RETRY_BASE_DEVICES:
        raise AcquisitionError("STM32U5 first-pass retry set drifted")
    retry_set = set(retry_bases)
    if len(retry_set) != EXPECTED_RETRY_BASE_DEVICES or not retry_set.issubset(base_by_name):
        raise AcquisitionError("STM32U5 first-pass retry Base Device set invalid")

    evidence = seed.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != EXPECTED_FIRST_PASS_SUCCESSES:
        raise AcquisitionError("STM32U5 first-pass evidence count drifted")

    rows: list[dict[str, object]] = []
    owners: set[str] = set()
    per_base: dict[str, int] = {}
    status_counts: Counter[str] = Counter()
    seeded_bases: set[str] = set()
    for item in evidence:
        if not isinstance(item, list) or len(item) != 3:
            raise AcquisitionError("STM32U5 first-pass evidence row shape drifted")
        base, subfamily, records = item
        if not isinstance(base, str) or not isinstance(subfamily, str) or not isinstance(records, list):
            raise AcquisitionError("STM32U5 first-pass evidence row type drifted")
        source_row = base_by_name.get(base)
        if source_row is None or source_row["subfamily"] != subfamily or base in retry_set:
            raise AcquisitionError(f"{base}: invalid first-pass seed Base Device")
        if base in seeded_bases or not records:
            raise AcquisitionError(f"{base}: duplicate/empty first-pass seed evidence")
        seeded_bases.add(base)
        per_base[base] = len(records)
        source_url = source_row["manufacturer_url"]

        for record in records:
            if not isinstance(record, list) or len(record) != 3:
                raise AcquisitionError(f"{base}: invalid first-pass Part Number record")
            icpn, status, active_int = record
            if (
                not isinstance(icpn, str)
                or not icpn.startswith(base)
                or not isinstance(status, str)
                or not status.strip()
                or active_int not in (0, 1)
            ):
                raise AcquisitionError(f"{base}: malformed first-pass Part Number record")
            if icpn in owners:
                raise AcquisitionError(f"{icpn}: duplicate exact ICPN in first-pass seed")
            owners.add(icpn)
            status_counts[status] += 1
            rows.append(
                {
                    "exact_icpn": icpn,
                    "base_device": base,
                    "subfamily": subfamily,
                    "marketing_status_observed": status,
                    "active_observed": bool(active_int),
                    "manufacturer_url": source_url,
                    "final_url": source_url,
                    "observation_scope": "frozen_first_pass_dual_surface_exact_identity",
                    "retrieved_at_utc": "2026-09-16T00:00:00Z",
                    "rendered_dom_sha256": "retained_in_source_artifact",
                    "evidence_section_sha256": "retained_in_source_artifact",
                }
            )

    expected_seeded = set(base_by_name) - retry_set
    if seeded_bases != expected_seeded:
        raise AcquisitionError("STM32U5 first-pass seeded Base Device set drifted")
    if len(owners) != 211 or _set_sha(owners) != seed.get("exact_icpn_set_sha256"):
        raise AcquisitionError("STM32U5 first-pass exact ICPN digest drifted")
    return rows, owners, per_base, status_counts, retry_set, seed


def _append_live_records(
    *,
    base: str,
    subfamily: str,
    source_url: str,
    evidence: dict[str, object],
    exact_rows: list[dict[str, object]],
    owners: set[str],
    per_base: dict[str, int],
    status_counts: Counter[str],
) -> None:
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
        if icpn in owners:
            raise AcquisitionError(f"{icpn}: duplicate exact identity across seed/retry")
        owners.add(icpn)
        status_counts[status] += 1
        exact_rows.append(
            {
                "exact_icpn": icpn,
                "base_device": base,
                "subfamily": subfamily,
                "marketing_status_observed": status,
                "active_observed": active,
                "manufacturer_url": source_url,
                "final_url": evidence["final_url"],
                "observation_scope": OBSERVATION_SCOPE,
                "retrieved_at_utc": evidence["retrieved_at_utc"],
                "rendered_dom_sha256": evidence["rendered_dom_sha256"],
                "evidence_section_sha256": evidence["evidence_section_sha256"],
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive")
    if args.delay < MIN_DELAY_SECONDS:
        raise SystemExit(f"--delay must be at least {MIN_DELAY_SECONDS:.1f}s")

    bases = _read_bases()
    base_by_name = {row["base_device"]: row for row in bases}
    if len(base_by_name) != EXPECTED_BASE_DEVICES:
        raise SystemExit("STM32U5 Base Device set is not unique")

    exact_rows, owners, per_base, status_counts, retry_set, seed = _seed_rows(
        args.seed, base_by_name
    )
    retry_rows = [row for row in bases if row["base_device"] in retry_set]
    if len(retry_rows) != EXPECTED_RETRY_BASE_DEVICES:
        raise SystemExit("STM32U5 retry target set count drifted")

    failures: list[dict[str, str]] = []
    evidence_records: list[dict[str, object]] = []
    with STBrowserAcquirer(headless=args.headless, navigation_attempts=2) as acquirer:
        for index, row in enumerate(retry_rows, start=1):
            if index > 1:
                time.sleep(args.delay)
            base = row["base_device"]
            subfamily = row["subfamily"]
            source_url = row["manufacturer_url"]
            print(f"[{index:02d}/{EXPECTED_RETRY_BASE_DEVICES}] {base}: retrying Q&R identity", flush=True)
            try:
                body, final_url, etag, last_modified = acquirer.fetch(source_url, args.timeout)
                retrieved_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                evidence = build_browser_evidence_record(
                    body=body,
                    source_url=source_url,
                    final_url=final_url,
                    base_device=base,
                    retrieved_at_utc=retrieved_at,
                    http_etag=etag,
                    http_last_modified=last_modified,
                )
                _append_live_records(
                    base=base,
                    subfamily=subfamily,
                    source_url=source_url,
                    evidence=evidence,
                    exact_rows=exact_rows,
                    owners=owners,
                    per_base=per_base,
                    status_counts=status_counts,
                )
                evidence_records.append({"subfamily": subfamily, "base_device": base, "evidence": evidence})
                if args.evidence_dir is not None:
                    _write_json(args.evidence_dir / f"{base.lower()}.json", evidence_records[-1])
                print(
                    f"[{index:02d}/{EXPECTED_RETRY_BASE_DEVICES}] {base}: {per_base[base]} exact Part Numbers",
                    flush=True,
                )
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
                    f"[{index:02d}/{EXPECTED_RETRY_BASE_DEVICES}] {base}: retry failure: {exc}",
                    flush=True,
                )

        browser = {
            "headless": args.headless,
            "browser_version": acquirer.browser_version,
            "playwright_version": _playwright_version(),
            "per_device_timeout_seconds": args.timeout,
            "inter_device_delay_seconds": args.delay,
            "navigation_attempts": acquirer.navigation_attempts,
            "fresh_browser_per_retry_target": True,
        }

    complete = (
        len(per_base) == EXPECTED_BASE_DEVICES
        and not failures
        and len(exact_rows) == len(owners)
        and all(per_base.get(row["base_device"], 0) > 0 for row in bases)
    )
    _write_csv(args.output_csv, exact_rows)
    summary: dict[str, object] = {
        "schema_version": 1,
        "transaction": "stm32u5-exact-orderable-identity-enumeration",
        "authority": AUTHORITY,
        "identity_scope": "all Quality & Reliability exact Part Number rows regardless of lifecycle status",
        "acquisition_transport": BROWSER_TRANSPORT,
        "parser_profile": PARSER_PROFILE,
        "first_pass_seed": {
            "path": str(args.seed),
            "run_id": FIRST_PASS_RUN_ID,
            "artifact_id": FIRST_PASS_ARTIFACT_ID,
            "artifact_sha256": FIRST_PASS_ARTIFACT_SHA256,
            "successful_base_devices": seed["successful_base_devices"],
            "exact_icpn_count": seed["exact_icpn_count"],
        },
        "retry_base_devices": sorted(retry_set),
        "retry_base_device_count": len(retry_set),
        "observed_base_devices": EXPECTED_BASE_DEVICES,
        "successful_base_devices": len(per_base),
        "base_devices_with_exact_identity": len(per_base),
        "acquisition_failures": len(failures),
        "exact_icpn_count": len(owners),
        "exact_icpn_set_sha256": _set_sha(owners),
        "marketing_status_counts": dict(sorted(status_counts.items())),
        "per_base_counts": dict(sorted(per_base.items())),
        "duplicate_exact_icpns": [],
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
