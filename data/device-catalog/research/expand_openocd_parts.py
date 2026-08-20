#!/usr/bin/env python3
"""Expand Flash-capable OpenOCD MCU targets into sourced device identifiers.

The generator is deliberately fail-closed.  It emits all 114 MCU/Wireless MCU
capability candidates, but only emits a part mapping when a versioned CMSIS
PDSC source and a deterministic rule select exactly one customer target CFG.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin


OPENOCD_COMMIT = "56b8d93fbe61a78dc903d770820d6d896b6d8134"
RESEARCHED_WITHOUT_SELECTABLE_FLASH = {
    "tcl/target/infineon/tle987x.cfg",
    "tcl/target/stm32n6x.cfg",
}
MCU_TYPES = {"MCU", "Wireless MCU"}

SOURCE_RE = re.compile(r"^\s*source\s+\[find\s+([^\]\s]+)\s*\]", re.MULTILINE)
FLASH_RE = re.compile(
    r"^\s*flash\s+bank\s+(?P<bank>[^\s#]+)\s+(?P<driver>[^\s#]+)"
    r"(?:\s+(?P<base>[^\s#]+))?",
    re.MULTILINE,
)


@dataclass(frozen=True)
class PackSpec:
    pack_vendor: str
    pack_name: str
    silicon_vendor: str


PACK_SPECS = (
    PackSpec("NXP", "LPC8N04_DFP", "NXP"),
    PackSpec("Keil", "SAM3_DFP", "Microchip"),
    PackSpec("Keil", "SAM4_DFP", "Microchip"),
    PackSpec("Keil", "LPC1100_DFP", "NXP"),
    PackSpec("Keil", "LPC1200_DFP", "NXP"),
    PackSpec("Keil", "LPC1300_DFP", "NXP"),
    PackSpec("Keil", "LPC1700_DFP", "NXP"),
    PackSpec("Keil", "LPC4000_DFP", "NXP"),
    PackSpec("Keil", "LPC4300_DFP", "NXP"),
    PackSpec("Keil", "LPC800_DFP", "NXP"),
    PackSpec("Keil", "Kinetis_K40_DFP", "NXP"),
    PackSpec("Keil", "Kinetis_K60_DFP", "NXP"),
    PackSpec("Keil", "Kinetis_KLxx_DFP", "NXP"),
    PackSpec("Keil", "S32K116_SDK_DFP", "NXP"),
    PackSpec("Keil", "S32K118_SDK_DFP", "NXP"),
    PackSpec("Keil", "STBlueNRG_DFP", "STMicroelectronics"),
    PackSpec("Keil", "STBlueNRG-1_DFP", "STMicroelectronics"),
    PackSpec("Keil", "STBlueNRG-2_DFP", "STMicroelectronics"),
    PackSpec("Keil", "STBlueNRG-LP_DFP", "STMicroelectronics"),
    PackSpec("Keil", "STM32H7RSxx_DFP", "STMicroelectronics"),
    PackSpec("Keil", "STM32WBAxx_DFP", "STMicroelectronics"),
    PackSpec("Keil", "STM32WBxx_DFP", "STMicroelectronics"),
    PackSpec("Keil", "STM32WLxx_DFP", "STMicroelectronics"),
    PackSpec("Keil", "LM3S_DFP", "Texas Instruments"),
    PackSpec("Keil", "LM4F_DFP", "Texas Instruments"),
    PackSpec("Keil", "TM4C_DFP", "Texas Instruments"),
    PackSpec("Nuvoton", "NuMicroM4_DFP", "Nuvoton"),
)


# Order matters: put narrower selectors before family selectors.
MAPPING_RULES = (
    ("microchip-sam3a4x4", "Microchip", r"^ATSAM3[AX]4", "tcl/target/at91sam3ax_4x.cfg"),
    ("microchip-sam3a8x8", "Microchip", r"^ATSAM3[AX]8", "tcl/target/at91sam3ax_8x.cfg"),
    ("microchip-sam3n", "Microchip", r"^ATSAM3N", "tcl/target/at91sam3nXX.cfg"),
    ("microchip-sam3sd", "Microchip", r"^ATSAM3SD", "tcl/target/at91sam3sXX.cfg"),
    ("microchip-sam3s", "Microchip", r"^ATSAM3S(?!D)", "tcl/target/at91sam3sXX.cfg"),
    ("microchip-sam3u1c", "Microchip", r"^ATSAM3U1C$", "tcl/target/at91sam3u1c.cfg"),
    ("microchip-sam3u1e", "Microchip", r"^ATSAM3U1E$", "tcl/target/at91sam3u1e.cfg"),
    ("microchip-sam3u2c", "Microchip", r"^ATSAM3U2C$", "tcl/target/at91sam3u2c.cfg"),
    ("microchip-sam3u2e", "Microchip", r"^ATSAM3U2E$", "tcl/target/at91sam3u2e.cfg"),
    ("microchip-sam3u4c", "Microchip", r"^ATSAM3U4C$", "tcl/target/at91sam3u4c.cfg"),
    ("microchip-sam3u4e", "Microchip", r"^ATSAM3U4E$", "tcl/target/at91sam3u4e.cfg"),
    ("microchip-sam4c32", "Microchip", r"^ATSAM4C(?:MP|MS|P)?32", "tcl/target/at91sam4c32x.cfg"),
    ("microchip-sam4c", "Microchip", r"^ATSAM4C", "tcl/target/at91sam4cXXX.cfg"),
    ("microchip-sam4l", "Microchip", r"^ATSAM4L[CS]", "tcl/target/at91sam4lXX.cfg"),
    ("microchip-sam4sd32", "Microchip", r"^ATSAM4SD32", "tcl/target/at91sam4sd32x.cfg"),
    ("microchip-sam4s", "Microchip", r"^ATSAM4S(?!D32)", "tcl/target/at91sam4sXX.cfg"),
    ("nxp-k40", "NXP", r"^MK40", "tcl/target/k40.cfg"),
    ("nxp-k60", "NXP", r"^MK60", "tcl/target/k60.cfg"),
    ("nxp-kl25", "NXP", r"^MKL25", "tcl/target/kl25.cfg"),
    ("nxp-lpc11", "NXP", r"^LPC11", "tcl/target/lpc11xx.cfg"),
    ("nxp-lpc12", "NXP", r"^LPC12", "tcl/target/lpc12xx.cfg"),
    ("nxp-lpc13", "NXP", r"^LPC13", "tcl/target/lpc13xx.cfg"),
    ("nxp-lpc17", "NXP", r"^LPC17", "tcl/target/lpc17xx.cfg"),
    ("nxp-lpc40", "NXP", r"^LPC40", "tcl/target/lpc40xx.cfg"),
    ("nxp-lpc4357", "NXP", r"^LPC4357$", "tcl/target/lpc4357.cfg"),
    ("nxp-lpc8n", "NXP", r"^LPC8N", "tcl/target/lpc8nxx.cfg"),
    ("nxp-lpc8", "NXP", r"^LPC8[0-3]", "tcl/target/lpc8xx.cfg"),
    ("nxp-s32k11", "NXP", r"^S32K11", "tcl/target/s32k.cfg"),
    ("st-bluenrg", "STMicroelectronics", r"^BlueNRG", "tcl/target/bluenrg-x.cfg"),
    ("st-stm32h7rs", "STMicroelectronics", r"^STM32H7[RS]", "tcl/target/stm32h7rsx.cfg"),
    ("st-stm32wba2", "STMicroelectronics", r"^STM32WBA2", "tcl/target/stm32wba2x.cfg"),
    ("st-stm32wba5", "STMicroelectronics", r"^STM32WBA5", "tcl/target/stm32wba5x.cfg"),
    ("st-stm32wba6", "STMicroelectronics", r"^STM32WBA6", "tcl/target/stm32wba6x.cfg"),
    ("st-stm32wb", "STMicroelectronics", r"^STM32WB", "tcl/target/stm32wbx.cfg"),
    ("st-stm32wl", "STMicroelectronics", r"^STM32WL", "tcl/target/stm32wlx.cfg"),
    ("ti-stellaris", "Texas Instruments", r"^(?:LM3S|LM4F|TM4C)", "tcl/target/ti/stellaris.cfg"),
    ("nuvoton-numicro-m4", "Nuvoton", r".+", "tcl/target/numicro_m4.cfg"),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def script_path(openocd_root: Path, value: str) -> Path:
    path = Path(value)
    return openocd_root / path if value.startswith("tcl/") else openocd_root / "tcl" / path


def include_graph(openocd_root: Path, target_config: str) -> tuple[list[str], list[dict[str, str]]]:
    visited: set[Path] = set()
    includes: list[str] = []
    banks: list[dict[str, str]] = []

    def visit(value: str) -> None:
        path = script_path(openocd_root, value).resolve()
        if path in visited or not path.is_file():
            return
        visited.add(path)
        relative = str(path.relative_to(openocd_root))
        includes.append(relative)
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in FLASH_RE.finditer(text):
            banks.append(
                {
                    "declaration_file": relative,
                    "bank": match.group("bank") or "",
                    "driver": match.group("driver") or "",
                    "base": match.group("base") or "",
                }
            )
        for include in SOURCE_RE.findall(text):
            visit(include)

    visit(target_config)
    return includes, banks


def capability_status(target_config: str, classification_status: str, banks: list[dict[str, str]]) -> tuple[str, str]:
    stem = Path(target_config).stem.lower()
    concrete = {bank["driver"] for bank in banks if bank["driver"] != "virtual"}
    if classification_status == "Internal/helper" or stem.endswith("_common") or "dual_bank" in stem:
        return "helper_or_alias", "Common/base or bank-layout configuration; collapse into a customer target"
    if concrete and concrete <= {"cfi", "jtagspi", "stmsmi", "stmqspi"}:
        return "external_flash_only", "Only an external/general-purpose Flash bank was resolved"
    if concrete:
        return "flash_driver_declared", "Concrete OpenOCD Flash driver resolved statically"
    if banks:
        return "helper_or_alias", "Only virtual Flash aliases were resolved"
    return "flash_driver_missing", "No Flash bank resolved"


def load_researched(paths: list[Path]) -> set[str]:
    researched = set(RESEARCHED_WITHOUT_SELECTABLE_FLASH)
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            researched.update(row["target_config"] for row in csv.DictReader(handle))
    return researched


def build_capabilities(
    openocd_root: Path, targets_path: Path, researched_csvs: list[Path]
) -> tuple[dict[str, object], list[dict[str, object]]]:
    payload = json.loads(targets_path.read_text(encoding="utf-8"))
    if payload["source"]["commit"] != OPENOCD_COMMIT:
        raise SystemExit("target catalog is not pinned to the expected OpenOCD commit")
    if subprocess.run(
        ["git", "-C", str(openocd_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() != OPENOCD_COMMIT:
        raise SystemExit("OpenOCD checkout is not pinned to the expected commit")

    researched = load_researched(researched_csvs)
    backlog = [row for row in payload["targets"] if row["target_config"] not in researched]
    flash_backlog: list[tuple[dict[str, str], list[str], list[dict[str, str]]]] = []
    for target in backlog:
        includes, banks = include_graph(openocd_root, target["target_config"])
        if banks:
            flash_backlog.append((target, includes, banks))
    candidates = [entry for entry in flash_backlog if entry[0]["device_type"] in MCU_TYPES]

    if (len(researched), len(backlog), len(flash_backlog), len(candidates)) != (55, 344, 124, 114):
        raise SystemExit(
            "expansion baseline changed: expected researched/backlog/flash/MCU "
            f"55/344/124/114, got {len(researched)}/{len(backlog)}/"
            f"{len(flash_backlog)}/{len(candidates)}"
        )

    rows: list[dict[str, object]] = []
    for target, includes, banks in candidates:
        status, reason = capability_status(target["target_config"], target["classification_status"], banks)
        drivers = sorted({bank["driver"] for bank in banks})
        rows.append(
            {
                "vendor": target["vendor"],
                "series": target["series"],
                "target_config": target["target_config"],
                "device_type": target["device_type"],
                "classification_status": target["classification_status"],
                "capability_status": status,
                "capability_reason": reason,
                "flash_drivers": drivers,
                "flash_banks": banks,
                "include_graph": includes,
                "openocd_distribution": "upstream-openocd",
                "openocd_commit": OPENOCD_COMMIT,
                "validation_status": "not_verified",
            }
        )
    rows.sort(key=lambda row: (str(row["vendor"]), str(row["target_config"])))
    metadata = {
        "schema_version": "1.0",
        "openocd_commit": OPENOCD_COMMIT,
        "researched_target_count": len(researched),
        "backlog_target_count": len(backlog),
        "flash_declaring_backlog_count": len(flash_backlog),
        "mcu_candidate_count": len(candidates),
        "mcu_count": sum(row["device_type"] == "MCU" for row in rows),
        "wireless_mcu_count": sum(row["device_type"] == "Wireless MCU" for row in rows),
    }
    return metadata, rows


def pack_url(element: ET.Element) -> str:
    base = element.get("url", "").replace("http://", "https://")
    return urljoin(base, f"{element.get('vendor', '')}.{element.get('name', '')}.pdsc")


def download(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["curl", "-L", "--retry", "2", "--max-time", "90", "-sS", url, "-o", str(destination)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode or not destination.exists() or not destination.stat().st_size:
        destination.unlink(missing_ok=True)
        raise RuntimeError(result.stderr.strip() or f"curl failed for {url}")


def extract_devices(pdsc: Path, source: dict[str, str]) -> list[dict[str, str]]:
    root = ET.parse(pdsc).getroot()
    records: list[dict[str, str]] = []
    for family in root.findall(".//devices/family"):
        family_name = family.get("Dfamily", "")
        nodes = [(family, "")]
        nodes.extend((node, node.get("DsubFamily", "")) for node in family.findall("./subFamily"))
        for parent, subfamily_name in nodes:
            for device in parent.findall("./device"):
                device_name = device.get("Dname", "")
                variants = [node.get("Dvariant", "") for node in device.findall("./variant") if node.get("Dvariant")]
                for part_number in variants or ([device_name] if device_name else []):
                    records.append(
                        {
                            "vendor": source["silicon_vendor"],
                            "family": family_name,
                            "subfamily": subfamily_name,
                            "part_number": part_number,
                            "cmsis_device": device_name or part_number,
                        }
                    )
    return records


def identifier_kind(name: str) -> str:
    if re.search(r"(?:_xx|x(?:tr)?$|xxx)", name, re.IGNORECASE):
        return "ordering_pattern"
    return "cmsis_device_name"


def find_rule(vendor: str, part_number: str) -> tuple[str, str] | None:
    # Rules are intentionally ordered from the narrowest selector to the
    # broader family fallback.  The exported rule ID preserves which selector
    # won, so overlaps stay auditable.
    for rule_id, rule_vendor, pattern, target_config in MAPPING_RULES:
        if vendor == rule_vendor and re.search(pattern, part_number, re.IGNORECASE):
            return rule_id, target_config
    return None


def load_sources(index_path: Path, cache: Path) -> list[dict[str, str]]:
    root = ET.parse(index_path).getroot()
    available = {(node.get("vendor", ""), node.get("name", "")): node for node in root.findall(".//pdsc")}
    sources: list[dict[str, str]] = []
    for spec in PACK_SPECS:
        element = available.get((spec.pack_vendor, spec.pack_name))
        if element is None:
            raise RuntimeError(f"pack missing from index: {spec.pack_vendor}.{spec.pack_name}")
        url = pack_url(element)
        path = cache / f"{spec.pack_vendor}.{spec.pack_name}.pdsc"
        download(url, path)
        # Parsing here also rejects HTML error pages cached under a PDSC name.
        ET.parse(path)
        sources.append(
            {
                "silicon_vendor": spec.silicon_vendor,
                "pack_vendor": spec.pack_vendor,
                "pack_name": spec.pack_name,
                "pack_version": element.get("version", ""),
                "source_url": url,
                "content_sha256": sha256(path),
                "path": str(path),
            }
        )
    return sources


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openocd-root", required=True, type=Path)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--researched-csv", action="append", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    metadata, capabilities = build_capabilities(args.openocd_root, args.targets, args.researched_csv)
    capability_by_target = {str(row["target_config"]): row for row in capabilities}
    sources = load_sources(args.index, args.cache)

    mapped: dict[tuple[str, str, str], dict[str, object]] = {}
    for source in sources:
        for device in extract_devices(Path(source["path"]), source):
            match = find_rule(device["vendor"], device["part_number"])
            if match is None:
                continue
            rule_id, target_config = match
            capability = capability_by_target.get(target_config)
            if capability is None or capability["capability_status"] != "flash_driver_declared":
                continue
            row: dict[str, object] = {
                **device,
                "identifier_kind": identifier_kind(device["part_number"]),
                "target_config": target_config,
                "flash_drivers": capability["flash_drivers"],
                "openocd_distribution": "upstream-openocd",
                "openocd_commit": OPENOCD_COMMIT,
                "source_pack_vendor": source["pack_vendor"],
                "source_pack_name": source["pack_name"],
                "source_pack_version": source["pack_version"],
                "source_url": source["source_url"],
                "source_content_sha256": source["content_sha256"],
                "mapping_rule_id": rule_id,
                "mapping_status": "mapping_candidate",
                "validation_status": "not_verified",
            }
            key = (device["vendor"], device["part_number"].upper(), target_config)
            mapped.setdefault(key, row)
    mapped_rows = sorted(mapped.values(), key=lambda row: (str(row["vendor"]), str(row["part_number"]), str(row["target_config"])))

    mapping_counts = Counter(str(row["target_config"]) for row in mapped_rows)
    outcomes: list[dict[str, object]] = []
    for capability in capabilities:
        target_config = str(capability["target_config"])
        count = mapping_counts[target_config]
        status = str(capability["capability_status"])
        if count:
            outcome = "mapped"
            reason = "One or more deterministic identifiers were found in a pinned PDSC source"
        elif status != "flash_driver_declared":
            outcome = "deferred"
            reason = str(capability["capability_reason"])
        else:
            outcome = "source_adapter_pending"
            reason = "No identifier matched the implemented PDSC source adapters and mapping rules"
        outcomes.append(
            {
                "vendor": capability["vendor"],
                "target_config": target_config,
                "capability_status": status,
                "expansion_outcome": outcome,
                "mapped_identifier_count": count,
                "reason": reason,
                "validation_status": "not_verified",
            }
        )

    capability_fields = [
        "vendor", "series", "target_config", "device_type", "classification_status",
        "capability_status", "capability_reason", "flash_drivers", "flash_banks",
        "include_graph", "openocd_distribution", "openocd_commit", "validation_status",
    ]
    mapped_fields = [
        "vendor", "family", "subfamily", "part_number", "identifier_kind", "cmsis_device",
        "target_config", "flash_drivers", "openocd_distribution", "openocd_commit",
        "source_pack_vendor", "source_pack_name", "source_pack_version", "source_url",
        "source_content_sha256", "mapping_rule_id", "mapping_status", "validation_status",
    ]
    outcome_fields = [
        "vendor", "target_config", "capability_status", "expansion_outcome",
        "mapped_identifier_count", "reason", "validation_status",
    ]
    write_csv(args.output_dir / "openocd-target-capabilities.csv", capability_fields, capabilities)
    write_csv(args.output_dir / "openocd-parts-expanded.csv", mapped_fields, mapped_rows)
    write_csv(args.output_dir / "openocd-expansion-outcomes.csv", outcome_fields, outcomes)

    (args.output_dir / "openocd-target-capabilities.json").write_text(
        json.dumps({"metadata": metadata, "targets": capabilities}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "openocd-parts-expanded.json").write_text(
        json.dumps(
            {
                "metadata": {
                    **metadata,
                    "source_index_sha256": sha256(args.index),
                    "source_pack_count": len(sources),
                    "mapped_identifier_count": len(mapped_rows),
                    "mapped_target_count": len(mapping_counts),
                    "identifier_kinds": dict(Counter(str(row["identifier_kind"]) for row in mapped_rows)),
                },
                "devices": mapped_rows,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "source-manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "index": {
                    "url": "https://www.keil.com/pack/index.pidx",
                    "content_sha256": sha256(args.index),
                },
                "sources": [{key: value for key, value in source.items() if key != "path"} for source in sources],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "mapping-rules.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "rules": [
                    {"rule_id": rule_id, "vendor": vendor, "part_pattern": pattern, "target_config": target}
                    for rule_id, vendor, pattern, target in MAPPING_RULES
                ],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    outcome_counts = Counter(str(row["expansion_outcome"]) for row in outcomes)
    vendor_counts = Counter(str(row["vendor"]) for row in mapped_rows)
    kind_counts = Counter(str(row["identifier_kind"]) for row in mapped_rows)
    report = [
        "# OpenOCD MCU Part-Number Expansion Report",
        "",
        f"OpenOCD source commit: `{OPENOCD_COMMIT}`",
        "",
        "## Current execution result",
        "",
        f"- MCU/Wireless MCU CFG candidates evaluated: **{len(capabilities)}**",
        f"- CFG files with deterministic PDSC mappings: **{len(mapping_counts)}**",
        f"- Unique device identifiers mapped: **{len(mapped_rows)}**",
        f"- CMSIS device names: **{kind_counts['cmsis_device_name']}**",
        f"- Ordering patterns: **{kind_counts['ordering_pattern']}**",
        f"- Pinned PDSC sources parsed: **{len(sources)}**",
        f"- Helper/external-memory targets deferred: **{outcome_counts['deferred']}**",
        f"- Flash-capable targets awaiting a source adapter/rule: **{outcome_counts['source_adapter_pending']}**",
        "",
        "Every mapped row remains `not_verified`. This report proves only a deterministic software mapping and a declared OpenOCD Flash driver, not engineering, Socket, or production validation.",
        "",
        "## Mapped identifiers by vendor",
        "",
        "| Vendor | Identifiers |",
        "|---|---:|",
    ]
    report.extend(f"| {vendor} | {count} |" for vendor, count in sorted(vendor_counts.items()))
    report.extend(
        [
            "",
            "## Outcome interpretation",
            "",
            "- `mapped`: a pinned source plus one deterministic rule selected the Target CFG.",
            "- `source_adapter_pending`: Flash is declared, but the current automated sources/rules are insufficient.",
            "- `deferred`: the CFG is a helper/alias or resolves only an external/general-purpose Flash bank.",
            "",
        ]
    )
    (args.output_dir / "expansion-report.md").write_text("\n".join(report).rstrip() + "\n", encoding="utf-8")

    print(json.dumps({"metadata": metadata, "outcomes": outcome_counts, "mapped": len(mapped_rows), "mapped_targets": len(mapping_counts)}, default=dict))


if __name__ == "__main__":
    main()
