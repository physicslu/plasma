#!/usr/bin/env python3
"""Host-only validation of the proposed PYNQ-Z2 MPE two-Site architecture.

This checks a design contract, NOT synthesizable RTL, Image admission, MMIO,
electrical safety or real Blue Pill SWD/DPIDR.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


class ArchitectureRejected(ValueError):
    pass


def need(condition: bool, reason: str) -> None:
    if not condition:
        raise ArchitectureRejected(reason)


def num(value: str) -> int:
    need(isinstance(value, str) and value.startswith("0x"), "HEX_REQUIRED")
    return int(value, 16)


EXPECTED_PINS = {
    1: ("JA", "Y18", "Y19"),
    2: ("JB", "W14", "Y14"),
}
EXPECTED_OPS = {
    "LINE_RESET", "SWJ_SEQUENCE", "DP_READ", "DP_WRITE",
    "AP_READ", "AP_WRITE", "IDLE_CYCLES",
}
EXPECTED_REGISTERS = (
    ("SITE_ID_CAP", 0x00, "R"),
    ("STATUS", 0x04, "R"),
    ("CLK_HALF_PERIOD", 0x08, "RW_IDLE"),
    ("TIMEOUT_CYCLES", 0x0C, "RW_IDLE"),
    ("TX_DATA", 0x10, "W"),
    ("CMD_PUSH", 0x14, "W_ATOMIC"),
    ("COMPLETION_META", 0x18, "R"),
    ("COMPLETION_DATA", 0x1C, "R"),
    ("COMPLETION_POP", 0x20, "W_TAGGED"),
    ("FIFO_LEVELS", 0x24, "R"),
    ("CONTROL", 0x28, "W"),
    ("ERROR_LATCH", 0x2C, "R"),
    ("IRQ_ENABLE", 0x30, "RW"),
    ("IRQ_STATUS", 0x34, "RW1C"),
)


def validate(obj: dict) -> dict:
    need(isinstance(obj, dict), "MANIFEST_OBJECT_REQUIRED")
    need(obj.get("schema") == "plasma.mpe.architecture.v1", "SCHEMA_MISMATCH")
    need(obj.get("status") == "RTL_SLICE_SOURCE_ONLY_UNVERIFIED",
         "FALSE_IMPLEMENTATION_CLAIM")
    need(obj.get("image_family") == "plasma.mpe.swd.v1", "FAMILY_MISMATCH")
    need(obj.get("board") == "pynq-z2" and
         obj.get("fpga_part") == "xc7z020clg400-1", "BOARD_MISMATCH")
    need(obj.get("site_ids_one_based") is True and
         type(obj.get("site_count")) is int and obj["site_count"] == 2 and
         type(obj.get("expandable_max_sites")) is int and
         obj["expandable_max_sites"] == 8, "SITE_GEOMETRY_MISMATCH")
    need(obj.get("engine_per_site") ==
         "independent_clock_fsm_iobuf_fifo_irq", "NOT_INDEPENDENT_ENGINES")
    need(obj.get("host_execution") == "Z2_PS_OPENOCD_NATIVE_SWD_ADAPTER" and
         obj.get("ps_to_pl") == "AXI4LITE_TRANSACTION_COMMANDS_NOT_BITBANG",
         "HOST_OR_BITBANG_ARCHITECTURE_MISMATCH")
    bus = obj.get("axi")
    need(isinstance(bus, dict), "AXI_CONTRACT_MISSING")
    base, span = num(bus["base"]), num(bus["span"])
    stride, global_span = num(bus["site_stride"]), num(bus["global_span"])
    need(base == 0x43C00000 and span == 0x10000 and
         base % span == 0 and stride == global_span == 0x1000 and
         bus.get("site_bank_index_origin") == 1 and
         bus.get("data_bits") == 32 and bus.get("fclk_hz") == 100_000_000 and
         bus.get("full_word_write_required") is True and
         8 * stride + 0x1000 <= span, "AXI_GEOMETRY_MISMATCH")
    physical = obj.get("physical")
    need(isinstance(physical, dict) and
         physical.get("io_standard") == "LVCMOS33" and
         physical.get("target_io_voltage") == 3.3 and
         physical.get("no_power_control") is True and
         physical.get("no_external_reset") is True and
         physical.get("swdio_idle") == "HIZ" and
         physical.get("swclk_idle") == 0 and
         physical.get("pmoda_shared_raspberry_pi_header") is True and
         physical.get("other_data_pins") == "HIZ_ONLY",
         "PHYSICAL_ELECTRICAL_SCOPE_MISMATCH")
    sites = obj.get("sites")
    need(isinstance(sites, list) and len(sites) == 2, "TWO_SITES_REQUIRED")
    claimed = set()
    for expected_id, site in enumerate(sites, start=1):
        need(type(site.get("site_id")) is int and
             site["site_id"] == expected_id, "SITE_ID_NOT_ONE_BASED_ORDERED")
        pm, clk, dio = EXPECTED_PINS[expected_id]
        need((site.get("pmod"), site["swclk"]["fpga_pin"],
              site["swdio"]["fpga_pin"]) == (pm, clk, dio) and
             site["swclk"]["pmod_pin"] == 1 and
             site["swdio"]["pmod_pin"] == 2 and
             site.get("ground_pins") == [5, 11],
             "BOARD_PIN_ASSIGNMENT_MISMATCH")
        claimed.update((site["swclk"]["fpga_pin"], site["swdio"]["fpga_pin"]))
        need(len(claimed) == 2 * expected_id, "PHYSICAL_PIN_ALIAS")
        need(base + stride * expected_id + stride <= base + span,
             "SITE_APERTURE_OVERFLOW")
    regs = obj.get("site_registers")
    need(isinstance(regs, list) and len(regs) == len(EXPECTED_REGISTERS),
         "REGISTERS_MISSING")
    found = [(r.get("name"), num(r["offset"]), r.get("access")) for r in regs]
    need(tuple(found) == EXPECTED_REGISTERS, "REGISTER_ABI_MISMATCH")
    need(all(offset % 4 == 0 and offset < stride for _, offset, _ in found),
         "REGISTER_ALIGNMENT_OR_WINDOW_MISMATCH")
    need(set(obj.get("swd_operations", ())) == EXPECTED_OPS and
         len(obj["swd_operations"]) == len(EXPECTED_OPS),
         "SWD_OPERATION_COVERAGE_MISMATCH")
    need(obj.get("command_fifo_depth_target") == 16 and
         obj.get("completion_fifo_depth_target") == 16,
         "FIFO_DEPTH_TARGET_MISMATCH")
    proof = obj.get("proof")
    need(isinstance(proof, dict) and len(proof) >= 7 and
         all(v == "NOT_RUN" for v in proof.values()),
         "FALSE_HARDWARE_OR_SIMULATION_PASS")
    return {
        "status": "ARCHITECTURE_CONTRACT_PASS_HOST_ONLY",
        "site_1": {"connector": "JA", "base": f"0x{base+stride:08X}"},
        "site_2": {"connector": "JB", "base": f"0x{base+2*stride:08X}"},
        "synthesis": "NOT_RUN", "dpidr": "NOT_RUN",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("architecture", nargs="?", type=Path,
                   default=Path(__file__).with_name("architecture.json"))
    args = p.parse_args()
    print(json.dumps(validate(json.loads(args.architecture.read_text())),
                     indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
