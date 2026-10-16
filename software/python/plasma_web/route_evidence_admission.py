"""Vendor-neutral, fail-closed admission of source-backed candidate routes.

An admission is not a programming provider, executable route, or support claim.
Entries must be independently sourced and joined to exact canonical identities.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, DeviceCatalogRecord


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SHA1 = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class RouteEvidence:
    manufacturer: str
    exact_icpn: str
    base_device: str
    identity_source: str
    identity_sha256: str
    base_device_source: str
    provider_id: str
    provider_version: str
    provider_source_commit: str
    route_kind: str
    route_source_path: str
    route_source_blob: str
    applicability_source: str
    applicability: str
    route_source_sha256: str = ""  # Official non-Git programming documents


class AdmittedRouteCandidateRegistry:
    """Read-only candidate lookup compatible with ProgrammingQualificationRegistry.

    The constructor accepts only individually reviewed evidence. It does not
    convert a bulk Research coverage report into Production identities or L1.
    """

    def __init__(self, catalog: DeviceCatalog, evidence: tuple[RouteEvidence, ...]):
        self._by_key: dict[tuple[str, str], dict[str, object]] = {}
        identities = {
            (r.vendor.casefold(), r.identifier.casefold()): r for r in catalog.records
            if r.identity_state == "IDENTIFIED" and r.production_admitted
            and r.identifier_kind == "manufacturer_part_number"
        }
        for item in evidence:
            key = (item.manufacturer.strip().casefold(), item.exact_icpn.strip().casefold())
            row = identities.get(key)
            self._require(row is not None, "missing admitted exact manufacturer identity")
            self._require(key not in self._by_key, "duplicate exact ICPN candidate evidence")
            self._require(bool(item.base_device.strip()), "missing verified base device")
            self._require(row.base_device is not None and row.base_device.casefold() == item.base_device.casefold(),
                          "base device does not match admitted identity")
            self._require(bool(item.identity_source.strip()) and bool(item.base_device_source.strip()),
                          "missing manufacturer identity/base-device provenance")
            self._require(_SHA256.fullmatch(item.identity_sha256) is not None, "invalid identity source digest")
            self._require(bool(item.provider_id.strip()) and bool(item.provider_version.strip()),
                          "missing provider identity/version")
            if item.route_kind == "OFFICIAL_PATH":
                self._require(not item.provider_source_commit or
                              _SHA1.fullmatch(item.provider_source_commit) is not None,
                              "invalid optional provider commit")
            else:
                self._require(_SHA1.fullmatch(item.provider_source_commit) is not None,
                              "provider source commit not locked")
            self._require(item.route_kind in {"TARGET", "DRIVER", "ALGORITHM", "ROM_IAP", "OFFICIAL_PATH"},
                          "unrecognized route kind")
            if item.route_kind == "OFFICIAL_PATH":
                self._require(item.route_source_path.startswith("https://")
                              and _SHA256.fullmatch(item.route_source_sha256) is not None
                              and not item.route_source_blob,
                              "official route must have immutable HTTPS/document SHA-256 evidence")
            else:
                self._require(bool(item.route_source_path.strip()) and
                              _SHA1.fullmatch(item.route_source_blob) is not None
                              and not item.route_source_sha256,
                              "Git route source path/blob must be immutable")
            self._require(item.applicability in {"EXACT_ICPN", "VERIFIED_BASE_DEVICE", "VERIFIED_FAMILY"},
                          "route applicability has not been validated")
            self._require(bool(item.applicability_source.strip()), "missing applicability provenance")
            if catalog.status == "production":
                self._require(isinstance(row.source_reference, str)
                              and item.identity_sha256 in row.source_reference
                              and f"basePartNumber={item.base_device}" in row.source_reference
                              and bool(row.source_authority),
                              "production route identity provenance not bound to canonical row")
            self._by_key[key] = {
                "status": "research_only",
                "family": row.family,
                "provider_id": item.provider_id,
                "source_commit": item.provider_source_commit,
                "target_config_source_path": item.route_source_path,
                "target_config_git_blob": item.route_source_blob or None,
                "route_source_sha256": item.route_source_sha256 or None,
                "route_source_url": item.route_source_path if item.route_kind == "OFFICIAL_PATH" else None,
                "route_kind": item.route_kind,
                "applicability": item.applicability,
                "applicability_source": item.applicability_source,
                "executable": False,
                "production_binding_authorized": False,
                "hardware_runtime_ready": False,
                "physical_programming_qualified": False,
            }

    @staticmethod
    def _require(ok: bool, reason: str) -> None:
        if not ok:
            raise DeviceCatalogIntegrityError(f"route evidence admission: {reason}")

    def lookup(self, row: DeviceCatalogRecord):
        return self._by_key.get((row.vendor.casefold(), row.identifier.casefold()))
