"""Host-only checks for the d0add58c two-Site Image and its HWH (ab79b04e, bd976140 retired).

This does not authorize a Linux MMIO owner or a physical FPGA operation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


SOURCE_SHA = "d0add58c3e36ce930b812ec9eb1e37f22c95a615"
BIT_SHA = "8419dfff8cb634a47738cf6cecf8e332f70f820e61e87326013daf21635bb2f3"  # Vivado run 41648270405
HWH_SHA = "0b0e32c2129c08c8bcdcf66fb8ab9ae2ee7c37f204415b50fb0608c23f488acd"
BIN_SHA = "0d99ecafcb570c39217aa39723ccfcf593ae2021158599085a01436665374bc7"
MANIFEST_SHA = "4e33fee583611f70c60d30f971cc8499c165486b4621119a6b219da6fd3f1d78"
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
            data["image_id"] == "z2-independent-swd-v5-d0add58c",
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
