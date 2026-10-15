#!/usr/bin/env python3
"""ADR-0002 Phase 1 ST IC Information field-level baseline.

This module projects the already-admitted ST exact ICPN Production identity rows and
existing ST Manufacturer Device Basic profiles into the ADR-0002 Phase 1 contract.

It intentionally does NOT:
- promote Production identity,
- infer missing RAM/VDD from family names,
- read OpenOCD/programming/HIL evidence,
- create Programming Profile or VPP claims,
- treat the legacy all-or-nothing M1 blocker as a Phase 1 field blocker.

Unknown fields remain UNKNOWN until a manufacturer Phase 1 source is admitted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data" / "device-catalog" / "production" / "icpn-v1-manifest.json"
DEVICE_BASIC_ROOT = ROOT / "data" / "ic-support" / "device-basic"
LEGACY_M1_LEDGER = DEVICE_BASIC_ROOT / "st-m1-remaining-enrichment-v1.json"

PHASE = "IC_INFORMATION"
ADR = "ADR-0002"
MANUFACTURER = "STMicroelectronics"
STATES = ("VERIFIED", "PARTIAL", "UNKNOWN", "CONFLICT")
FIELDS = (
    "manufacturer",
    "icpn",
    "base_device",
    "package",
    "pin_count",
    "flash",
    "ram",
    "working_vdd",
    "io_supply",
    "vdda",
    "temperature",
)


class Phase1Error(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Phase1Error(message)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(payload, dict), f"{path}: top-level JSON object required")
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evidence(
    *,
    value: Any,
    state: str,
    source_scope: str,
    source_authority: str | None,
    source_locator: str | None,
    source_file: str | None,
    source_sha256: str | None,
    source_surface: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    require(state in STATES, f"invalid evidence state: {state}")
    result = {
        "value": value,
        "state": state,
        "source_scope": source_scope,
        "source_authority": source_authority,
        "source_locator": source_locator,
        "source_file": source_file,
        "source_sha256": source_sha256,
    }
    if source_surface is not None:
        result["source_surface"] = source_surface
    if note is not None:
        result["note"] = note
    return result


def unknown(note: str) -> dict[str, Any]:
    return evidence(
        value=None,
        state="UNKNOWN",
        source_scope="none",
        source_authority=None,
        source_locator=None,
        source_file=None,
        source_sha256=None,
        note=note,
    )


def load_production_st_rows() -> list[dict[str, Any]]:
    manifest = load_json(MANIFEST)
    require(manifest.get("status") == "production", "Production manifest status drift")
    require(
        manifest.get("selection_policy") == "admitted_exact_manufacturer_part_number_only",
        "Production selection policy drift",
    )

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in manifest.get("sources", []):
        if source.get("manufacturer") != MANUFACTURER:
            continue
        rel = source.get("path")
        require(isinstance(rel, str) and rel, "ST manifest source path missing")
        path = (MANIFEST.parent / rel).resolve()
        require(path.is_file(), f"missing ST Production source: {rel}")
        require(
            sha256_file(path) == source.get("sha256"),
            f"ST Production source SHA-256 drift: {rel}",
        )

        with path.open("r", encoding="utf-8", newline="") as handle:
            source_rows = list(csv.DictReader(handle))
        require(
            len(source_rows) == source.get("row_count"),
            f"ST Production row_count drift: {rel}",
        )

        source_file = str(path.relative_to(ROOT))
        for row in source_rows:
            require(row.get("manufacturer") == MANUFACTURER, f"{source_file}: vendor drift")
            icpn = (row.get("icpn") or "").strip()
            require(icpn and icpn not in seen, f"duplicate/empty ST exact ICPN: {icpn!r}")
            seen.add(icpn)
            copy = dict(row)
            copy["_catalog_source_file"] = source_file
            copy["_catalog_source_sha256"] = source["sha256"]
            rows.append(copy)

    rows.sort(key=lambda row: row["icpn"])
    require(len(rows) == 4629, f"ST Production denominator drift: {len(rows)}")
    return rows


def load_basic_bindings() -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for path in sorted(DEVICE_BASIC_ROOT.glob("*-device-basic-v1.json")):
        payload = load_json(path)
        if payload.get("manufacturer") != MANUFACTURER:
            continue
        groups = payload.get("groups")
        exact = payload.get("bindings")
        require(isinstance(groups, dict) and isinstance(exact, dict), f"{path}: malformed profile")
        profile_sha256 = sha256_file(path)
        for icpn, group_id in exact.items():
            require(icpn not in bindings, f"duplicate ST basic binding: {icpn}")
            group = groups.get(group_id)
            require(isinstance(group, dict), f"{path}: dangling group {group_id}")
            ev = group.get("evidence")
            require(isinstance(ev, dict), f"{path}: missing evidence for {group_id}")
            require(
                ev.get("authority") == "STMicroelectronics official",
                f"{path}: non-ST evidence authority",
            )
            bindings[icpn] = {
                "profile_id": payload.get("profile_id"),
                "profile_file": str(path.relative_to(ROOT)),
                "profile_sha256": profile_sha256,
                "group_id": group_id,
                "group": group,
                "evidence": ev,
            }
    require(len(bindings) == 1622, f"existing ST Basic Profile denominator drift: {len(bindings)}")
    return bindings


def load_legacy_family_context() -> dict[str, dict[str, Any]]:
    ledger = load_json(LEGACY_M1_LEDGER)
    require(ledger.get("status") == "completed", "legacy ST M1 ledger status drift")
    families = ledger.get("families")
    require(isinstance(families, dict), "legacy ST M1 family ledger missing")
    return families


def catalog_field(row: dict[str, Any], key: str, *, output_name: str | None = None) -> dict[str, Any]:
    value = row.get(key)
    require(value not in (None, ""), f"{row.get('icpn')}: missing Production field {key}")
    authority = row.get("source_authority")
    state = "VERIFIED" if authority == "STMicroelectronics official" else "PARTIAL"
    return evidence(
        value=value,
        state=state,
        source_scope="exact_icpn_production_identity",
        source_authority=authority or None,
        source_locator=row.get("source_reference") or None,
        source_file=row["_catalog_source_file"],
        source_sha256=row["_catalog_source_sha256"],
        source_surface=row.get("source_type") or None,
        note=None if output_name is None else f"Production field {key} projected as {output_name}",
    )


def profile_field(binding: dict[str, Any], key: str, *, value_key: str | None = None) -> dict[str, Any]:
    group = binding["group"]
    actual_key = value_key or key
    value = group.get(actual_key)
    ev = binding["evidence"]
    if value is None:
        return unknown(
            f"{key} has no admitted direct value in existing manufacturer evidence; "
            "ADR-0002 Phase 1 keeps the field UNKNOWN rather than copying another rail."
        )
    return evidence(
        value=value,
        state="VERIFIED",
        source_scope="explicit_exact_icpn_binding_to_reusable_manufacturer_group",
        source_authority=ev.get("authority"),
        source_locator=ev.get("selector_url"),
        source_file=binding["profile_file"],
        source_sha256=binding["profile_sha256"],
        source_surface=ev.get("source_surface"),
        note=f"Existing source-backed group {binding['group_id']} projected field-by-field; "
        "this does not grant Programming or hardware authority.",
    )


def build() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = load_production_st_rows()
    bindings = load_basic_bindings()
    legacy = load_legacy_family_context()

    records: list[dict[str, Any]] = []
    coverage = {field: Counter() for field in FIELDS}
    by_family: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: {field: Counter() for field in FIELDS}
    )

    for row in rows:
        icpn = row["icpn"]
        family = row["family"]
        binding = bindings.get(icpn)
        legacy_context = legacy.get(family)

        fields: dict[str, dict[str, Any]] = {
            "manufacturer": evidence(
                value=MANUFACTURER,
                state="VERIFIED",
                source_scope="exact_icpn_production_identity",
                source_authority=row.get("source_authority") or None,
                source_locator=row.get("source_reference") or None,
                source_file=row["_catalog_source_file"],
                source_sha256=row["_catalog_source_sha256"],
                source_surface=row.get("source_type") or None,
            ),
            "icpn": evidence(
                value=icpn,
                state="VERIFIED",
                source_scope="exact_icpn_production_identity",
                source_authority=row.get("source_authority") or None,
                source_locator=row.get("source_reference") or None,
                source_file=row["_catalog_source_file"],
                source_sha256=row["_catalog_source_sha256"],
                source_surface=row.get("source_type") or None,
            ),
            "base_device": catalog_field(row, "base_device"),
            "package": catalog_field(row, "package"),
            "pin_count": catalog_field(row, "pin_count"),
            "flash": catalog_field(row, "flash_size", output_name="flash"),
            # ADR-0002 explicitly permits preserving conditional/original temperature text.
            "temperature": catalog_field(row, "temperature_grade", output_name="temperature"),
        }

        if binding is None:
            fields["ram"] = unknown(
                "No field-level RAM value has yet been admitted into the ADR-0002 ST Phase 1 "
                "projection. Legacy M1 family blocking is context, not evidence that RAM is absent."
            )
            fields["working_vdd"] = unknown(
                "No field-level working-VDD value has yet been admitted into the ADR-0002 ST "
                "Phase 1 projection. Official datasheet/product evidence may close this independently."
            )
            fields["io_supply"] = unknown(
                "No independently sourced I/O supply value admitted for this exact ICPN."
            )
            fields["vdda"] = unknown(
                "No independently sourced VDDA value admitted for this exact ICPN."
            )
        else:
            fields["ram"] = profile_field(binding, "ram", value_key="ram_size")
            fields["working_vdd"] = profile_field(
                binding, "working_vdd", value_key="operating_vdd_v"
            )
            fields["io_supply"] = profile_field(
                binding, "io_supply", value_key="io_supply_v"
            )
            fields["vdda"] = profile_field(binding, "vdda", value_key="vdda_v")

        for name, item in fields.items():
            coverage[name][item["state"]] += 1
            by_family[family][name][item["state"]] += 1

        records.append(
            {
                "adr": ADR,
                "phase": PHASE,
                "manufacturer": MANUFACTURER,
                "icpn": icpn,
                "family": family,
                "series": row.get("series") or None,
                "fields": fields,
                "legacy_m1_context": (
                    None
                    if legacy_context is None
                    else {
                        "disposition": legacy_context.get("disposition"),
                        "blocker": legacy_context.get("blocker"),
                        "note": (
                            "Historical all-or-nothing M1 disposition only. ADR-0002 Phase 1 "
                            "uses independent field states and does not inherit this as a field result."
                        ),
                    }
                ),
                "non_claims": {
                    "production_admission_changed": False,
                    "openocd_software_supported": False,
                    "programming_profile_authority": False,
                    "external_vpp_evaluated": False,
                    "hardware_runtime_ready": False,
                    "physical_programming_qualified": False,
                },
            }
        )

    for binding_icpn in bindings:
        require(
            any(record["icpn"] == binding_icpn for record in records),
            f"basic binding outside ST Production: {binding_icpn}",
        )

    summary = {
        "schema_version": 1,
        "adr": ADR,
        "phase": PHASE,
        "manufacturer": MANUFACTURER,
        "scope": "all_current_st_production_exact_icpns",
        "exact_icpn_count": len(records),
        "existing_source_backed_basic_bindings": len(bindings),
        "legacy_m1_blocked_exact_icpns": sum(
            int(item.get("production_exact_icpns", 0))
            for item in legacy.values()
            if item.get("disposition") == "blocked_evidence_gap"
        ),
        "field_coverage": {
            field: {state: coverage[field].get(state, 0) for state in STATES}
            for field in FIELDS
        },
        "family_coverage": {
            family: {
                field: {state: counters[field].get(state, 0) for state in STATES}
                for field in FIELDS
            }
            for family, counters in sorted(by_family.items())
        },
        "interpretation": [
            "Legacy M1 blocked_evidence_gap is not a Phase 1 field state.",
            "Production identity fields are projected from exact admitted ST rows and their pinned source files.",
            "Existing 1,622 Device Basic bindings provide field-level RAM/working-VDD and optional rail evidence.",
            "Unprojected RAM/VDD/rail fields remain UNKNOWN pending permitted manufacturer Phase 1 source acquisition.",
            "External VPP and all programming semantics are Phase 2 and are intentionally absent.",
        ],
    }

    for field in FIELDS:
        require(
            sum(summary["field_coverage"][field].values()) == len(records),
            f"{field}: coverage denominator mismatch",
        )
    require(
        summary["legacy_m1_blocked_exact_icpns"] == 3007,
        "legacy ST M1 blocked denominator drift",
    )
    return records, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    records, summary = build()
    if args.ledger:
        args.ledger.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "adr": ADR,
                    "phase": PHASE,
                    "manufacturer": MANUFACTURER,
                    "records": records,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
    if args.summary:
        args.summary.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    if not args.ledger and not args.summary:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
