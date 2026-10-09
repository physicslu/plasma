#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
LEGACY = HERE / "openocd-parts-canonical.csv"
SUCCESSOR = HERE / "openocd-parts-canonical-v627.csv"
DELTA = HERE / "openocd-c0-bounded-route-inventory-v6.25.csv"
RECEIPT = HERE / "openocd-c0-canonical-route-write-v6.27.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

FIELDS = (
    "vendor", "family", "subfamily", "plasma_series", "part_number", "identifier_kind",
    "cpu_architectures", "target_config", "openocd_distribution", "mapping_status",
    "validation_status", "catalog_origin",
)

EXACT = (
    "STM32C011D6Y6TR",
    "STM32C051D8Y6TR",
    "STM32C091ECY6TR",
    "STM32C092ECY3TR",
    "STM32C092ECY6TR",
)


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def parse(raw: bytes) -> list[dict[str, str]]:
    with io.StringIO(raw.decode("utf-8")) as stream:
        reader = csv.DictReader(stream)
        req(tuple(reader.fieldnames or ()) == FIELDS, f"schema drift: {reader.fieldnames}")
        return list(reader)


def render(rows: list[dict[str, str]]) -> bytes:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def validate() -> dict:
    receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
    scope = receipt["approved_scope"]

    legacy_raw = LEGACY.read_bytes()
    successor_raw = SUCCESSOR.read_bytes()
    delta_raw = DELTA.read_bytes()

    req(
        git_blob_sha(legacy_raw) == scope["legacy_snapshot_git_blob_sha"],
        "legacy canonical snapshot changed",
    )
    req(
        git_blob_sha(successor_raw) == scope["successor_git_blob_sha"],
        "canonical successor blob mismatch",
    )
    req(
        hashlib.sha256(successor_raw).hexdigest() == scope["successor_sha256"],
        "canonical successor sha256 mismatch",
    )
    req(
        hashlib.sha256(delta_raw).hexdigest() == scope["source_delta_sha256"],
        "delta sha256 mismatch",
    )

    legacy = parse(legacy_raw)
    successor = parse(successor_raw)
    delta = parse(delta_raw)

    req(len(legacy) == scope["legacy_rows"] == 7657, "legacy row-count drift")
    req(len(successor) == scope["successor_rows"] == 7661, "successor row-count drift")
    req(len(delta) == scope["delta_rows"] == 4, "delta row-count drift")

    delta_keys = {(row["vendor"], row["part_number"].upper()) for row in delta}
    req(len(delta_keys) == 4, "delta duplicate keys")

    by_key = {
        (row["vendor"], row["part_number"].upper()): row
        for row in successor
    }
    req(len(by_key) == len(successor), "successor duplicate keys")
    req(delta_keys <= set(by_key), "delta rows missing from successor")

    for row in delta:
        key = (row["vendor"], row["part_number"].upper())
        req(
            by_key[key] == row,
            f"successor row differs from provenance row: {row['part_number']}",
        )

    inverse = [
        row
        for row in successor
        if (row["vendor"], row["part_number"].upper()) not in delta_keys
    ]
    req(len(inverse) == scope["legacy_rows"] == 7657, "inverse legacy row-count drift")
    inverse_raw = render(inverse)
    req(
        git_blob_sha(inverse_raw) == scope["legacy_snapshot_git_blob_sha"],
        "inverse reconstruction did not reproduce frozen legacy snapshot",
    )
    req(inverse_raw == legacy_raw, "inverse reconstruction is not byte-identical to legacy snapshot")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    production: dict[str, dict[str, str]] = {}
    mapped = 0
    no_mapping = 0

    for source in manifest["sources"]:
        source_path = (MANIFEST.parent / source["path"]).resolve()
        with source_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                production[row["icpn"]] = row
                if row["mapping_status"] == "no_mapping":
                    no_mapping += 1
                else:
                    mapped += 1

    expected = receipt["production_state_expected_unchanged"]
    req(mapped == expected["mapped"] == 4054, f"Production mapped drift: {mapped}")
    req(no_mapping == expected["no_mapping"] == 575, f"Production no_mapping drift: {no_mapping}")

    for icpn in EXACT:
        req(
            production[icpn]["mapping_status"] == "no_mapping",
            f"{icpn}: Production changed during successor-only write",
        )

    patterns = {row["part_number"] for row in delta}
    req(
        patterns == {
            "STM32C011D6Yx",
            "STM32C051D8Yx",
            "STM32C091ECYx",
            "STM32C092ECYx",
        },
        "delta pattern set drift",
    )

    summary = {
        "transaction_id": receipt["transaction_id"],
        "legacy_snapshot_git_blob_sha": git_blob_sha(legacy_raw),
        "legacy_rows": len(legacy),
        "canonical_postimage_git_blob_sha": git_blob_sha(successor_raw),
        "canonical_postimage_sha256": hashlib.sha256(successor_raw).hexdigest(),
        "canonical_rows": len(successor),
        "delta_rows": len(delta),
        "delta_sha256": hashlib.sha256(delta_raw).hexdigest(),
        "inverse_preimage_git_blob_sha": git_blob_sha(inverse_raw),
        "inverse_preimage_rows": len(inverse),
        "production_mapped": mapped,
        "production_no_mapping": no_mapping,
        "production_exact_scope_still_no_mapping": len(EXACT),
        "active_openocd_route_exact_count": expected["active_openocd_route_exact_count"],
        "active_openocd_route_denominator": expected["active_openocd_route_denominator"],
        "active_openocd_route_coverage_percent": expected["active_openocd_route_coverage_percent"],
        "next_gate": receipt["next_gate"],
        "claims": receipt["claims"],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("OPENOCD_C0_CANONICAL_WRITE_V627_PASS")
    return summary


if __name__ == "__main__":
    validate()
