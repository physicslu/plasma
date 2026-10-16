"""Microchip SAM L10/L11 OFFICIAL programming-route evidence adapter.

This manufacturer-specific source adapter yields the common route candidate
contract, not a new Product Catalog level, UI policy or execution backend.

Authoritative Microchip SAM L10/L11 Data Sheet DS60001513G (already locked
as the 122 Exact ICPN identity evidence):
  - printed page 3: SWD programming and debugging interface
  - printed page 121: Section 16.7, SWD/DAP, Boot ROM, erase and programming,
    subject to Debug Access Level (DAL) and security restrictions.
These are L1 programming-path evidence. OpenOCD atsaml1x.cfg alone has no
flash bank, so this adapter never claims OpenOCD software support.
"""
from __future__ import annotations

import re

from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError
from .microchip_phase1_admission_guard import (
    PDF_SHA, admitted_microchip_phase1_count,
)
from .route_evidence_admission import AdmittedRouteCandidateRegistry, RouteEvidence


PDF_URL = "https://ww1.microchip.com/downloads/en/DeviceDoc/SAM-L10L11-Family-Data-Sheet-DS60001513G.pdf"
DOCUMENT_REVISION = "DS60001513G"
MCP_URL = "https://api.microchip.com/mcp/resources"
SOURCE_SHA = re.compile(r"original_response_sha256=([0-9a-f]{64})")


def admitted_saml1x_official_programming_routes(
    catalog: DeviceCatalog,
) -> AdmittedRouteCandidateRegistry:
    """Project only existing source-pinned 122 identities into canonical L1.

    This function validates Microchip's frozen identity cohort; it cannot
    manufacture new order codes from DFP target names or Research candidates.
    """
    total = admitted_microchip_phase1_count(catalog)
    if total == 0:
        return AdmittedRouteCandidateRegistry(catalog, ())
    items: list[RouteEvidence] = []
    for row in catalog.records:
        if row.vendor != "Microchip" or row.family != "SAML1X":
            continue
        ref = row.source_reference or ""
        match = SOURCE_SHA.search(ref)
        if not (row.family == "SAML1X"
                and row.base_device
                and row.base_device.startswith(("ATSAML10", "ATSAML11"))
                and match is not None
                and DOCUMENT_REVISION in ref
                and PDF_URL in ref
                and PDF_SHA in ref):
            raise DeviceCatalogIntegrityError(
                f"Microchip official programming route missing pinned source: {row.identifier}"
            )
        items.append(RouteEvidence(
            manufacturer=row.vendor,
            exact_icpn=row.identifier,
            base_device=row.base_device,
            identity_source=MCP_URL,
            identity_sha256=match.group(1),
            base_device_source=ref,
            provider_id="microchip-official-sam-l10-l11-programming-research",
            provider_version=DOCUMENT_REVISION,
            provider_source_commit="",
            route_kind="OFFICIAL_PATH",
            route_source_path=PDF_URL,
            route_source_blob="",
            route_source_sha256=PDF_SHA,
            applicability_source=(
                "DS60001513G printed page 3 (SWD programming);"
                " section 16.7 printed page 121 (Boot ROM/DAP programming, DAL restrictions)"
            ),
            applicability="VERIFIED_BASE_DEVICE",
        ))
    if len(items) != 122:
        raise DeviceCatalogIntegrityError(
            "Microchip SAM L1X route adapter cohort differs from 122 frozen exact identities"
        )
    return AdmittedRouteCandidateRegistry(catalog, tuple(items))
