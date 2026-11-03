"""Host-only checks for the bd976140 two-Site Image and its HWH (ab79b04e retired).

This does not authorize a Linux MMIO owner or a physical FPGA operation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


SOURCE_SHA = "bd976140e7b76b907db48e9f344be1301a502d49"
BIT_SHA = "6f7c562f269319af058c874f401ca44c9fa3b46dcdb0e9de9f026ec5fd7ce21c"  # Vivado run 41469421780
HWH_SHA = "042892bb59fa8f0d62b54ae6ab47806a592151820c2d9fd9288d21215690010b"
BIN_SHA = "19143158b47e79569b673660315e58cd0765b52c7e60e6258422c437aea3da40"
MANIFEST_SHA = "857228ddff88458edaad040a75a757729b5f2b667c57da7e2c5d245d28fe5222"
SITES = {"swd_site1": (0x43C01000, 0x00050001),
         "swd_site2": (0x43C02000, 0x00050002)}


class IndependentImageDenied(ValueError):
    pass


def require(condition: bool, code: str) -> None:
    if not condition:
        raise IndependentImageDenied(code)


def sha256(path: Path) -> str:
    require(path.is_file() and not path.is_symlink(), "ARTIFACT_MISSING")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(hwh: Path, manifest: Path, *, bit: Path | None = None,
           firmware: Path | None = None) -> dict:
    require(sha256(hwh) == HWH_SHA, "HWH_SHA_MISMATCH")
    require(sha256(manifest) == MANIFEST_SHA, "MANIFEST_SHA_MISMATCH")
    if bit is not None:
        require(sha256(bit) == BIT_SHA, "BIT_SHA_MISMATCH")
    if firmware is not None:
        require(sha256(firmware) == BIN_SHA, "BIN_SHA_MISMATCH")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    require(data["firmware_sha256"] == BIN_SHA and
            data["image_id"] == "z2-independent-swd-v5-bd976140",
            "IMAGE_PAIR_MISMATCH")
    root = ET.parse(hwh).getroot()
    modules = {m.get("INSTANCE"): m for m in root.iter("MODULE")}
    require(set(modules) == {"ps7_0", "axi_interconnect_0",
                             "rst_ps7_0_100M", *SITES}, "HWH_MODULES_MISMATCH")
    ranges = list(root.iter("MEMRANGE"))
    require(len(ranges) == 2, "HWH_SITE_COUNT_MISMATCH")
    actual = {}
    for item in ranges:
        name = item.get("INSTANCE")
        require(name in SITES and name not in actual and
                item.get("MASTERBUSINTERFACE") == "M_AXI_GP0" and
                item.get("SLAVEBUSINTERFACE") == "S_AXI",
                "HWH_AXI_ROUTE_MISMATCH")
        actual[name] = (int(item.get("BASEVALUE"), 0),
                        int(item.get("HIGHVALUE"), 0))
    require(set(actual) == set(SITES), "HWH_SITE_MISSING")
    for name, (base, _) in SITES.items():
        require(actual[name] == (base, base + 0xFFF), "HWH_SITE_RANGE_MISMATCH")
    require(not any(lo <= 0x43C00000 <= hi for lo, hi in actual.values()),
            "HWH_FALSE_GLOBAL_IDENTITY")
    require(data["axi_base"] == SITES["swd_site1"][0] and
            data["axi_bytes"] == 0x2000 and
            data["abi_offset"] == 0 and
            data["abi_version"] == SITES["swd_site1"][1],
            "MANIFEST_AXI_BASE_MISMATCH")
    words = data["identity_words"]
    require(len(words) == 2, "MANIFEST_IDENTITY_COUNT_MISMATCH")
    for (name, (base, value)), word in zip(SITES.items(), words):
        require(len(word) == 3 and word ==
                [base - data["axi_base"], value, 0xFFFFFFFF],
                "MANIFEST_IDENTITY_MISMATCH")
        address = data["axi_base"] + word[0]
        require(actual[name][0] <= address <= actual[name][1] - 3,
                "IDENTITY_OUTSIDE_SITE")
    # A 64-KiB UIO cover is not a Vivado slave or proof of its Linux owner.
    require(data["owner_base"] == 0x43C00000 and
            data["expected_uio"]["maps"] == [[0x43C00000, 0x10000]],
            "MANIFEST_OWNER_GEOMETRY_MISMATCH")
    def ports(name):
        return {p.get("NAME"): p.get("SIGNAME")
                for p in modules[name].iter("PORT")}
    ps, fabric, reset = (ports(n) for n in
                         ("ps7_0", "axi_interconnect_0", "rst_ps7_0_100M"))
    require(ps.get("M_AXI_GP0_ACLK") == ps.get("FCLK_CLK0") ==
            fabric.get("ACLK") == fabric.get("S00_ACLK") ==
            fabric.get("M00_ACLK") == fabric.get("M01_ACLK"),
            "HWH_CLOCK_MISMATCH")
    require(reset.get("ext_reset_in") == ps.get("FCLK_RESET0_N") and
            fabric.get("ARESETN") == fabric.get("S00_ARESETN") ==
            fabric.get("M00_ARESETN") == fabric.get("M01_ARESETN") ==
            reset.get("peripheral_aresetn"), "HWH_RESET_MISMATCH")
    for name in SITES:
        site = ports(name)
        require(site.get("s_axi_aclk") == ps.get("FCLK_CLK0") and
                site.get("s_axi_aresetn") == reset.get("peripheral_aresetn"),
                "HWH_SITE_CLOCK_RESET_MISMATCH")
    buses = {name: {b.get("NAME"): b.get("BUSNAME")
                    for b in modules[name].iter("BUSINTERFACE")}
             for name in ("ps7_0", "axi_interconnect_0", *SITES)}
    require(buses["ps7_0"].get("M_AXI_GP0") ==
            buses["axi_interconnect_0"].get("S00_AXI") and
            buses["axi_interconnect_0"].get("M00_AXI") ==
            buses["swd_site1"].get("S_AXI") and
            buses["axi_interconnect_0"].get("M01_AXI") ==
            buses["swd_site2"].get("S_AXI"), "HWH_INTERCONNECT_MISMATCH")
    return {"source_sha": SOURCE_SHA, "bit_sha256": BIT_SHA,
            "hwh_sha256": HWH_SHA, "firmware_sha256": BIN_SHA,
            "manifest_sha256": MANIFEST_SHA,
            "identity_addresses": [base for base, _ in SITES.values()],
            "linux_owner": "NOT_VERIFIED"}
