#!/usr/bin/env python3
"""ADR-0002 Phase 1: source-locked, chart-scoped Microchip P0 batch research.

P0 is a *research lead* from the pinned OpenOCD source, not software support.
Chart family fields are at most PARTIAL. P1 is deferred; P2 archived cheaply.
Only original manufacturer HTML bytes + pinned sources are processed offline.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from microchip_phase1_chart_html_source_v1 import replay
from microchip_phase1_chart_html_row_probe_v1 import RowProbe
from microchip_phase1_chart_semantics_v1 import HEADERS, LOCK, parse_value
from microchip_phase1_information_v1 import DEFAULT_PATH, check

EXPECTED_OPENOCD_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
REQUIRED_CANARY_BASE = "ATSAMD21G18"
MAX_CHART_ROWS = 5000
NUMERIC_UNITS = {"flash": "KB", "ram": "KB", "vdd": "V",
                 "temperature": "°C", "pin_count": "pins"}
INFO_FIELDS = (*HEADERS.keys(), "io_supply", "vdda")


def require(ok, message):
    if not ok:
        raise ValueError(message)


class ChartRows(RowProbe):
    """Collect raw HTML rows without losing the original row ordinals."""

    def __init__(self):
        super().__init__()
        self.rows = []

    def _finalize(self):
        cells = self.current_cells
        if len(cells) >= len(HEADERS) and not any(c["kind"] == "th" for c in cells):
            require(len(self.rows) < MAX_CHART_ROWS, "chart row cap reached")
            self.rows.append((self.total_rows, [c["text"] for c in cells]))
        super()._finalize()


def chart_name(raw):
    match = re.fullmatch(r"([A-Z0-9_-]{4,80})(?:\s+\[More Info\])?",
                         raw.strip(), flags=re.IGNORECASE)
    return match.group(1).upper() if match else None


def research_lead(base, lock):
    matches = []
    for rank, key in (("P0", "p0_research_leads"), ("P1", "p1_bounded_leads")):
        for lead in lock[key]:
            if re.match(lead["matcher"], base):
                matches.append((rank, lead["id"]))
    require(len(matches) <= 1,
            "ambiguous source-pinned OpenOCD research priority for " + base)
    return matches[0] if matches else ("P2", None)


def evidence_for_field(field, header, raw, row_number, column, sha):
    evidence = {
        "status": "UNKNOWN", "value": None, "original_raw_value": raw,
        "original_header": header, "original_unit": NUMERIC_UNITS.get(field),
        "source_tr_ordinal": row_number, "source_column_number_1based": column,
        "source_original_sha256": sha,
        "evidence_scope": "official_base_device_chart_not_exact_icpn",
    }
    if not raw:
        evidence["gap"] = "BLANK_CHART_CELL"
        return evidence
    try:
        value = parse_value(field, raw)
    except ValueError:
        evidence["gap"] = "UNPARSEABLE_CHART_VALUE"
        return evidence
    evidence.update(status="PARTIAL", value=value)
    return evidence


def build_report(original_root, lock_path=LOCK, pilot_path=DEFAULT_PATH):
    integrity = replay(original_root)  # SHA-256 / allowlisted original bytes
    source_bytes = (Path(original_root) / "original-chart.html").read_bytes()
    probe = ChartRows()
    probe.feed(source_bytes.decode("utf-8", errors="replace"))
    probe.close()

    candidates = [
        h for h in probe.header_samples
        if len(h["headers_observed"]) == len(set(h["headers_observed"]))
        and set(HEADERS.values()) <= set(h["headers_observed"])
    ]
    require(len(candidates) == 1,
            "chart-scoped Phase 1 header row missing or ambiguous")
    header = candidates[0]
    names = header["headers_observed"]
    positions = {key: names.index(value) for key, value in HEADERS.items()}

    lock_bytes = Path(lock_path).read_bytes()
    lock = json.loads(lock_bytes)
    require(lock.get("schema_version") == 2
            and lock.get("manufacturer") == "Microchip"
            and lock.get("policy") == "ADR-0002/Issue-851"
            and lock.get("provider", {}).get("version") == "0.12.0"
            and lock["provider"].get("commit") == EXPECTED_OPENOCD_COMMIT
            and lock.get("p0_source_leads_are_not_software_supported") is True
            and lock.get("production_write_authorized") is False,
            "untrusted research lead lock/Provider pin")

    pilot = json.loads(Path(pilot_path).read_text(encoding="utf-8"))
    check(pilot)
    reviewed_icpns = {}
    for entry in pilot["records"]:
        field = entry["fields"]["base_device"]
        if field["status"] == "VERIFIED":
            reviewed_icpns.setdefault(field["value"].upper(), []).append(entry["icpn"])

    p0 = []
    p1 = []
    p2 = []
    observed = set()
    ignored = 0
    scope_count = Counter()
    coverage = {key: Counter() for key in INFO_FIELDS}
    for row_num, cells in probe.rows:
        if len(cells) != len(names):
            ignored += 1
            continue
        base = chart_name(cells[positions["base_device"]])
        if base is None:
            ignored += 1
            continue
        require(base not in observed, "duplicate chart Base Device " + base)
        observed.add(base)
        priority, lead = research_lead(base, lock)
        scope_count[priority] += 1
        item = {
            "base_device_chart_observation": base,
            "priority": priority, "source_lead_id": lead,
            "source_tr_ordinal": row_num,
            "record_scope": "manufacturer_chart_base_device_research_only",
            "exact_icpn_verified_from_chart": False,
            "internal_admission_state": "NOT_ADMITTED",
            "openocd_software_supported_claimed": False,
        }
        if priority == "P0":
            fields = {}
            for field, header_name in HEADERS.items():
                col = positions[field]
                fields[field] = evidence_for_field(
                    field, header_name, cells[col], row_num, col + 1,
                    integrity["original_byte_sha256"])
            for missing in ("io_supply", "vdda"):
                fields[missing] = {
                    "status": "UNKNOWN", "value": None,
                    "gap": "NO_SEPARATE_SUPPLY_FIELD_IN_CHART",
                    "evidence_scope": "not_observed_in_this_chart",
                }
            for field, value in fields.items():
                coverage[field][value["status"]] += 1
            item["fields_family_scope_only"] = fields
            item["existing_reviewed_mcp_pilot_icpns_not_replayed_here"] = sorted(
                reviewed_icpns.get(base, []))
            p0.append(item)
        elif priority == "P1":
            item["deep_enrichment_deferred"] = True
            p1.append(item)
        else:
            item["archive_only"] = True
            p2.append(item)

    require(REQUIRED_CANARY_BASE in {r["base_device_chart_observation"] for r in p0},
            "previously replayed P0 chart canary Base Device missing")
    require(len(p0) > 0 and sum(scope_count.values()) <= MAX_CHART_ROWS,
            "empty/unbounded chart cohort")
    p0.sort(key=lambda row: (row["source_lead_id"], row["base_device_chart_observation"]))
    p1.sort(key=lambda row: (row["source_lead_id"], row["base_device_chart_observation"]))
    p2.sort(key=lambda row: row["base_device_chart_observation"])
    result = {
        "schema_version": 1,
        "policy": "ADR-0002 Phase 1 - IC Information",
        "manufacturer": "Microchip",
        "chart_scope": "microchipdirect_chart_branchID_21_mid_3_only",
        "source_url": integrity["source_url"],
        "source_original_sha256": integrity["original_byte_sha256"],
        "source_original_byte_count": integrity["size_bytes"],
        "source_header_tr_ordinal": header["source_tr_ordinal"],
        "source_original_header_names": names,
        "pinned_openocd_provider_version": lock["provider"]["version"],
        "pinned_openocd_commit": EXPECTED_OPENOCD_COMMIT,
        "pinned_research_leads_source_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "research_priority_is_not_software_qualification": True,
        "chart_records": {
            "observed_chart_base_devices": len(observed),
            "P0_source_leads": scope_count["P0"],
            "P1_deferred": scope_count["P1"],
            "P2_archive_only": scope_count["P2"],
            "excluded_non_identity_or_wrong_width_rows": ignored,
            "total_html_tr_nodes": probe.total_rows,
        },
        "p0_by_source_lead": dict(sorted(Counter(
            item["source_lead_id"] for item in p0).items())),
        "p0_field_coverage": {
            field: {state: coverage[field][state]
                    for state in ("PARTIAL", "UNKNOWN", "CONFLICT", "VERIFIED")}
            for field in INFO_FIELDS
        },
        "p0_family_records": p0,
        "p1_deferred_base_names": p1,
        "p2_archive_only_base_names": p2,
        "exact_icpn_fields_verified_from_chart": 0,
        "all_records_research_only": True,
        "manufacturer_population_complete": False,
        "software_supported_icpn_count": None,
        "internal_admission_count": 0,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--output", type=Path)
    choice.add_argument("--verify", type=Path)
    args = parser.parse_args()
    destination = args.output or args.verify
    require("production" not in {x.casefold() for x in destination.resolve().parts},
            "Production destination prohibited")
    report = build_report(args.original_root)
    if args.verify:
        require(report == json.loads(args.verify.read_text(encoding="utf-8")),
                "Phase 1 P0 batch source/field replay mismatch")
        print("Microchip Phase 1 P0 original-source batch replay PASS")
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps({"chart_records": report["chart_records"],
                          "p0_by_source_lead": report["p0_by_source_lead"],
                          "p0_field_coverage": report["p0_field_coverage"]},
                         indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
