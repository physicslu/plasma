"""Fail-closed Microchip Production exact identity admission guard.

Preserve the historical 122 SAM L10/L11 identities byte-for-byte and admit
only the separately source-pinned 893 PIC32MX exact MCP order codes.
Neither identity cohort authorizes OpenOCD execution, L2 or physical burning.
"""
from __future__ import annotations

import hashlib
import re

from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError

EXPECTED_SHA = "7a75e18a5f23cc2b80e10e1675918ce7da0601fe0d8d35664ebb78c4fb8d3b64"
EXPECTED = 122
PDF_SHA = "ee9c04451141173b787374388ddf9b607a5a569415ae85d9b5715237fd1cbb9e"
PIC32_EXPECTED = 893
PIC32_BASE_EXPECTED = 85
PIC32_SOURCE_INDEX_BLOB = "2f7a2b1b768e2c4ccb0eb184330c405cc3826357"
PIC32_DRIVER_BLOB = "9a1a6341256039bf9fd68e41a109e7483a5f694e"
PIC32_PINNED_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
SAM_PHASE2_COHORTS = {
    "SAMDCRL0": (538, 59, "src/flash/nor/at91samd.c",
                "33e86c76e9f8310510844793da3f3074ed5dae8f"),
    "SAMD5E5": (354, 25, "src/flash/nor/atsame5.c",
                "fdd610f5f38bcbeddd3131105f046c7b67f30381"),
}
SAM_PHASE2_ORIGINAL_BLOB = PIC32_SOURCE_INDEX_BLOB

_SHA256 = re.compile(r"original_response_sha256=([0-9a-f]{64})(?:;|\\s|$)")


def _require(ok: bool, why: str) -> None:
    if not ok:
        raise DeviceCatalogIntegrityError(f"Microchip exact identity freeze: {why}")


def admitted_microchip_phase1_count(catalog: DeviceCatalog) -> int:
    """Validate each cohort independently; never infer identities from CFG."""
    rows = [r for r in catalog.records if r.vendor == "Microchip"]
    if not rows:
        return 0  # Pre-Microchip/fixture catalogs remain valid.

    sam = [r for r in rows if r.family == "SAML1X"]
    ids = sorted(x.identifier for x in sam)
    digest = hashlib.sha256(("".join(code + "\n" for code in ids)).encode()).hexdigest()
    _require(len(sam) == EXPECTED and len(set(ids)) == EXPECTED and digest == EXPECTED_SHA,
             "historical SAML1X 122 exact ICPN identity membership changed")
    for row in sam:
        _require(
            row.production_admitted
            and row.identifier_kind == "manufacturer_part_number"
            and row.mapping_status == "no_mapping"
            and not row.target_config
            and bool(row.base_device)
            and bool(row.source_reference)
            and "original_response_sha256=" in row.source_reference
            and PDF_SHA in row.source_reference
            and row.source_authority == "Microchip Technology official"
            and row.verification_status ==
                "verified_microchip_mcp_exact_ordering_and_pdf_applicability",
            f"{row.identifier}: historical SAML1X identity/route freeze violated",
        )

    pic = [r for r in rows if r.family == "PIC32MX"]
    phase2 = [r for r in rows if r.family in SAM_PHASE2_COHORTS]
    _require(len(rows) == len(sam) + len(pic) + len(phase2),
             "unknown Microchip family bypass")
    allowed_counts = {family: sum(row.family == family for row in phase2)
                      for family in SAM_PHASE2_COHORTS}
    # Never accept a partially landed Phase-2 source/manifest.
    _require(allowed_counts in (
        {"SAMDCRL0": 0, "SAMD5E5": 0},
        {"SAMDCRL0": 538, "SAMD5E5": 354},
    ), "partial Microchip SAM Phase-2 official identity cohort")
    for family, (expected, base_count, driver_path, driver_sha) in SAM_PHASE2_COHORTS.items():
        subset = [r for r in phase2 if r.family == family]
        if not subset:
            continue
        _require(len(subset) == expected
                 and len({r.identifier.casefold() for r in subset}) == expected
                 and len({r.base_device for r in subset}) == base_count,
                 f"{family}: manufacturer identities/Base Device set drift")
        for row in subset:
            ref = row.source_reference or ""
            _require(
                row.production_admitted
                and row.identifier_kind == "manufacturer_part_number"
                and row.identifier.startswith("AT")
                and bool(row.base_device)
                and row.base_device.startswith("AT")
                and row.mapping_status == "no_mapping"
                and not row.target_config
                and f"partNumber={row.identifier}" in ref
                and f"basePartNumber={row.base_device}" in ref
                and f"original_replay_index_git_blob={SAM_PHASE2_ORIGINAL_BLOB}" in ref
                and f"source_commit={PIC32_PINNED_COMMIT}" in ref
                and f"driver_path={driver_path}" in ref
                and f"driver_blob={driver_sha}" in ref
                and f"explicit_driver_part={row.base_device[2:]}" in ref
                and "driver_devsel=0x" in ref
                and "candidate_only_no_executable_mapping" in ref
                and _SHA256.search(ref) is not None
                and row.source_type ==
                    "microchip_official_mcp_replayed_identity_openocd_driver_devsel"
                and row.source_authority == "Microchip Technology official"
                and row.verification_status ==
                    "verified_microchip_mcp_exact_ordering_and_pinned_driver_part_devsel",
                f"{row.identifier}: SAM Phase-2 exact identity/source guard rejected",
            )
    # Both old 122-member fixtures and new independently admitted 893 cohort
    # are valid. Partial/changed Product source membership fails closed.
    _require(len(pic) in (0, PIC32_EXPECTED), "partial PIC32MX identity admission")
    if pic:
        _require(len({r.identifier.casefold() for r in pic}) == PIC32_EXPECTED,
                 "duplicate PIC32MX manufacturer part number")
        bases = {r.base_device for r in pic}
        _require(len(bases) == PIC32_BASE_EXPECTED, "PIC32MX Base Device freeze changed")
        for row in pic:
            ref = row.source_reference or ""
            match = _SHA256.search(ref)
            _require(
                row.production_admitted
                and row.identifier_kind == "manufacturer_part_number"
                and row.identifier.startswith("PIC32MX")
                and bool(row.base_device)
                and row.base_device.startswith("PIC32MX")
                # Do NOT infer order-code syntax from Base Device; manufacturer\n                # explicitly supplies the exact code/base link for BT/T variants.\n                and row.mapping_status == "no_mapping"
                and not row.target_config
                and match is not None
                and f"basePartNumber={row.base_device}" in ref
                and f"partNumber={row.identifier}" in ref
                and f"git_blob={PIC32_SOURCE_INDEX_BLOB}" in ref
                and f"driver_blob={PIC32_DRIVER_BLOB}" in ref
                and f"source_commit={PIC32_PINNED_COMMIT}" in ref
                and row.source_authority == "Microchip Technology official"
                and row.verification_status ==
                    "verified_microchip_mcp_exact_ordering_and_pinned_openocd_devid",
                f"{row.identifier}: PIC32MX original identity/driver source pin invalid",
            )
    return len(rows)
