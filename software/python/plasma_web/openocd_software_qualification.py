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
SOURCE_LOCK_REL = "release/openocd-qualification/openocd-0.12.0-stm32f1-source-lock-v1.json"
QUALIFICATION_REL = "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v3.json"
APPLICABILITY_REL = "release/openocd-qualification/stm32f103-medium-density-rv-t6-applicability-v1.json"
EQUIVALENCE_REL = "release/openocd-qualification/stm32f103-medium-density-tr-ordering-equivalence-v2.json"
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
        applicability = _read_json(root / APPLICABILITY_REL)
        equivalence = _read_json(root / EQUIVALENCE_REL)

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

        authority_locks = qualification.get("authority_artifact_locks")
        _require(
            isinstance(authority_locks, dict)
            and authority_locks.get(APPLICABILITY_REL)
            and authority_locks.get(EQUIVALENCE_REL),
            "qualification authority artifact locks missing",
        )
        for rel in (APPLICABILITY_REL, EQUIVALENCE_REL):
            raw = (root / rel).read_bytes()
            _require(
                _git_blob_sha1(raw) == authority_locks[rel],
                f"qualification authority artifact drift: {rel}",
            )

        review = _read_json(
            root / "data/ic-support/benchmarks/stm32f103c/vendor-neutral-admission-contract-v1.json"
        )
        comparison = _read_json(
            root / "data/ic-support/openocd-comparison/stm32f103c8t6-openocd-v0.12.0-v1.json"
        )
        baseline = _read_json(
            root / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json"
        )
        backend_reference = comparison.get("backend_reference", {})
        _require(
            comparison.get("target", {}).get("icpn") == "STM32F103C8T6"
            and backend_reference.get("version") == release["version"]
            and backend_reference.get("source_commit") == release["source_commit"]
            and "src/flash/nor/stm32f1x.c" in backend_reference.get("files", [])
            and "tcl/target/stm32f1x.cfg" in backend_reference.get("files", []),
            "independent OpenOCD comparison provenance drift",
        )
        observations = {
            item.get("id"): item
            for item in comparison.get("observations", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        expected_observations = {
            "medium_density_page_size": "exact_match",
            "program_alignment": "exact_match",
            "page_erase_core": "exact_match",
            "program_core": "exact_match",
            "verify_layering": "functionally_equivalent",
            "device_family_probe": "backend_extra_requires_manufacturer_validation",
            "blue_pill_flash_override": "conflict_or_out_of_spec",
        }
        for observation_id, expected_class in expected_observations.items():
            _require(
                observations.get(observation_id, {}).get("classification") == expected_class,
                f"OpenOCD semantic observation drift: {observation_id}",
            )
        conclusions = comparison.get("conclusions", {})
        _require(
            conclusions.get("same_core_flash_programming_semantics") is True
            and conclusions.get("hardware_runtime_ready") is False
            and conclusions.get("physical_programming_qualified") is False,
            "OpenOCD differential qualification boundary drift",
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
        review_fact_ids = {
            item.get("fact_id")
            for item in review.get("review_facts", [])
            if isinstance(item, dict)
        }
        constraint_ids = {
            item.get("id")
            for item in baseline.get("programming_profile", {}).get("special_constraints", [])
            if isinstance(item, dict)
        }
        for operation in REQUIRED_OPERATIONS:
            row = opq[operation]
            for basis in row.get("manufacturer_basis", []):
                _require(
                    basis in review_fact_ids or basis in constraint_ids,
                    f"manufacturer operation evidence not resolved: {operation}/{basis}",
                )
            for basis in row.get("differential_basis", []):
                _require(
                    basis in observations,
                    f"OpenOCD differential evidence not resolved: {operation}/{basis}",
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

        _require(
            qualification.get("applicability_authority_id")
            == applicability.get("applicability_id"),
            "qualification/applicability authority identity mismatch",
        )
        _require(
            applicability.get("manufacturer") == "STMicroelectronics"
            and applicability.get("phase") == "02_PROGRAMMING"
            and applicability.get("family") == "STM32F1"
            and applicability.get("series") == "STM32F103"
            and applicability.get("density_class") == "medium",
            "manufacturer applicability authority drift",
        )
        app_authority = applicability.get("manufacturer_authority")
        _require(isinstance(app_authority, dict), "manufacturer applicability sources missing")
        for source_name in (
            "ordering",
            "production_exact_identity",
            "programming_review",
            "programming_profile",
        ):
            item = app_authority.get(source_name)
            _require(isinstance(item, dict), f"applicability source missing: {source_name}")
            rel = item.get("path")
            _require(isinstance(rel, str) and rel, f"applicability source path missing: {source_name}")
            raw = (root / rel).read_bytes()
            _require(
                _git_blob_sha1(raw) == item.get("git_blob_sha1"),
                f"applicability source blob drift: {source_name}/{rel}",
            )

        app_ordering = app_authority["ordering"]
        app_ordering_payload = _read_json(root / app_ordering["path"])
        app_stm32f103 = app_ordering_payload.get("records", {}).get("STM32F103", {})
        app_medium = next(
            (
                band
                for band in app_stm32f103.get("bands", [])
                if band.get("name") == app_ordering.get("band")
            ),
            None,
        )
        _require(
            isinstance(app_medium, dict)
            and app_medium.get("document") == app_ordering.get("document") == "DS5319 Rev 20"
            and set(app_ordering.get("required_flash_codes", [])) == {"8", "B"}
            and app_medium.get("flash_codes") == ["8", "B"]
            and app_medium.get("pin_count", {}).get("R") == 64
            and app_medium.get("pin_count", {}).get("V") == 100
            and app_medium.get("package", {}).get("T") == "LQFP"
            and app_medium.get("temperature_c", {}).get("6") == "-40 to 85 C",
            "STM32F103 medium-density manufacturer applicability drift",
        )

        app_review = _read_json(root / app_authority["programming_review"]["path"])
        app_review_fact_ids = {
            item.get("fact_id")
            for item in app_review.get("review_facts", [])
            if isinstance(item, dict)
        }
        for fact_id in app_authority["programming_review"].get("required_fact_ids", []):
            _require(
                fact_id in app_review_fact_ids,
                f"manufacturer applicability review fact missing: {fact_id}",
            )
        app_profile = _read_json(root / app_authority["programming_profile"]["path"])
        _require(
            app_profile.get("profile_id")
            == app_authority["programming_profile"].get("profile_id")
            == "stm32f1-medium-density-flash-v0",
            "manufacturer applicability Programming Profile drift",
        )

        applicability_targets = {
            item.get("icpn"): item
            for item in applicability.get("targets", [])
            if isinstance(item, dict) and isinstance(item.get("icpn"), str)
        }
        _require(
            set(applicability_targets)
            == {
                "STM32F103R8T6",
                "STM32F103RBT6",
                "STM32F103V8T6",
                "STM32F103VBT6",
            },
            "manufacturer applicability scope expanded without review",
        )
        for target in applicability_targets.values():
            geometry_path = target.get("memory_geometry_path")
            _require(
                isinstance(geometry_path, str) and geometry_path,
                f"memory geometry path missing: {target.get('icpn')}",
            )
            geometry_raw = (root / geometry_path).read_bytes()
            _require(
                _git_blob_sha1(geometry_raw)
                == target.get("memory_geometry_git_blob_sha1"),
                f"memory geometry blob drift: {target.get('icpn')}",
            )
            geometry = json.loads(geometry_raw.decode("utf-8"))
            data = geometry.get("data", {})
            _require(
                geometry.get("profile_id") == target.get("memory_geometry_profile_id")
                and geometry.get("scope", {}).get("manufacturer") == "STMicroelectronics"
                and geometry.get("scope", {}).get("base_device") == target.get("base_device")
                and data.get("main_flash_start") == "0x08000000"
                and data.get("main_flash_size_bytes") == target.get("main_flash_size_bytes")
                and data.get("page_size_bytes") == 1024
                and data.get("page_count") == target.get("page_count")
                and data.get("erase_granularity_bytes") == 1024
                and data.get("program_granularity_bytes") == 2,
                f"memory geometry content drift: {target.get('icpn')}",
            )

        _require(
            qualification.get("ordering_equivalence_id") == equivalence.get("equivalence_id"),
            "qualification/ordering-equivalence identity mismatch",
        )
        _require(
            equivalence.get("manufacturer") == "STMicroelectronics"
            and equivalence.get("phase") == "02_PROGRAMMING",
            "ordering-equivalence authority drift",
        )
        ordering = equivalence.get("ordering_authority")
        _require(isinstance(ordering, dict), "ordering authority missing")
        ordering_path = ordering.get("path")
        _require(isinstance(ordering_path, str) and ordering_path, "ordering authority path missing")
        ordering_bytes = (root / ordering_path).read_bytes()
        _require(
            _git_blob_sha1(ordering_bytes) == ordering.get("git_blob_sha1"),
            "ordering authority blob drift",
        )
        ordering_payload = json.loads(ordering_bytes.decode("utf-8"))
        stm32f103 = ordering_payload.get("records", {}).get("STM32F103", {})
        medium = next(
            (
                band
                for band in stm32f103.get("bands", [])
                if band.get("name") == ordering.get("band")
            ),
            None,
        )
        _require(
            isinstance(medium, dict)
            and medium.get("document") == ordering.get("document") == "DS5319 Rev 20"
            and medium.get("allowed_tails") == ["", "TR"]
            and ordering.get("suffix") == "TR"
            and ordering.get("meaning") == "tape-and-reel",
            "ST medium-density TR ordering semantics drift",
        )
        production_identity = equivalence.get("production_exact_identity")
        _require(
            isinstance(production_identity, dict),
            "ordering-equivalence Production identity authority missing",
        )
        production_identity_path = production_identity.get("path")
        _require(
            isinstance(production_identity_path, str) and production_identity_path,
            "ordering-equivalence Production identity path missing",
        )
        production_identity_raw = (root / production_identity_path).read_bytes()
        _require(
            _git_blob_sha1(production_identity_raw)
            == production_identity.get("git_blob_sha1"),
            "ordering-equivalence Production identity blob drift",
        )
        equivalence_variants = {
            item.get("icpn"): item
            for item in equivalence.get("variants", [])
            if isinstance(item, dict) and isinstance(item.get("icpn"), str)
        }
        _require(
            set(equivalence_variants)
            == {
                "STM32F103C8T6TR",
                "STM32F103CBT6TR",
                "STM32F103R8T6TR",
                "STM32F103RBT6TR",
                "STM32F103V8T6TR",
                "STM32F103VBT6TR",
            },
            "ordering-equivalence scope expanded without review",
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
            basis = raw.get("qualification_basis")
            _require(isinstance(basis, dict), f"qualification basis missing: {key[1]}")
            basis_kind = basis.get("kind")
            if basis_kind == "direct_reference":
                target = review_targets.get(key[1])
                _require(isinstance(target, dict), f"manufacturer review target missing: {key[1]}")
                _require(
                    raw.get("base_device") == target.get("base_device")
                    and raw.get("memory_geometry_profile_id") == target.get("memory_geometry_profile_id")
                    and raw.get("main_flash_size_bytes") == target.get("main_flash_size_bytes")
                    and raw.get("page_count") == target.get("page_count"),
                    f"exact geometry/applicability drift: {key[1]}",
                )
            elif basis_kind == "manufacturer_applicability":
                target = applicability_targets.get(key[1])
                _require(
                    isinstance(target, dict)
                    and basis.get("applicability_id")
                    == applicability.get("applicability_id"),
                    f"manufacturer applicability target missing: {key[1]}",
                )
                expected_catalog = {
                    "base_device": target.get("base_device"),
                    "package": target.get("package"),
                    "pin_count": target.get("pin_count"),
                    "flash_size": target.get("flash_size"),
                    "temperature_grade": target.get("temperature_grade"),
                    "option_suffix": target.get("option_suffix"),
                    "target_config": target.get("target_config"),
                }
                for field, expected in expected_catalog.items():
                    actual = getattr(row, field)
                    actual = actual or "" if field == "option_suffix" else actual
                    _require(
                        actual == expected,
                        f"manufacturer applicability Catalog field drift: {key[1]}/{field}",
                    )
                _require(
                    row.source_authority
                    == app_authority["production_exact_identity"]["source_authority"]
                    and row.verification_status,
                    f"manufacturer applicability exact identity evidence drift: {key[1]}",
                )
                _require(
                    raw.get("base_device") == target.get("base_device")
                    and raw.get("programming_profile_id")
                    == applicability.get("shared_programming_semantics", {}).get(
                        "programming_profile_id"
                    )
                    and raw.get("memory_geometry_profile_id")
                    == target.get("memory_geometry_profile_id")
                    and raw.get("main_flash_size_bytes")
                    == target.get("main_flash_size_bytes")
                    and raw.get("page_count") == target.get("page_count"),
                    f"manufacturer applicability programming geometry drift: {key[1]}",
                )
            elif basis_kind == "ordering_equivalence":
                eq = equivalence_variants.get(key[1])
                _require(isinstance(eq, dict), f"ordering equivalence missing: {key[1]}")
                source_icpn = basis.get("equivalent_to_icpn")
                _require(
                    source_icpn == eq.get("equivalent_to_icpn")
                    and basis.get("ordering_equivalence_id") == equivalence.get("equivalence_id"),
                    f"ordering equivalence identity drift: {key[1]}",
                )
                source_key = (key[0], source_icpn)
                source = self._records.get(source_key)
                source_row = catalog_by_key.get(source_key)
                _require(
                    isinstance(source, dict) and source.get("software_state") == "SUPPORTED",
                    f"ordering-equivalence source not directly qualified first: {key[1]}",
                )
                _require(source_row is not None, f"ordering-equivalence source absent from Catalog: {source_icpn}")
                for field in equivalence.get("inheritance_contract", {}).get(
                    "required_equal_catalog_fields", []
                ):
                    _require(
                        getattr(row, field) == getattr(source_row, field),
                        f"ordering-equivalence Catalog field drift: {key[1]}/{field}",
                    )
                permitted = equivalence.get("inheritance_contract", {}).get(
                    "permitted_commercial_difference", {}
                )
                _require(
                    permitted.get("field") == "option_suffix"
                    and (source_row.option_suffix or "") == permitted.get("reference")
                    and row.option_suffix == permitted.get("variant") == "TR",
                    f"ordering-equivalence packing suffix drift: {key[1]}",
                )
                for field in (
                    "programming_profile_id",
                    "memory_geometry_profile_id",
                    "main_flash_size_bytes",
                    "page_count",
                    "operations",
                ):
                    _require(
                        raw.get(field) == source.get(field),
                        f"ordering-equivalence programming semantic drift: {key[1]}/{field}",
                    )
                _require(
                    raw.get("base_device") == row.base_device == source.get("base_device"),
                    f"ordering-equivalence Base Device drift: {key[1]}",
                )
            else:
                raise DeviceCatalogIntegrityError(
                    f"OpenOCD software qualification: unsupported qualification basis: {key[1]}/{basis_kind}"
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
                ("STMicroelectronics", "STM32F103C8T6TR"),
                ("STMicroelectronics", "STM32F103CBT6"),
                ("STMicroelectronics", "STM32F103CBT6TR"),
                ("STMicroelectronics", "STM32F103R8T6"),
                ("STMicroelectronics", "STM32F103R8T6TR"),
                ("STMicroelectronics", "STM32F103RBT6"),
                ("STMicroelectronics", "STM32F103RBT6TR"),
                ("STMicroelectronics", "STM32F103V8T6"),
                ("STMicroelectronics", "STM32F103V8T6TR"),
                ("STMicroelectronics", "STM32F103VBT6"),
                ("STMicroelectronics", "STM32F103VBT6TR"),
            },
            "Phase 2 qualification scope expanded without review",
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
        self.programming_group = deepcopy(group)
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

    def describe(self, manufacturer: str, exact_icpn: str) -> dict[str, Any]:
        """Return the read-only Phase 2 software-qualification projection.

        UNKNOWN is explicit when the exact ICPN has not completed review. A
        Catalog mapping or family relationship never fills provider, operation,
        electrical, or geometry qualification fields for an unreviewed ICPN.
        """

        record = self._records.get((manufacturer, exact_icpn))
        state = record["software_state"] if record is not None else self.default_unreviewed_state
        payload: dict[str, Any] = {
            "schema_version": "1.0.0",
            "registry_id": self.qualification_id,
            "software_state": state,
            "reviewed": record is not None,
            "provider": None,
            "operations": {},
            "programming": None,
            "public_catalog_visibility_changed": False,
            "job_batch_execution_changed": False,
            "installed_runtime_attested": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }
        if record is None:
            return payload

        group = self.programming_group
        shared_geometry = group["shared_flash_geometry"]
        payload["provider"] = {
            "provider_id": self.provider["provider_id"],
            "version": self.provider["version"],
            "source_commit": self.provider["source_commit"],
            "runtime_id": self.provider["runtime_id"],
            "target_config": self.provider["target_config"],
            "flash_driver": self.provider["flash_driver"],
        }
        payload["operations"] = {
            operation: {
                "state": self.operation_qualification[operation]["state"],
                "scope": self.operation_qualification[operation].get("scope"),
            }
            for operation in REQUIRED_OPERATIONS
        }
        payload["programming"] = {
            "programming_profile_id": record["programming_profile_id"],
            "memory_geometry_profile_id": record["memory_geometry_profile_id"],
            "debug_transport": list(group["debug_transport"]),
            "electrical": {
                "vdd_programming_v": deepcopy(
                    group["programming_electrical"]["vdd_programming_v"]
                ),
                "external_vpp_required": group["programming_electrical"][
                    "external_vpp_required"
                ],
            },
            "flash_geometry": {
                "main_flash_start": shared_geometry["main_flash_start"],
                "main_flash_size_bytes": record["main_flash_size_bytes"],
                "page_count": record["page_count"],
                "erase_unit": shared_geometry["erase_unit"],
                "erase_unit_bytes": shared_geometry["erase_unit_bytes"],
                "program_unit": shared_geometry["program_unit"],
                "program_unit_bytes": shared_geometry["program_unit_bytes"],
            },
            "blocked_operations": list(group["blocked_operations"]),
            "backend_constraints": list(group["backend_constraints"]),
        }
        return payload

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
    required = (
        RELEASE_REL,
        SOURCE_LOCK_REL,
        QUALIFICATION_REL,
        APPLICABILITY_REL,
        EQUIVALENCE_REL,
    )
    if not source_files_available(ROOT, required):
        return None
    return OpenOCDSoftwareQualificationRegistry(get_default_device_catalog(), ROOT)
