"""Read-only upstream OpenOCD source evidence, separate from Production CFG binding.

No Target CFG in this projection authorizes a runtime, Flash operation, Job,
Catalog level, or Production mapping. The source-pinned data is limited to
already admitted manufacturer exact identities. Absence means NOT ATTESTED,
not proof that an upstream file does not exist.
"""
from __future__ import annotations

from .device_catalog import DeviceCatalogIntegrityError, DeviceCatalogRecord
from .microchip_phase1_admission_guard import (
    PIC32_DRIVER_BLOB, PIC32_PINNED_COMMIT, PIC32_SOURCE_INDEX_BLOB,
)
from .microchip_pic32mx_route_evidence import PIC32MX_BASE_DEVID

OPENOCD_VERSION = "0.12.0"
# Exact upstream OpenOCD v0.12.0 Git blobs, not installed runtime evidence.
PIC32_TARGET = ("tcl/target/pic32mx.cfg", "df68e807aeb504ab8b23b547803405df586b3928")
PIC32_DRIVER = ("src/flash/nor/pic32mx.c", PIC32_DRIVER_BLOB)
SAML1X_TARGET = ("tcl/target/atsaml1x.cfg", "5a1b8f8a2bc8f99a718e826aa699ab88cc449522")


def microchip_upstream_openocd_evidence(row: DeviceCatalogRecord) -> dict | None:
    """Explicit source-pinned facts only; no heuristic suffix/family Flash support."""
    if row.vendor != "Microchip":
        return None
    if not (row.production_admitted and row.identifier_kind == "manufacturer_part_number"
            and row.mapping_status == "no_mapping" and not row.target_config
            and row.base_device and row.icpn):
        raise DeviceCatalogIntegrityError("Microchip upstream evidence requires unbound exact Product identity")

    ref = row.source_reference or ""
    if row.family == "PIC32MX":
        devid = PIC32MX_BASE_DEVID.get(row.base_device)
        if not (devid and row.icpn.startswith("PIC32MX")
                and f"partNumber={row.icpn}" in ref
                and f"basePartNumber={row.base_device}" in ref
                and f"expected_devid={devid}" in ref
                and f"git_blob={PIC32_SOURCE_INDEX_BLOB}" in ref
                and f"driver_blob={PIC32_DRIVER_BLOB}" in ref
                and f"source_commit={PIC32_PINNED_COMMIT}" in ref
                and row.verification_status ==
                "verified_microchip_mcp_exact_ordering_and_pinned_openocd_devid"):
            raise DeviceCatalogIntegrityError("PIC32MX official identity / upstream DEVID source pin mismatch")
        target, flash, device_id = PIC32_TARGET, PIC32_DRIVER, devid
    elif row.family == "SAML1X":
        # The upstream SWD target script exists, but declares NO flash bank;
        # the programming-route L1 evidence is a separate Microchip datasheet.
        if not (row.base_device.startswith(("ATSAML10", "ATSAML11"))
                and f"partNumber={row.icpn}" in ref
                and f"basePartNumber={row.base_device}" in ref
                and "DS60001513G" in ref
                and row.verification_status ==
                "verified_microchip_mcp_exact_ordering_and_pdf_applicability"):
            raise DeviceCatalogIntegrityError("SAM L1x upstream CFG / official source pin mismatch")
        target, flash, device_id = SAML1X_TARGET, None, None
    else:
        return None

    return {
        "status": "PINNED_UPSTREAM_SOURCE",
        "scope": "source_only_non_executable",
        "distribution": "upstream-openocd",
        "source_version": OPENOCD_VERSION,
        "source_commit": PIC32_PINNED_COMMIT,
        "target_cfg": {"path": target[0], "git_blob": target[1]},
        "flash_driver": {"path": flash[0], "git_blob": flash[1]} if flash else None,
        "device_id": {"kind": "DEVID", "value": device_id, "source": "pinned_flash_driver_table"} if device_id else None,
        "base_device": row.base_device,
        "production_binding_authorized": False,
        "executable": False,
        "physical_programming_qualified": False,
    }
