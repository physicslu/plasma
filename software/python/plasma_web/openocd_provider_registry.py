"""Versioned *metadata-only* OpenOCD provider registry for exact Production ICPNs.

Not an execution router. Never returns an executable command, flash plan,
installed binary attestation or a hardware programming authorization.
Separate versions can have the same reported runtime ID but different
artifact SHA256s; evidence cannot be transferred between their artifacts.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from .backend_candidate_registry import BackendCandidateRegistry
from .backend_provenance import load_source_authorities
from .device_catalog import (
    DeviceCatalog, DeviceCatalogIntegrityError, DeviceCatalogRecord,
    get_default_device_catalog,
)

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_REL = "data/device-catalog/research/st-h5-offline-runtime-evidence-v1.json"
EVIDENCE_GIT_BLOB = "ba332b1209eb6d1202759500558fa777f8baf0a5"
ST_COMMIT = "c8d973bdad9a6fddb51459eda109b3b95d23b57a"
UPSTREAM_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
H5_BUILD_EXPECTED = {
    "x86_64": (
        "1758f03aef0a9ce6bbd212343622b174a85f0bda446bb2e26763113f460a64db",
        "af506c77d06ffb22b178cde078f13f6a8b9272eb101695e1ea1dc00f09dc967e",
        38020833350,
    ),
    "armv7l": (
        "f3a60db251a53bd18bf2a5acb80625abfc47c2eb298bb8a3a17112827cb502cd",
        "a7216d585358faf2710444b04d004c2aa531a16ef105d04129268883f0fc863d",
        38034789548,
    ),
}


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DeviceCatalogIntegrityError(f"OpenOCD provider registry: {reason}")


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _h5_build_evidence(root: Path, fork: dict[str, Any]) -> dict[str, Any]:
    raw = (root / EVIDENCE_REL).read_bytes()
    blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw, usedforsecurity=False).hexdigest()
    _require(blob == EVIDENCE_GIT_BLOB, "H5 reviewed evidence blob drift")
    doc = json.loads(raw)
    _require(doc.get("schema_version") == 1 and doc.get("status") == "OFFLINE_SOFTWARE_ONLY"
             and doc.get("source_commit") == ST_COMMIT
             and doc.get("source_repository") == "https://github.com/STMicroelectronics/OpenOCD.git"
             and doc.get("target_config_path") == fork["files"]["h5_cfg"]["path"]
             and doc.get("target_config_git_blob") == fork["files"]["h5_cfg"]["blob"]
             and doc.get("flash_driver_path") == fork["files"]["h5_flash_driver"]["path"]
             and doc.get("flash_driver_git_blob") == fork["files"]["h5_flash_driver"]["blob"]
             and doc.get("reported_openocd_version") == "0.12.0",
             "H5 source/binary-report provenance drift")
    for gate in ("physical_silicon_qualified", "ppu_installed_runtime_attested",
                 "hardware_runtime_ready", "production_mapping_authorized",
                 "redistribution_license_review_complete"):
        _require(doc.get(gate) is False, f"unsafe H5 qualification gate: {gate}")
    builds = doc.get("builds", [])
    _require(isinstance(builds, list) and len(builds) == 2, "H5 requires two distinct build records")
    architectures = set()
    digests = set()
    for row in builds:
        arch = row.get("architecture")
        _require(arch in H5_BUILD_EXPECTED and arch not in architectures, "unexpected H5 architecture")
        architectures.add(arch)
        artifact, payload, run = H5_BUILD_EXPECTED[arch]
        _require(row.get("artifact_sha256") == artifact
                 and row.get("payload_sha256") == payload
                 and row.get("github_actions_run_id") == run,
                 f"H5 CI source-artifact fingerprint drift: {arch}")
        _require(row.get("runtime_id") == "0.12.0-c8d973bdad9a"
                 and row.get("binary_sha256") is None
                 and row.get("published_binary") is False
                 and row.get("scope") in {
                     "no_real_target_no_fpga_no_hardware",
                     "not_z2_abi_not_fpga_swd_no_real_target",
                 }, f"H5 build scope drift: {arch}")
        _require(row.get("qualification") in {
            "SOURCE_BUILD_AND_DUMMY_JTAG_CFG_PARSE_PASS",
            "ARMV7_SOURCE_BUILD_AND_QEMU_DUMMY_CFG_PARSE_PASS",
        }, "unexpected H5 software test")
        _require(_is_sha256(artifact) and _is_sha256(payload), "invalid H5 build hash")
        digests.add(artifact)
    _require(architectures == set(H5_BUILD_EXPECTED) and len(digests) == 2,
             "runtime_id cannot substitute for individual artifact identity")
    return doc


def _base_provider(row: DeviceCatalogRecord, *, provider_id: str,
                   distribution: str, source_repository: str, commit: str,
                   source_version: str | None, release_runtime_id: str | None,
                   mapping_status: str, target_config: str,
                   driver: str | None, software_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    _require(row.production_admitted and row.identifier_kind == "manufacturer_part_number",
             "provider projection requires admitted exact ICPN")
    _require(row.mapping_status in {"mapped", "no_mapping"}, "unexpected catalog mapping status")
    _require(re.fullmatch("[a-f0-9]{40}", commit) is not None, "source commit must be pinned")
    _require(mapping_status in {"mapped", "candidate"}, "invalid provider mapping scope")
    if mapping_status == "mapped":
        _require(row.mapping_status == "mapped" and row.target_config == target_config,
                 "mapped provider cannot invent a catalog route")
    else:
        _require(row.mapping_status == "no_mapping" and row.target_config == "",
                 "candidate cannot mutate a Production target route")
    return {
        "provider_id": provider_id,
        "provider_distribution": distribution,
        "source_repository": source_repository,
        "source_commit": commit,
        "source_version": source_version,
        "declared_release_runtime_id": release_runtime_id,
        "target_config": target_config,
        "flash_driver": driver,
        "mapping_status": mapping_status,
        "software_build_evidence": software_evidence,
        "installed_runtime_id": None,
        "installed_binary_sha256": None,
        "site_id": None,
        "software_process_capability": "metadata_description_only",
        "qualified_hardware_operations": [],
        "hardware_runtime_ready": False,
        "real_ic_erase_program_verify": False,
        "production_write_authorized": False,
        "executable": False,
        "source_evidence_only": True,
    }


class OpenOCDProviderRegistry:
    """Many-to-one capable source binding; never consumed by Job/Batch execution."""

    def __init__(self, catalog: DeviceCatalog, root: Path = ROOT) -> None:
        self.catalog_revision_sha256 = catalog.revision_sha256
        _require(catalog.status == "production" and catalog.size == 4629,
                 "canonical 4,629-IC Production Catalog required")
        upstream, gap = load_source_authorities(root)
        fork = gap["candidate_st_fork"]
        _require(fork["commit"] == ST_COMMIT and upstream["source_commit"] == UPSTREAM_COMMIT
                 and upstream["runtime_id"] == "0.12.0-9ea7f3d647c8",
                 "openocd source authority changed")
        h5 = _h5_build_evidence(root, fork)
        candidates = BackendCandidateRegistry(catalog, root)
        _require(candidates.size == 362, "expected 362 separately guarded source candidates")
        self._routes: dict[tuple[str, str], tuple[dict[str, Any], ...]] = {}
        cnt = Counter()
        for row in catalog.records:
            key = (row.vendor, row.identifier)
            _require(key not in self._routes, f"duplicate Production ICPN {key}")
            entries = []
            if row.mapping_status == "mapped":
                entries.append(_base_provider(
                    row, provider_id="openocd-upstream",
                    distribution="openocd-org/openocd",
                    source_repository=upstream["source_repository"],
                    commit=upstream["source_commit"],
                    source_version=upstream["version"],
                    release_runtime_id=upstream["runtime_id"],
                    mapping_status="mapped", target_config=row.target_config,
                    driver=None, software_evidence=[],
                ))
                cnt["mapped"] += 1
            else:
                candidate = candidates.lookup(row)
                if candidate is not None:
                    _require(candidate["source_commit"] == ST_COMMIT,
                             "H5/C5 source commit drift")
                    build = h5["builds"] if row.family == "STM32H5" else []
                    entries.append(_base_provider(
                        row, provider_id=candidate["provider_id"],
                        distribution="STMicroelectronics/OpenOCD",
                        source_repository=candidate["source_repository"],
                        commit=candidate["source_commit"],
                        source_version=(h5["reported_openocd_version"]
                                        if row.family == "STM32H5" else None),
                        release_runtime_id=None,  # Offline build artifact is not an installed release.
                        mapping_status="candidate",
                        target_config=candidate["target_config_source_path"],
                        driver=candidate["flash_driver"],
                        software_evidence=[dict(r) for r in build],
                    ))
                    cnt[row.family] += 1
                else:
                    cnt["no_candidate"] += 1
            self._routes[key] = self._guard_distinct_providers(entries)
        _require(cnt == {"mapped": 4164, "STM32H5": 190,
                         "STM32C5": 172, "no_candidate": 103},
                 f"Unexpected catalog/backend baseline {dict(cnt)}")
        _require(len(self._routes) == 4629, "full exact-ICPN graph incomplete")

    @staticmethod
    def _guard_distinct_providers(values: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
        ids = [v["provider_id"] for v in values]
        _require(len(ids) == len(set(ids)), "duplicate provider_id on same ICPN")
        for v in values:
            _require(v["hardware_runtime_ready"] is False and
                     v["real_ic_erase_program_verify"] is False and
                     v["production_write_authorized"] is False and
                     v["executable"] is False and
                     v["installed_runtime_id"] is None and
                     v["installed_binary_sha256"] is None,
                     "source-only provider cannot impersonate a runtime")
        return tuple(sorted(values, key=lambda p: p["provider_id"]))

    def describe(self, manufacturer: str, exact_icpn: str) -> list[dict[str, Any]]:
        """Return isolated per-ICPN descriptive records, never runnable handles."""
        return [
            {**p, "software_build_evidence": [dict(e) for e in p["software_build_evidence"]],
             "qualified_hardware_operations": list(p["qualified_hardware_operations"])}
            for p in self._routes.get((manufacturer, exact_icpn), ())
        ]

    @property
    def inventory(self) -> dict[str, int]:
        c = Counter()
        for rows in self._routes.values():
            for row in rows:
                c[row["provider_id"]] += 1
        return dict(sorted(c.items()))



def offline_build_correlates(record: dict[str, Any], observation: dict[str, Any]) -> bool:
    """Prove equality to a known offline *build artifact* only.

    This cannot attest installed files, prove loader/adapter capability, select
    a Production backend, authorize erase/write, or validate real silicon.
    Even a positive match does not make a source candidate executable.
    """
    if record.get("provider_id") != "openocd-st-h5-research":
        return False
    if observation.get("source_commit") != record.get("source_commit"):
        return False
    b = next((r for r in record["software_build_evidence"]
              if r["architecture"] == observation.get("architecture")), None)
    if b is None:
        return False
    return (
        observation.get("runtime_id") == b["runtime_id"]
        and observation.get("artifact_sha256") == b["artifact_sha256"]
        and observation.get("payload_sha256") == b["payload_sha256"]
        and record.get("executable") is False
        and record.get("installed_binary_sha256") is None
    )
