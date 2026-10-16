"""SWD-04 exact HIL-02/03 functions against actual RTL, host only."""
import cocotb

from pl.hil.swd04 import mmio_contract as m
from test_swd03_axi import AXIBench, BASE, OKAY


@cocotb.test()
async def hil02_hil03_against_synthesizable_fixture(dut):
    bench = AXIBench(dut)
    await bench.setup()
    # Same bus boundary as SWD-06, without importing the production driver
    # package: the HIL tool itself has no PyYAML or other runtime dependency.
    trace = []
    @cocotb.function
    async def read32(address):
        response, value = await bench.read(address - BASE)
        assert response == OKAY
        trace.append(('r', address, value))
        return value
    @cocotb.function
    async def write32(address, value):
        assert await bench.write(address - BASE, value) == OKAY
        trace.append(('w', address, value))
    class Bridge:
        def read32(self, address): return read32(address)
        def write32(self, address, value): write32(address, value)
    bridge = Bridge()

    @cocotb.external
    def exercise():
        io = m.RestrictedMMIO(bridge)
        assert m.hil02_dpidr(io)['dpidr'] == '0x2BA01477'
        recovery = m.hil03_recovery(io)
        assert recovery['abort'] == 'PASS'
        assert recovery['repeat_rdata'] == ['0x2BA01477'] * 3
        assert ('w', m.HALF, 65535) in trace
        assert ('w', m.COMMAND, 2) in trace
    await exercise()
