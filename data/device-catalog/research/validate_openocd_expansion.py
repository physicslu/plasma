#!/usr/bin/env python3
"""Validate checked-in OpenOCD expansion artifacts without network access."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def csv_rows(name: str) -> list[dict[str, str]]:
    with (ROOT / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    capabilities = csv_rows("openocd-target-capabilities.csv")
    parts = csv_rows("openocd-parts-expanded.csv")
    outcomes = csv_rows("openocd-expansion-outcomes.csv")
    canonical = csv_rows("openocd-parts-canonical.csv")
    resolutions = csv_rows("openocd-duplicate-resolutions.csv")
    baseline = csv_rows("plasma_openocd_parts_top5_mapped.csv") + csv_rows(
        "plasma_openocd_parts_next5_mapped.csv"
    )
    rules = json.loads((ROOT / "mapping-rules.json").read_text(encoding="utf-8"))["rules"]
    manifest = json.loads((ROOT / "source-manifest.json").read_text(encoding="utf-8"))
    payload = json.loads((ROOT / "openocd-parts-expanded.json").read_text(encoding="utf-8"))
    metadata = payload["metadata"]

    assert len(capabilities) == 114
    assert len(outcomes) == 114
    assert len(baseline) == 5760
    assert len(parts) == metadata["mapped_identifier_count"] == len(payload["devices"])
    assert len({row["target_config"] for row in parts}) == metadata["mapped_target_count"]
    assert len(parts) > 1023
    assert metadata["mapped_target_count"] > 36
    assert Counter(row["identifier_kind"] for row in parts) == metadata["identifier_kinds"]
    assert all(
        row["identifier_kind"] == "manufacturer_part_number"
        for row in parts
        if row["source_kind"] == "vendor_product_page"
    )
    assert Counter(row["device_type"] for row in capabilities) == {"MCU": 110, "Wireless MCU": 4}
    outcome_counts = Counter(row["expansion_outcome"] for row in outcomes)
    assert set(outcome_counts) == {"mapped", "deferred"}
    assert outcome_counts["mapped"] == metadata["mapped_target_count"]
    assert outcome_counts["source_adapter_pending"] == 0

    capability_by_target = {row["target_config"]: row for row in capabilities}
    assert len(capability_by_target) == len(capabilities)
    assert {row["target_config"] for row in outcomes} == set(capability_by_target)
    assert all(
        capability_by_target[row["target_config"]]["capability_status"] == "flash_driver_declared"
        for row in parts
    )
    assert all(row["validation_status"] == "not_verified" for row in parts + outcomes + capabilities + canonical)
    assert all(json.loads(row["cpu_architectures"]) for row in capabilities + parts + canonical)
    assert capability_by_target["tcl/target/k1921vk01t.cfg"]["vendor"] == "NIIET"
    assert capability_by_target["tcl/target/lpc2460.cfg"]["capability_status"] == "flash_driver_missing"
    assert all(
        capability_by_target[target]["capability_status"] == "needs_review"
        for target in ("tcl/target/at91sam7se512.cfg", "tcl/target/lpc2294.cfg")
    )
    assert all(
        capability_by_target[target]["capability_status"] == "helper_or_alias"
        for target in (
            "tcl/target/silabs/series0.cfg",
            "tcl/target/silabs/series2.cfg",
            "tcl/target/stm32xl.cfg",
        )
    )

    part_keys = {(row["vendor"], row["part_number"].upper(), row["target_config"]) for row in parts}
    assert len(part_keys) == len(parts)
    rule_ids = {row["rule_id"] for row in rules}
    assert all(row["mapping_rule_id"] in rule_ids for row in parts)
    source_keys = {
        (row["pack_vendor"], row["pack_name"], row["content_sha256"])
        for row in manifest["sources"]
    }
    assert len(source_keys) == len(manifest["sources"]) == metadata["source_count"]
    assert metadata["source_pack_count"] == sum(
        row["source_kind"] == "cmsis_pdsc" for row in manifest["sources"]
    )
    assert {row["source_kind"] for row in manifest["sources"]} == {
        "cmsis_pdsc", "vendor_sdk_text", "openocd_flash_driver", "vendor_product_page",
        "vendor_product_pdf", "cmsis_device_database", "openocd_target_definition",
    }
    assert all("board" not in row["source_kind"] for row in manifest["sources"])
    artery_parts = [row for row in parts if row["vendor"] == "Artery"]
    assert len(artery_parts) == 107
    assert all(row["source_kind"] == "openocd_flash_driver" for row in artery_parts)
    assert all(row["identifier_kind"] == "manufacturer_part_number" for row in artery_parts)
    assert all(row["part_number"].startswith("AT32F4") for row in artery_parts)
    assert not any(row["part_number"] == "LPC2930" for row in parts)
    assert all(
        "62" in row["part_number"] and "32" not in row["part_number"]
        for row in parts
        if row["target_config"] == "tcl/target/aduc702x.cfg"
    )
    assert all(
        row["identifier_kind"] == "ordering_pattern"
        for row in parts
        if row["target_config"] == "tcl/target/psoc5lp.cfg"
    )
    assert all(
        row["part_number"].startswith(("EM3585-", "EM3586-", "EM3587-", "EM3588-"))
        for row in parts
        if row["target_config"] == "tcl/target/em358.cfg"
    )
    assert all(
        row["part_number"] == "STM32W108C8"
        for row in parts
        if row["target_config"] == "tcl/target/stm32w108xx.cfg"
    )
    assert {
        row["part_number"]
        for row in parts
        if row["target_config"] == "tcl/target/npcx.cfg"
    } == {"NPCX7M6FB", "NPCX7M6FC", "NPCX7M7FC"}
    assert all(
        (row["source_pack_vendor"], row["source_pack_name"], row["source_content_sha256"])
        in source_keys
        for row in parts
    )
    assert all(
        row["target_config"] == "tcl/target/fm3.cfg"
        for row in parts
        if row["vendor"] == "Cypress/Fujitsu" and row["source_pack_name"].startswith("FM3")
    )
    assert all(
        row["target_config"] in {"tcl/target/fm4_mb9bf.cfg", "tcl/target/fm4_s6e2cc.cfg"}
        for row in parts
        if row["vendor"] == "Cypress/Fujitsu" and row["source_pack_name"] == "FM4_DFP"
    )

    canonical_keys = {(row["vendor"], row["part_number"].upper()) for row in canonical}
    assert len(canonical_keys) == len(canonical) == metadata["canonical_identifier_count"]
    assert canonical_keys == {
        (row["vendor"], row["part_number"].upper()) for row in baseline + parts
    }
    assert len({row["target_config"] for row in canonical}) == metadata["canonical_target_count"]
    assert len(resolutions) == metadata["cross_catalog_duplicate_count"]
    canonical_by_key = {(row["vendor"], row["part_number"].upper()): row for row in canonical}
    assert all(
        canonical_by_key[(row["vendor"], row["part_number"].upper())]["target_config"]
        == row["selected_target_config"]
        for row in resolutions
    )
    h7_resolutions = [row for row in resolutions if row["selected_target_config"] == "tcl/target/stm32h7rsx.cfg"]
    assert len(h7_resolutions) == 34
    assert {row["superseded_target_config"] for row in h7_resolutions} == {"tcl/target/stm32h7x.cfg"}
    assert {
        architecture
        for row in canonical
        for architecture in json.loads(row["cpu_architectures"])
    } >= {"ARM Cortex-M", "ARM7TDMI", "ARM966E-S", "AVR", "MIPS32", "RISC-V", "Xtensa"}
    rp2350 = canonical_by_key[("Raspberry Pi", "RP2350A")]
    assert json.loads(rp2350["cpu_architectures"]) == ["ARM Cortex-M", "RISC-V"]

    print("OpenOCD expansion artifacts: PASS")
    print(
        f"114 candidates; {len(parts):,} expansion identifiers; "
        f"{metadata['mapped_target_count']} mapped targets; "
        f"{len(canonical):,} canonical identifiers; "
        f"{metadata['source_pack_count']} pinned PDSCs; "
        f"{len(resolutions)} target conflicts resolved"
    )


if __name__ == "__main__":
    main()
