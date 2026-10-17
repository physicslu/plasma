"""Adversarial Host-only tests for fixed-image Driver Architecture M1 Gate 1."""
import copy
import json
from pathlib import Path

import pytest

from pl.tools.fixed_image_abi_contract import (
    ContractError, admit_host_transaction, select_uio_resource, validate_abi,
)

SPEC = Path(__file__).resolve().parents[1] / "verification/fixed_image_abi_v1_gate1.json"


@pytest.fixture
def abi():
    return json.loads(SPEC.read_text(encoding="utf-8"))


@pytest.fixture
def pin():
    return {"label": "fabric", "platform_device": "40000000.fabric",
            "driver": "uio_pdrv_genirq", "map_index": 0,
            "physical_base": 0x40000000, "size": 0x10000, "byte_offset": 0}


@pytest.fixture
def broker():
    return {"state": "READY", "hardware_authority": False, "runtime_reload": False,
            "generation": 7, "epoch": "host-instance-a", "exact_ic": "STM32F103C8T6",
            "busy_sites": [], "site_present_bitmap": 3, "site_ready_bitmap": 3,
            "capabilities": 3, "capacity_words": 8, "max_transfer_bits": 256}


@pytest.fixture
def lease():
    return {"active": True, "site_id": 1, "generation": 7,
            "epoch": "host-instance-a", "exact_ic": "STM32F103C8T6"}


@pytest.fixture
def swd():
    return {"opcode": "SWD_XFER", "protocol": "SWD", "sequence": 5,
            "bit_count": 32, "timeout_ticks": 8000, "clock_div": 4,
            "flags": 0, "arg0": 9, "wdata": 0xA5A50000, "tx_words": []}


def test_contract_is_only_host_review_candidate(abi):
    result = validate_abi(abi)
    assert result["status"] == "HOST_CONTRACT_VALID"
    assert result["hardware_authority"] is False
    assert result["real_z2_hil"] == "NOT_RUN"
    assert result["m1"] == "NO_GO"


@pytest.mark.parametrize("key,value", [
    ("status", "accepted"),
    ("contract", "plasma-dynamic-switching"),
])
def test_unapproved_contract_labels_refused(abi, key, value):
    abi[key] = value
    with pytest.raises(ContractError):
        validate_abi(abi)


@pytest.mark.parametrize("field,value", [
    ("runtime_fpga_reload_supported", True),
    ("image_lifecycle", "RUNTIME_A_B"),
    ("sites_physically_verified", 8),
])
def test_wrong_hardware_claims_fail_closed(abi, field, value):
    abi["hardware"][field] = value
    with pytest.raises(ContractError):
        validate_abi(abi)


def test_identity_site_windows_and_tail_nonoverlap(abi):
    validate_abi(abi)
    regions = abi["regions"]
    for i, region in enumerate(regions):
        for next_region in regions[i+1:]:
            assert region["base"] + region["size"] <= next_region["base"]
    assert regions[-1]["base"] + regions[-1]["size"] == 65536
    assert [s["site_id"] for s in regions[4:12]] == list(range(1, 9))


def test_reserved_holes_and_unaligned_offsets_denied(abi):
    abi["regions"][2]["registers"].append(
        {"name": "UNSAFE", "offset": 0, "access": "ro", "semantics": "bad"})
    with pytest.raises(ContractError):
        validate_abi(abi)
    abi["regions"][2]["registers"] = []
    abi["regions"][4]["registers"][0]["offset"] = 1
    with pytest.raises(ContractError):
        validate_abi(abi)


def test_duplicate_word_and_changed_register_access_denied(abi):
    abi["regions"][4]["registers"][1]["offset"] = 0
    with pytest.raises(ContractError):
        validate_abi(abi)
    abi = json.loads(SPEC.read_text(encoding="utf-8"))
    abi["regions"][4]["registers"][0]["access"] = "rw"
    with pytest.raises(ContractError):
        validate_abi(abi)


def test_one_fabric_map_can_renumber_uio0_to_uio1(pin):
    for device_name in ("uio0", "uio1", "uio42"):
        selected = select_uio_resource([{"device_name": device_name, **pin}], pin)
        assert selected["device_name"] == device_name


def test_competing_map_denied_even_when_unrelated_uio_label(pin):
    inventory = [{"device_name": "uio1", **pin},
                 {"device_name": "uio2", **{**pin, "label": "other",
                   "physical_base": pin["physical_base"] + 4096,
                   "size": 4096}}]
    with pytest.raises(ContractError, match="Competing"):
        select_uio_resource(inventory, pin)


@pytest.mark.parametrize("change", [
    {"label": "renamed"},
    {"driver": "different_driver"},
    {"physical_base": 0x50000000},
    {"map_index": 1},
    {"size": 0x2000},
])
def test_changed_target_pin_refused(pin, change):
    altered = {"device_name": "uio1", **pin, **change}
    with pytest.raises(ContractError):
        select_uio_resource([altered], pin)


def test_duplicate_uio_name_refused(pin):
    with pytest.raises(ContractError, match="Ambiguous"):
        select_uio_resource([{"device_name": "uio1", **pin},
                             {"device_name": "uio1", **pin}], pin)


def test_swd_transfer_command_last_without_real_access(abi, broker, lease, swd):
    p = admit_host_transaction(abi, broker, lease, swd)
    assert p["status"] == "HOST_PLAN_ONLY"
    assert p["hardware_authority"] is False
    assert p["writes"][-2:] == [("BARRIER_REQUIRED", 0), ("COMMAND", 1)]
    assert not any(x in ("FPGA_LOAD", "POWER_CONTROL") for x, _ in p["writes"])


@pytest.mark.parametrize("field,value", [
    ("state", "QUIESCE"), ("hardware_authority", True),
    ("runtime_reload", True), ("generation", 8),
    ("epoch", "stale"), ("exact_ic", "OTHER_IC"),
    ("site_present_bitmap", 2), ("site_ready_bitmap", 2),
])
def test_broker_admission_fails_on_unknown_ownership(
        abi, broker, lease, swd, field, value):
    broker[field] = value
    with pytest.raises(ContractError):
        admit_host_transaction(abi, broker, lease, swd)


def test_busy_or_stale_site_lease_cannot_issue_command(abi, broker, lease, swd):
    broker["busy_sites"] = [1]
    with pytest.raises(ContractError):
        admit_host_transaction(abi, broker, lease, swd)
    broker["busy_sites"] = []
    lease["active"] = False
    with pytest.raises(ContractError):
        admit_host_transaction(abi, broker, lease, swd)


@pytest.mark.parametrize("field,value", [
    ("opcode", "FPGA_IMAGE_SWITCH"),
    ("protocol", "SPI"), ("sequence", 0),
    ("bit_count", 31), ("arg0", 16), ("flags", 4),
    ("clock_div", 0), ("timeout_ticks", 0),
])
def test_swd_unsupported_or_unsafe_request_fails(abi, broker, lease, swd, field, value):
    swd[field] = value
    with pytest.raises(ContractError):
        admit_host_transaction(abi, broker, lease, swd)


def test_swd_line_reset_explicit_bounds(abi, broker, lease, swd):
    swd.update(opcode="SWD_LINE_RESET", bit_count=50, arg0=0, wdata=0)
    assert admit_host_transaction(abi, broker, lease, swd)["writes"][-1] == ("COMMAND", 2)
    swd["bit_count"] = 49
    with pytest.raises(ContractError):
        admit_host_transaction(abi, broker, lease, swd)


def test_spi_word_packing_and_fifo_bounds(abi, broker, lease, swd):
    swd.update(opcode="SPI_TRANSFER", protocol="SPI", bit_count=40,
               arg0=0, wdata=0, flags=0, tx_words=[0x12345678, 0xAB])
    plan = admit_host_transaction(abi, broker, lease, swd)
    assert plan["writes"][-1] == ("COMMAND", 3)
    swd["tx_words"][-1] = 0x100
    with pytest.raises(ContractError, match="padding"):
        admit_host_transaction(abi, broker, lease, swd)


def test_spi_not_admitted_without_hardware_capability(abi, broker, lease, swd):
    swd.update(opcode="SPI_TRANSFER", protocol="SPI", bit_count=8,
               arg0=0, wdata=0, tx_words=[0x12])
    broker["capabilities"] = 1
    with pytest.raises(ContractError):
        admit_host_transaction(abi, broker, lease, swd)


def test_reserved_protocols_cannot_be_issued(abi, broker, lease, swd):
    for protocol in ("JTAG", "I2C", "ICSP"):
        swd.update(opcode="SPI_TRANSFER", protocol=protocol)
        with pytest.raises(ContractError):
            admit_host_transaction(abi, broker, lease, swd)


def test_no_device_io_from_host_contract(tmp_path, abi, broker, lease, swd):
    before = list(tmp_path.iterdir())
    validate_abi(abi)
    admit_host_transaction(abi, broker, lease, swd)
    assert before == list(tmp_path.iterdir())
