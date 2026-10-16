"""NXP KL25 pinned OpenOCD L1->L2 review adapter (CANDIDATE ONLY).

The immutable record is evidence of *missing* required qualification, not a
software support claim. It never executes OpenOCD and cannot produce SUPPORTED.
The vendor-neutral ProgrammingQualificationRegistry remains Catalog authority.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .device_catalog import (
    DeviceCatalog, DeviceCatalogIntegrityError, get_default_device_catalog,
)
from .runtime_evidence_root import default_runtime_evidence_root, source_files_available

ICPN = "MKL25Z128VLK4"
VENDOR = "NXP"
CURRENT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
LEGACY = "56b8d93fbe61a78dc903d770820d6d896b6d8134"
REGISTRY_ID = "adr0002-nxp-kl25-current-openocd-candidate-review-v1"

# Git blob integrity locks were independently recorded by earlier NXP reviews.
# Treat the old executor as a historical negative-control, never as authority
# for the approved provider revision.
BLOBS = {
    "release/openocd.json": "08c884b1bf6f5999c6d34c090992a8b59d85971d",
    "data/device-catalog/research/nxp-kl25-commercial-icpn.csv":
        "53087e9082445e7948f88e688ecd890b0454d788",
    "data/device-catalog/research/nxp-kl25-openocd-provider-delta-v1.json":
        "25ed0d2335f22021ae06b463dd7dbda0cb4fc25d",
    "data/device-catalog/research/nxp-kl25-fcf-sector-safety-v1.json":
        "c2995d8501d31301cb4c1507be76379b881b8f96",
    "data/ic-support/benchmarks/nxp-kl25/backend-implementation-lock.json":
        "9b87a1a53df7ce9d361927608b72661327ef6310",
    "data/ic-support/benchmarks/nxp-kl25/vendor-neutral-admission-adapter-contract-v1.json":
        "aa8424d05e5ac913dffa5f774befd284a0aa0776",
}
# All research records must be present together or wholly absent in a slim
# installation. The release pin is checked separately after source availability.
RESEARCH_FILES = tuple(rel for rel in BLOBS if rel != "release/openocd.json")
BLOCKERS = (
    "CURRENT_OPENOCD_TRANSPORT_DRIVER_SEMANTICS_NOT_REQUALIFIED",
    "EXACT_SILICON_REVISION_FLASH_GEOMETRY_NOT_QUALIFIED",
    "FCF_SECTOR_0X400_0X800_OPERATION_SAFETY_NOT_QUALIFIED",
    "CURRENT_PROVIDER_READ_VERIFY_PROGRAM_ERASE_NOT_QUALIFIED",
)


def _require(ok: bool, reason: str) -> None:
    if not ok:
        raise DeviceCatalogIntegrityError("NXP KL25 qualification: " + reason)


def _read_locked(root: Path, rel: str) -> bytes:
    raw = (root / rel).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + bytes((0,)) + raw).hexdigest()
    _require(blob == BLOBS[rel], "evidence Git blob mismatch: " + rel)
    return raw


class NxpKl25QualificationProvider:
    """One exact, reviewed, deliberately INCOMPLETE Provider record."""

    reviewed_exact_keys = ((VENDOR, ICPN),)

    def __init__(self, catalog: DeviceCatalog, root: Path) -> None:
        self._catalog = catalog
        self._root = root
        record = catalog.resolve(VENDOR, ICPN)
        _require(
            record is not None and record.production_admitted
            and record.identity_state == "IDENTIFIED"
            and record.mapping_status == "mapped"
            and record.target_config == "tcl/target/kl25.cfg",
            "canonical exact identity/route drift",
        )
        payload: dict[str, Any] = {}
        for rel in BLOBS:
            if rel.endswith(".json"):
                payload[rel] = json.loads(_read_locked(root, rel))
            else:
                _read_locked(root, rel)

        release = payload["release/openocd.json"]
        delta = payload["data/device-catalog/research/nxp-kl25-openocd-provider-delta-v1.json"]
        fcf = payload["data/device-catalog/research/nxp-kl25-fcf-sector-safety-v1.json"]
        legacy = payload["data/ic-support/benchmarks/nxp-kl25/backend-implementation-lock.json"]
        adapter = payload["data/ic-support/benchmarks/nxp-kl25/vendor-neutral-admission-adapter-contract-v1.json"]

        _require(
            release.get("engine") == "openocd"
            and release.get("version") == "0.12.0"
            and release.get("source_commit") == CURRENT
            and release.get("runtime_id") == "0.12.0-9ea7f3d647c8",
            "approved provider release changed",
        )
        _require(
            legacy.get("commit") == LEGACY
            and legacy.get("admitted_constraints", {}).get("flash_configuration_field_sector_start") == "0x00000400"
            and legacy.get("admitted_constraints", {}).get("flash_configuration_field_sector_size_bytes") == 1024
            and legacy.get("trust_boundary", {}).get("production_admission") is False,
            "historical backend lock/FCF geometry changed",
        )
        _require(
            adapter.get("target") == {"vendor_id": VENDOR, "icpn": ICPN}
            and adapter.get("legacy_release", {}).get("openocd_commit") == LEGACY
            and adapter.get("gate58", {}).get("qualification_status") == "REJECTED_REVIEW",
            "rejected historical Gate 5.8 was rewritten",
        )
        conclusions = delta.get("conclusions", {})
        _require(
            delta.get("prior_software_prototype_commit") == LEGACY
            and delta.get("current_plasma_openocd_commit") == CURRENT
            and conclusions.get("flash_driver_source_changed") is True
            and conclusions.get("tcl_dependency_changed") is True
            and conclusions.get("source_semantic_equivalence_proven") is False
            and conclusions.get("can_transfer_software_profile_admission") is False
            and conclusions.get("current_provider_exact_operations_qualified") is False
            and delta.get("transport_dependency_delta", {}).get(
                "current_provider_transport_selection_independently_qualified") is False,
            "current provider change was qualified without evidence",
        )
        risk = fcf.get("safety_issue", {})
        outcome = fcf.get("result", {})
        _require(
            fcf.get("historical_prototype_commit") == LEGACY
            and fcf.get("approved_provider_commit") == CURRENT
            and fcf.get("kinetis_c_blobs", {}).get("approved")
            == "7137b4aa078719af31122f8276494f006589e8ab"
            and "0x400,0x800" in risk.get("expected_safe_compiler_restriction", "")
            and outcome.get("current_provider_operation_qualification_certified") is False
            and outcome.get("source_semantic_equivalence_certified") is False
            and outcome.get("all_nxp_phase2_supported_new_from_this_change") == 0,
            "FCF safety audit/qualification limits changed",
        )
        self._provider = {
            "provider_id": "openocd-upstream",
            "version": release["version"],
            "source_commit": CURRENT,
            "runtime_id": release["runtime_id"],
            "target_config": "tcl/target/kl25.cfg",
            "flash_driver": "kinetis",
        }

    def lookup(self, manufacturer: str, exact_icpn: str) -> dict[str, Any] | None:
        return self.describe(manufacturer, exact_icpn) if (manufacturer, exact_icpn) == (VENDOR, ICPN) else None

    def describe(self, manufacturer: str, exact_icpn: str) -> dict[str, Any]:
        if (manufacturer, exact_icpn) != (VENDOR, ICPN):
            return {"software_state": "UNKNOWN", "reviewed": False}
        return {
            "schema_version": "1.0.0",
            "registry_id": REGISTRY_ID,
            "software_state": "CANDIDATE",
            "reviewed": True,
            "provider": dict(self._provider),
            "operations": {op: {"state": "UNKNOWN", "scope": "not_qualified"}
                           for op in ("READ", "VERIFY", "PROGRAM", "ERASE")},
            "programming": None,
            "qualification_gaps": list(BLOCKERS),
            "installed_runtime_attested": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }


@lru_cache(maxsize=1)
def get_default_nxp_kl25_qualification_provider() -> NxpKl25QualificationProvider | None:
    root = default_runtime_evidence_root()
    if not source_files_available(root, RESEARCH_FILES):
        return None
    _require(root is not None, "root missing despite full evidence")
    return NxpKl25QualificationProvider(get_default_device_catalog(), root)
