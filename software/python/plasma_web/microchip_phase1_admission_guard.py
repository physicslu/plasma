"""Immutable Microchip Phase 1 Production identity admission guard.

An admitted manufacturer identity is searchable, but is neither a software
SUPPORTED qualification nor an executable OpenOCD mapping. Keep the exact
122-member publisher-source-verified cohort immutable during migration.
"""
from __future__ import annotations
import hashlib
from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError

EXPECTED_SHA="7a75e18a5f23cc2b80e10e1675918ce7da0601fe0d8d35664ebb78c4fb8d3b64"
EXPECTED=122
PDF_SHA="ee9c04451141173b787374388ddf9b607a5a569415ae85d9b5715237fd1cbb9e"

def admitted_microchip_phase1_count(catalog:DeviceCatalog)->int:
    rows=[r for r in catalog.records if r.vendor=="Microchip"]
    if not rows:
        return 0  # older immutable catalog fixtures remain valid
    ids=sorted(x.identifier for x in rows)
    digest=hashlib.sha256(("".join(code+"\n" for code in ids)).encode()).hexdigest()
    if len(ids)!=EXPECTED or len(set(ids))!=EXPECTED or digest!=EXPECTED_SHA:
        raise DeviceCatalogIntegrityError("Microchip Phase 1 122 exact ICPN identity freeze mismatch")
    for r in rows:
        if not (r.family=="SAML1X" and r.production_admitted
                and r.identifier_kind=="manufacturer_part_number"
                and r.mapping_status=="no_mapping" and not r.target_config
                and r.base_device and r.source_reference
                and "original_response_sha256=" in r.source_reference
                and PDF_SHA in r.source_reference
                and r.source_authority=="Microchip Technology official"
                and r.verification_status==
                    "verified_microchip_mcp_exact_ordering_and_pdf_applicability"):
            raise DeviceCatalogIntegrityError(
                f"{r.identifier}: Microchip Phase 1 identity cannot create backend route or unsupported evidence")
    return EXPECTED
