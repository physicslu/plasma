"""Host-only source contract guard; not an RTL simulation or FPGA hardware proof."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "pl/rtl/bus/opp_common_regs_v1.sv"
SWD = ROOT / "software/python/plasma_interfaces/swd_native_linux_mmio.py"

def test_common_aperture_has_expected_identity_and_scratch_registers():
    rtl = RTL.read_text()
    for offset in range(0, 0x44, 4):
        assert re.search(rf"8'h{offset:02x}:", rtl) or (
            offset == 0x40 and "SCRATCH_ADDR: begin" in rtl
        ), f"missing common register 0x{offset:02x}"
    assert "SCRATCH_ADDR = 8'h40" in rtl
    assert "if (write_i && addr_i == SCRATCH_ADDR)" in rtl

def test_legacy_swd_v5_keeps_removed_debug_offsets_denied():
    src = SWD.read_text()
    assert "0x3C/0x40" in src
    for name in ("_SWD_READ", "_SWD_WRITE"):
        match = re.search(rf"{name} = frozenset\\(\\((.*?)\\)\\)", src, re.S)
        assert match is not None
        offsets = {int(x, 16) for x in re.findall(r"0x[0-9a-fA-F]+", match.group(1))}
        assert 0x3c not in offsets
        assert 0x40 not in offsets
