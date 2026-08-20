#!/usr/bin/env python3
"""Generate a Plasma seed catalog from an OpenOCD recursive Git tree JSON.

Usage:
  python generate_openocd_target_catalog.py openocd-tree.json output.csv output.json

The Git tree can be obtained from:
  https://api.github.com/repos/openocd-org/openocd/git/trees/master?recursive=1
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

RULES = [
  [
    "STMicroelectronics",
    "^(stm32|stm8|str7|str9|stmsmi|bluenrg)",
    "MCU"
  ],
  [
    "Microchip",
    "^(at91|atsam|atmega|avr|pic32)",
    "MCU"
  ],
  [
    "NXP",
    "^(lpc|imx|kinetis|k[elx]?\\d|kl\\d|s32k|nhs31|qn908|vybrid)",
    "MCU"
  ],
  [
    "Nordic Semiconductor",
    "^nrf",
    "Wireless MCU"
  ],
  [
    "Espressif",
    "^(esp|xtensa-core-esp)",
    "Wireless MCU"
  ],
  [
    "Texas Instruments",
    "^(cc26|cc32|msp|stellaris|tms470)",
    "MCU"
  ],
  [
    "Infineon",
    "^(psoc|xmc)",
    "MCU"
  ],
  [
    "Silicon Labs",
    "^(efm|em35|sim3)",
    "MCU"
  ],
  [
    "Analog Devices",
    "^(aduc|adsp|max32)",
    "MCU"
  ],
  [
    "Nuvoton",
    "^(numicro|nuc9|npcx)",
    "MCU"
  ],
  [
    "Renesas",
    "^renesas",
    "MCU"
  ],
  [
    "Raspberry Pi",
    "^rp(2040|2350)",
    "MCU"
  ],
  [
    "Bouffalo Lab",
    "^bl(602|616|702)",
    "Wireless MCU"
  ],
  [
    "Cypress/Fujitsu",
    "^fm[34]",
    "MCU"
  ],
  [
    "Artery",
    "^artery",
    "MCU"
  ],
  [
    "GigaDevice",
    "^gd32",
    "MCU"
  ],
  [
    "MindMotion",
    "^mm32",
    "MCU"
  ],
  [
    "WCH",
    "^(ch32|wch)",
    "MCU"
  ],
  [
    "Intel/Altera",
    "^altera",
    "FPGA SoC"
  ],
  [
    "AMD/Xilinx",
    "^xilinx",
    "FPGA SoC"
  ],
  [
    "Allwinner",
    "^allwinner",
    "SoC"
  ],
  [
    "Broadcom",
    "^bcm",
    "SoC"
  ],
  [
    "Rockchip",
    "^rk\\d",
    "SoC"
  ],
  [
    "Qualcomm/Atheros",
    "^(qualcomm|atheros|ar71)",
    "SoC"
  ],
  [
    "Samsung",
    "^(samsung|exynos)",
    "SoC"
  ],
  [
    "NXP",
    "^ls\\d|^lsch",
    "SoC"
  ],
  [
    "Arm",
    "^arm_corelink",
    "SoC"
  ],
  [
    "Intel",
    "^quark",
    "MCU"
  ],
  [
    "Infineon/Cypress",
    "^c100",
    "MCU"
  ],
  [
    "XMOS",
    "^xmos",
    "MCU"
  ],
  [
    "Gowin?",
    "^gw",
    "FPGA"
  ]
]
INTERNAL = re.compile(r"^(test_|faux$|tmp|vd_|esp_common$|bl602_common$|imx$|kx$|klx$|lpc1xxx$|lpc2xxx$|max32xxx_common$|lsch3_common$|renesas_rcar_reset_common$|stm32x5x_common$|xtensa$|feroceon$|or1k$|nds32v5$)", re.I)
DIRECTORY_VENDORS = {
    "artery": ("Artery", "MCU"),
    "geehy": ("Geehy", "MCU"),
    "gigadevice": ("GigaDevice", "MCU"),
    "holtek": ("Holtek", "MCU"),
    "hpmicro": ("HPMicro", "MCU"),
    "infineon": ("Infineon", "MCU"),
    "marvell": ("Marvell", "SoC"),
    "microchip": ("Microchip", "MCU"),
    "nordic": ("Nordic Semiconductor", "Wireless MCU"),
    "nxp": ("NXP", "MCU"),
    "qualcomm": ("Qualcomm", "SoC"),
    "silabs": ("Silicon Labs", "MCU"),
    "st": ("STMicroelectronics", "MCU"),
    "ti": ("Texas Instruments", "MCU"),
    "xlnx": ("AMD/Xilinx", "FPGA SoC"),
}


def classify(name: str, path: str) -> tuple[str, str]:
    parts = Path(path).parts
    if len(parts) > 3 and parts[2] in DIRECTORY_VENDORS:
        return DIRECTORY_VENDORS[parts[2]]
    for vendor, pattern, device_type in RULES:
        if re.search(pattern, name, re.I):
            return vendor, device_type
    if re.search(r"fpga|xilinx|altera", name, re.I):
        return "Unclassified", "FPGA/SoC"
    if re.search(r"dsp", name, re.I):
        return "Unclassified", "DSP"
    return "Unclassified", "Unknown"


def series_name(name: str) -> str:
    match = re.match(r"^(stm32[a-z]\d+|stm32[a-z]\dx|stm8[sl]|esp32[a-z0-9]*|nrf\d+|lpc\d{2}|at91sam[a-z0-9]+|atsam[a-z0-9]+|atmega\d+|pic32[a-z]+|psoc\d|xmc\d|max326\d*|rp\d+|bl\d+|cc\d+|msp\d+|s32k|imx\d+[a-z]*|kinetis(?:_ke)?|efm32|numicro|renesas_[a-z0-9]+|rk\d+|bcm\d+|str\d+)", name, re.I)
    if match:
        return re.sub(r"x+$", "X", match.group(1), flags=re.I).upper()
    return re.sub(r"(_common|_dual_bank|_ext_.*|_reset_.*|_arm)$", "", name, flags=re.I).replace("_", " ").upper()


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: generate_openocd_target_catalog.py TREE_JSON OUT_CSV OUT_JSON")
    tree = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    paths = sorted(item["path"] for item in tree["tree"] if item.get("type") == "blob" and re.fullmatch(r"tcl/target/.+\.cfg", item["path"]))
    rows = []
    for path in paths:
        name = Path(path).stem
        vendor, device_type = classify(name, path)
        status = "Internal/helper" if INTERNAL.search(name) else ("Needs review" if vendor == "Unclassified" else "Auto-classified")
        rows.append({"vendor": vendor, "series": series_name(name), "display_name": name.replace("_", " ").title(), "target_config": path, "device_type": device_type, "classification_status": status, "part_number": ""})
    fields = ["vendor", "series", "display_name", "target_config", "device_type", "classification_status", "part_number"]
    with Path(sys.argv[2]).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    payload = {"schema_version": "1.0", "source": {"repository": "openocd-org/openocd", "ref": "master", "commit": tree.get("sha"), "path": "tcl/target/*.cfg"}, "targets": rows}
    Path(sys.argv[3]).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
