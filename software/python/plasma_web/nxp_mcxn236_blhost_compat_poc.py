"""Host-only MCXN236VKLT ROM ISP / blhost contract experiment (NOT an executable Provider).

This module deliberately does not implement ProgrammingQualificationProvider,
invoke a transport, or register in the canonical Provider registry. A mock
operation plan is NOT L2 evidence or permission to access a DUT.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MANUFACTURER = "NXP"
EXACT_ICPN = "MCXN236VKLT"
SEC_VERSION = "26.06"
SPSDK_VERSION = "3.10.0"  # SEC 26.06 Release Notes: integrated SPSDK 3.10.0
SEC_RELEASE_URL = "https://mcuxpresso.nxp.com/secure/26.06/release_notes.html"
SEC_RELEASE_SHA256 = "5f58034e556df7d3c7a7c99aae8ded8aa9e339e2dcd1e81fd452119c830b0205"
DATASHEET_URL = "https://www.nxp.com/docs/en/data-sheet/MCXN23x.pdf"
DATASHEET_REV = "Rev. 3, 2025-01-21"
BLHOST_DOC_URL = "https://spsdk.readthedocs.io/en/v3.10.0/apps/blhost.html"

# Table 1 identifies MCXN236VKLT as 1024 KB; Table 42 describes 8 KB
# flash sectors and 128 B program pages. These are conservative PoC
# assumptions, NOT a qualified memory map or PDF-byte SHA256 lock.
FLASH_START = 0
FLASH_BYTES = 1024 * 1024
ERASE_SECTOR_BYTES = 8192
PROGRAM_PAGE_BYTES = 128
INTERNAL_MEMORY_ID = 0
# No protected/IFR/PFR/CFPA/CMPA partition was qualified from the source.
# This is an explicit blocker for issuing real erase/program requests.
PROTECTED_REGION_MAP_QUALIFIED = False

class CompatibilityBlocked(ValueError):
    """Unproven target/operation: fail closed before physical side effects."""


@dataclass(frozen=True)
class MockPlan:
    operation: str
    start: int
    length: int
    memory_id: int = INTERNAL_MEMORY_ID
    mock_only: bool = True


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise CompatibilityBlocked(reason)


def canonical_admission_status(registry: Any) -> dict[str, Any]:
    """Inspect the existing canonical registry without changing or enrolling it."""
    row = registry.describe(MANUFACTURER, EXACT_ICPN)
    level = row.get("catalog_level")
    admitted = isinstance(level, int) and not isinstance(level, bool) and level >= 1
    return {
        "exact_icpn": EXACT_ICPN,
        "has_l1_prerequisite": admitted,
        "canonical_level": level,
        "canonical_state": row.get("state"),
        "software_state": "CANDIDATE" if admitted else "BLOCKED",
        "l2_qualified": False,
        "execution_authorized": False,
    }


def mock_probe_properties(observation: dict[str, Any]) -> dict[str, Any]:
    """Validate synthetic ROM GetProperty data; cannot independently identify exact IC."""
    _require(isinstance(observation, dict), "invalid mock probe")
    expected = {
        "flash_start": FLASH_START,
        "flash_size_in_bytes": FLASH_BYTES,
        "flash_sector_size": ERASE_SECTOR_BYTES,
    }
    for name, value in expected.items():
        actual = observation.get(name)
        _require(type(actual) is int and actual == value, "ROM geometry mismatch: " + name)
    _require(observation.get("security_state") == "OPEN", "security state not explicitly OPEN")
    commands = observation.get("available_commands")
    _require(isinstance(commands, (tuple, list, set, frozenset))
             and all(isinstance(c, str) for c in commands),
             "available commands are not a validated collection")
    required = {"get-property", "flash-erase-region", "write-memory", "read-memory"}
    _require(required.issubset(set(commands)), "missing ROM ISP command")
    return {
        "software_state": "CANDIDATE",
        "exact_icpn_confirmed": False,  # GetProperty geometry is not an exact ordering-code attestation.
        "mock_only": True,
        "physical_programming_qualified": False,
    }


def _checked_range(start: int, length: int) -> None:
    _require(type(start) is int and type(length) is int, "address/length must be integers")
    _require(length > 0 and start >= FLASH_START, "empty/negative/outside Flash range")
    _require(start < FLASH_START + FLASH_BYTES, "start outside candidate Flash")
    _require(length <= FLASH_BYTES - (start - FLASH_START), "end outside candidate Flash")


def plan_mock_operation(operation: str, start: int, length: int) -> MockPlan:
    """Conservative *mock-only* planning; cannot be dispatched to a real blhost CLI."""
    _require(operation in {"erase", "program", "read", "verify"}, "forbidden operation")
    _checked_range(start, length)
    if operation == "erase":
        _require(start % ERASE_SECTOR_BYTES == 0
                 and length % ERASE_SECTOR_BYTES == 0,
                 "erase must cover complete 8 KB sectors")
    if operation == "program":
        _require(start % PROGRAM_PAGE_BYTES == 0
                 and length % PROGRAM_PAGE_BYTES == 0,
                 "program must use complete 128 B pages; no implicit padding")
    return MockPlan(operation=operation, start=start, length=length)


def validate_mock_reply(expected_operation: str, reply: dict[str, Any]) -> None:
    """Do not treat a timeout, missing result, or partial completion as success."""
    _require(isinstance(reply, dict), "missing mock response")
    _require(reply.get("operation") == expected_operation, "response operation mismatch")
    _require(reply.get("status") == "SUCCESS", "operation failed or unknown")
    _require(reply.get("complete") is True, "partial operation / uncertain completion")


def compare_mock_readback(expected: bytes, observed: bytes) -> None:
    _require(isinstance(expected, bytes) and isinstance(observed, bytes)
             and len(expected) > 0 and expected == observed,
             "read-back does not match programmed image")


def qualification_gap() -> dict[str, Any]:
    """Explicitly prevent a mock test from being interpreted as L2 SUPPORTED."""
    return {
        "exact_icpn": EXACT_ICPN,
        "provider_kind": "nxp-rom-isp-blhost-compatibility-research",
        "sec_version": SEC_VERSION,
        "spsdk_version": SPSDK_VERSION,
        "software_state": "CANDIDATE",
        "registered_provider": False,
        "operations_qualified": (),
        "missing": (
            "MCXN_31_CANONICAL_L1_NOT_ADMITTED",
            "SEC_SPSDK_BLHOST_BINARY_SOURCE_LOCK_NOT_VERIFIED",
            "MCXN236_EXACT_TARGET_IDENTITY_UNQUALIFIED",
            "MCXN23X_FLASH_BANK_PROTECTED_REGION_MAP_UNQUALIFIED",
            "ROM_GET_PROPERTY_AND_OPERATION_SEMANTICS_NOT_TARGET_VALIDATED",
            "PROBE_ERASE_PROGRAM_READ_VERIFY_NOT_ACTUALLY_QUALIFIED",
        ),
        "execution_authorized": False,
        "installed_runtime_attested": False,
        "physical_programming_qualified": False,
    }
