import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def test_basic_addition(dut):
    dut.a.value = 1
    dut.b.value = 2
    await Timer(1, unit="ns")
    actual = dut.sum.value.to_unsigned()
    assert actual == 3


@cocotb.test()
async def test_carry(dut):
    dut.a.value = 255
    dut.b.value = 1
    await Timer(1, unit="ns")
    actual = dut.sum.value.to_unsigned()
    assert actual == 256


@cocotb.test()
async def test_maximum(dut):
    dut.a.value = 255
    dut.b.value = 255
    await Timer(1, unit="ns")
    actual = dut.sum.value.to_unsigned()
    assert actual == 510
