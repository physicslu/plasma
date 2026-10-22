"""ADR-0002 Phase 2 OpenOCD provider-specific qualification registry.

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
from functools import lru_cache
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
QUALIFICATION_REL = "release/openocd-qualification/openocd-0.12.0-stm32f103-v8.json"
MEDIUM_QUALIFICATION_REL = "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json"
APPLICABILITY_REL = "release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json"
EQUIVALENCE_REL = "release/openocd-qualification/stm32f103-medium-density-tr-ordering-equivalence-v3.json"
HIGH_QUALIFICATION_REL = "release/openocd-qualification/openocd-0.12.0-stm32f103-high-rvz-package-v4.json"
HIGH_APPLICABILITY_REL = "release/openocd-qualification/stm32f103-high-density-rvz-package-t6-t7-applicability-v4.json"
HIGH_EQUIVALENCE_REL = "release/openocd-qualification/stm32f103-high-density-rvz-lqfp-tr-ordering-equivalence-v3.json"
MEDIUM_NONLQFP_APPLICABILITY_REL = "release/openocd-qualification/stm32f103-medium-nonlqfp-exact-12-applicability-v1.json"
MEDIUM_NONLQFP_QUALIFICATION_REL = "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-nonlqfp-12-v1.json"
QUALIFICATION_V9_REL = "release/openocd-qualification/openocd-0.12.0-stm32f103-v9.json"
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
        qualification_manifest = _read_json(root / QUALIFICATION_REL)
        qualification = _read_json(root / MEDIUM_QUALIFICATION_REL)
        applicability = _read_json(root / APPLICABILITY_REL)
        equivalence = _read_json(root / EQUIVALENCE_REL)
        high_qualification = _read_json(root / HIGH_QUALIFICATION_REL)
        high_applicability = _read_json(root / HIGH_APPLICABILITY_REL)
        high_equivalence = _read_json(root / HIGH_EQUIVALENCE_REL)
        package_applicability = _read_json(root / MEDIUM_NONLQFP_APPLICABILITY_REL)
        package_qualification = _read_json(root / MEDIUM_NONLQFP_QUALIFICATION_REL)
        qualification_v9 = _read_json(root / QUALIFICATION_V9_REL)

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

        _require(
            qualification_manifest.get("provider_source_lock_id") == source_lock.get("source_lock_id")
            and qualification_manifest.get("provider") == q_provider
            and qualification_manifest.get("qualification_id")
            == "adr0002-phase2-openocd-012-stm32f103-v8"
            and qualification_manifest.get("predecessor_qualification_id")
            == "adr0002-phase2-openocd-012-stm32f103-v7"
            and qualification_manifest.get("supported_exact_icpn_count") == 65,
            "STM32F103 v8 qualification manifest drift",
        )
        manifest_cohorts = {
            item.get("qualification_path"): item
            for item in qualification_manifest.get("cohorts", [])
            if isinstance(item, dict)
        }
        _require(
            set(manifest_cohorts) == {MEDIUM_QUALIFICATION_REL, HIGH_QUALIFICATION_REL},
            "STM32F103 v8 cohort manifest scope drift",
        )
        for rel in (MEDIUM_QUALIFICATION_REL, HIGH_QUALIFICATION_REL):
            raw = (root / rel).read_bytes()
            _require(
                _git_blob_sha1(raw) == manifest_cohorts[rel].get("git_blob_sha1"),
                f"STM32F103 v8 cohort lock drift: {rel}",
            )
        _require(
            high_qualification.get("provider_source_lock_id") == source_lock.get("source_lock_id")
            and high_qualification.get("provider") == q_provider,
            "high-density qualification provider drift",
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
            and app_medium.get("pin_count", {}).get("C") == 48
            and app_medium.get("pin_count", {}).get("R") == 64
            and app_medium.get("pin_count", {}).get("V") == 100
            and app_medium.get("package", {}).get("T") == "LQFP"
            and app_medium.get("temperature_c", {}).get("6") == "-40 to 85 C"
            and app_medium.get("temperature_c", {}).get("7") == "-40 to 105 C"
            and app_ordering.get("required_temperature_codes")
            == {"6": "-40 to 85 C", "7": "-40 to 105 C"},
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
                "STM32F103C8T7",
                "STM32F103CBT7",
                "STM32F103R8T7",
                "STM32F103RBT7",
                "STM32F103VBT7",
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
                "STM32F103C8T7TR",
                "STM32F103CBT7TR",
                "STM32F103R8T7TR",
                "STM32F103RBT7TR",
                "STM32F103VBT7TR",
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
                row.identity_state == "IDENTIFIED"
                and row.identifier_kind == "manufacturer_part_number"
                and row.family == "STM32F1"
                and row.mapping_status == "mapped"
                and row.target_config == q_provider["target_config"],
                f"qualified exact ICPN identity / Programming route drift: {key[1]}",
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
                ("STMicroelectronics", "STM32F103C8T7"),
                ("STMicroelectronics", "STM32F103C8T7TR"),
                ("STMicroelectronics", "STM32F103CBT7"),
                ("STMicroelectronics", "STM32F103CBT7TR"),
                ("STMicroelectronics", "STM32F103R8T7"),
                ("STMicroelectronics", "STM32F103R8T7TR"),
                ("STMicroelectronics", "STM32F103RBT7"),
                ("STMicroelectronics", "STM32F103RBT7TR"),
                ("STMicroelectronics", "STM32F103VBT7"),
                ("STMicroelectronics", "STM32F103VBT7TR"),
            },
            "Programming Qualification scope expanded without review",
        )
        _require(
            all(record["software_state"] == "SUPPORTED" for record in self._records.values()),
            "reference cohort must be explicitly SUPPORTED",
        )

        high_group = high_qualification.get("manufacturer_programming_group")
        _require(
            isinstance(high_group, dict)
            and high_group.get("manufacturer") == "STMicroelectronics"
            and high_group.get("family") == "STM32F1"
            and high_group.get("series") == "STM32F103"
            and high_group.get("density_class") == "high"
            and high_group.get("silicon_identity", {}).get("openocd_device_id") == "0x414"
            and high_group.get("shared_flash_geometry", {}).get("main_flash_start") == "0x08000000"
            and high_group.get("shared_flash_geometry", {}).get("erase_unit_bytes") == 2048
            and high_group.get("shared_flash_geometry", {}).get("program_unit_bytes") == 2
            and high_group.get("programming_electrical", {}).get("vdd_programming_v")
            == {"min": 2.0, "max": 3.6}
            and high_group.get("programming_electrical", {}).get("external_vpp_required") is False,
            "STM32F103 high-density programming-group drift",
        )
        high_opq = high_group.get("operation_qualification")
        _require(isinstance(high_opq, dict), "high-density operation qualification missing")
        for operation in REQUIRED_OPERATIONS:
            _require(
                high_opq.get(operation, {}).get("state") == "SUPPORTED",
                f"high-density operation not software-qualified: {operation}",
            )

        high_local_locks = high_qualification.get("local_evidence_locks")
        _require(isinstance(high_local_locks, dict) and high_local_locks, "high-density local evidence locks missing")
        for rel, expected_blob in high_local_locks.items():
            evidence_path = root / rel
            _require(evidence_path.is_file(), f"high-density local evidence missing: {rel}")
            _require(
                _git_blob_sha1(evidence_path.read_bytes()) == expected_blob,
                f"high-density local evidence blob drift: {rel}",
            )

        high_authority_locks = high_qualification.get("authority_artifact_locks")
        _require(
            isinstance(high_authority_locks, dict)
            and high_authority_locks.get(HIGH_APPLICABILITY_REL)
            and high_authority_locks.get(HIGH_EQUIVALENCE_REL),
            "high-density qualification authority artifact locks missing",
        )
        for rel in (HIGH_APPLICABILITY_REL, HIGH_EQUIVALENCE_REL):
            _require(
                _git_blob_sha1((root / rel).read_bytes()) == high_authority_locks[rel],
                f"high-density qualification authority artifact drift: {rel}",
            )
        _require(
            high_qualification.get("applicability_authority_id")
            == high_applicability.get("applicability_id")
            and high_qualification.get("ordering_equivalence_id")
            == high_equivalence.get("equivalence_id"),
            "high-density authority identity mismatch",
        )

        high_comparison_path = high_group.get("manufacturer_evidence", {}).get(
            "openocd_comparison_path"
        )
        _require(
            isinstance(high_comparison_path, str) and high_comparison_path,
            "high-density OpenOCD comparison path missing",
        )
        high_comparison = _read_json(root / high_comparison_path)
        high_observations = {
            item.get("id"): item
            for item in high_comparison.get("observations", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        expected_high_observations = {
            "high_density_device_id": "exact_match",
            "high_density_page_size": "exact_match",
            "high_density_max_flash": "exact_match",
            "program_alignment": "exact_match",
            "page_erase_core": "exact_match",
            "program_core": "exact_match",
            "verify_layering": "functionally_equivalent",
        }
        for observation_id, expected_class in expected_high_observations.items():
            _require(
                high_observations.get(observation_id, {}).get("classification")
                == expected_class,
                f"high-density OpenOCD semantic observation drift: {observation_id}",
            )
        high_conclusions = high_comparison.get("conclusions", {})
        _require(
            high_conclusions.get("same_core_flash_programming_semantics") is True
            and high_conclusions.get("high_density_geometry_is_distinct_from_medium_density") is True
            and high_conclusions.get("medium_density_page_geometry_must_not_be_inherited") is True
            and high_conclusions.get("installed_runtime_attested") is False
            and high_conclusions.get("hardware_runtime_ready") is False
            and high_conclusions.get("physical_programming_qualified") is False,
            "high-density OpenOCD differential qualification boundary drift",
        )

        _require(
            high_applicability.get("manufacturer") == "STMicroelectronics"
            and high_applicability.get("phase") == "02_PROGRAMMING"
            and high_applicability.get("family") == "STM32F1"
            and high_applicability.get("series") == "STM32F103"
            and high_applicability.get("density_class") == "high",
            "high-density manufacturer applicability authority drift",
        )
        high_app_authority = high_applicability.get("manufacturer_authority")
        _require(isinstance(high_app_authority, dict), "high-density applicability sources missing")
        for source_name in (
            "ordering",
            "production_exact_identity",
            "programming_review",
            "programming_profile",
        ):
            item = high_app_authority.get(source_name)
            _require(isinstance(item, dict), f"high-density applicability source missing: {source_name}")
            rel = item.get("path")
            _require(isinstance(rel, str) and rel, f"high-density applicability path missing: {source_name}")
            _require(
                _git_blob_sha1((root / rel).read_bytes()) == item.get("git_blob_sha1"),
                f"high-density applicability source blob drift: {source_name}/{rel}",
            )

        high_ordering = high_app_authority["ordering"]
        high_ordering_payload = _read_json(root / high_ordering["path"])
        high_stm32f103 = high_ordering_payload.get("records", {}).get("STM32F103", {})
        high_band = next(
            (
                band
                for band in high_stm32f103.get("bands", [])
                if band.get("name") == high_ordering.get("band")
            ),
            None,
        )
        _require(
            isinstance(high_band, dict)
            and high_band.get("document") == high_ordering.get("document") == "DS5792 Rev 13"
            and set(high_ordering.get("required_flash_codes", [])) == {"C", "D", "E"}
            and high_band.get("flash_codes") == ["C", "D", "E"]
            and high_band.get("pin_count", {}).get("R") == 64
            and high_band.get("pin_count", {}).get("V") == 100
            and high_band.get("pin_count", {}).get("Z") == 144
            and high_ordering.get("required_package_codes")
            == {"T": "LQFP", "H": "LFBGA", "Y": "WLCSP64"}
            and high_band.get("package", {}).get("T") == "LQFP"
            and high_band.get("package", {}).get("H") == "LFBGA"
            and high_band.get("package", {}).get("Y") == "WLCSP64"
            and high_band.get("temperature_c", {}).get("6") == "-40 to 85 C"
            and high_band.get("temperature_c", {}).get("7") == "-40 to 105 C"
            and high_ordering.get("required_temperature_codes")
            == {"6": "-40 to 85 C", "7": "-40 to 105 C"},
            "STM32F103 high-density manufacturer applicability drift",
        )

        high_review = _read_json(root / high_app_authority["programming_review"]["path"])
        _require(
            high_review.get("shared", {}).get("programming_profile_id")
            == "stm32f1-high-density-flash-v0"
            and set(high_review.get("operations", {}).get("admitted", []))
            == {"READ", "VERIFY", "PROGRAM", "ERASE"},
            "high-density manufacturer programming review drift",
        )
        high_review_fact_ids = {
            item.get("fact_id")
            for item in high_review.get("review_facts", [])
            if isinstance(item, dict)
        }
        for fact_id in high_app_authority["programming_review"].get("required_fact_ids", []):
            _require(
                fact_id in high_review_fact_ids,
                f"high-density manufacturer review fact missing: {fact_id}",
            )
        high_profile = _read_json(root / high_app_authority["programming_profile"]["path"])
        _require(
            high_profile.get("profile_id")
            == high_app_authority["programming_profile"].get("profile_id")
            == "stm32f1-high-density-flash-v0"
            and high_profile.get("scope", {}).get("density_class") == "high"
            and high_profile.get("data", {}).get("program_granularity_bytes") == 2,
            "high-density Programming Profile drift",
        )

        high_applicability_targets = {
            item.get("icpn"): item
            for item in high_applicability.get("targets", [])
            if isinstance(item, dict) and isinstance(item.get("icpn"), str)
        }
        _require(
            set(high_applicability_targets)
            == {
                "STM32F103RCT6",
                "STM32F103RCT7",
                "STM32F103RDT6",
                "STM32F103RET6",
                "STM32F103RET7",
                "STM32F103VCT6",
                "STM32F103VDT6",
                "STM32F103VDT7",
                "STM32F103VET6",
                "STM32F103VET7",
                "STM32F103ZCT6",
                "STM32F103ZCT7",
                "STM32F103ZDT6",
                "STM32F103ZET6",
                "STM32F103ZET7",
                "STM32F103RCY6TR",
                "STM32F103RDY6TR",
                "STM32F103REY6TR",
                "STM32F103VCH6",
                "STM32F103VDH6",
                "STM32F103VDH6TR",
                "STM32F103VEH6",
                "STM32F103VEH6TR",
                "STM32F103VEH7",
                "STM32F103ZCH6",
                "STM32F103ZDH6",
                "STM32F103ZDH6TR",
                "STM32F103ZEH6",
                "STM32F103ZEH6TR",
                "STM32F103ZEH7",
                "STM32F103ZEH7TR",
            },
            "high-density manufacturer applicability scope expanded without review",
        )
        for target in high_applicability_targets.values():
            geometry_path = target.get("memory_geometry_path")
            _require(
                isinstance(geometry_path, str) and geometry_path,
                f"high-density memory geometry path missing: {target.get('icpn')}",
            )
            geometry_raw = (root / geometry_path).read_bytes()
            _require(
                _git_blob_sha1(geometry_raw)
                == target.get("memory_geometry_git_blob_sha1"),
                f"high-density memory geometry blob drift: {target.get('icpn')}",
            )
            geometry = json.loads(geometry_raw.decode("utf-8"))
            data = geometry.get("data", {})
            _require(
                geometry.get("profile_id") == target.get("memory_geometry_profile_id")
                and geometry.get("scope", {}).get("manufacturer") == "STMicroelectronics"
                and geometry.get("scope", {}).get("base_device") == target.get("base_device")
                and data.get("main_flash_start") == "0x08000000"
                and data.get("main_flash_size_bytes") == target.get("main_flash_size_bytes")
                and data.get("page_size_bytes") == 2048
                and data.get("page_count") == target.get("page_count")
                and data.get("erase_granularity_bytes") == 2048
                and data.get("program_granularity_bytes") == 2,
                f"high-density memory geometry content drift: {target.get('icpn')}",
            )

        high_ordering_authority = high_equivalence.get("ordering_authority")
        _require(
            isinstance(high_ordering_authority, dict)
            and high_ordering_authority.get("band") == "high"
            and high_ordering_authority.get("document") == "DS5792 Rev 13"
            and high_ordering_authority.get("suffix") == "TR"
            and high_ordering_authority.get("meaning") == "tape-and-reel"
            and high_band.get("allowed_tails") == ["", "TR"],
            "high-density TR ordering semantics drift",
        )
        _require(
            _git_blob_sha1((root / high_ordering_authority["path"]).read_bytes())
            == high_ordering_authority.get("git_blob_sha1"),
            "high-density TR ordering authority blob drift",
        )
        high_eq_identity = high_equivalence.get("production_exact_identity")
        _require(
            isinstance(high_eq_identity, dict)
            and _git_blob_sha1((root / high_eq_identity["path"]).read_bytes())
            == high_eq_identity.get("git_blob_sha1"),
            "high-density TR Production identity authority drift",
        )
        high_equivalence_variants = {
            item.get("icpn"): item
            for item in high_equivalence.get("variants", [])
            if isinstance(item, dict) and isinstance(item.get("icpn"), str)
        }
        _require(
            set(high_equivalence_variants)
            == {
                "STM32F103RCT6TR",
                "STM32F103RCT7TR",
                "STM32F103RDT6TR",
                "STM32F103RET6TR",
                "STM32F103VCT6TR",
                "STM32F103VDT6TR",
                "STM32F103VDT7TR",
                "STM32F103VET6TR",
                "STM32F103VET7TR",
                "STM32F103ZCT6TR",
                "STM32F103ZCT7TR",
                "STM32F103ZET6TR",
            },
            "high-density ordering-equivalence scope expanded without review",
        )

        for raw in high_qualification.get("records", []):
            _require(isinstance(raw, dict), "high-density qualification record must be object")
            key = (raw.get("manufacturer"), raw.get("icpn"))
            _require(
                all(isinstance(v, str) and v for v in key)
                and key not in self._records,
                f"invalid/duplicate high-density qualification key: {key}",
            )
            _require(
                raw.get("software_state") == "SUPPORTED",
                f"high-density record not explicitly SUPPORTED: {key[1]}",
            )
            row = catalog_by_key.get(key)
            _require(row is not None, f"high-density qualified ICPN missing from Production Catalog: {key}")
            _require(
                row.identity_state == "IDENTIFIED"
                and row.identifier_kind == "manufacturer_part_number"
                and row.family == "STM32F1"
                and row.mapping_status == "mapped"
                and row.target_config == q_provider["target_config"],
                f"high-density exact ICPN identity / Programming route drift: {key[1]}",
            )
            basis = raw.get("qualification_basis")
            _require(isinstance(basis, dict), f"high-density qualification basis missing: {key[1]}")
            basis_kind = basis.get("kind")
            if basis_kind == "manufacturer_applicability":
                target = high_applicability_targets.get(key[1])
                _require(
                    isinstance(target, dict)
                    and basis.get("applicability_id")
                    == high_applicability.get("applicability_id"),
                    f"high-density applicability target missing: {key[1]}",
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
                        f"high-density applicability Catalog field drift: {key[1]}/{field}",
                    )
                _require(
                    row.source_authority
                    == high_app_authority["production_exact_identity"]["source_authority"]
                    and row.verification_status,
                    f"high-density exact identity evidence drift: {key[1]}",
                )
                _require(
                    raw.get("base_device") == target.get("base_device")
                    and raw.get("programming_profile_id")
                    == high_applicability.get("shared_programming_semantics", {}).get(
                        "programming_profile_id"
                    )
                    and raw.get("memory_geometry_profile_id")
                    == target.get("memory_geometry_profile_id")
                    and raw.get("main_flash_size_bytes")
                    == target.get("main_flash_size_bytes")
                    and raw.get("page_count") == target.get("page_count"),
                    f"high-density programming geometry drift: {key[1]}",
                )
            elif basis_kind == "ordering_equivalence":
                eq = high_equivalence_variants.get(key[1])
                _require(isinstance(eq, dict), f"high-density ordering equivalence missing: {key[1]}")
                source_icpn = basis.get("equivalent_to_icpn")
                _require(
                    source_icpn == eq.get("equivalent_to_icpn")
                    and basis.get("ordering_equivalence_id")
                    == high_equivalence.get("equivalence_id"),
                    f"high-density ordering equivalence identity drift: {key[1]}",
                )
                source_key = (key[0], source_icpn)
                source = self._records.get(source_key)
                source_row = catalog_by_key.get(source_key)
                _require(
                    isinstance(source, dict) and source.get("software_state") == "SUPPORTED",
                    f"high-density equivalence source not directly qualified first: {key[1]}",
                )
                _require(
                    source_row is not None,
                    f"high-density equivalence source absent from Catalog: {source_icpn}",
                )
                for field in high_equivalence.get("inheritance_contract", {}).get(
                    "required_equal_catalog_fields", []
                ):
                    _require(
                        getattr(row, field) == getattr(source_row, field),
                        f"high-density equivalence Catalog field drift: {key[1]}/{field}",
                    )
                permitted = high_equivalence.get("inheritance_contract", {}).get(
                    "permitted_commercial_difference", {}
                )
                _require(
                    permitted.get("field") == "option_suffix"
                    and (source_row.option_suffix or "") == permitted.get("reference")
                    and row.option_suffix == permitted.get("variant") == "TR",
                    f"high-density equivalence packing suffix drift: {key[1]}",
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
                        f"high-density equivalence semantic drift: {key[1]}/{field}",
                    )
                _require(
                    raw.get("base_device") == row.base_device == source.get("base_device"),
                    f"high-density equivalence Base Device drift: {key[1]}",
                )
            else:
                raise DeviceCatalogIntegrityError(
                    "OpenOCD software qualification: unsupported high-density "
                    f"qualification basis: {key[1]}/{basis_kind}"
                )
            _require(
                raw.get("programming_profile_id")
                == high_group.get("manufacturer_evidence", {}).get("programming_profile_id")
                and raw.get("operations") == list(REQUIRED_OPERATIONS),
                f"high-density operation/profile mismatch: {key[1]}",
            )
            self._records[key] = deepcopy(raw)

        high_exact = {
            ("STMicroelectronics", "STM32F103RCT6"),
            ("STMicroelectronics", "STM32F103RCT6TR"),
            ("STMicroelectronics", "STM32F103RCT7"),
            ("STMicroelectronics", "STM32F103RCT7TR"),
            ("STMicroelectronics", "STM32F103RDT6"),
            ("STMicroelectronics", "STM32F103RDT6TR"),
            ("STMicroelectronics", "STM32F103RET6"),
            ("STMicroelectronics", "STM32F103RET6TR"),
            ("STMicroelectronics", "STM32F103RET7"),
            ("STMicroelectronics", "STM32F103VCT6"),
            ("STMicroelectronics", "STM32F103VCT6TR"),
            ("STMicroelectronics", "STM32F103VDT6"),
            ("STMicroelectronics", "STM32F103VDT6TR"),
            ("STMicroelectronics", "STM32F103VDT7"),
            ("STMicroelectronics", "STM32F103VDT7TR"),
            ("STMicroelectronics", "STM32F103VET6"),
            ("STMicroelectronics", "STM32F103VET6TR"),
            ("STMicroelectronics", "STM32F103VET7"),
            ("STMicroelectronics", "STM32F103VET7TR"),
            ("STMicroelectronics", "STM32F103ZCT6"),
            ("STMicroelectronics", "STM32F103ZCT6TR"),
            ("STMicroelectronics", "STM32F103ZCT7"),
            ("STMicroelectronics", "STM32F103ZCT7TR"),
            ("STMicroelectronics", "STM32F103ZDT6"),
            ("STMicroelectronics", "STM32F103ZET6"),
            ("STMicroelectronics", "STM32F103ZET6TR"),
            ("STMicroelectronics", "STM32F103ZET7"),
            ("STMicroelectronics", "STM32F103RCY6TR"),
            ("STMicroelectronics", "STM32F103RDY6TR"),
            ("STMicroelectronics", "STM32F103REY6TR"),
            ("STMicroelectronics", "STM32F103VCH6"),
            ("STMicroelectronics", "STM32F103VDH6"),
            ("STMicroelectronics", "STM32F103VDH6TR"),
            ("STMicroelectronics", "STM32F103VEH6"),
            ("STMicroelectronics", "STM32F103VEH6TR"),
            ("STMicroelectronics", "STM32F103VEH7"),
            ("STMicroelectronics", "STM32F103ZCH6"),
            ("STMicroelectronics", "STM32F103ZDH6"),
            ("STMicroelectronics", "STM32F103ZDH6TR"),
            ("STMicroelectronics", "STM32F103ZEH6"),
            ("STMicroelectronics", "STM32F103ZEH6TR"),
            ("STMicroelectronics", "STM32F103ZEH7"),
            ("STMicroelectronics", "STM32F103ZEH7TR"),
        }
        _require(
            high_exact.issubset(self._records) and len(self._records) == 65,
            "combined Programming Qualification scope expanded without review",
        )

        # v9 adds a bounded medium-density C/R/V non-LQFP cohort without
        # mutating or weakening the previously qualified 65 exact ST ICPNs.
        old_ledger = qualification_v9.get("predecessor_qualification", {})
        added_ledger = qualification_v9.get("added_cohort", {})
        _require(
            qualification_v9.get("qualification_id") == "adr0002-phase2-openocd-012-stm32f103-v9"
            and qualification_v9.get("provider_source_lock_id") == source_lock["source_lock_id"]
            and qualification_v9.get("provider") == q_provider
            and qualification_v9.get("default_unreviewed_software_state") == "UNKNOWN"
            and old_ledger.get("path") == QUALIFICATION_REL
            and old_ledger.get("qualification_id") == qualification_manifest["qualification_id"]
            and old_ledger.get("supported_exact_icpn_count") == 65
            and _git_blob_sha1((root / QUALIFICATION_REL).read_bytes()) == old_ledger.get("git_blob_sha1")
            and added_ledger.get("path") == MEDIUM_NONLQFP_QUALIFICATION_REL
            and added_ledger.get("qualification_id") == package_qualification.get("qualification_id")
            and added_ledger.get("supported_exact_icpn_count") == 12
            and _git_blob_sha1((root / MEDIUM_NONLQFP_QUALIFICATION_REL).read_bytes()) == added_ledger.get("git_blob_sha1")
            and qualification_v9.get("supported_exact_icpn_count") == 77,
            "ST medium non-LQFP v9 admission manifest drift",
        )
        _require(
            package_qualification.get("qualification_id")
            == "adr0002-phase2-openocd-012-stm32f103-medium-nonlqfp-12-v1"
            and package_qualification.get("status") == "reviewed_source_only"
            and package_qualification.get("provider_source_lock_id") == source_lock["source_lock_id"]
            and package_qualification.get("provider") == q_provider
            and package_qualification.get("reference_programming_group_id") == group["group_id"]
            and package_qualification.get("supported_exact_icpn_count") == 12,
            "ST non-LQFP medium cohort/provider drift",
        )
        package_reference = package_qualification.get("reference_medium_qualification", {})
        package_app_binding = package_qualification.get("applicability_authority", {})
        _require(
            package_reference.get("path") == MEDIUM_QUALIFICATION_REL
            and _git_blob_sha1((root / MEDIUM_QUALIFICATION_REL).read_bytes()) == package_reference.get("git_blob_sha1")
            and package_app_binding.get("path") == MEDIUM_NONLQFP_APPLICABILITY_REL
            and _git_blob_sha1((root / MEDIUM_NONLQFP_APPLICABILITY_REL).read_bytes())
            == package_app_binding.get("git_blob_sha1")
            and package_app_binding.get("applicability_id") == package_applicability.get("applicability_id"),
            "ST non-LQFP source/applicability blob drift",
        )
        _require(
            package_applicability.get("applicability_id")
            == "st-stm32f103-medium-nonlqfp-exact-12-v1"
            and package_applicability.get("phase") == "02_PROGRAMMING"
            and package_applicability.get("manufacturer") == "STMicroelectronics"
            and package_applicability.get("family") == "STM32F1"
            and package_applicability.get("series") == "STM32F103"
            and package_applicability.get("density_class") == "medium"
            and package_applicability.get("shared_programming_semantics")
            == {
                "openocd_device_id": "0x410",
                "programming_profile_id": "stm32f1-medium-density-flash-v0",
                "main_flash_start": "0x08000000",
                "erase_unit_bytes": 1024,
                "program_unit_bytes": 2,
                "operations": list(REQUIRED_OPERATIONS),
            },
            "ST non-LQFP shared programming semantics drift",
        )
        package_authority = package_applicability.get("manufacturer_authority", {})
        for source_name, expected_rel in (
            ("ordering", "data/device-catalog/research/stm32f1-ordering-authority-v2.4.json"),
            ("production_exact_identity", "data/device-catalog/research/stm32f1-commercial-icpn.csv"),
            ("programming_review", "data/ic-support/benchmarks/stm32f103c/vendor-neutral-admission-contract-v1.json"),
            ("programming_profile", "data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json"),
        ):
            source = package_authority.get(source_name, {})
            _require(
                source.get("path") == expected_rel
                and _git_blob_sha1((root / expected_rel).read_bytes()) == source.get("git_blob_sha1"),
                f"non-LQFP manufacturer authority lock drift: {source_name}",
            )
        source_spec = package_authority.get("manufacturer_source_lock", {})
        _require(
            source_spec.get("path") == "data/ic-support/benchmarks/stm32f103c/source-lock.json"
            and source_spec.get("source_id") == "st_ds5319_rev20"
            and source_spec.get("sha256")
            == group["manufacturer_evidence"]["source_lock"]["st_ds5319_rev20"],
            "non-LQFP manufacturer DS5319 source lock drift",
        )
        sources_payload = _read_json(root / source_spec["path"])
        source_records = [
            x for x in sources_payload.get("sources", [])
            if x.get("source_id") == source_spec["source_id"]
        ]
        _require(
            len(source_records) == 1
            and source_records[0].get("integrity", {}).get("digest") == source_spec["sha256"],
            "non-LQFP manufacturer PDF byte custody drift",
        )
        medium_band = next(
            (x for x in app_stm32f103.get("bands", []) if x.get("name") == "medium"),
            None,
        )
        _require(
            isinstance(medium_band, dict)
            and medium_band.get("document") == "DS5319 Rev 20"
            and medium_band.get("package", {}).get("H") == "BGA"
            and medium_band.get("package", {}).get("U") == "UFQFPN"
            and medium_band.get("package_pin_overrides", {}).get("H/R") == "TFBGA"
            and medium_band.get("package_pin_overrides", {}).get("H/V") == "LFBGA"
            and medium_band.get("pin_count", {}).get("T") == 36
            and medium_band.get("flash_kib") == {"8": 64, "B": 128}
            and medium_band.get("allowed_tails") == ["", "TR"],
            "ST DS5319 medium-density package evidence drift",
        )

        direct_exact = {
            "STM32F103CBU6", "STM32F103R8H6", "STM32F103R8H7",
            "STM32F103RBH6", "STM32F103RBH7",
            "STM32F103V8H6", "STM32F103VBH6", "STM32F103VBH7",
        }
        variant_pairs = {
            "STM32F103CBU6TR": "STM32F103CBU6",
            "STM32F103R8H6TR": "STM32F103R8H6",
            "STM32F103RBH6TR": "STM32F103RBH6",
            "STM32F103V8H6TR": "STM32F103V8H6",
        }
        excluded_exact = {
            "STM32F103RBH6R", "STM32F103RBH6RTR",
            "STM32F103T8U6", "STM32F103T8U6TR",
            "STM32F103T8U7", "STM32F103T8U7TR",
            "STM32F103TBU6", "STM32F103TBU6TR", "STM32F103TBU7",
        }
        direct_targets = {
            x["icpn"]: x for x in package_applicability.get("targets", [])
            if isinstance(x, dict) and isinstance(x.get("icpn"), str)
        }
        variants = {
            x["icpn"]: x for x in package_applicability.get("packing_variants", [])
            if isinstance(x, dict) and isinstance(x.get("icpn"), str)
        }
        _require(
            len(package_applicability.get("targets", [])) == 8
            and set(direct_targets) == direct_exact
            and len(package_applicability.get("packing_variants", [])) == 4
            and {k: v.get("equivalent_to_icpn") for k, v in variants.items()} == variant_pairs
            and set(package_applicability.get("explicit_non_targets", [])) == excluded_exact
            and set(package_qualification.get("non_targets", [])) == excluded_exact
            and set(qualification_v9.get("excluded_exact_icpns", [])) == excluded_exact,
            "ST non-LQFP 12 exact admitted / 9 excluded scope drift",
        )

        def validate_medium_package_target(target: dict[str, Any]) -> None:
            icpn = target["icpn"]
            row = catalog_by_key.get(("STMicroelectronics", icpn))
            _require(row is not None and row.identity_state == "IDENTIFIED", "missing Production exact " + icpn)
            _require(row.mapping_status == "mapped" and row.target_config == q_provider["target_config"],
                     "missing pinned OpenOCD mapping " + icpn)
            base = target["base_device"]
            _require(icpn.startswith(base) and base.startswith("STM32F103"), "base mismatch " + icpn)
            pin_letter = base[9]
            flash_letter = base[10]
            order_tail = icpn[len(base):]
            _require(
                (pin_letter, order_tail[0]) in {("C", "U"), ("R", "H"), ("V", "H")}
                and flash_letter in {"8", "B"}
                and order_tail[1] in {"6", "7"}
                and order_tail[2:] == "",
                "ST non-LQFP direct order-code out of scope " + icpn,
            )
            expected_package = {
                ("C", "U"): "UFQFPN", ("R", "H"): "TFBGA", ("V", "H"): "LFBGA",
            }[(pin_letter, order_tail[0])]
            for field, expected in (
                ("base_device", base),
                ("package", expected_package),
                ("pin_count", str(medium_band["pin_count"][pin_letter])),
                ("flash_size", str(medium_band["flash_kib"][flash_letter]) + " KiB"),
                ("temperature_grade", medium_band["temperature_c"][order_tail[1]]),
                ("option_suffix", ""),
                ("target_config", q_provider["target_config"]),
            ):
                _require(
                    (getattr(row, field) or "") == expected
                    and target.get(field) == expected,
                    f"non-LQFP canonical/manufacturer identity drift: {icpn}/{field}",
                )
            _require(row.source_authority == "STMicroelectronics official", "source authority drift " + icpn)
            rel = target.get("memory_geometry_path")
            _require(isinstance(rel, str) and rel.startswith("data/ic-support/profiles/memory-geometry/"),
                     "missing exact geometry " + icpn)
            raw = (root / rel).read_bytes()
            geometry = json.loads(raw.decode("utf-8"))
            mem = medium_band["flash_kib"][flash_letter] * 1024
            g = geometry.get("data", {})
            _require(
                _git_blob_sha1(raw) == target.get("memory_geometry_git_blob_sha1")
                and geometry.get("profile_id") == target.get("memory_geometry_profile_id")
                and geometry.get("scope", {}).get("manufacturer") == "STMicroelectronics"
                and geometry.get("scope", {}).get("base_device") == base
                and g.get("main_flash_start") == "0x08000000"
                and g.get("main_flash_size_bytes") == mem
                and g.get("main_flash_end") == f"0x{(0x08000000 + mem - 1):08X}"
                and g.get("page_size_bytes") == 1024
                and g.get("erase_granularity_bytes") == 1024
                and g.get("program_granularity_bytes") == 2
                and g.get("page_count") == mem // 1024
                and target.get("main_flash_size_bytes") == mem
                and target.get("page_count") == mem // 1024,
                "non-LQFP Flash geometry evidence drift " + icpn,
            )

        for target in direct_targets.values():
            validate_medium_package_target(target)
        additions = package_qualification.get("records", [])
        _require(len(additions) == 12 and len({x.get("icpn") for x in additions}) == 12,
                 "non-LQFP qualification record cardinality drift")
        for raw in additions:
            icpn = raw.get("icpn")
            key = ("STMicroelectronics", icpn)
            _require(key not in self._records, "non-LQFP provider duplicate claim " + str(icpn))
            _require(
                raw.get("manufacturer") == "STMicroelectronics"
                and raw.get("software_state") == "SUPPORTED"
                and raw.get("programming_profile_id") == "stm32f1-medium-density-flash-v0"
                and raw.get("operations") == list(REQUIRED_OPERATIONS),
                "non-LQFP reviewed operation mismatch " + str(icpn),
            )
            basis = raw.get("qualification_basis", {})
            if icpn in direct_exact:
                target = direct_targets[icpn]
                _require(
                    basis == {
                        "kind": "manufacturer_applicability",
                        "applicability_id": package_applicability["applicability_id"],
                    },
                    "direct package applicability missing " + icpn,
                )
            elif icpn in variant_pairs:
                variant = variants[icpn]
                source_icpn = variant_pairs[icpn]
                source = self._records.get(("STMicroelectronics", source_icpn))
                source_row = catalog_by_key.get(("STMicroelectronics", source_icpn))
                row = catalog_by_key.get(key)
                _require(
                    basis == {
                        "kind": "ordering_equivalence",
                        "equivalent_to_icpn": source_icpn,
                        "applicability_id": package_applicability["applicability_id"],
                    }
                    and variant.get("base_device") == raw.get("base_device")
                    and variant.get("packing_suffix") == "TR"
                    and source is not None
                    and source.get("software_state") == "SUPPORTED"
                    and source_row is not None and row is not None
                    and row.option_suffix == "TR"
                    and (source_row.option_suffix or "") == "",
                    "TR equivalence source/order missing " + icpn,
                )
                for field in (
                    "base_device", "package", "pin_count", "flash_size",
                    "temperature_grade", "target_config",
                ):
                    _require(getattr(source_row, field) == getattr(row, field),
                             f"TR package/catalog mismatch {icpn}/{field}")
                for field in (
                    "base_device", "programming_profile_id",
                    "memory_geometry_profile_id", "main_flash_size_bytes",
                    "page_count", "operations",
                ):
                    _require(raw.get(field) == source.get(field),
                             f"TR programming mismatch {icpn}/{field}")
                target = direct_targets[source_icpn]
            else:
                raise DeviceCatalogIntegrityError("unexpected non-LQFP qualified exact: " + str(icpn))
            for field in (
                "base_device", "memory_geometry_profile_id",
                "main_flash_size_bytes", "page_count",
            ):
                _require(raw.get(field) == target.get(field),
                         f"non-LQFP qualified geometry mismatch {icpn}/{field}")
            self._records[key] = deepcopy(raw)
        _require(
            len(self._records) == 77
            and all(("STMicroelectronics", icpn) not in self._records for icpn in excluded_exact),
            "ST v9 non-LQFP combined exact scope exceeded",
        )
        for item in (package_applicability, package_qualification, qualification_v9):
            boundary = item.get("non_claims", item.get("acceptance_boundary", {}))
            for k in ("hardware_runtime_ready", "physical_programming_qualified", "execution_authorized"):
                _require(boundary.get(k) is False, "non-LQFP physical/run execution boundary drift: " + k)

        for qualification_name, boundary in (
            ("medium-density", qualification.get("acceptance_boundary", {})),
            ("high-density", high_qualification.get("acceptance_boundary", {})),
            ("v8 manifest", qualification_manifest.get("acceptance_boundary", {})),
        ):
            for boundary_key in (
                "job_batch_execution_changed",
                "installed_runtime_attested",
                "hardware_runtime_ready",
                "physical_programming_qualified",
                "phase3_compatibility_claimed",
            ):
                _require(
                    boundary.get(boundary_key) is False,
                    f"unsafe {qualification_name} Programming Qualification boundary: {boundary_key}",
                )

        boundary = qualification_manifest.get("acceptance_boundary", {})
        for key in (
            "job_batch_execution_changed",
            "installed_runtime_attested",
            "hardware_runtime_ready",
            "physical_programming_qualified",
            "phase3_compatibility_claimed",
        ):
            _require(boundary.get(key) is False, f"unsafe Programming Qualification boundary: {key}")

        self.source_lock_id = source_lock["source_lock_id"]
        self.qualification_id = qualification_v9["qualification_id"]
        self.provider = deepcopy(q_provider)
        self.programming_group = deepcopy(group)
        self.operation_qualification = deepcopy(opq)
        self._programming_groups_by_profile = {
            group["manufacturer_evidence"]["programming_profile_id"]: deepcopy(group),
            high_group["manufacturer_evidence"]["programming_profile_id"]: deepcopy(high_group),
        }
        self._operation_qualification_by_profile = {
            group["manufacturer_evidence"]["programming_profile_id"]: deepcopy(opq),
            high_group["manufacturer_evidence"]["programming_profile_id"]: deepcopy(high_opq),
        }
        self.acceptance_boundary = deepcopy(boundary)
        self.default_unreviewed_state = qualification_manifest.get(
            "default_unreviewed_software_state"
        )
        _require(self.default_unreviewed_state == "UNKNOWN", "unreviewed exact ICPNs must remain UNKNOWN")

    @property
    def reviewed_exact_keys(self) -> tuple[tuple[str, str], ...]:
        """Exact ICPNs with an explicit provider review result."""
        return tuple(sorted(self._records))

    def lookup(self, manufacturer: str, exact_icpn: str) -> dict[str, Any] | None:
        record = self._records.get((manufacturer, exact_icpn))
        return deepcopy(record) if record is not None else None

    def state_for(self, manufacturer: str, exact_icpn: str) -> str:
        record = self._records.get((manufacturer, exact_icpn))
        return record["software_state"] if record is not None else self.default_unreviewed_state

    def describe(self, manufacturer: str, exact_icpn: str) -> dict[str, Any]:
        """Return the read-only provider Programming Qualification projection.

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
            "selector_visibility_rule": "CATALOG_LEVEL_2_PROGRAMMABLE",
            "job_batch_execution_changed": False,
            "installed_runtime_attested": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }
        if record is None:
            return payload

        profile_id = record["programming_profile_id"]
        group = self._programming_groups_by_profile[profile_id]
        operation_qualification = self._operation_qualification_by_profile[profile_id]
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
                "state": operation_qualification[operation]["state"],
                "scope": operation_qualification[operation].get("scope"),
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
            "selector_visibility_rule": "CATALOG_LEVEL_2_PROGRAMMABLE",
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }


@lru_cache(maxsize=1)
def get_default_openocd_software_qualification_registry() -> OpenOCDSoftwareQualificationRegistry | None:
    required = (
        RELEASE_REL,
        SOURCE_LOCK_REL,
        QUALIFICATION_REL,
        MEDIUM_QUALIFICATION_REL,
        APPLICABILITY_REL,
        EQUIVALENCE_REL,
        HIGH_QUALIFICATION_REL,
        HIGH_APPLICABILITY_REL,
        HIGH_EQUIVALENCE_REL,
        MEDIUM_NONLQFP_APPLICABILITY_REL,
        MEDIUM_NONLQFP_QUALIFICATION_REL,
        QUALIFICATION_V9_REL,
    )
    if not source_files_available(ROOT, required):
        return None
    return OpenOCDSoftwareQualificationRegistry(get_default_device_catalog(), ROOT)
