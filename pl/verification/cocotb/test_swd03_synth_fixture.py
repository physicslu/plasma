"""End-to-end SWD-03 AXI -> synthesizable line-level DP fixture acceptance."""
import cocotb
from test_swd03_axi import AXIBench, BASE, OKAY, SLVERR, REG_CONFIG, REG_HALF

COMMAND = 0x04
STATUS = 0x24
META = 0x28
RDATA = 0x2C
DPIDR = 0x2BA01477


async def result(bench, limit=3000):
    for _ in range(limit):
        resp, status = await bench.read(STATUS)
        assert resp == OKAY
        if status & 4:
            assert not (status & 2)
            meta = (await bench.read(META))[1]
            data = (await bench.read(RDATA))[1]
            return meta, data
    raise AssertionError("No response from synthesizable SWD fixture")


@cocotb.test()
async def synthetic_dpidr_and_fault(dut):
    b = AXIBench(dut)
    await b.setup()

    assert await b.write(REG_CONFIG, 5) == OKAY  # line reset
    assert await b.write(COMMAND, 1) == OKAY
    meta, data = await result(b)
    assert (meta & 0xF) == 0 and data == 0
    assert await b.write(COMMAND, 4) == OKAY

    assert await b.write(REG_CONFIG, 4) == OKAY  # DP DPIDR read
    assert await b.write(COMMAND, 1) == OKAY
    meta, data = await result(b)
    assert (meta & 0xF) == 0
    assert ((meta >> 4) & 0x7) == 1
    assert ((meta >> 7) & 1) == 1
    assert ((meta >> 8) & 0x1FF) == 1
    assert data == DPIDR
    # Stable result under AXI side backpressure.
    for _ in range(5):
        assert (await b.read(META))[1] == meta
        assert (await b.read(RDATA))[1] == DPIDR
    assert await b.write(COMMAND, 4) == OKAY

    # Test-only fixture rejects everything except DPIDR, not a MEM-AP.
    assert await b.write(REG_CONFIG, 0x24) == OKAY  # DP read CTRL/STAT
    assert await b.write(COMMAND, 1) == OKAY
    meta, data = await result(b)
    assert (meta & 0xF) == 4  # FAULT
    assert ((meta >> 4) & 7) == 4
    assert ((meta >> 7) & 1) == 0 and data == 0
    assert await b.write(COMMAND, 4) == OKAY
    dut._log.info("SWD03_SYNTH_DPIDR_FIXTURE_PASS")
