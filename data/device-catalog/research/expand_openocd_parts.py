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
import tarfile
import xml.etree.ElementTree as ET
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin


OPENOCD_COMMIT = "56b8d93fbe61a78dc903d770820d6d896b6d8134"
RESEARCHED_WITHOUT_SELECTABLE_FLASH = {
    "tcl/target/infineon/tle987x.cfg",
    "tcl/target/stm32n6x.cfg",
}
MCU_TYPES = {"MCU", "Wireless MCU"}
HELPER_TARGETS = {
    "tcl/target/silabs/series0.cfg",
    "tcl/target/silabs/series2.cfg",
    "tcl/target/stm32xl.cfg",
}
VENDOR_OVERRIDES = {"tcl/target/k1921vk01t.cfg": "NIIET"}
TARGET_ARCHITECTURES = {
    "arm7tdmi": "ARM7TDMI",
    "arm926ejs": "ARM926EJ-S",
    "arm966e": "ARM966E-S",
    "avr": "AVR",
    "cortex_m": "ARM Cortex-M",
    "hla_target": "ARM Cortex-M",
    "mips_m4k": "MIPS32",
    "riscv": "RISC-V",
    "xtensa": "Xtensa",
}

SOURCE_RE = re.compile(r"^\s*source\s+\[find\s+([^\]\s]+)\s*\]", re.MULTILINE)
TARGET_RE = re.compile(r"^\s*target\s+create\s+\S+\s+(?P<type>\S+)", re.MULTILINE)
ESP_ARCH_RE = re.compile(r"^\s*set\s+_ESP_ARCH\s+[\"']?(?P<type>riscv|xtensa)", re.MULTILINE)
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
    source_url: str = ""


@dataclass(frozen=True)
class VendorSourceSpec:
    silicon_vendor: str
    source_name: str
    source_commit: str
    source_url: str
    source_kind: str
    device_pattern: str = ""
    expected_content_sha256: str = ""


PACK_SPECS = (
    PackSpec("AnalogDevices", "ADuCM36x_DFP", "Analog Devices"),
    PackSpec("Maxim", "MAX32620", "Analog Devices"),
    PackSpec("Maxim", "MAX32625", "Analog Devices"),
    PackSpec("Maxim", "MAX32630", "Analog Devices"),
    PackSpec("Maxim", "MAX32650", "Analog Devices"),
    PackSpec("Maxim", "MAX32655", "Analog Devices"),
    PackSpec("Maxim", "MAX32660", "Analog Devices"),
    PackSpec("Maxim", "MAX32665", "Analog Devices"),
    PackSpec("Maxim", "MAX32670", "Analog Devices"),
    PackSpec("Maxim", "MAX32672", "Analog Devices"),
    PackSpec("Maxim", "MAX32675", "Analog Devices"),
    PackSpec("Maxim", "MAX32690", "Analog Devices"),
    PackSpec("Keil", "FM3Basic_DFP", "Cypress/Fujitsu"),
    PackSpec("Keil", "FM3HighPerformance_DFP", "Cypress/Fujitsu"),
    PackSpec("Keil", "FM3LowPower_DFP", "Cypress/Fujitsu"),
    PackSpec("Keil", "FM3UltraLowLeak_DFP", "Cypress/Fujitsu"),
    PackSpec("Keil", "FM4_DFP", "Cypress/Fujitsu"),
    PackSpec("Geehy", "APM32F00x_DFP", "Geehy"),
    PackSpec("Geehy", "APM32F035_DFP", "Geehy"),
    PackSpec("Geehy", "APM32F0xx_DFP", "Geehy"),
    PackSpec("Geehy", "APM32F1xx_DFP", "Geehy"),
    PackSpec("Geehy", "APM32F4xx_DFP", "Geehy"),
    PackSpec("Geehy", "APM32F445_446_DFP", "Geehy"),
    PackSpec("GigaDevice", "GD32E23x_DFP", "GigaDevice"),
    PackSpec("Holtek", "HT32F493x5_DFP", "Holtek"),
    PackSpec("Holtek", "HT32F491x3_DFP", "Holtek"),
    PackSpec("Holtek", "HT32F490x1_DFP", "Holtek"),
    PackSpec("Holtek", "HT32_DFP", "Holtek"),
    PackSpec("Microchip", "SAMG_DFP", "Microchip"),
    PackSpec(
        "Microchip", "ATmega_DFP", "Microchip",
        "https://packs.download.microchip.com/Microchip.ATmega_DFP.pdsc",
    ),
    PackSpec(
        "Microchip", "PIC32MX_DFP", "Microchip",
        "https://packs.download.microchip.com/Microchip.PIC32MX_DFP.pdsc",
    ),
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

VENDOR_SOURCES = (
    VendorSourceSpec(
        "Analog Devices", "AnalogDevices.MSDK-user-guide", "e0446b176b7080098fecddd174317ba47946695e",
        "https://raw.githubusercontent.com/analogdevicesinc/msdk/"
        "e0446b176b7080098fecddd174317ba47946695e/USERGUIDE.md",
        "vendor_sdk_text",
        r"\b(MAX32662|MAX32680)\b",
    ),
    VendorSourceSpec(
        "Artery", "ArteryTek.PlatformIO-boards", "7313140183db3ca5e74e723c2abcc4da82992dc5",
        "https://github.com/ArteryTek/platform-arterytekat32/archive/"
        "7313140183db3ca5e74e723c2abcc4da82992dc5.tar.gz",
        "vendor_board_archive",
    ),
    VendorSourceSpec(
        "Bouffalo Lab", "BouffaloLab.SDK-README", "5cd17516dfe8d9813e79008aeb29c3f930797804",
        "https://raw.githubusercontent.com/bouffalolab/bouffalo_sdk/"
        "5cd17516dfe8d9813e79008aeb29c3f930797804/README.md",
        "vendor_sdk_text",
        r"\b(BL602|BL604|BL702L|BL704L|BL702|BL704|BL706)\b",
    ),
    VendorSourceSpec(
        "GigaDevice", "GigaDevice.GD32VF103-official-product-announcement", "article-247",
        "https://www.gd32mcu.com/cn/detail/247",
        "vendor_product_page",
        r"\b(GD32VF103[CRTV][468B][TU]6)\b",
        "fe8526fb9ca74db230cf55b08a0464fb7958793184c78778a00e8dd8a2fc79d2",
    ),
    VendorSourceSpec(
        "Microchip", "Microchip.SAM-BA-release-notes", "2.16",
        "https://ww1.microchip.com/downloads/en/DeviceDoc/sam-ba_2.16_releasenote.txt",
        "vendor_sdk_text",
        r"\b(at91sam7s(?:64|128|256)|at91sam7x(?:256|512))\b",
        "d988b014d3e21c5320c3675f98eabfb56c828ff4d6974aa1767d1a8a41562514",
    ),
    VendorSourceSpec(
        "Raspberry Pi", "RaspberryPi.PicoSDK-GPIO", "98a542c1a62fb549ffb5d66a3e5892b06276b670",
        "https://raw.githubusercontent.com/raspberrypi/pico-sdk/"
        "98a542c1a62fb549ffb5d66a3e5892b06276b670/"
        "src/rp2_common/hardware_gpio/include/hardware/gpio.h",
        "vendor_sdk_text",
        r"\b(RP2040|RP2350A|RP2350B)\b",
    ),
    VendorSourceSpec(
        "Texas Instruments", "TexasInstruments.FlashRover-supported-devices",
        "02b5d99477b3e7acc595af4bc0f123ae27a96473",
        "https://raw.githubusercontent.com/TexasInstruments/flash-rover/"
        "02b5d99477b3e7acc595af4bc0f123ae27a96473/README.md",
        "vendor_sdk_text",
        r"\b(CC1310|CC1350|CC1312R|CC1352P|CC1352R|CC2640|CC2650|CC2642R|"
        r"CC2652P7|CC2652R7|CC2652P|CC2652RB|CC2652R)\b",
    ),
    VendorSourceSpec(
        "Texas Instruments", "TexasInstruments.SimpleLink-Zephyr-devices",
        "498f982e61f0d652a1fbf47438f7686613d87670",
        "https://raw.githubusercontent.com/TexasInstruments/simplelink-zephyr/"
        "498f982e61f0d652a1fbf47438f7686613d87670/README.md",
        "vendor_sdk_text",
        r"\b(CC3220SF)\b",
    ),
)


# Order matters: put narrower selectors before family selectors.
MAPPING_RULES = (
    ("adi-aducm36", "Analog Devices", r"^ADUCM36", "tcl/target/aducm360.cfg"),
    ("adi-max32620", "Analog Devices", r"^MAX32620$", "tcl/target/max32620.cfg"),
    ("adi-max32625", "Analog Devices", r"^MAX32625", "tcl/target/max32625.cfg"),
    ("adi-max3263", "Analog Devices", r"^MAX3263", "tcl/target/max3263x.cfg"),
    ("adi-max32650", "Analog Devices", r"^MAX32650", "tcl/target/max32650.cfg"),
    ("adi-max32655", "Analog Devices", r"^MAX32655", "tcl/target/max32655.cfg"),
    ("adi-max32660", "Analog Devices", r"^MAX32660", "tcl/target/max32660.cfg"),
    ("adi-max32662", "Analog Devices", r"^MAX32662", "tcl/target/max32662.cfg"),
    ("adi-max32670", "Analog Devices", r"^MAX32670", "tcl/target/max32670.cfg"),
    ("adi-max32672", "Analog Devices", r"^MAX32672", "tcl/target/max32672.cfg"),
    ("adi-max32675", "Analog Devices", r"^MAX32675", "tcl/target/max32675.cfg"),
    ("adi-max32680", "Analog Devices", r"^MAX32680", "tcl/target/max32680.cfg"),
    ("adi-max32690", "Analog Devices", r"^MAX32690", "tcl/target/max32690.cfg"),
    ("artery-at32f4", "Artery", r"^AT32F4", "tcl/target/artery/at32f4x.cfg"),
    ("bouffalo-bl602", "Bouffalo Lab", r"^BL60[24]$", "tcl/target/bl602.cfg"),
    ("bouffalo-bl702l", "Bouffalo Lab", r"^BL70[24]L$", "tcl/target/bl702l.cfg"),
    ("bouffalo-bl702", "Bouffalo Lab", r"^BL70[246]$", "tcl/target/bl702.cfg"),
    ("fujitsu-fm4-mb9bf", "Cypress/Fujitsu", r"^MB9BF", "tcl/target/fm4_mb9bf.cfg"),
    ("fujitsu-fm4-s6e2cc", "Cypress/Fujitsu", r"^S6E2CC", "tcl/target/fm4_s6e2cc.cfg"),
    ("fujitsu-fm3", "Cypress/Fujitsu", r"^MB9[AB]", "tcl/target/fm3.cfg"),
    ("geehy-apm32f0", "Geehy", r"^APM32F0", "tcl/target/geehy/apm32f0x.cfg"),
    ("geehy-apm32f1", "Geehy", r"^APM32F1", "tcl/target/geehy/apm32f1x.cfg"),
    ("geehy-apm32f4", "Geehy", r"^APM32F4", "tcl/target/geehy/apm32f4x.cfg"),
    ("gigadevice-gd32e23", "GigaDevice", r"^GD32E23", "tcl/target/gigadevice/gd32e23x.cfg"),
    ("gigadevice-gd32vf103", "GigaDevice", r"^GD32VF103", "tcl/target/gigadevice/gd32vf103.cfg"),
    ("holtek-ht32f4", "Holtek", r"^HT32F4", "tcl/target/holtek/ht32f4x.cfg"),
    ("microchip-atmega128rfa1", "Microchip", r"^ATMEGA128RFA1$", "tcl/target/atmega128rfa1.cfg"),
    ("microchip-atmega128", "Microchip", r"^ATMEGA128$", "tcl/target/atmega128.cfg"),
    ("microchip-atmega32u4", "Microchip", r"^ATMEGA32U4$", "tcl/target/atmega32u4.cfg"),
    ("microchip-pic32mx", "Microchip", r"^PIC32MX", "tcl/target/pic32mx.cfg"),
    ("microchip-sam7x256", "Microchip", r"^AT91SAM7X256$", "tcl/target/at91sam7x256.cfg"),
    ("microchip-sam7x512", "Microchip", r"^AT91SAM7X512$", "tcl/target/at91sam7x512.cfg"),
    ("microchip-sam7s", "Microchip", r"^AT91SAM7S(?:64|128|256)$", "tcl/target/at91sam7sx.cfg"),
    ("microchip-samg5", "Microchip", r"^ATSAMG5", "tcl/target/at91samg5x.cfg"),
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
    ("raspberry-rp2040", "Raspberry Pi", r"^RP2040$", "tcl/target/rp2040.cfg"),
    ("raspberry-rp2350", "Raspberry Pi", r"^RP2350[AB]$", "tcl/target/rp2350.cfg"),
    ("st-bluenrg", "STMicroelectronics", r"^BlueNRG", "tcl/target/bluenrg-x.cfg"),
    ("st-stm32h7rs", "STMicroelectronics", r"^STM32H7[RS]", "tcl/target/stm32h7rsx.cfg"),
    ("st-stm32wba2", "STMicroelectronics", r"^STM32WBA2", "tcl/target/stm32wba2x.cfg"),
    ("st-stm32wba5", "STMicroelectronics", r"^STM32WBA5", "tcl/target/stm32wba5x.cfg"),
    ("st-stm32wba6", "STMicroelectronics", r"^STM32WBA6", "tcl/target/stm32wba6x.cfg"),
    ("st-stm32wb", "STMicroelectronics", r"^STM32WB", "tcl/target/stm32wbx.cfg"),
    ("st-stm32wl", "STMicroelectronics", r"^STM32WL", "tcl/target/stm32wlx.cfg"),
    ("ti-cc13x0", "Texas Instruments", r"^CC13(?:10|50)$", "tcl/target/ti/cc13x0.cfg"),
    ("ti-cc13x2", "Texas Instruments", r"^CC13(?:12R|52[PR])$", "tcl/target/ti/cc13x2.cfg"),
    ("ti-cc26x0", "Texas Instruments", r"^CC26(?:40|50)$", "tcl/target/ti/cc26x0.cfg"),
    ("ti-cc26x2x7", "Texas Instruments", r"^CC2652[PR]7$", "tcl/target/ti/cc26x2x7.cfg"),
    ("ti-cc26x2", "Texas Instruments", r"^CC26(?:42R|52(?:P|R|RB))$", "tcl/target/ti/cc26x2.cfg"),
    ("ti-cc3220sf", "Texas Instruments", r"^CC3220SF$", "tcl/target/ti/cc3220sf.cfg"),
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


def target_architectures(openocd_root: Path, includes: list[str]) -> list[str]:
    found: set[str] = set()
    for include in includes:
        text = (openocd_root / include).read_text(encoding="utf-8", errors="replace")
        for match in (*TARGET_RE.finditer(text), *ESP_ARCH_RE.finditer(text)):
            architecture = TARGET_ARCHITECTURES.get(match.group("type"))
            if architecture:
                found.add(architecture)
    return sorted(found)


def capability_status(target_config: str, classification_status: str, banks: list[dict[str, str]]) -> tuple[str, str]:
    stem = Path(target_config).stem.lower()
    concrete = {bank["driver"] for bank in banks if bank["driver"] != "virtual"}
    if (
        target_config in HELPER_TARGETS
        or classification_status == "Internal/helper"
        or stem.endswith("_common")
        or "dual_bank" in stem
    ):
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
                "vendor": VENDOR_OVERRIDES.get(target["target_config"], target["vendor"]),
                "series": target["series"],
                "target_config": target["target_config"],
                "device_type": target["device_type"],
                "classification_status": target["classification_status"],
                "cpu_architectures": target_architectures(openocd_root, includes),
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
    return urljoin(base.rstrip("/") + "/", f"{element.get('vendor', '')}.{element.get('name', '')}.pdsc")


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


def identifier_kind(name: str, source_kind: str = "cmsis_pdsc") -> str:
    if re.search(r"(?:_xx|x(?:tr)?$|xxx)", name, re.IGNORECASE):
        return "ordering_pattern"
    if source_kind in {"vendor_board_archive", "vendor_product_page"}:
        return "manufacturer_part_number"
    return "cmsis_device_name"


def find_rule(vendor: str, part_number: str, source_pack_name: str) -> tuple[str, str] | None:
    # Rules are intentionally ordered from the narrowest selector to the
    # broader family fallback.  The exported rule ID preserves which selector
    # won, so overlaps stay auditable.
    for rule_id, rule_vendor, pattern, target_config in MAPPING_RULES:
        if vendor == "Cypress/Fujitsu":
            if rule_id.startswith("fujitsu-fm4-") and source_pack_name.startswith("FM3"):
                continue
            if rule_id == "fujitsu-fm3" and not source_pack_name.startswith("FM3"):
                continue
        if vendor == rule_vendor and re.search(pattern, part_number, re.IGNORECASE):
            return rule_id, target_config
    return None


def load_sources(index_path: Path, cache: Path) -> list[dict[str, str]]:
    root = ET.parse(index_path).getroot()
    available = {(node.get("vendor", ""), node.get("name", "")): node for node in root.findall(".//pdsc")}
    pending: list[tuple[PackSpec | VendorSourceSpec, str, Path, str]] = []
    for spec in PACK_SPECS:
        element = available.get((spec.pack_vendor, spec.pack_name))
        if element is None and not spec.source_url:
            raise RuntimeError(f"pack missing from index: {spec.pack_vendor}.{spec.pack_name}")
        url = spec.source_url or pack_url(element)
        path = cache / f"{spec.pack_vendor}.{spec.pack_name}.pdsc"
        pending.append((spec, url, path, element.get("version", "") if element is not None else ""))
    for spec in VENDOR_SOURCES:
        suffix = ".tar.gz" if spec.source_kind == "vendor_board_archive" else ".txt"
        pending.append((spec, spec.source_url, cache / f"{spec.source_name}{suffix}", spec.source_commit))

    def fetch(item: tuple[PackSpec | VendorSourceSpec, str, Path, str]) -> dict[str, str]:
        spec, url, path, version = item
        download(url, path)
        content_hash = sha256(path)
        if isinstance(spec, VendorSourceSpec) and spec.expected_content_sha256:
            if content_hash != spec.expected_content_sha256:
                raise RuntimeError(f"authoritative source content changed: {spec.source_name}")
        if isinstance(spec, PackSpec):
            # Parsing here also rejects HTML error pages cached under a PDSC name.
            root = ET.parse(path).getroot()
            release = root.find("./releases/release")
            actual_version = release.get("version", "") if release is not None else ""
            if version and actual_version and version != actual_version:
                raise RuntimeError(f"pack index/PDSC version mismatch: {spec.pack_vendor}.{spec.pack_name}")
            return {
                "silicon_vendor": spec.silicon_vendor,
                "pack_vendor": spec.pack_vendor,
                "pack_name": spec.pack_name,
                "pack_version": version or actual_version,
                "source_kind": "cmsis_pdsc",
                "source_url": url,
                "content_sha256": content_hash,
                "path": str(path),
            }
        return {
            "silicon_vendor": spec.silicon_vendor,
            "pack_vendor": spec.source_name.split(".", 1)[0],
            "pack_name": spec.source_name.split(".", 1)[1],
            "pack_version": version,
            "source_kind": spec.source_kind,
            "device_pattern": spec.device_pattern,
            "source_url": url,
            "content_sha256": content_hash,
            "path": str(path),
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        sources = list(executor.map(fetch, pending))
    return sources


def extract_source_devices(
    source: dict[str, str], openocd_root: Path
) -> list[dict[str, str]]:
    path = Path(source["path"])
    if source["source_kind"] == "cmsis_pdsc":
        return extract_devices(path, source)

    names: set[str] = set()
    if source["source_kind"] in {"vendor_sdk_text", "vendor_product_page"}:
        names.update(
            name.upper()
            for name in re.findall(source["device_pattern"], path.read_text(encoding="utf-8"))
        )
    elif source["source_kind"] == "vendor_board_archive":
        driver_source = (openocd_root / "src/flash/nor/artery.c").read_text(encoding="utf-8")
        supported = set(re.findall(r'\.name\s*=\s*"(AT32[^\"]+)"', driver_source))
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                if not member.isfile() or "/boards/" not in member.name or not member.name.endswith(".json"):
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                name = str(json.load(handle).get("build", {}).get("mcu", "")).upper()
                if name in supported:
                    names.add(name)
    else:
        raise RuntimeError(f"unsupported authoritative source kind: {source['source_kind']}")

    return [
        {
            "vendor": source["silicon_vendor"],
            "family": re.match(r"^[A-Z]+\d+", name).group(0),
            "subfamily": "",
            "part_number": name,
            "cmsis_device": name,
        }
        for name in sorted(names)
    ]


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


def build_canonical_catalog(
    openocd_root: Path,
    researched_csvs: list[Path],
    mapped_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    canonical: dict[tuple[str, str], dict[str, object]] = {}
    conflicts: list[dict[str, object]] = []
    architecture_cache: dict[str, list[str]] = {}

    for path in researched_csvs:
        with path.open(encoding="utf-8", newline="") as handle:
            for source in csv.DictReader(handle):
                architecture = architecture_cache.get(source["target_config"])
                if architecture is None:
                    includes, _ = include_graph(openocd_root, source["target_config"])
                    architecture = target_architectures(openocd_root, includes)
                    architecture_cache[source["target_config"]] = architecture
                row: dict[str, object] = {
                    "vendor": source["vendor"],
                    "part_number": source["part_number"],
                    "identifier_kind": source["identifier_kind"],
                    "cpu_architectures": architecture,
                    "target_config": source["target_config"],
                    "openocd_distribution": "openocd-esp32" if source["vendor"] == "Espressif" else "upstream-openocd",
                    "mapping_status": "mapping_candidate",
                    "validation_status": "not_verified",
                    "catalog_origin": path.name,
                }
                key = (source["vendor"], source["part_number"].upper())
                if key in canonical:
                    raise RuntimeError(f"duplicate identifier already exists in the baseline catalogs: {key}")
                canonical[key] = row

    for source in mapped_rows:
        row = {
            "vendor": source["vendor"],
            "part_number": source["part_number"],
            "identifier_kind": source["identifier_kind"],
            "cpu_architectures": source["cpu_architectures"],
            "target_config": source["target_config"],
            "openocd_distribution": source["openocd_distribution"],
            "mapping_status": source["mapping_status"],
            "validation_status": source["validation_status"],
            "catalog_origin": "openocd-parts-expanded.csv",
        }
        key = (str(source["vendor"]), str(source["part_number"]).upper())
        previous = canonical.get(key)
        if previous is not None:
            if previous["target_config"] == row["target_config"]:
                continue
            conflicts.append(
                {
                    "vendor": row["vendor"],
                    "part_number": row["part_number"],
                    "superseded_target_config": previous["target_config"],
                    "selected_target_config": row["target_config"],
                    "resolution": "prefer_specific_expansion_mapping",
                }
            )
        canonical[key] = row

    return (
        sorted(canonical.values(), key=lambda row: (str(row["vendor"]), str(row["part_number"]))),
        sorted(conflicts, key=lambda row: (str(row["vendor"]), str(row["part_number"]))),
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
        for device in extract_source_devices(source, args.openocd_root):
            match = find_rule(device["vendor"], device["part_number"], source["pack_name"])
            if match is None:
                continue
            rule_id, target_config = match
            capability = capability_by_target.get(target_config)
            if capability is None or capability["capability_status"] != "flash_driver_declared":
                continue
            row: dict[str, object] = {
                **device,
                "identifier_kind": identifier_kind(device["part_number"], source["source_kind"]),
                "target_config": target_config,
                "cpu_architectures": capability["cpu_architectures"],
                "flash_drivers": capability["flash_drivers"],
                "openocd_distribution": "upstream-openocd",
                "openocd_commit": OPENOCD_COMMIT,
                "source_pack_vendor": source["pack_vendor"],
                "source_pack_name": source["pack_name"],
                "source_pack_version": source["pack_version"],
                "source_kind": source["source_kind"],
                "source_url": source["source_url"],
                "source_content_sha256": source["content_sha256"],
                "mapping_rule_id": rule_id,
                "mapping_status": "mapping_candidate",
                "validation_status": "not_verified",
            }
            key = (device["vendor"], device["part_number"].upper(), target_config)
            mapped.setdefault(key, row)
    mapped_rows = sorted(mapped.values(), key=lambda row: (str(row["vendor"]), str(row["part_number"]), str(row["target_config"])))
    canonical_rows, duplicate_resolutions = build_canonical_catalog(
        args.openocd_root, args.researched_csv, mapped_rows
    )

    mapping_counts = Counter(str(row["target_config"]) for row in mapped_rows)
    outcomes: list[dict[str, object]] = []
    for capability in capabilities:
        target_config = str(capability["target_config"])
        count = mapping_counts[target_config]
        status = str(capability["capability_status"])
        if count:
            outcome = "mapped"
            reason = "One or more deterministic identifiers were found in a pinned authoritative source"
        elif status != "flash_driver_declared":
            outcome = "deferred"
            reason = str(capability["capability_reason"])
        else:
            outcome = "source_adapter_pending"
            reason = "No identifier matched the implemented authoritative source adapters and mapping rules"
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
        "cpu_architectures", "capability_status", "capability_reason", "flash_drivers", "flash_banks",
        "include_graph", "openocd_distribution", "openocd_commit", "validation_status",
    ]
    mapped_fields = [
        "vendor", "family", "subfamily", "part_number", "identifier_kind", "cmsis_device",
        "target_config", "cpu_architectures", "flash_drivers", "openocd_distribution", "openocd_commit",
        "source_pack_vendor", "source_pack_name", "source_pack_version", "source_kind", "source_url",
        "source_content_sha256", "mapping_rule_id", "mapping_status", "validation_status",
    ]
    outcome_fields = [
        "vendor", "target_config", "capability_status", "expansion_outcome",
        "mapped_identifier_count", "reason", "validation_status",
    ]
    write_csv(args.output_dir / "openocd-target-capabilities.csv", capability_fields, capabilities)
    write_csv(args.output_dir / "openocd-parts-expanded.csv", mapped_fields, mapped_rows)
    write_csv(args.output_dir / "openocd-expansion-outcomes.csv", outcome_fields, outcomes)
    write_csv(
        args.output_dir / "openocd-parts-canonical.csv",
        [
            "vendor", "part_number", "identifier_kind", "cpu_architectures", "target_config",
            "openocd_distribution", "mapping_status", "validation_status", "catalog_origin",
        ],
        canonical_rows,
    )
    write_csv(
        args.output_dir / "openocd-duplicate-resolutions.csv",
        ["vendor", "part_number", "superseded_target_config", "selected_target_config", "resolution"],
        duplicate_resolutions,
    )

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
                    "source_count": len(sources),
                    "source_pack_count": sum(source["source_kind"] == "cmsis_pdsc" for source in sources),
                    "mapped_identifier_count": len(mapped_rows),
                    "mapped_target_count": len(mapping_counts),
                    "canonical_identifier_count": len(canonical_rows),
                    "canonical_target_count": len({str(row["target_config"]) for row in canonical_rows}),
                    "cross_catalog_duplicate_count": len(duplicate_resolutions),
                    "identifier_kinds": dict(Counter(str(row["identifier_kind"]) for row in mapped_rows)),
                },
                "devices": mapped_rows,
            },
            ensure_ascii=False,
            separators=(",", ":"),
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
    architecture_counts = Counter(
        architecture
        for row in canonical_rows
        for architecture in row["cpu_architectures"]
    )
    pdsc_count = sum(source["source_kind"] == "cmsis_pdsc" for source in sources)
    report = [
        "# OpenOCD MCU Part-Number Expansion Report",
        "",
        f"OpenOCD source commit: `{OPENOCD_COMMIT}`",
        "",
        "## Current execution result",
        "",
        f"- MCU/Wireless MCU CFG candidates evaluated: **{len(capabilities)}**",
        f"- CFG files with deterministic authoritative-source mappings: **{len(mapping_counts)}**",
        f"- Unique device identifiers mapped: **{len(mapped_rows)}**",
        f"- CMSIS/vendor device names: **{kind_counts['cmsis_device_name']}**",
        f"- Manufacturer ordering part numbers: **{kind_counts['manufacturer_part_number']}**",
        f"- Ordering patterns: **{kind_counts['ordering_pattern']}**",
        f"- Pinned PDSC sources parsed: **{pdsc_count}**",
        f"- Pinned vendor SDK/board/product sources parsed: **{len(sources) - pdsc_count}**",
        f"- Canonical unique identifiers across baseline and expansion: **{len(canonical_rows)}**",
        f"- Canonical unique target CFG files: **{len({str(row['target_config']) for row in canonical_rows})}**",
        f"- Baseline/expansion target conflicts resolved: **{len(duplicate_resolutions)}**",
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
    report.extend(["", "## Canonical identifiers by CPU architecture", "", "| CPU architecture | Identifiers |", "|---|---:|"])
    report.extend(f"| {architecture} | {count} |" for architecture, count in sorted(architecture_counts.items()))
    report.extend(
        [
            "",
            "## Outcome interpretation",
            "",
            "- `mapped`: a pinned authoritative source plus one deterministic rule selected the Target CFG.",
            "- `source_adapter_pending`: Flash is declared, but the current automated sources/rules are insufficient.",
            "- `deferred`: the CFG is a helper/alias or resolves only an external/general-purpose Flash bank.",
            "- Canonical deduplication prefers the narrower expansion rule when a baseline family CFG overlaps.",
            "- A dual-architecture device appears once in the canonical CSV and once under each supported architecture.",
            "",
        ]
    )
    (args.output_dir / "expansion-report.md").write_text("\n".join(report).rstrip() + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "metadata": metadata,
                "outcomes": outcome_counts,
                "mapped": len(mapped_rows),
                "mapped_targets": len(mapping_counts),
                "canonical": len(canonical_rows),
                "duplicates_resolved": len(duplicate_resolutions),
            },
            default=dict,
        )
    )


if __name__ == "__main__":
    main()
