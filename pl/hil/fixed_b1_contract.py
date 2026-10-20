"""F1-B HIL-B1 host-only contract: real-Z2 one-shot callbacks, not a launcher.

Never opens MMIO, FPGA Manager, SSH or a device. The actual supervisor,
candidate BIN conversion and privileged owner route need separate qualification.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
import re

FPGA_BASE = 0x40000000
FPGA_END = 0x40010000  # exclusive; all 64 KiB, NOT SWD-03's 16 KiB
F1_BIT_SHA256 = "ad7c525385ae265f8f479acbe4227b2ef97fee51d68ba85b8efeff804bc740f6"
F1_HWH_SHA256 = "a367f820e375c7770b7b71c4c7dfee42b64c64eb57fc3d0cdf906a944100ce2e"
BASE_BIN_SHA256 = "c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c"
BASE_HWH_SHA256 = "222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a"
IDENTITY_OFFSETS = (0x000, 0x004, 0x028, 0x030, 0x044, 0x048)
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class B1Blocked(RuntimeError):
    """Fail-closed contract or ambiguous hardware state."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise B1Blocked(reason)


def verify_pins(receipt: Mapping[str, object]) -> None:
    """Check specific previously hashed Host Build and known-good restore pins.

    Candidate BIN digest is not yet established. No caller-provided bool or
    generic Host Build PASS is accepted as permission to load a real FPGA.
    """
    expected = {
        "bit_sha256": F1_BIT_SHA256,
        "hwh_sha256": F1_HWH_SHA256,
        "recovery_bin_sha256": BASE_BIN_SHA256,
        "recovery_hwh_sha256": BASE_HWH_SHA256,
    }
    require(all(receipt.get(k) == v for k, v in expected.items()),
            "B1_ARTIFACT_PROVENANCE_MISMATCH")
    require(type(receipt.get("candidate_bin_sha256")) is str
            and HEX64.fullmatch(receipt["candidate_bin_sha256"]) is not None,
            "B1_CANDIDATE_BIN_UNPINNED")
    # A digest field is necessary but not sufficient: independent BIT-to-BIN
    # conversion and root-protected live staging remain outside this module.


def overlaps_64k(start: int, size: int) -> bool:
    require(type(start) is int and type(size) is int and start >= 0
            and size > 0 and start + size <= (1 << 64),
            "B1_BAD_RESOURCE_RANGE")
    return start < FPGA_END and start + size > FPGA_BASE


def admit_ownership(*, uio_maps: list[Mapping[str, object]],
                    platform_maps: list[Mapping[str, object]],
                    unknown_owners: bool, open_pl_consumers: bool,
                    retained_mmio_maps: bool) -> None:
    """Host-testable policy; the future Z2 supervisor must collect atomically.

    Bound UIO/platform driver overlapping ANY of F1's 64 KiB is an immediate
    block. Quiet /proc at one instant does not prove exclusive ownership.
    """
    require(not unknown_owners and not open_pl_consumers
            and not retained_mmio_maps, "B1_PL_OWNER_UNKNOWN_OR_ACTIVE")
    for item in uio_maps + platform_maps:
        require(set(item) == {"base", "size", "driver_bound"},
                "B1_RESOURCE_SCHEMA")
        require(type(item["driver_bound"]) is bool, "B1_RESOURCE_SCHEMA")
        if overlaps_64k(item["base"], item["size"]):
            require(not item["driver_bound"], "B1_BOUND_DRIVER_CONFLICT")


def read_identity(read32: Callable[[int], int]) -> dict[str, int]:
    """Only six authorized RO global words through an injected native u32 port.

    Do not substitute SWD-03 registers, read reserved offsets or perform a
    write. The injected live reader requires separate native-word HIL approval.
    """
    values = {}
    for offset in IDENTITY_OFFSETS:
        word = read32(FPGA_BASE + offset)
        require(type(word) is int and 0 <= word <= 0xFFFFFFFF,
                "B1_IDENTITY_READ_INVALID")
        values[offset] = word
    require(values[0x000] == 0x4D534C50, "B1_MAGIC_MISMATCH")
    require(values[0x004] == 0x00010000, "B1_ABI_MISMATCH")
    require(values[0x028] & 1 and values[0x028] & ~1 == 0,
            "B1_CAPABILITY_MISMATCH")
    require(values[0x030] == 1, "B1_SITE1_ONLY_REQUIRED")
    require(values[0x044] == 1, "B1_MAP_REVISION_MISMATCH")
    require(values[0x048] == 4096, "B1_SITE_STRIDE_MISMATCH")
    return {
        "magic": values[0x000], "abi": values[0x004],
        "capabilities": values[0x028], "site_present": values[0x030],
        "map_revision": values[0x044], "site_stride": values[0x048],
    }


def one_shot(*, preflight: Callable[[], None],
             load_candidate: Callable[[], None],
             identity_child: Callable[[], dict[str, int]],
             child_stopped_and_unmapped: Callable[[], bool],
             restore_original: Callable[[], None],
             verify_restoration: Callable[[], None]) -> dict[str, str]:
    """Host-only callback engine; nothing here can access Z2 or a real device.

    A blocked preflight never attempts an FPGA load. Restore is marked
    required BEFORE attempting a load. If the identity child may still own
    MMIO, restoration is refused rather than risk reconfiguring under a stall.
    """
    state = {x: "NOT_RUN" for x in
             ("preflight", "load", "identity", "restore", "restored_verified")}
    state["overall"] = "NO_GO"
    try:
        preflight()
        state["preflight"] = "PASS"
    except Exception:
        state["overall"] = "BLOCKED_PREFLIGHT"
        return state

    state["load"] = "ATTEMPTED"
    try:
        load_candidate()
        state["load"] = "PASS"
        observed = identity_child()
        require(type(observed) is dict and observed == {
            "magic": 0x4D534C50, "abi": 0x00010000,
            "capabilities": 1, "site_present": 1,
            "map_revision": 1, "site_stride": 4096,
        }, "B1_IDENTITY_RESULT_INVALID")
        state["identity"] = "PASS"
    except Exception:
        state["overall"] = "FAIL_OR_BLOCKED"
    finally:
        try:
            require(child_stopped_and_unmapped(),
                    "B1_CHILD_OR_MAPPING_STILL_ACTIVE_NO_RELOAD")
        except Exception:
            state["restore"] = "BLOCKED_UNSAFE"
            state["restored_verified"] = "NOT_RUN"
            state["overall"] = "FAIL_OR_UNKNOWN"
        else:
            try:
                restore_original()
                state["restore"] = "PASS"
                verify_restoration()
                state["restored_verified"] = "PASS"
            except Exception:
                state["restore"] = "FAIL_OR_UNKNOWN"
                state["restored_verified"] = "FAIL_OR_UNKNOWN"
                state["overall"] = "FAIL_OR_UNKNOWN"
    if all(state[k] == "PASS" for k in
           ("preflight", "load", "identity", "restore", "restored_verified")):
        state["overall"] = "PASS_INTERNAL_IDENTITY_ONLY"
    return state
