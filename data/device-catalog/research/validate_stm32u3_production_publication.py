#!/usr/bin/env python3
"""Validate historical STM32U3 publication inside the current grown catalog."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from publish_stm32u3_catalog import (
    EXPECTED_BASES,
    EXPECTED_EXACT_SET_SHA256,
    EXPECTED_POSTSTATE_EXACT,
    EXPECTED_POSTSTATE_FAMILIES,
    EXPECTED_ROWS,
    FAMILY,
    PRODUCTION_FIELDS,
    PRODUCTION_MANIFEST,
    _git_blob_sha,
    _publication_rows,
    _render_csv,
)

HERE = Path(__file__).resolve().parent
CANONICAL = HERE / "stm32u3-commercial-icpn.csv"
PROPOSAL = HERE / "stm32u3-production-publication-proposal.json"

EXPECTED_HISTORICAL_BLOB = "c35e5e4e10c6c514ee82b099cc7ca3d1b7cf79af"
EXPECTED_HISTORICAL_SHA256 = "171cc7344ee65da9fd89052f2e7a0f0cd6e9ccbc8da02d20f8e33bbc1c1eeaff"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def set_sha(values: set[str]) -> str:
    return hashlib.sha256(("\n".join(sorted(values)) + "\n").encode("utf-8")).hexdigest()


def main() -> int:
    historical_rows, statuses = _publication_rows()
    historical_bytes = _render_csv(historical_rows)
    historical_ids = {row["icpn"] for row in historical_rows}

    req(len(historical_rows) == EXPECTED_ROWS, "historical STM32U3 row count drifted")
    req(len(historical_ids) == EXPECTED_ROWS, "historical STM32U3 exact identities not unique")
    req(set_sha(historical_ids) == EXPECTED_EXACT_SET_SHA256, "historical STM32U3 exact set drifted")
    req(_git_blob_sha(historical_bytes) == EXPECTED_HISTORICAL_BLOB,
        "historical STM32U3 canonical Git blob drifted")
    req(hashlib.sha256(historical_bytes).hexdigest() == EXPECTED_HISTORICAL_SHA256,
        "historical STM32U3 canonical SHA-256 drifted")

    current_raw = CANONICAL.read_bytes()
    current_rows = list(csv.DictReader(io.StringIO(current_raw.decode("utf-8"))))
    current_ids = {row["icpn"] for row in current_rows}
    req(len(current_rows) >= EXPECTED_ROWS, "current STM32U3 regressed below historical row count")
    req(historical_ids.issubset(current_ids), "historical STM32U3 identity disappeared")

    lines = current_raw.decode("utf-8").splitlines()
    header = lines[0]
    historical_lines = [
        line for line in lines[1:]
        if line.split(",", 2)[1] in historical_ids
    ]
    reconstructed = (header + "\n" + "\n".join(historical_lines) + "\n").encode("utf-8")
    req(reconstructed == historical_bytes,
        "historical STM32U3 canonical rows changed inside current file")

    req(tuple(current_rows[0].keys()) == PRODUCTION_FIELDS if current_rows else False,
        "STM32U3 canonical schema drifted")
    historical_current = [row for row in current_rows if row["icpn"] in historical_ids]
    req(len({row["base_device"] for row in historical_current}) == EXPECTED_BASES,
        "historical STM32U3 Base Device count drifted")
    req({row["family"] for row in historical_current} == {FAMILY},
        "historical STM32U3 contains foreign family")
    req({row["manufacturer"] for row in historical_current} == {"STMicroelectronics"},
        "historical STM32U3 manufacturer drifted")
    req(
        {row["mapping_status"] for row in historical_current}
        <= {"deterministic_ordering_pattern", "deterministic_cmsis_device_name"},
        "historical STM32U3 mapping method escaped deterministic allowlist",
    )
    req(all(row["verification_status"].startswith("verified_") for row in historical_current),
        "historical STM32U3 admitted identity lacks verified provenance")
    req(all(row["openocd_target_config"] == "tcl/target/stm32u3x.cfg" for row in historical_current),
        "historical STM32U3 target config drifted")

    proposal = json.loads(PROPOSAL.read_text(encoding="utf-8"))
    req(proposal.get("family") == FAMILY, "STM32U3 historical proposal family drifted")
    req(proposal.get("published_exact_icpns") == EXPECTED_ROWS,
        "STM32U3 historical proposal row count drifted")
    req(proposal.get("published_base_devices") == EXPECTED_BASES,
        "STM32U3 historical proposal Base Device count drifted")
    req(proposal.get("exact_icpn_set_sha256") == EXPECTED_EXACT_SET_SHA256,
        "STM32U3 historical proposal exact-set drifted")
    req(proposal.get("canonical_csv_sha256") == EXPECTED_HISTORICAL_SHA256,
        "STM32U3 historical proposal canonical SHA drifted")
    req(proposal.get("canonical_csv_git_blob_sha") == EXPECTED_HISTORICAL_BLOB,
        "STM32U3 historical proposal canonical blob drifted")
    req(proposal.get("marketing_status_observed") == {"Active": 100, "Evaluation": 6},
        "STM32U3 observed historical marketing statuses drifted")
    for key in (
        "ppu_hil_required_for_catalog_admission",
        "socket_hil_required_for_catalog_admission",
        "physical_programming_success_required_for_catalog_admission",
        "physical_validation_claimed",
        "runtime_programming_support_claimed",
        "security_mutation_support_claimed",
        "debug_attach_support_claimed",
        "catalog_membership_authorizes_target_execution",
    ):
        req(proposal.get(key) is False, f"unsafe historical STM32U3 claim enabled: {key}")

    manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    u3 = [s for s in sources if s.get("family") == FAMILY]
    req(len(u3) == 1, "current STM32U3 Production source missing/duplicated")
    source = u3[0]
    req(source["row_count"] == len(current_rows), "current STM32U3 manifest row-count drift")
    req(source["path"] == "../research/stm32u3-commercial-icpn.csv",
        "current STM32U3 manifest path drift")
    req(source["sha256"] == hashlib.sha256(current_raw).hexdigest(),
        "current STM32U3 manifest SHA binding drift")
    req(source["git_blob_sha"] == _git_blob_sha(current_raw),
        "current STM32U3 manifest blob binding drift")

    total = sum(int(s["row_count"]) for s in sources)
    families = {s["family"] for s in sources}
    req(total >= EXPECTED_POSTSTATE_EXACT, "Production exact count regressed below U3 publication")
    req(len(families) >= EXPECTED_POSTSTATE_FAMILIES,
        "Production family count regressed below U3 publication")

    print(json.dumps({
        "family": FAMILY,
        "historical_published_exact_icpns": EXPECTED_ROWS,
        "historical_published_base_devices": EXPECTED_BASES,
        "current_stm32u3_exact_icpns": len(current_rows),
        "production_exact_icpns": total,
        "production_families": len(families),
        "physical_validation_claimed": False,
        "runtime_programming_support_claimed": False,
    }, indent=2, sort_keys=True))
    print("STM32U3 Production publication historical-subset validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
