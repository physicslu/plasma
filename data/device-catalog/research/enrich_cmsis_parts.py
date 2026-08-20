#!/usr/bin/env python3
"""Build a five-vendor CMSIS device-to-OpenOCD target candidate catalog.

This tool intentionally records confidence and mapping status. A CMSIS device
entry proves that a device name exists in a Device Family Pack; it does not
prove that the mapped OpenOCD target has been validated on Plasma hardware.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

SILICON_VENDORS = {
    "STMicroelectronics",
    "NXP",
    "Microchip",
    "NordicSemiconductor",
    "TexasInstruments",
}
GROUP2_VENDORS = {
    "Infineon",
    "Espressif",
    "Silicon Labs",
    "Nuvoton",
    "Renesas",
}

# A target CFG can provide CPU debug access without a known usable Flash
# programming backend. Keep those devices in the research export as unmapped,
# but do not promote them into the selectable `*_mapped` catalog. Espressif
# targets are intentionally not listed here because the official
# `openocd-esp32` distribution supplies their Flash programming backend.
TARGETS_WITHOUT_FLASH_DRIVER = {
    "tcl/target/infineon/tle987x.cfg",
    "tcl/target/stm32n6x.cfg",
}


def selected_pack(element: ET.Element, group: str) -> tuple[str, str] | None:
    vendor = element.get("vendor", "")
    name = element.get("name", "")
    if element.get("deprecated"):
        return None
    if group == "top5":
        if vendor in {"NXP", "Microchip", "TexasInstruments"} and name.upper().endswith("_DFP"):
            return vendor, name
        if vendor == "NordicSemiconductor" and name == "nRF_DeviceFamilyPack":
            return vendor, name
        # Arm/Keil hosts the established STM32 family packs.
        if vendor == "Keil" and re.fullmatch(r"STM32.+_DFP", name, re.I):
            return "STMicroelectronics", name
        if vendor == "STMicroelectronics" and name.lower().endswith("_dfp"):
            return vendor, name
    else:
        if vendor == "Infineon" and name.upper().endswith("_DFP"):
            return "Infineon", name
        if vendor == "SiliconLabs" and name.upper().endswith("_DFP"):
            return "Silicon Labs", name
        if vendor == "Nuvoton" and (name.upper().endswith("_DFP") or name == "NuMicro_DFP"):
            return "Nuvoton", name
        if vendor == "Renesas" and name == "RA_DFP":
            return "Renesas", name
    return None


def pack_url(element: ET.Element) -> str:
    base = element.get("url", "")
    vendor = element.get("vendor", "")
    name = element.get("name", "")
    return urljoin(base.replace("http://", "https://"), f"{vendor}.{name}.pdsc")


def download_one(item: dict[str, str], cache: Path) -> tuple[dict[str, str], str | None]:
    destination = cache / f"{item['pack_vendor']}.{item['pack_name']}.pdsc"
    if destination.exists() and destination.stat().st_size:
        return item, None
    result = subprocess.run(
        ["curl", "-L", "--retry", "2", "--max-time", "90", "-sS", item["source_url"], "-o", str(destination)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode or not destination.exists() or not destination.stat().st_size:
        destination.unlink(missing_ok=True)
        return item, (result.stderr.strip() or f"curl exit {result.returncode}")
    return item, None


def extract_devices(pdsc: Path, pack: dict[str, str]) -> list[dict[str, str]]:
    try:
        root = ET.parse(pdsc).getroot()
    except ET.ParseError:
        return []
    records: list[dict[str, str]] = []
    for family in root.findall(".//devices/family"):
        family_name = family.get("Dfamily", "")
        vendor_name = family.get("Dvendor", "")
        nodes = [(family, "")]
        for subfamily in family.findall("./subFamily"):
            nodes.append((subfamily, subfamily.get("DsubFamily", "")))
        for parent, subfamily_name in nodes:
            for device in parent.findall("./device"):
                device_name = device.get("Dname", "")
                variants = [v.get("Dvariant", "") for v in device.findall("./variant") if v.get("Dvariant")]
                names = variants or ([device_name] if device_name else [])
                for name in names:
                    records.append(
                        {
                            "vendor": pack["silicon_vendor"],
                            "family": family_name,
                            "subfamily": subfamily_name,
                            "part_number": name,
                            "cmsis_device": device_name or name,
                            "pack_vendor": pack["pack_vendor"],
                            "pack_name": pack["pack_name"],
                            "pack_version": pack["pack_version"],
                            "source_url": pack["source_url"],
                            "cmsis_vendor": vendor_name,
                        }
                    )
    return records


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def identifier_kind(name: str) -> str:
    # CMSIS packs often use a lowercase x (or _xx) as an ordering-code
    # wildcard. Preserve it for search, but do not present it as an exact MPN.
    if re.search(r"(?:_xx|x(?:tr)?$)", name):
        return "ordering_pattern"
    return "cmsis_device_name"


def target_for(record: dict[str, str], targets: list[dict[str, str]]) -> tuple[str, str, str]:
    vendor = record["vendor"]
    part = record["part_number"].upper()
    candidates = [t for t in targets if t["vendor"] == vendor and t["classification_status"] != "Internal/helper"]
    wanted = ""
    if vendor == "STMicroelectronics":
        match = re.match(r"STM32([A-Z])([0-9])", part)
        if match:
            wanted = f"stm32{match.group(1).lower()}{match.group(2)}"
    elif vendor == "Nordic Semiconductor":
        match = re.match(r"NRF(51|52|53|54L|91)", part)
        if match:
            wanted = f"nrf{match.group(1).lower()}"
    elif vendor == "Microchip":
        if part.startswith(("ATSAMD", "SAMD")):
            wanted = "at91samd"
        elif part.startswith(("ATSAME5", "SAME5")):
            wanted = "atsame5"
        elif part.startswith(("ATSAMV", "SAMV")):
            wanted = "atsamv"
        elif part.startswith(("ATSAM3", "SAM3")):
            wanted = "at91sam3"
        elif part.startswith(("ATSAM4", "SAM4")):
            wanted = "at91sam4"
    elif vendor == "NXP":
        match = re.match(r"LPC(\d{2})", part)
        if match:
            wanted = f"lpc{match.group(1)}"
        elif part.startswith("MKE0"):
            wanted = "ke0x"
        elif re.match(r"MKE1.*F", part):
            wanted = "ke1xf"
        elif re.match(r"MKE1.*Z", part):
            wanted = "ke1xz"
        elif part.startswith("MKL25"):
            wanted = "kl25"
        elif part.startswith("MKL46"):
            wanted = "kl46"
        elif part.startswith("MKL"):
            wanted = "klx"
        elif part.startswith("MK40"):
            wanted = "k40"
        elif part.startswith("MK60"):
            wanted = "k60"
        elif part.startswith(("MK", "MKW", "MCX")):
            wanted = "kx"
        elif part.startswith("QN908"):
            wanted = "qn908"
    elif vendor == "Texas Instruments":
        if part.startswith("CC26"):
            wanted = "cc26"
        elif part.startswith("CC32"):
            wanted = "cc32"
        elif part.startswith("MSP432"):
            wanted = "msp432"
        elif part.startswith("MSPM0"):
            wanted = "mspm0"
        elif part.startswith(("LM3S", "LM4F", "TM4C")):
            wanted = "stellaris"
    elif vendor == "Infineon":
        pack_name = record.get("pack_name", "").upper()
        if part.startswith("XMC1") or "XMC1000" in pack_name:
            wanted = "xmc1"
        elif part.startswith("XMC4") or "XMC4000" in pack_name:
            wanted = "xmc4"
        elif part.startswith(("CY8C4", "PSoC4".upper())):
            wanted = "psoc4"
        elif part.startswith("CY8C5"):
            wanted = "psoc5lp"
        elif part.startswith(("CY8C6", "CYBLE", "CYW")) or "CAT1" in pack_name or "CAT2" in pack_name:
            wanted = "psoc6"
        elif part.startswith("TLE987") or "TLE987" in pack_name:
            wanted = "tle987"
    elif vendor == "Espressif":
        wanted = normalize(part)
    elif vendor == "Silicon Labs":
        match = re.match(r"(?:EFR32|BGM|MGM)[A-Z]{0,2}(\d{1,2})", part)
        if match and int(match.group(1)) >= 21:
            wanted = f"xg{match.group(1)}"
        elif part.startswith("EFR32"):
            wanted = "series1"
        elif part.startswith(("EFM32", "EZR32")):
            wanted = "efm32"
        elif part.startswith("SIM3"):
            wanted = "sim3"
    elif vendor == "Nuvoton":
        pack_name = record.get("pack_name", "").upper()
        if "M4_DFP" in pack_name or "KM1M4" in pack_name:
            wanted = "numicro_m4"
        elif "M0_DFP" in pack_name or "KM1M0" in pack_name or record.get("family", "").upper().find("CORTEX-M0") >= 0:
            wanted = "numicro"
    elif vendor == "Renesas":
        if part.startswith("R7S721"):
            wanted = "r7s72100"
        elif part.startswith("R7FS7G2"):
            wanted = "s7g2"

    if not wanted:
        return "", "unmapped", "No deterministic target rule"
    matches = [t for t in candidates if wanted in normalize(Path(t["target_config"]).stem)]
    programmable_matches = [t for t in matches if t["target_config"] not in TARGETS_WITHOUT_FLASH_DRIVER]
    if matches and not programmable_matches:
        return "", "unmapped", "No known OpenOCD Flash programming backend"
    matches = programmable_matches
    if len(matches) == 1:
        return matches[0]["target_config"], "candidate", f"Deterministic {vendor} family rule"
    if len(matches) > 1:
        # Prefer the shortest (usually the family base config).
        matches.sort(key=lambda item: len(item["target_config"]))
        return matches[0]["target_config"], "candidate", f"Family rule; {len(matches)} target candidates"
    return "", "unmapped", f"No OpenOCD target matching {wanted}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--targets", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--output-csv", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--group", choices=("top5", "next5"), default="top5")
    args = parser.parse_args()

    root = ET.parse(args.index).getroot()
    packs: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for element in root.findall(".//pdsc"):
        selected = selected_pack(element, args.group)
        if not selected:
            continue
        silicon_vendor, name = selected
        key = (element.get("vendor", ""), name)
        if key in seen:
            continue
        seen.add(key)
        packs.append(
            {
                "silicon_vendor": silicon_vendor,
                "pack_vendor": element.get("vendor", ""),
                "pack_name": name,
                "pack_version": element.get("version", ""),
                "source_url": pack_url(element),
            }
        )

    args.cache.mkdir(parents=True, exist_ok=True)
    failures: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(download_one, item, args.cache) for item in packs]
        for index, future in enumerate(as_completed(futures), 1):
            item, error = future.result()
            if error:
                failures.append({**item, "error": error})
            if index % 25 == 0 or index == len(futures):
                print(f"downloaded {index}/{len(futures)}; failures={len(failures)}", flush=True)

    target_payload = json.loads(args.targets.read_text(encoding="utf-8"))
    targets = target_payload["targets"]
    # Normalize the one public-facing vendor name used by the original seed.
    for target in targets:
        if target["vendor"] == "Nordic Semiconductor":
            continue

    records: list[dict[str, str]] = []
    for pack in packs:
        pdsc = args.cache / f"{pack['pack_vendor']}.{pack['pack_name']}.pdsc"
        if not pdsc.exists():
            continue
        for record in extract_devices(pdsc, pack):
            if record["vendor"] == "NordicSemiconductor":
                record["vendor"] = "Nordic Semiconductor"
            elif record["vendor"] == "TexasInstruments":
                record["vendor"] = "Texas Instruments"
            target_config, mapping_status, mapping_note = target_for(record, targets)
            record.update(
                {
                    "identifier_kind": identifier_kind(record["part_number"]),
                    "target_config": target_config,
                    "mapping_status": mapping_status,
                    "mapping_note": mapping_note,
                    "plasma_status": "not_validated",
                }
            )
            records.append(record)

    if args.group == "next5":
        # Espressif does not publish a CMSIS DFP. Use the official ESP-IDF SoC
        # directory as the authoritative family list, then map those names to
        # OpenOCD target files.
        result = subprocess.run(
            [
                "curl", "-L", "--retry", "2", "--max-time", "90", "-sS",
                "https://api.github.com/repos/espressif/esp-idf/contents/components/soc?ref=master",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            try:
                entries = json.loads(result.stdout)
            except json.JSONDecodeError:
                entries = []
            for entry in entries:
                name = entry.get("name", "")
                if entry.get("type") != "dir" or not re.fullmatch(r"esp32[a-z0-9]*", name):
                    continue
                record = {
                    "vendor": "Espressif",
                    "family": name.upper(),
                    "subfamily": "",
                    "part_number": name.upper(),
                    "identifier_kind": "cmsis_device_name",
                    "cmsis_device": name.upper(),
                    "pack_vendor": "Espressif",
                    "pack_name": "ESP-IDF",
                    "pack_version": "master",
                    "source_url": "https://github.com/espressif/esp-idf/tree/master/components/soc",
                }
                target_config, mapping_status, mapping_note = target_for(record, targets)
                record.update(
                    {
                        "target_config": target_config,
                        "mapping_status": mapping_status,
                        "mapping_note": mapping_note,
                        "plasma_status": "not_validated",
                    }
                )
                records.append(record)

    # Device packs can overlap. Keep one row per vendor/part/target, preferring
    # the numerically newest pack version only after deterministic sorting.
    records.sort(key=lambda item: (item["vendor"], item["part_number"], item["target_config"], item["pack_name"], item["pack_version"]), reverse=True)
    unique: dict[tuple[str, str, str], dict[str, str]] = {}
    for record in records:
        unique.setdefault((record["vendor"], record["part_number"], record["target_config"]), record)
    records = sorted(unique.values(), key=lambda item: (item["vendor"], item["family"], item["part_number"], item["target_config"]))

    fields = [
        "vendor", "family", "subfamily", "part_number", "identifier_kind", "cmsis_device",
        "target_config", "mapping_status", "mapping_note", "plasma_status",
        "pack_vendor", "pack_name", "pack_version", "source_url",
    ]
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in records)
    payload = {
        "schema_version": "1.0",
        "notes": [
            "CMSIS DFP device names are authoritative catalog entries but OpenOCD mappings are candidates.",
            "No row is production validated.",
            "Production UI must filter plasma_status=production_validated.",
        ],
        "statistics": {
            "packs_selected": len(packs),
            "packs_failed": len(failures),
            "parts": len(records),
            "by_vendor": Counter(row["vendor"] for row in records),
            "by_mapping_status": Counter(row["mapping_status"] for row in records),
        },
        "download_failures": failures,
        "parts": records,
    }
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=dict) + "\n", encoding="utf-8")
    print(json.dumps(payload["statistics"], ensure_ascii=False, default=dict), flush=True)


if __name__ == "__main__":
    main()
