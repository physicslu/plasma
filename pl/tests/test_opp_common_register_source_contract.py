"""Host-only source contract guard; not an RTL simulation or FPGA hardware proof."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "pl/rtl/bus/opp_common_regs_v1.sv"

def test_common_aperture_has_expected_identity_and_scratch_registers():
    rtl = RTL.read_text()
    for offset in range(0, 0x44, 4):
        assert re.search(rf"8'h{offset:02x}:", rtl) or (
            offset == 0x40 and "SCRATCH_ADDR: begin" in rtl
        ), f"missing common register 0x{offset:02x}"
    assert "SCRATCH_ADDR = 8'h40" in rtl
    assert "if (write_i && addr_i == SCRATCH_ADDR)" in rtl
