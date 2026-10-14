"""Four-state electrical control checks, using test-only IOBUF model.

These prove digital RTL direction semantics, NOT PMODB voltage suitability,
real OpenOCD linuxgpiod turnaround timing, or electrical protection.
"""
import cocotb
from cocotb.triggers import Timer


async def settle():
    await Timer(2, units="ns")


def binary(signal):
    return int(signal.value)


def logic(signal):
    return str(signal.value).lower()


@cocotb.test()
async def site1_swdio_turnaround_and_external_sampling(dut):
    dut.gpio_o.value = 0
    dut.gpio_t.value = 0b111  # all three GPIO Hi-Z at reset/pre-enable
    dut.ext_oe.value = 0
    dut.ext_data.value = 0
    await settle()
    assert logic(dut.swdio_pin) == "z"
    assert logic(dut.swclk_pin) == "z"
    assert logic(dut.nrst_pin) == "z"
    assert binary(dut.gpio_i) & ~0b111 == 0

    # PS drives bits only while GPIO_T is low.
    for bit in (1, 0, 1):
        dut.gpio_o.value = bit << 1
        dut.gpio_t.value = 0b101  # SWDIO drives, others float
        await settle()
        assert logic(dut.swdio_pin) == str(bit)
        assert binary(dut.gpio_i) & 0b10 == bit << 1

    # SWD request/ack turnaround: relinquish to target and sample 0/1.
    dut.gpio_t.value = 0b111
    dut.ext_oe.value = 0b010
    for bit in (0, 1, 0):
        dut.ext_data.value = bit << 1
        await settle()
        assert logic(dut.swdio_pin) == str(bit)
        assert binary(dut.gpio_i) & 0b10 == bit << 1
    dut.ext_oe.value = 0
    await settle()
    assert logic(dut.swdio_pin) == "z"


@cocotb.test()
async def swclk_direction_and_nreset_open_drain(dut):
    dut.gpio_o.value = 0
    dut.gpio_t.value = 0b111
    dut.ext_oe.value = 0
    dut.ext_data.value = 0
    await settle()

    for bit in (0, 1, 0):
        dut.gpio_o.value = bit
        dut.gpio_t.value = 0b110  # SWCLK output
        await settle()
        assert logic(dut.swclk_pin) == str(bit)
        assert binary(dut.gpio_i) & 1 == bit

    # nRESET only ever drives low or floats (never drives high).
    dut.gpio_t.value = 0b011  # reset output enable
    dut.gpio_o.value = 0
    await settle()
    assert logic(dut.nrst_pin) == "0"
    dut.gpio_o.value = 0b100  # PS asks for 1 -> must FLOAT, not drive high
    await settle()
    assert logic(dut.nrst_pin) == "z"
    dut.gpio_o.value = 0
    dut.gpio_t.value = 0b111  # PS direction Hi-Z
    await settle()
    assert logic(dut.nrst_pin) == "z"

    # Target-side pull-up simulated by active external 1 (logic only).
    dut.ext_oe.value = 0b100
    dut.ext_data.value = 0b100
    await settle()
    assert logic(dut.nrst_pin) == "1"
    assert binary(dut.gpio_i) & 0b100 == 0b100


@cocotb.test()
async def swdio_push_pull_contention_is_observable(dut):
    dut.gpio_o.value = 0b010
    dut.gpio_t.value = 0b101  # PS drives SWDIO high
    dut.ext_oe.value = 0b010
    dut.ext_data.value = 0  # target drives low; illegal simultaneous drive
    await settle()
    assert logic(dut.swdio_pin) == "x", "digital simulation should expose contention"
    # No HIL action; simply prove the model detects the unsafe state.
    dut.gpio_t.value = 0b111
    await settle()
    assert logic(dut.swdio_pin) == "0"
