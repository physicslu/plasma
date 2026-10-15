"""ADR-0002 Phase 2A OpenOCD software-qualification registry.

This registry is intentionally separate from:
- Production identity admission,
- OpenOCD mapping metadata,
- installed runtime attestation,
- Phase 3 physical compatibility,
- Job/Batch execution authorization.

Only exact ICPNs explicitly present in the reviewed qualification ledger can
return SUPPORTED. All other exact ICPNs remain UNKNOWN by default.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from .device_catalog import (
    DeviceCatalog,
    DeviceCatalogIntegrityError,
    get_default_device_catalog,
)
from .runtime_evidence_root import default_runtime_evidence_root, source_files_available


ROOT = default_runtime_evidence_root()
SOURCE_LOCK_REL = "data/ic-support/software-qualification/openocd-0.12.0-stm32f1-source-lock-v1.json"
QUALIFICATION_REL = "data/ic-support/software-qualification/openocd-0.12.0-stm32f103c-reference-v1.json"
RELEASE_REL = "release/openocd.json"
SOFTWARE_STATES = frozenset({"UNKNOWN", "CANDIDATE", "SUPPORTED", "UNSUPPORTED"})
REQUIRED_OPERATIONS = ("probe", "erase", "program", "read", "verify")


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise DeviceCatalogIntegrityError(f"OpenOCD software qualification: {reason}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeviceCatalogIntegrityError(f"cannot read qualification evidence: {path}") from exc
    _require(isinstance(payload, dict), f"top-level object required: {path}")
    return payload


def _git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(raw)}\0".encode("ascii") + raw,
        usedforsecurity=False,
    ).hexdigest()


class OpenOCDSoftwareQualificationRegistry:
    """Reviewed software qualification; never a hardware/runtime execution grant."""

    def __init__(self, catalog: DeviceCatalog, root: Path | None = ROOT) -> None:
        _require(root is not None, "explicit/full evidence root required")
        self._catalog = catalog
        self._root = root

        release = _read_json(root / RELEASE_REL)
        source_lock = _read_json(root / SOURCE_LOCK_REL)
        qualification = _read_json(root / QUALIFICATION_REL)

        provider = source_lock.get("provider", {})
        _require(
            release.get("engine") == "openocd"
            and release.get("version") == "0.12.0"
            and release.get("source_tag") == "v0.12.0"
            and release.get("source_commit") == "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
            and release.get("runtime_id") == "0.12.0-9ea7f3d647c8",
            "pinned release identity drift",
        )
        _require(
            provider.get("source_commit") == release["source_commit"]
            and provider.get("source_tag") == release["source_tag"]
            and provider.get("runtime_id") == release["runtime_id"],
            "source-lock provider does not match packaged release authority",
        )
        _require(
            qualification.get("provider_source_lock_id") == source_lock.get("source_lock_id"),
            "qualification/source-lock identity mismatch",
        )
        q_provider = qualification.get("provider", {})
        _require(
            q_provider.get("provider_id") == "openocd-upstream"
            and q_provider.get("version") == release["version"]
            and q_provider.get("source_commit") == release["source_commit"]
            and q_provider.get("runtime_id") == release["runtime_id"]
            and q_provider.get("target_config") == "tcl/target/stm32f1x.cfg"
            and q_provider.get("flash_driver") == "stm32f1x",
            "qualification provider drift",
        )

        files = source_lock.get("files")
        _require(isinstance(files, dict), "source-lock files missing")
        expected_external = {
            "target_config": ("tcl/target/stm32f1x.cfg", "53e81a59f6b479cb503e7b73ba32bfbe9c685313"),
            "flash_driver": ("src/flash/nor/stm32f1x.c", "ab1ef2aefef0642d831a088a8c915f6ea9021f00"),
            "flash_framework": ("src/flash/nor/tcl.c", "4ff6d983868f74233235189b2d90efd11c7f9ae5"),
        }
        for key, (path, blob) in expected_external.items():
            item = files.get(key)
            _require(
                isinstance(item, dict)
                and item.get("path") == path
                and item.get("git_blob_sha1") == blob,
                f"reviewed upstream source lock drift: {key}",
            )

        local_locks = qualification.get("local_evidence_locks")
        _require(isinstance(local_locks, dict) and local_locks, "local evidence locks missing")
        for rel, expected_blob in local_locks.items():
            path = root / rel
            _require(path.is_file(), f"local evidence missing: {rel}")
            _require(
                _git_blob_sha1(path.read_bytes()) == expected_blob,
                f"local evidence blob drift: {rel}",
            )

        review = _read_json(
            root / "data/ic-support/benchmarks/stm32f103c/vendor-neutral-admission-contract-v1.json"
        )
        _require(
            review.get("shared", {}).get("programming_profile_id")
            == "stm32f1-medium-density-flash-v0",
            "reviewed Programming Profile drift",
        )
        admitted_ops = set(review.get("operations", {}).get("admitted", []))
        _require(
            admitted_ops == {"READ", "VERIFY", "PROGRAM", "ERASE"},
            "manufacturer review operation scope drift",
        )

        group = qualification.get("manufacturer_programming_group")
        _require(isinstance(group, dict), "programming group missing")
        opq = group.get("operation_qualification")
        _require(isinstance(opq, dict), "operation qualification missing")
        for operation in REQUIRED_OPERATIONS:
            _require(
                opq.get(operation, {}).get("state") == "SUPPORTED",
                f"reference operation not software-qualified: {operation}",
            )
        _require(
            group.get("programming_electrical", {}).get("external_vpp_required") is False,
            "external VPP qualification drift",
        )
        _require(
            group.get("programming_electrical", {}).get("vdd_programming_v")
            == {"min": 2.0, "max": 3.6},
            "programming VDD qualification drift",
        )

        self._records: dict[tuple[str, str], dict[str, Any]] = {}
        catalog_by_key = {(row.vendor, row.identifier): row for row in catalog.records}
        review_targets = review.get("targets", {})
        for raw in qualification.get("records", []):
            _require(isinstance(raw, dict), "qualification record must be object")
            state = raw.get("software_state")
            _require(state in SOFTWARE_STATES, f"invalid software state: {state!r}")
            key = (raw.get("manufacturer"), raw.get("icpn"))
            _require(
                all(isinstance(v, str) and v for v in key)
                and key not in self._records,
                f"invalid/duplicate exact qualification key: {key}",
            )
            row = catalog_by_key.get(key)
            _require(row is not None, f"qualified ICPN missing from Production Catalog: {key}")
            _require(
                row.production_admitted
                and row.identifier_kind == "manufacturer_part_number"
                and row.family == "STM32F1"
                and row.mapping_status == "mapped"
                and row.target_config == q_provider["target_config"],
                f"qualified exact ICPN Production route drift: {key[1]}",
            )
            target = review_targets.get(key[1])
            _require(isinstance(target, dict), f"manufacturer review target missing: {key[1]}")
            _require(
                raw.get("base_device") == target.get("base_device")
                and raw.get("memory_geometry_profile_id") == target.get("memory_geometry_profile_id")
                and raw.get("main_flash_size_bytes") == target.get("main_flash_size_bytes")
                and raw.get("page_count") == target.get("page_count"),
                f"exact geometry/applicability drift: {key[1]}",
            )
            _require(
                raw.get("programming_profile_id") == group.get("manufacturer_evidence", {}).get("programming_profile_id"),
                f"Programming Profile mismatch: {key[1]}",
            )
            _require(
                raw.get("operations") == list(REQUIRED_OPERATIONS),
                f"exact operation set mismatch: {key[1]}",
            )
            self._records[key] = deepcopy(raw)

        _require(
            set(self._records)
            == {
                ("STMicroelectronics", "STM32F103C8T6"),
                ("STMicroelectronics", "STM32F103CBT6"),
            },
            "Phase 2A reference scope expanded without review",
        )
        _require(
            all(record["software_state"] == "SUPPORTED" for record in self._records.values()),
            "reference cohort must be explicitly SUPPORTED",
        )

        boundary = qualification.get("acceptance_boundary", {})
        for key in (
            "public_catalog_visibility_changed",
            "job_batch_execution_changed",
            "installed_runtime_attested",
            "hardware_runtime_ready",
            "physical_programming_qualified",
            "phase3_compatibility_claimed",
        ):
            _require(boundary.get(key) is False, f"unsafe Phase 2A boundary: {key}")

        self.source_lock_id = source_lock["source_lock_id"]
        self.qualification_id = qualification["qualification_id"]
        self.provider = deepcopy(q_provider)
        self.operation_qualification = deepcopy(opq)
        self.acceptance_boundary = deepcopy(boundary)
        self.default_unreviewed_state = qualification.get("default_unreviewed_software_state")
        _require(self.default_unreviewed_state == "UNKNOWN", "unreviewed exact ICPNs must remain UNKNOWN")

    def lookup(self, manufacturer: str, exact_icpn: str) -> dict[str, Any] | None:
        record = self._records.get((manufacturer, exact_icpn))
        return deepcopy(record) if record is not None else None

    def state_for(self, manufacturer: str, exact_icpn: str) -> str:
        record = self._records.get((manufacturer, exact_icpn))
        return record["software_state"] if record is not None else self.default_unreviewed_state

    def supported_exact_icpns(self, manufacturer: str | None = None) -> tuple[str, ...]:
        values = [
            icpn
            for (vendor, icpn), record in self._records.items()
            if record["software_state"] == "SUPPORTED"
            and (manufacturer is None or manufacturer == vendor)
        ]
        return tuple(sorted(values))

    @property
    def summary(self) -> dict[str, Any]:
        supported = len(self.supported_exact_icpns())
        return {
            "qualification_id": self.qualification_id,
            "provider_id": self.provider["provider_id"],
            "provider_version": self.provider["version"],
            "provider_source_commit": self.provider["source_commit"],
            "reviewed_exact_icpns": len(self._records),
            "supported_exact_icpns": supported,
            "catalog_exact_icpns": self._catalog.size,
            "unreviewed_default_unknown_exact_icpns": self._catalog.size - len(self._records),
            "public_catalog_visibility_changed": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }


def get_default_openocd_software_qualification_registry() -> OpenOCDSoftwareQualificationRegistry | None:
    required = (RELEASE_REL, SOURCE_LOCK_REL, QUALIFICATION_REL)
    if not source_files_available(ROOT, required):
        return None
    return OpenOCDSoftwareQualificationRegistry(get_default_device_catalog(), ROOT)
