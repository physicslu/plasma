"""Pure host-only reviewers for the proposed PLASMA fixed-image ABI.

This module never discovers /sys, opens devices, maps memory, loads FPGA images,
executes commands or grants a hardware capability. The input is untrusted
JSON/fixture data; every function must fail closed on ambiguity.
"""
from __future__ import annotations

import json
from pathlib import Path


class ContractError(ValueError):
    """A proposed layout, resource, Site, or command is not admissible."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _natural(value: object, *, lo: int = 0, hi: int = 0xFFFFFFFF) -> bool:
    return type(value) is int and lo <= value <= hi


def validate_abi(spec: dict) -> dict:
    """Check an offline JSON contract, NOT physical RTL or ABI readback."""
    _require(type(spec) is dict, "ABI must be an object")
    _require(spec.get("contract") == "plasma-universal-fixed-fpga-abi-v1-gate1", "Wrong ABI contract")
    _require(spec.get("status") == "review_candidate_not_implemented", "Hardware status inflated")
    hw, wire, geom = (spec.get(k, {}) for k in ("hardware", "transport", "geometry"))
    _require(hw.get("development_soc") == "XC7Z020-1CLG400C", "Wrong development SoC")
    _require(hw.get("image_lifecycle") == "FIXED_PER_BOOT", "Not a fixed image")
    _require(hw.get("runtime_fpga_reload_supported") is False, "Runtime FPGA reload forbidden")
    _require(hw.get("full_reload_in_regular_job") is False, "Job load forbidden")
    _require(hw.get("axi_base_source") == "VERIFIED_BOARD_DESCRIPTOR_NOT_HTTP", "Untrusted base")
    _require(hw.get("sites_physically_verified") == 0, "Cannot manufacture physical Sites")
    _require(hw.get("site_count_ceiling") == 8, "Eight-Site ceiling required")
    _require(wire.get("endianness") == "little" and wire.get("access_bits") == 32
             and wire.get("alignment_bytes") == 4, "Unexpected wire width")
    _require(wire.get("irq_v1") is False and wire.get("dma_v1") is False, "IRQ/DMA not qualified")
    _require(wire.get("map_policy") == "SINGLE_UIO_MAP0_CANDIDATE_NOT_QUALIFIED", "Incorrect map policy")
    _require(geom == {
        "aperture_bytes": 4096, "identity_base": 0, "global_base": 4096,
        "shared_reserved": [8192, 12288], "sites_base": 16384,
        "site_stride": 4096, "site_count": 8, "reserved_tail_base": 49152
    }, "ABI geometry changed without review")
    _require(hw.get("ppu_window_bytes") == 65536, "Window mismatch")
    _require(spec.get("capabilities") == {
        "SWD": 0, "SPI": 1, "JTAG_RESERVED": 2,
        "I2C_RESERVED": 3, "ICSP_RESERVED": 4
    }, "Capability numbering not frozen")
    _require(spec.get("protocols") == {"SWD": 1, "SPI": 2}, "Protocol numbering changed")
    _require(spec.get("commands") == {
        "SWD_XFER": 1, "SWD_LINE_RESET": 2, "SPI_TRANSFER": 3
    }, "Command numbering changed")
    expected_results = ["OK", "SWD_WAIT", "SWD_FAULT", "SWD_NO_ACK",
                        "PARITY", "TIMEOUT", "ABORTED", "BAD_ARGUMENT",
                        "ENGINE_UNAVAILABLE", "INTERNAL_FAULT"]
    _require(spec.get("results") == {name: i for i, name in enumerate(expected_results)},
             "Result numbering changed")
    regions = spec.get("regions")
    _require(type(regions) is list and len(regions) == 13, "Wrong region count")
    expected = ([("identity", 0, 4096, "registers"),
                 ("global", 4096, 4096, "registers"),
                 ("shared_0_reserved", 8192, 4096, "reserved"),
                 ("shared_1_reserved", 12288, 4096, "reserved")]
                + [(f"site_{i}", 16384 + (i-1)*4096, 4096, "site") for i in range(1, 9)]
                + [("tail_reserved", 49152, 16384, "reserved")])
    for region, (name, base, size, kind) in zip(regions, expected):
        _require((region.get("name"), region.get("base"), region.get("size"),
                  region.get("kind")) == (name, base, size, kind),
                 f"Wrong region: {name}")
        if kind == "site":
            _require(region.get("site_id") == int(name.split("_")[-1]), "Site identity mismatch")
        registers = region.get("registers")
        _require(type(registers) is list, "No register list")
        _require((kind == "reserved") == (len(registers) == 0),
                 "Reserved regions must have no registers")
        seen: set[int] = set()
        names: set[str] = set()
        for reg in registers:
            offset = reg.get("offset")
            _require(_natural(offset, hi=size-4) and offset % 4 == 0,
                     "Invalid register offset/alignment")
            _require(reg.get("name") not in names and offset not in seen,
                     "Duplicate register")
            _require(reg.get("access") in ("ro", "wo"), "Ambiguous RMW access")
            _require(type(reg.get("semantics")) is str and bool(reg["semantics"].strip()),
                     "Undefined register semantics")
            seen.add(offset)
            names.add(reg["name"])
    sites = regions[4:12]
    _require(all(s["registers"] == sites[0]["registers"] for s in sites),
             "Site register schemas diverge")
    ids = {r["name"]: (r["offset"], r["access"]) for r in regions[0]["registers"]}
    site = {r["name"]: (r["offset"], r["access"]) for r in sites[0]["registers"]}
    _require(ids.get("MAGIC") == (0, "ro") and
             ids.get("ABI_VERSION") == (4, "ro") and
             ids.get("SITE_PRESENT_BITMAP") == (48, "ro") and
             ids.get("SITE_READY_BITMAP") == (52, "ro"), "Identity contract missing")
    exact = {
        "SITE_ID": (0, "ro"), "SITE_ABI_VERSION": (4, "ro"),
        "SITE_CAPABILITIES": (8, "ro"), "SITE_STATUS": (12, "ro"),
        "SITE_ERROR": (16, "ro"), "INFLIGHT_SEQ": (20, "ro"),
        "RX_WORDS_AVAILABLE": (24, "ro"), "TX_WORDS_FREE": (28, "ro"),
        "COMMAND": (32, "wo"), "SEQUENCE": (36, "wo"),
        "PROTOCOL": (40, "wo"), "FLAGS": (44, "wo"),
        "BIT_COUNT": (48, "wo"), "ARG0": (52, "wo"),
        "WDATA": (56, "wo"), "TIMEOUT_TICKS": (60, "wo"),
        "TX_DATA": (64, "wo"), "RX_DATA": (68, "ro"),
        "DONE_SEQ": (72, "ro"), "DONE_STATUS": (76, "ro"),
        "DONE_WORDS": (80, "ro"), "ABORT": (84, "wo"),
        "CAPACITY_WORDS": (88, "ro"), "CLOCK_DIV": (92, "wo"),
        "DONE_DATA": (96, "ro"), "ACK_SEQ": (100, "wo"),
        "TRANSACTION_COUNTER": (104, "ro")
    }
    _require(site == exact, "Required data-plane register layout changed")
    sw = spec.get("software_contract", {})
    _require(sw.get("broker") == "ONE_PRIVILEGED_BACKEND_OWNER_PER_PPU"
             and sw.get("register_policy") == "DENY_RESERVED_REGIONS_AND_UNLISTED_OFFSETS"
             and sw.get("fpga_manager") == "NO_RUNTIME_RELOAD_IN_V1", "Software policy missing")
    q = spec.get("qualification", {})
    _require(q.get("hardware_authority") is False and
             q.get("real_z2_abi_readback") is False and
             q.get("eight_site_hil") is False and
             q.get("m1_architecture_freeze") == "NO_GO_PENDING_OWNER_REVIEW",
             "Unqualified hardware acceptance")
    return {"status": "HOST_CONTRACT_VALID", "hardware_authority": False,
            "real_z2_hil": "NOT_RUN", "m1": "NO_GO", "site_count_ceiling": 8}


def select_uio_resource(snapshot: list[dict], pin: dict) -> dict:
    """Select one exact physical resource despite uioN renumbering.

    Snapshot is provided by a Host test; no sysfs/dev paths are read here.
    All competing physical overlaps fail closed even if names differ.
    """
    _require(type(snapshot) is list and bool(snapshot) and type(pin) is dict,
             "Missing UIO inventory or Board Descriptor")
    fields = ("label", "platform_device", "driver", "map_index",
              "physical_base", "size", "byte_offset")
    for key in fields:
        _require(key in pin, f"Board pin missing {key}")
    _require(_natural(pin["physical_base"]) and
             _natural(pin["size"], lo=4, hi=0x1000000) and
             pin["physical_base"] + pin["size"] <= 0x100000000, "Invalid pin window")
    _require(pin["physical_base"] % 4096 == pin["byte_offset"] and
             _natural(pin["map_index"], hi=7), "Invalid map selector or page offset")
    selected = []
    lo, hi = pin["physical_base"], pin["physical_base"] + pin["size"]
    names: set[str] = set()
    for resource in snapshot:
        _require(type(resource) is dict and
                 all(k in resource for k in (*fields, "device_name")), "Incomplete UIO record")
        name = resource["device_name"]
        _require(type(name) is str and name.startswith("uio") and
                 name[3:].isdigit() and name not in names, "Ambiguous UIO inventory")
        names.add(name)
        start, size = resource["physical_base"], resource["size"]
        _require(_natural(start) and _natural(size, lo=4, hi=0x1000000)
                 and start+size <= 0x100000000, "Invalid UIO resource")
        match = all(resource[k] == pin[k] for k in fields)
        if start < hi and lo < start + size:
            _require(match, "Competing/changed physical UIO resource")
        if match:
            selected.append(resource)
    _require(len(selected) == 1, "Required UIO resource missing or not unique")
    return dict(selected[0])


def admit_host_transaction(spec: dict, broker: dict, lease: dict, command: dict) -> dict:
    """Validate a proposed Site command; return a PLAN, never write registers."""
    validate_abi(spec)
    _require(type(broker) is dict and type(lease) is dict and
             type(command) is dict, "Invalid host transaction")
    _require(broker.get("state") == "READY" and
             broker.get("hardware_authority") is False and
             broker.get("runtime_reload") is False, "Broker is not a safe Host model")
    site = lease.get("site_id")
    _require(_natural(site, lo=1, hi=8) and
             broker.get("site_present_bitmap", 0) & (1 << (site - 1)) and
             broker.get("site_ready_bitmap", 0) & (1 << (site - 1)),
             "Site not present/ready")
    _require(lease.get("active") is True and
             lease.get("generation") == broker.get("generation") and
             lease.get("epoch") == broker.get("epoch") and
             lease.get("site_id") not in broker.get("busy_sites", []),
             "Site lease not exclusive/current/idle")
    ic = broker.get("exact_ic")
    _require(type(ic) is str and bool(ic.strip()) and
             lease.get("exact_ic") == ic, "Mixed/unknown exact IC batch")
    name = command.get("opcode")
    _require(name in spec["commands"], "Unknown/unsupported command")
    protocol = "SPI" if name == "SPI_TRANSFER" else "SWD"
    _require(command.get("protocol") == protocol, "Opcode/protocol mismatch")
    _require(broker.get("capabilities", 0) & (1 << spec["capabilities"][protocol]),
             "Protocol not present")
    seq, bits, ticks, div, flags, arg, data = (
        command.get(k) for k in ("sequence", "bit_count", "timeout_ticks",
                                 "clock_div", "flags", "arg0", "wdata"))
    _require(_natural(seq, lo=1) and _natural(ticks, lo=1) and
             _natural(div, lo=1, hi=65535) and _natural(flags) and
             _natural(arg) and _natural(data), "Invalid command fields")
    capacity = broker.get("capacity_words")
    max_bits = broker.get("max_transfer_bits")
    _require(_natural(capacity, lo=1, hi=256) and
             _natural(max_bits, lo=8, hi=8192) and max_bits % 8 == 0,
             "Hardware capability not bounded")
    words = command.get("tx_words", [])
    _require(type(words) is list and
             all(_natural(w) for w in words) and len(words) <= capacity,
             "Invalid TX FIFO words")
    if name == "SWD_XFER":
        _require(bits == 32 and arg <= 15 and flags == 0 and not words, "Bad SWD transfer")
    elif name == "SWD_LINE_RESET":
        _require(_natural(bits, lo=50, hi=128) and
                 flags == 0 and arg == 0 and data == 0 and not words,
                 "Bad SWD line reset")
    elif name == "SPI_TRANSFER":
        _require(_natural(bits, lo=8, hi=max_bits) and bits % 8 == 0 and
                 arg <= 3 and flags in (0, 1) and data == 0 and
                 len(words) == (bits+31)//32, "Bad SPI transfer")
        rem = bits % 32
        _require(not rem or words[-1] < (1 << rem), "Nonzero unused SPI TX padding")
    return {"status": "HOST_PLAN_ONLY", "hardware_authority": False,
            "site_id": site, "sequence": seq, "opcode": name,
            "writes": [("SEQUENCE", seq), ("PROTOCOL", spec["protocols"][protocol]),
                       ("FLAGS", flags), ("BIT_COUNT", bits), ("ARG0", arg),
                       ("WDATA", data), ("TIMEOUT_TICKS", ticks), ("CLOCK_DIV", div),
                       *[("TX_DATA", word) for word in words],
                       ("BARRIER_REQUIRED", 0),
                       ("COMMAND", spec["commands"][name])]}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Offline fixed FPGA ABI v1 validator")
    parser.add_argument("spec", type=Path)
    args = parser.parse_args()
    try:
        result = validate_abi(json.loads(args.spec.read_text(encoding="utf-8")))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, ContractError) as exc:
        print(json.dumps({"status": "REJECTED", "hardware_authority": False,
                          "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
