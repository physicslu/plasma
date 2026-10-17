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
    "data/device-catalog/research/nxp-kl25-current-source-review-v2.json":
        "92b526ed30b2e159e45f3eff2e3b59fff2f86e72",
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
# installation. The Production Catalog CSV and release pin are checked after source availability.
RESEARCH_FILES = tuple(rel for rel in BLOBS if rel not in (
    "release/openocd.json",
    "data/device-catalog/research/nxp-kl25-commercial-icpn.csv",
))
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

        source_review = payload["data/device-catalog/research/nxp-kl25-current-source-review-v2.json"]
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
        # Pinned upstream source inspection cannot certify a live probe or flash operation.
        _require(
            source_review.get("schema_version") == "1.0.0"
            and source_review.get("audit_id") == "nxp-kl25-current-openocd-source-review-v2"
            and source_review.get("review_boundary") == "SOURCE_ONLY_NO_EXECUTION"
            and source_review.get("exact") == {
                "manufacturer": VENDOR, "icpn": ICPN, "other_kl25_variants_inherited": 0
            },
            "source review exact-ICPN scope drift",
        )
        upstream = source_review.get("source_files", {})
        expected_blobs = {
            "tcl/target/kl25.cfg": "916edf6853c3f26a004d2ca5a2f0e08f43a24093",
            "tcl/target/klx.cfg": "cd236b3395e42310f1475f3b64580758a7f3b9ea",
            "tcl/target/swj-dp.tcl": "f2b233fb78133fd5e45395fd307674c16a65ed70",
            "src/flash/nor/kinetis.c": "7137b4aa078719af31122f8276494f006589e8ab",
        }
        _require(
            set(upstream) == set(expected_blobs)
            and all(upstream[rel].get("git_blob") == blob
                    and type(upstream[rel].get("bytes")) is int
                    and upstream[rel]["bytes"] > 0
                    for rel, blob in expected_blobs.items())
            and source_review.get("provider", {}).get("source_commit") == CURRENT
            and source_review["provider"].get("runtime_id") == release["runtime_id"]
            and source_review["provider"].get("target_config") == "tcl/target/kl25.cfg"
            and source_review["provider"].get("flash_driver") == "kinetis"
            and source_review.get("historical_non_authority", {}).get("commit") == LEGACY
            and source_review["historical_non_authority"].get("gate58_state") == "REJECTED_REVIEW"
            and source_review["historical_non_authority"].get("operation_admission_transferable") is False,
            "pinned current source or historical non-authority changed",
        )
        expected_observations = {
            "TRANSPORT_DEPENDS_ON_SELECTED_SESSION",
            "SWJ_DISPATCHES_SWD_OR_JTAG",
            "TARGET_RESET_INIT_HAS_SIDE_EFFECT",
            "EXACT_PROBE_READS_DEVICE_REGISTERS",
            "PROBE_DECODES_DYNAMIC_GEOMETRY",
            "FCF_GENERATOR_HAS_ASSERT_PATH",
            "SECTOR_ERASE_CAN_WRITE_FCF",
            "ANY_FCF_SECTOR_WRITE_CAN_WRITE_FCF",
        }
        observations = source_review.get("observations", ())
        _require(
            type(observations) is list
            and len(observations) == len(expected_observations)
            and {o.get("id") for o in observations if isinstance(o, dict)}
                == expected_observations
            and all(
                o.get("source") in upstream
                and isinstance(o.get("line_start"), int)
                and isinstance(o.get("line_end"), int)
                and 0 < o["line_start"] <= o["line_end"]
                and bool(o.get("implication"))
                for o in observations
            ),
            "upstream source observation incomplete",
        )
        safe = source_review.get("protected_flash", {})
        legacy_constraints = legacy["admitted_constraints"]
        _require(
            safe.get("fcf_start") == int(legacy_constraints["flash_configuration_field_start"], 0)
            and safe.get("fcf_end_exclusive") == (
                safe["fcf_start"] + legacy_constraints["flash_configuration_field_size_bytes"])
            and safe.get("sector_start") == int(
                legacy_constraints["flash_configuration_field_sector_start"], 0)
            and safe.get("sector_end_exclusive") == (
                safe["sector_start"] + legacy_constraints["flash_configuration_field_sector_size_bytes"])
            and safe["sector_start"] == 0x400
            and safe["sector_end_exclusive"] == 0x800
            and safe.get("geometry_runtime_verified") is False
            and safe.get("program_intersection_requires_rejection") is True
            and safe.get("erase_containing_sector_requires_rejection") is True
            and safe.get("fcf_rewrite_qualified") is False,
            "FCF whole-sector safety contract changed",
        )
        _require(
            source_review.get("operation_review") == {
                "READ": "NOT_QUALIFIED",
                "VERIFY": "NOT_QUALIFIED",
                "PROGRAM": "NOT_QUALIFIED",
                "ERASE_SECTOR": "NOT_QUALIFIED",
            }
            and source_review.get("gates") == {
                "swd_session_and_debug_id_pass": False,
                "exact_sdid_revision_and_sim_fcfg_pass": False,
                "fcf_no_implicit_mutation_proven": False,
                "pinned_binary_runtime_attested": False,
                "read_verify_program_erase_qualified": False,
                "hardware_hil_pass": False,
            }
            and source_review.get("result") == {
                "programming_qualification_state": "CANDIDATE",
                "catalog_level": 1,
                "job_selectable": False,
                "execution_authorized": False,
                "installed_runtime_attested": False,
                "physical_programming_qualified": False,
                "supported_exact_icpn_count_new": 0,
            },
            "source-only audit may not grant qualification or execution",
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
