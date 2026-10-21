"""PLASMA PPU Fixed-Image Global Identity + UIO + Broker HOST MODEL ONLY.

No sysfs reads, file IO, /dev/uio*, /dev/mem, mapping, FPGA Manager, hardware
authority or cryptographic attestation. Input records are synthetic fixtures.
Hash strings here are reviewed *expectations*, not proof of loaded bitstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from threading import RLock

from pl.tools.fixed_image_abi_contract import (
    ContractError, select_uio_resource, validate_abi,
)


def reject_if(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def u32(value: object) -> bool:
    return type(value) is int and 0 <= value <= 0xFFFFFFFF


def mask8(value: object) -> bool:
    return type(value) is int and 0 <= value <= 0xFF


def nonblank(value: object) -> bool:
    return type(value) is str and bool(value.strip())


def digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


@dataclass(frozen=True)
class HostAdmission:
    descriptor_fingerprint: str
    board_id: str
    source_sha256: str
    image_sha256: str
    owner_epoch: str
    generation: int
    uio_name: str
    site_present_bitmap: int
    site_ready_bitmap: int
    capabilities: int
    hardware_authority: bool = False


@dataclass(frozen=True)
class HostSiteLease:
    site_id: int
    exact_ic: str
    batch_id: str
    generation: int
    owner_epoch: str
    descriptor_fingerprint: str
    hardware_authority: bool = False


def validate_board_descriptor(descriptor: dict, spec: dict) -> dict:
    """Validate a fully pinned synthetic Board Descriptor, not its provenance."""
    validate_abi(spec)
    reject_if(type(descriptor) is dict, "Board Descriptor must be an object")
    reject_if(set(descriptor) == {
        "schema", "soc", "image_policy", "board_id", "boot_id", "owner_epoch",
        "generation", "source_sha256", "image_sha256", "manifest_sha256",
        "hardware_authority", "uio_pin", "expected_identity",
    }, "Unknown/missing Board Descriptor fields")
    reject_if(descriptor.get("schema") == "plasma-fixed-ppu-board-host-v1", "Wrong descriptor schema")
    reject_if(descriptor.get("soc") == "XC7Z020-1CLG400C", "Wrong development SoC")
    reject_if(descriptor.get("image_policy") == "FIXED_PER_BOOT", "Runtime reload is not allowed")
    for key in ("board_id", "boot_id", "owner_epoch"):
        reject_if(nonblank(descriptor.get(key)), f"Missing immutable {key}")
    for key in ("source_sha256", "image_sha256", "manifest_sha256"):
        reject_if(digest(descriptor.get(key)), f"Malformed {key}")
    reject_if(type(descriptor.get("generation")) is int and descriptor["generation"] > 0,
              "Invalid owner generation")
    reject_if(descriptor.get("hardware_authority") is False, "Host descriptor must not grant hardware")
    pin = descriptor.get("uio_pin")
    reject_if(type(pin) is dict, "No UIO pin")
    reject_if(set(pin) == {"label", "platform_device", "driver",
                           "map_index", "physical_base", "size", "byte_offset"},
              "Unknown UIO Board pin fields")
    reject_if(pin.get("map_index") == 0 and pin.get("size") == 65536 and
              u32(pin.get("physical_base")) and pin["physical_base"] % 65536 == 0 and
              pin.get("byte_offset") == 0 and
              all(nonblank(pin.get(k)) for k in ("label", "platform_device", "driver")),
              "No exact 64KiB map0 Board Descriptor binding")
    expected = descriptor.get("expected_identity")
    reject_if(type(expected) is dict, "Missing expected ABI Identity")
    reject_if(set(expected) == {"image_id_words", "build_id_words",
                                "hw_revision", "site_present_bitmap",
                                "capabilities", "max_transfer_bits"},
              "Unknown expected Identity fields")
    for name in ("image_id_words", "build_id_words"):
        words = expected.get(name)
        reject_if(type(words) is list and len(words) == 4 and all(u32(w) for w in words),
                  f"Invalid {name}")
    reject_if(u32(expected.get("hw_revision")) and expected["hw_revision"] > 0,
              "Missing HW revision")
    reject_if(mask8(expected.get("site_present_bitmap")) and
              expected["site_present_bitmap"] != 0, "No reviewed RTL Site present")
    reject_if(type(expected.get("capabilities")) is int and
              expected["capabilities"] in (1, 2, 3),
              "Unsupported protocol capability")
    reject_if(type(expected.get("max_transfer_bits")) is int and
              8 <= expected["max_transfer_bits"] <= 8192 and
              expected["max_transfer_bits"] % 8 == 0,
              "Invalid transfer bound")
    # This is a mock / offline record; the public source hash is not trusted
    # until independently checked against the actual artifact bytes and loader.
    return descriptor


def admit_ppu_host(spec: dict, descriptor: dict, uio_inventory: list[dict],
                   registers: dict[int, int]) -> HostAdmission:
    """Match exact fake register snapshot after fake UIO resource resolution."""
    d = validate_board_descriptor(descriptor, spec)
    reject_if(type(registers) is dict and all(u32(k) and u32(v)
                                               for k, v in registers.items()),
              "Invalid offline register snapshot")
    resource = select_uio_resource(uio_inventory, d["uio_pin"])
    expected = d["expected_identity"]
    vals = {
        0x000: 0x4D534C50,
        0x004: 0x00010000,
        **{0x008 + i * 4: w for i, w in enumerate(expected["image_id_words"])},
        **{0x018 + i * 4: w for i, w in enumerate(expected["build_id_words"])},
        0x028: expected["capabilities"],
        0x02C: 0,
        0x030: expected["site_present_bitmap"],
        0x03C: expected["hw_revision"],
        0x044: 1,
        0x048: 4096,
        0x04C: expected["max_transfer_bits"],
        0x100C: 0,
    }
    for offset, word in vals.items():
        reject_if(registers.get(offset) == word, f"Identity mismatch at +0x{offset:04x}")
    present = registers[0x030]
    ready = registers.get(0x034)
    faults = registers.get(0x1004)
    ppu_status = registers.get(0x038)
    global_status = registers.get(0x1000)
    reject_if(mask8(ready) and mask8(faults), "Invalid Site status bitmap")
    reject_if(ready & ~present == 0 and faults & ~present == 0,
              "Site flags outside present bitmap")
    reject_if(ready & faults == 0, "Faulted Site may not be ready")
    reject_if(u32(ppu_status) and u32(global_status) and
              ppu_status == global_status and (ppu_status & ~3) == 0,
              "Inconsistent PPU/global status")
    reject_if(ppu_status & 1 and not (ppu_status & 2) and not faults,
              "PPU not globally ready")
    reject_if(registers.get(0x1008) == faults and registers.get(0x040) == 0,
              "Global event/PPU error drift")
    reject_if(registers.get(0x034) == ready, "Ready bitmap missing")
    # For this single-Site initial slice: reject unrelated SPI capability claims
    # unless the synthetic descriptor explicitly pins SPI, and never presume
    # capability => a fully wired SPI or physical 8 Sites.
    fingerprint = sha256(dumps(d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return HostAdmission(
        descriptor_fingerprint=fingerprint, board_id=d["board_id"],
        source_sha256=d["source_sha256"], image_sha256=d["image_sha256"],
        owner_epoch=d["owner_epoch"], generation=d["generation"],
        uio_name=resource["device_name"], site_present_bitmap=present,
        site_ready_bitmap=ready, capabilities=expected["capabilities"],
    )


class HostBrokerAdmission:
    """Synthetic admission gate. Not the actual privileged Hardware Broker."""

    def __init__(self, admission: HostAdmission):
        reject_if(isinstance(admission, HostAdmission) and
                  admission.hardware_authority is False,
                  "A Host-only admission receipt is required")
        self._receipt = admission
        self._leases: dict[int, HostSiteLease] = {}
        self._exact_ic: str | None = None
        self._batch_id: str | None = None
        self._sealed = False
        self._lock = RLock()

    def claim(self, site_id: int, *, exact_ic: str, batch_id: str,
              generation: int, owner_epoch: str) -> HostSiteLease:
        with self._lock:
            r = self._receipt
            reject_if(not self._sealed, "Broker admission sealed")
            reject_if(type(site_id) is int and 1 <= site_id <= 8, "Invalid Site ID")
            mask = 1 << (site_id - 1)
            reject_if(r.site_present_bitmap & mask and r.site_ready_bitmap & mask,
                      "Site absent or not READY")
            reject_if(site_id not in self._leases, "Duplicate active Site lease")
            reject_if(nonblank(exact_ic) and nonblank(batch_id), "Canonical exact IC / Batch required")
            reject_if(type(generation) is int and generation == r.generation and
                      owner_epoch == r.owner_epoch, "Stale owner epoch/generation")
            reject_if(self._exact_ic in (None, exact_ic), "Mixed exact IC in one PPU batch")
            reject_if(self._batch_id in (None, batch_id), "Second active PPU batch denied")
            self._exact_ic, self._batch_id = exact_ic, batch_id
            lease = HostSiteLease(site_id, exact_ic, batch_id, generation,
                                  owner_epoch, r.descriptor_fingerprint)
            self._leases[site_id] = lease
            return lease

    def release(self, lease: HostSiteLease) -> None:
        with self._lock:
            reject_if(type(lease) is HostSiteLease and
                      self._leases.get(lease.site_id) is lease,
                      "Unrecognized or stale Site lease")
            del self._leases[lease.site_id]
            if not self._leases:
                self._exact_ic = None
                self._batch_id = None

    def seal(self) -> None:
        with self._lock:
            self._sealed = True
            self._leases.clear()
            self._exact_ic = None
            self._batch_id = None

    @property
    def hardware_authority(self) -> bool:
        return False
