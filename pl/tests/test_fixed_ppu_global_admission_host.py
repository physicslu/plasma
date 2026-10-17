"""Pure Host-only Global Identity / UIO Resource / Broker Admission negative tests."""
import copy
import json
from pathlib import Path

import pytest

from pl.tools.fixed_image_abi_contract import ContractError
from pl.tools.fixed_ppu_global_admission_host import (
    admit_ppu_host, validate_board_descriptor, HostBrokerAdmission,
)

SPEC = json.loads(
    (Path(__file__).resolve().parents[1] /
     "verification/fixed_image_abi_v1_gate1.json").read_text(encoding="utf-8")
)


@pytest.fixture
def descriptor():
    return {
        "schema": "plasma-fixed-ppu-board-host-v1",
        "soc": "XC7Z020-1CLG400C",
        "image_policy": "FIXED_PER_BOOT",
        "board_id": "FAKE-Z2-BOARD",
        "boot_id": "FAKE-BOOT-A",
        "owner_epoch": "FAKE-OWNER-EPOCH-A",
        "generation": 7,
        "source_sha256": "a" * 64,
        "image_sha256": "b" * 64,
        "manifest_sha256": "c" * 64,
        "hardware_authority": False,
        "uio_pin": {
            "label": "fixed-ppu", "platform_device": "40000000.fixed-ppu",
            "driver": "uio_pdrv_genirq", "map_index": 0,
            "physical_base": 0x40000000, "size": 0x10000, "byte_offset": 0,
        },
        "expected_identity": {
            "image_id_words": [0x11112222, 0x33334444, 0x55556666, 0x77778888],
            "build_id_words": [0xABCDE001, 0xABCDE002, 0xABCDE003, 0xABCDE004],
            "hw_revision": 1, "site_present_bitmap": 1,
            "capabilities": 1, "max_transfer_bits": 64,
        },
    }


@pytest.fixture
def regs(descriptor):
    e = descriptor["expected_identity"]
    r = {
        0x000: 0x4D534C50, 0x004: 0x00010000,
        0x028: e["capabilities"], 0x02C: 0,
        0x030: e["site_present_bitmap"], 0x034: 1,
        0x038: 1, 0x03C: 1, 0x040: 0,
        0x044: 1, 0x048: 4096, 0x04C: 64,
        0x1000: 1, 0x1004: 0, 0x1008: 0, 0x100C: 0,
    }
    for i, w in enumerate(e["image_id_words"]):
        r[0x008 + 4*i] = w
    for i, w in enumerate(e["build_id_words"]):
        r[0x018 + 4*i] = w
    return r


@pytest.fixture
def inventory(descriptor):
    return [{"device_name": "uio1", **descriptor["uio_pin"]}]


def receipt(descriptor, inventory, regs):
    return admit_ppu_host(SPEC, descriptor, inventory, regs)


def test_exact_identity_descriptor_and_uio_resource(descriptor, inventory, regs):
    result = receipt(descriptor, inventory, regs)
    assert result.hardware_authority is False
    assert result.uio_name == "uio1"
    assert result.site_present_bitmap == result.site_ready_bitmap == 1
    assert len(result.descriptor_fingerprint) == 64


@pytest.mark.parametrize("ordinal", ["uio0", "uio1", "uio42"])
def test_uio_ordinal_is_not_device_identity(descriptor, inventory, regs, ordinal):
    inventory[0]["device_name"] = ordinal
    assert receipt(descriptor, inventory, regs).uio_name == ordinal


@pytest.mark.parametrize("field,value", [
    ("schema", "legacy"), ("soc", "XC7Z010-1"), ("image_policy", "RUNTIME_RELOAD"),
    ("generation", 0), ("owner_epoch", ""), ("board_id", ""),
    ("source_sha256", "short"), ("image_sha256", "A" * 64),
    ("hardware_authority", True),
])
def test_bad_board_descriptor_fails_closed(descriptor, inventory, regs, field, value):
    descriptor[field] = value
    with pytest.raises(ContractError):
        receipt(descriptor, inventory, regs)


@pytest.mark.parametrize("field,value", [
    ("map_index", 1), ("size", 0x2000), ("physical_base", 0x40001000),
    ("driver", ""), ("byte_offset", 4096),
])
def test_unpinned_map_refused(descriptor, inventory, regs, field, value):
    descriptor["uio_pin"][field] = value
    with pytest.raises(ContractError):
        receipt(descriptor, inventory, regs)


def test_overlap_and_renamed_resource_refused(descriptor, inventory, regs):
    inventory.append({
        "device_name": "uio2", **{**descriptor["uio_pin"],
                                 "label": "rogue", "physical_base": 0x40001000,
                                 "size": 4096}
    })
    with pytest.raises(ContractError):
        receipt(descriptor, inventory, regs)


@pytest.mark.parametrize("field,value", [
    ("driver", "changed"), ("label", "changed"), ("physical_base", 0x50000000),
])
def test_changed_actual_uiomap_fails_closed(descriptor, inventory, regs, field, value):
    inventory[0][field] = value
    with pytest.raises(ContractError):
        receipt(descriptor, inventory, regs)


@pytest.mark.parametrize("offset,bad", [
    (0x000, 0x504C534D), (0x004, 0x00020000),
    (0x008, 0xFEEDABCD), (0x018, 0),
    (0x028, 3), (0x02C, 1), (0x030, 2), (0x03C, 2),
    (0x044, 2), (0x048, 512), (0x04C, 8192), (0x100C, 9),
])
def test_wrong_abi_image_caps_and_aperture_fails(descriptor, inventory, regs, offset, bad):
    regs[offset] = bad
    with pytest.raises(ContractError):
        receipt(descriptor, inventory, regs)


@pytest.mark.parametrize("changes", [
    {0x034: 2},
    {0x1004: 2},
    {0x034: 1, 0x1004: 1},
    {0x038: 0, 0x1000: 0},
    {0x038: 3, 0x1000: 3, 0x040: 1, 0x1004: 1, 0x1008: 1, 0x034: 0},
    {0x038: 1, 0x1000: 3},
])
def test_unready_faulted_or_inconsistent_ppu_denied(descriptor, inventory, regs, changes):
    regs.update(changes)
    with pytest.raises(ContractError):
        receipt(descriptor, inventory, regs)


def test_active_two_site_leases_same_ic_and_batch(descriptor, inventory, regs):
    descriptor["expected_identity"]["site_present_bitmap"] = 3
    regs[0x030] = 3
    regs[0x034] = 3
    broker = HostBrokerAdmission(receipt(descriptor, inventory, regs))
    a = broker.claim(1, exact_ic="STM32F103C8T6", batch_id="B1",
                     generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")
    b = broker.claim(2, exact_ic="STM32F103C8T6", batch_id="B1",
                     generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")
    assert a.site_id == 1 and b.site_id == 2
    assert not broker.hardware_authority
    with pytest.raises(ContractError, match="Duplicate"):
        broker.claim(2, exact_ic="STM32F103C8T6", batch_id="B1",
                     generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")
    broker.release(a)
    broker.release(b)


def test_stale_epoch_wrong_batch_or_different_ic_rejected(descriptor, inventory, regs):
    descriptor["expected_identity"]["site_present_bitmap"] = 3
    regs[0x030] = 3
    regs[0x034] = 3
    b = HostBrokerAdmission(receipt(descriptor, inventory, regs))
    lease = b.claim(1, exact_ic="STM32F103C8T6", batch_id="B1",
                    generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")
    for kwargs in (
        dict(exact_ic="OTHER", batch_id="B1", generation=7, owner_epoch="FAKE-OWNER-EPOCH-A"),
        dict(exact_ic="STM32F103C8T6", batch_id="B2", generation=7, owner_epoch="FAKE-OWNER-EPOCH-A"),
        dict(exact_ic="STM32F103C8T6", batch_id="B1", generation=8, owner_epoch="FAKE-OWNER-EPOCH-A"),
        dict(exact_ic="STM32F103C8T6", batch_id="B1", generation=7, owner_epoch="STALE"),
    ):
        with pytest.raises(ContractError):
            b.claim(2, **kwargs)
    b.release(lease)
    with pytest.raises(ContractError, match="stale"):
        b.release(lease)


def test_nonpresent_site_and_sealed_broker_denied(descriptor, inventory, regs):
    b = HostBrokerAdmission(receipt(descriptor, inventory, regs))
    with pytest.raises(ContractError):
        b.claim(8, exact_ic="STM32F103C8T6", batch_id="B1",
                generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")
    b.seal()
    with pytest.raises(ContractError):
        b.claim(1, exact_ic="STM32F103C8T6", batch_id="B1",
                generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")


def test_host_contract_performs_no_disk_or_device_io(tmp_path, descriptor, inventory, regs):
    before = list(tmp_path.iterdir())
    result = receipt(descriptor, inventory, regs)
    b = HostBrokerAdmission(result)
    lease = b.claim(1, exact_ic="STM32F103C8T6", batch_id="B1",
                    generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")
    b.release(lease)
    assert list(tmp_path.iterdir()) == before


def test_board_descriptor_schema_and_synthetic_fixture_are_consistent(descriptor):
    root = Path(__file__).resolve().parents[1] / "verification"
    schema = json.loads((root / "fixed_ppu_board_descriptor_host_v1.schema.json").read_text())
    sample = json.loads((root / "examples/fixed_ppu_board_descriptor_synthetic.json").read_text())
    assert schema["properties"]["schema"]["const"] == sample["schema"]
    assert set(schema["required"]) == set(sample)
    assert set(schema["properties"]["uio_pin"]["required"]) == set(sample["uio_pin"])
    assert set(schema["properties"]["expected_identity"]["required"]) == set(sample["expected_identity"])
    assert schema["properties"]["hardware_authority"]["const"] is False
    assert validate_board_descriptor(sample, SPEC) is sample


def test_unknown_descriptor_and_pin_fields_fail_closed(descriptor, inventory, regs):
    descriptor["debug_allow_mmio"] = True
    with pytest.raises(ContractError):
        receipt(descriptor, inventory, regs)
    del descriptor["debug_allow_mmio"]
    descriptor["uio_pin"]["device_name"] = "uio0"
    with pytest.raises(ContractError):
        receipt(descriptor, inventory, regs)


def test_unready_site_cannot_get_lease(descriptor, inventory, regs):
    regs[0x034] = 0
    b = HostBrokerAdmission(receipt(descriptor, inventory, regs))
    with pytest.raises(ContractError, match="not READY"):
        b.claim(1, exact_ic="STM32F103C8T6", batch_id="B1",
                generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")


def test_host_broker_thread_race_only_one_owner(descriptor, inventory, regs):
    from concurrent.futures import ThreadPoolExecutor
    b = HostBrokerAdmission(receipt(descriptor, inventory, regs))
    def one_claim(_):
        try:
            return b.claim(1, exact_ic="STM32F103C8T6", batch_id="B1",
                           generation=7, owner_epoch="FAKE-OWNER-EPOCH-A")
        except ContractError:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        leases = list(pool.map(one_claim, range(16)))
    assert sum(x is not None for x in leases) == 1
    b.release(next(x for x in leases if x is not None))
