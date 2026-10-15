"""Run the actual HIL algorithms through AXI, including checked SLVERR."""
import os
import cocotb
from pl.hil.pspl02 import mmio as m
from test_pl_identity import setup, cycle, value
from test_pl_control import write


@cocotb.test()
async def exact_hil_sequence(dut):
    await setup(dut)
    variant = os.environ["PSPL02_HIL_VARIANT"]

    @cocotb.function
    async def read32(address):
        dut.s_axi_araddr.value = address
        dut.s_axi_arvalid.value = 1
        dut.s_axi_rready.value = 0
        await cycle(dut)
        dut.s_axi_arvalid.value = 0
        assert value(dut.s_axi_rvalid) == 1
        assert value(dut.s_axi_rresp) == 0
        result = value(dut.s_axi_rdata)
        dut.s_axi_rready.value = 1
        await cycle(dut)
        dut.s_axi_rready.value = 0
        return result

    @cocotb.function
    async def write32(address, data):
        # The only intentional semantic rejection is START with reset count 0.
        reject = variant == "waveform" and address == m.CMD and data == 1 and value(dut.core.count_cfg) == 0
        await write(dut, address, data, response=2 if reject else 0)

    class Bridge:
        def read32(self, address): return read32(address)
        def write32(self, address, data): write32(address, data)

    # Linux sleep is inappropriate for event-driven simulation; progress still
    # comes exclusively from the AXI bridge, not a mirror register model.
    original = m.completion
    def completion(io): original(io, sleep_seconds=0)
    m.completion = completion

    @cocotb.external
    def exercise():
        io = m.RestrictedMMIO(Bridge())
        if variant == "control":
            assert m.pspl02(io)["HIL-PSPL-02A"] == "PASS"
        else:
            assert len(m.swd00(io)["rx_vectors"]) == 4
            assert m.error_handling(io)["HIL-SWD-00C"] == "PASS"
            assert m.reset_recovery(io)["HIL-SWD-00D"] == "PASS"
    try:
        await exercise()
    finally:
        m.completion = original
