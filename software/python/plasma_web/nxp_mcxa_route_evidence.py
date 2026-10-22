"""Pinned, metadata-only NXP MCX A Secure Provisioning Tool L1 routes.

The NXP 26.06 processor list and A1/A2/A3/L2 workflow identify internal
Flash/ISP programming over UART/USB. They do not qualify a PLASMA runtime,
OpenOCD flash driver, or a physical programming operation. MCXA18x is held
at L0: listed as a processor, but absent from the reviewed workflow chapter.
"""
from __future__ import annotations

import hashlib
import re

from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError
from .route_evidence_admission import AdmittedRouteCandidateRegistry, RouteEvidence


VERSION = "26.06"
PROCESSORS_URL = "https://mcuxpresso.nxp.com/secure/26.06/release_notes.html"
PROCESSORS_SHA256 = "5f58034e556df7d3c7a7c99aae8ded8aa9e339e2dcd1e81fd452119c830b0205"
WORKFLOW_URL = "https://mcuxpresso.nxp.com/secure/26.06/06_processor_specific_workflow.html"
WORKFLOW_SHA256 = "9298f884dbb7dd1da4f543c0a8cdc49ffb51353128d5a83b4ff192fa6ea349ab"
ELIGIBLE_BASES = frozenset({
    "MCXA132", "MCXA133", "MCXA142", "MCXA143", "MCXA144", "MCXA145", "MCXA146",
    "MCXA152", "MCXA153", "MCXA154", "MCXA155", "MCXA156",
    "MCXA173", "MCXA174", "MCXA175", "MCXA176",
    "MCXA255", "MCXA256", "MCXA265", "MCXA266",
    "MCXA343", "MCXA344", "MCXA345", "MCXA346",
    "MCXA355", "MCXA356", "MCXA365", "MCXA366",
})
COHORT_SHA256 = "d316dd29e25dd4f137ff4daf2959137aa269156e2d7ae70f0033a88999014e78"
_IDENTITY_SHA = re.compile(r"manufacturer HTML SHA256 ([0-9a-f]{64});")
_FAMILY = re.compile(r"MCXA(13|14|15|17|25|26|34|35|36)\d")


def admitted_nxp_mcxa_official_programming_routes(catalog: DeviceCatalog) -> AdmittedRouteCandidateRegistry:
    rows = [r for r in catalog.records if r.vendor == "NXP" and r.family == "MCX"
            and r.identifier.startswith("MCXA")]
    if not rows:
        return AdmittedRouteCandidateRegistry(catalog, ())
    if len(rows) != 119 or len({r.identifier for r in rows}) != 119:
        raise DeviceCatalogIntegrityError("MCX A admission: canonical 119 exact ICPNs drifted")

    chosen = []
    for row in rows:
        base = row.identifier[:7]
        if base not in ELIGIBLE_BASES:
            if base not in {"MCXA185", "MCXA186"}:
                raise DeviceCatalogIntegrityError("MCX A admission: unknown official base " + base)
            continue
        family = _FAMILY.match(base)
        source = row.source_reference or ""
        identity_sha = _IDENTITY_SHA.search(source)
        if (family is None or row.base_device != row.identifier
                or row.mapping_status != "no_mapping" or row.target_config
                or row.source_type != "official_nxp_independent_exact_part_html_replay"
                or row.source_authority != f"https://www.nxp.com/part/{row.identifier}"
                or f"page /part/{row.identifier};" not in source
                or identity_sha is None):
            raise DeviceCatalogIntegrityError("MCX A admission: unproven identity/route " + row.identifier)
        chosen.append(RouteEvidence(
            manufacturer="NXP", exact_icpn=row.identifier, base_device=row.base_device,
            identity_source=row.source_authority, identity_sha256=identity_sha.group(1),
            base_device_source=source,
            provider_id="nxp-mcuxpresso-sec-official-isp-programming-research",
            provider_version=VERSION, provider_source_commit="", route_kind="OFFICIAL_PATH",
            route_source_path=WORKFLOW_URL, route_source_blob="",
            route_source_sha256=WORKFLOW_SHA256,
            applicability="VERIFIED_FAMILY",
            applicability_source=(
                f"NXP SEC {VERSION} supported processors {PROCESSORS_URL} sha256={PROCESSORS_SHA256}; "
                f"processor-specific MCX A1/A2/A3/L2 workflow {WORKFLOW_URL} "
                f"sha256={WORKFLOW_SHA256}; processor family MCXA{family.group(1)}x; "
                "ISP UART/USB internal Flash only; A25/A26/A36 HSM workflow differs"
            ),
        ))
    names = sorted(r.exact_icpn for r in chosen)
    digest = hashlib.sha256("\n".join(names).encode()).hexdigest()
    if len(names) != 111 or digest != COHORT_SHA256:
        raise DeviceCatalogIntegrityError("MCX A admission: exact 111-ICPN reviewed cohort drifted")
    return AdmittedRouteCandidateRegistry(catalog, tuple(chosen))
