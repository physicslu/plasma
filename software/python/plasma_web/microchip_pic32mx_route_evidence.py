"""OpenOCD v0.12.0 PIC32MX exact Base-Device DEVID candidate evidence.

85 source-locked names are copied from the pinned v0.12.0 pic32mx.c driver,
then independently cross-checked against Microchip original MCP exact identity
ordering records (893 commercial ICPNs). The canonical Product source and its
own Git blob SHA256 are checked separately by DeviceCatalog.from_manifest.

No executable target binding, operations, L2 qualification, or Job admission.
"""
from __future__ import annotations

from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError
from .microchip_phase1_admission_guard import (
    PIC32_EXPECTED, PIC32_BASE_EXPECTED, PIC32_SOURCE_INDEX_BLOB,
    PIC32_DRIVER_BLOB, PIC32_PINNED_COMMIT, admitted_microchip_phase1_count,
)
from .route_evidence_admission import AdmittedRouteCandidateRegistry, RouteEvidence


DRIVER_PATH = "src/flash/nor/pic32mx.c"
PINNED_VERSION = "0.12.0"
SOURCE_MAP_GIT_BLOB = "a25999e95be1c5c4dd64e82961f051680d88d430"
ORIGINAL_MCP_URI = "https://api.microchip.com/mcp/resources"

# Explicit OpenOCD DEVID table names; no device-family prefix, suffix or
# package guesses. Static inclusion allows packaged runtimes without research.
PIC32MX_BASE_DEVID = {
    "PIC32MX110F016B": "0x04A07053",
    "PIC32MX110F016D": "0x04A0B053",
    "PIC32MX120F032B": "0x04A06053",
    "PIC32MX120F032D": "0x04A0A053",
    "PIC32MX130F064B": "0x04D07053",
    "PIC32MX130F064C": "0x04D09053",
    "PIC32MX130F064D": "0x04D0B053",
    "PIC32MX150F128B": "0x04D06053",
    "PIC32MX150F128C": "0x04D08053",
    "PIC32MX150F128D": "0x04D0A053",
    "PIC32MX170F256B": "0x06610053",
    "PIC32MX170F256D": "0x0661A053",
    "PIC32MX210F016B": "0x04A01053",
    "PIC32MX210F016D": "0x04A05053",
    "PIC32MX220F032B": "0x04A00053",
    "PIC32MX220F032D": "0x04A04053",
    "PIC32MX230F064B": "0x04D01053",
    "PIC32MX230F064C": "0x04D03053",
    "PIC32MX230F064D": "0x04D05053",
    "PIC32MX250F128B": "0x04D00053",
    "PIC32MX250F128C": "0x04D02053",
    "PIC32MX250F128D": "0x04D04053",
    "PIC32MX270F256B": "0x06600053",
    "PIC32MX270F256D": "0x0660A053",
    "PIC32MX320F032H": "0x00902053",
    "PIC32MX320F064H": "0x00906053",
    "PIC32MX320F128H": "0x0090A053",
    "PIC32MX320F128L": "0x0092A053",
    "PIC32MX330F064H": "0x05600053",
    "PIC32MX330F064L": "0x05601053",
    "PIC32MX340F128H": "0x0090D053",
    "PIC32MX340F128L": "0x0092D053",
    "PIC32MX340F256H": "0x00912053",
    "PIC32MX340F512H": "0x00916053",
    "PIC32MX350F128H": "0x0570C053",
    "PIC32MX350F128L": "0x0570D053",
    "PIC32MX350F256H": "0x05704053",
    "PIC32MX350F256L": "0x05705053",
    "PIC32MX360F256L": "0x00934053",
    "PIC32MX360F512L": "0x00938053",
    "PIC32MX370F512H": "0x05808053",
    "PIC32MX370F512L": "0x05809053",
    "PIC32MX420F032H": "0x00942053",
    "PIC32MX430F064H": "0x05602053",
    "PIC32MX430F064L": "0x05603053",
    "PIC32MX440F128H": "0x0094D053",
    "PIC32MX440F128L": "0x0096D053",
    "PIC32MX440F256H": "0x00952053",
    "PIC32MX440F512H": "0x00956053",
    "PIC32MX450F128H": "0x0570E053",
    "PIC32MX450F128L": "0x0570F053",
    "PIC32MX450F256H": "0x05706053",
    "PIC32MX450F256L": "0x05707053",
    "PIC32MX460F256L": "0x00974053",
    "PIC32MX460F512L": "0x00978053",
    "PIC32MX470F512H": "0x0580A053",
    "PIC32MX470F512L": "0x0580B053",
    "PIC32MX534F064H": "0x04400053",
    "PIC32MX534F064L": "0x0440C053",
    "PIC32MX564F064H": "0x04401053",
    "PIC32MX564F064L": "0x0440D053",
    "PIC32MX564F128H": "0x04403053",
    "PIC32MX564F128L": "0x0440F053",
    "PIC32MX575F256H": "0x04317053",
    "PIC32MX575F256L": "0x04333053",
    "PIC32MX575F512H": "0x04309053",
    "PIC32MX575F512L": "0x0430F053",
    "PIC32MX664F064H": "0x04405053",
    "PIC32MX664F064L": "0x04411053",
    "PIC32MX664F128H": "0x04407053",
    "PIC32MX664F128L": "0x04413053",
    "PIC32MX675F256H": "0x0430B053",
    "PIC32MX675F256L": "0x04305053",
    "PIC32MX675F512H": "0x0430C053",
    "PIC32MX675F512L": "0x04311053",
    "PIC32MX695F512H": "0x04325053",
    "PIC32MX695F512L": "0x04341053",
    "PIC32MX764F128H": "0x0440B053",
    "PIC32MX764F128L": "0x04417053",
    "PIC32MX775F256H": "0x04303053",
    "PIC32MX775F256L": "0x04312053",
    "PIC32MX775F512H": "0x0430D053",
    "PIC32MX775F512L": "0x04306053",
    "PIC32MX795F512H": "0x0430E053",
    "PIC32MX795F512L": "0x04307053",
}


def admitted_pic32mx_openocd_devid_routes(
    catalog: DeviceCatalog,
) -> AdmittedRouteCandidateRegistry:
    """Normalize only already-admitted official PIC32MX identities to L1."""
    _ = admitted_microchip_phase1_count(catalog)
    rows = [r for r in catalog.records
            if r.vendor == "Microchip" and r.family == "PIC32MX"]
    if not rows:
        return AdmittedRouteCandidateRegistry(catalog, ())
    if (len(rows) != PIC32_EXPECTED or
            len(PIC32MX_BASE_DEVID) != PIC32_BASE_EXPECTED or
            set(r.base_device for r in rows) != set(PIC32MX_BASE_DEVID)):
        raise DeviceCatalogIntegrityError(
            "PIC32MX 893 exact ICPNs / 85 version-pinned DEVIDs inconsistent"
        )
    evidence = []
    for row in rows:
        ref = row.source_reference or ""
        base = row.base_device or ""
        devid = PIC32MX_BASE_DEVID.get(base)
        marker = "original_response_sha256="
        if (devid is None or marker not in ref
                or f"expected_devid={devid}" not in ref
                or f"git_blob={PIC32_SOURCE_INDEX_BLOB}" not in ref
                or f"driver_blob={PIC32_DRIVER_BLOB}" not in ref
                or f"source_commit={PIC32_PINNED_COMMIT}" not in ref):
            raise DeviceCatalogIntegrityError(
                f"PIC32MX OpenOCD route evidence/source mismatch: {row.identifier}"
            )
        digest = ref.split(marker, 1)[1][:64]
        evidence.append(RouteEvidence(
            manufacturer="Microchip",
            exact_icpn=row.identifier,
            base_device=base,
            identity_source=ORIGINAL_MCP_URI,
            identity_sha256=digest,
            base_device_source=ref,
            provider_id="openocd-upstream-pic32mx-driver-candidate",
            provider_version=PINNED_VERSION,
            provider_source_commit=PIC32_PINNED_COMMIT,
            route_kind="DRIVER",
            route_source_path=DRIVER_PATH,
            route_source_blob=PIC32_DRIVER_BLOB,
            applicability_source=(
                f"OpenOCD {PINNED_VERSION} {DRIVER_PATH} "
                f"pic32mx_devs[] explicit named Device ID {base}={devid}; "
                f"locked driver blob {PIC32_DRIVER_BLOB}; "
                f"source-locked mapping snapshot {SOURCE_MAP_GIT_BLOB}"
            ),
            applicability="VERIFIED_BASE_DEVICE",
        ))
    return AdmittedRouteCandidateRegistry(catalog, tuple(evidence))
