"""Read-only, per-ICPN OpenOCD source provenance, separate from Programming readiness.

This joins the *immutable Production Catalog*, the pinned upstream OpenOCD
release declaration, and the ST research-only source evidence. It does not
modify Catalog source CSVs, promote a backend, or attest any installed binary.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, DeviceCatalogRecord


def _read_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeviceCatalogIntegrityError(f"cannot read backend source authority: {path}") from exc
    if not isinstance(obj, dict):
        raise DeviceCatalogIntegrityError(f"backend source authority must be an object: {path}")
    return obj


def _commit(value: object, source: str) -> str:
    if not isinstance(value, str) or len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
        raise DeviceCatalogIntegrityError(f"invalid pinned source commit: {source}")
    return value


def load_source_authorities(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fail closed on drift between release authority and existing ST gap research."""
    upstream = _read_json(root / "release/openocd.json")
    gap = _read_json(root / "data/device-catalog/research/st-h5-c5-runtime-gap-v1.json")
    if upstream.get("schema_version") != 1 or upstream.get("engine") != "openocd":
        raise DeviceCatalogIntegrityError("invalid pinned OpenOCD release schema/engine")
    if upstream.get("source_repository") != "https://github.com/openocd-org/openocd.git":
        raise DeviceCatalogIntegrityError("unexpected packaged OpenOCD source repository")
    upstream_commit = _commit(upstream.get("source_commit"), "release/openocd.json")
    if upstream.get("runtime_id") != f"{upstream.get('version')}-{upstream_commit[:12]}":
        raise DeviceCatalogIntegrityError("upstream runtime_id does not match its pinned version/commit")
    runtime = gap.get("packaged_runtime")
    candidate = gap.get("candidate_st_fork")
    if not isinstance(runtime, dict) or not isinstance(candidate, dict):
        raise DeviceCatalogIntegrityError("missing runtime/candidate provenance in ST gap evidence")
    if runtime.get("repository") != "openocd-org/openocd" or runtime.get("commit") != upstream_commit:
        raise DeviceCatalogIntegrityError("ST gap packaged-runtime provenance conflicts with release/openocd.json")
    if candidate.get("repository") != "STMicroelectronics/OpenOCD":
        raise DeviceCatalogIntegrityError("unexpected ST candidate source repository")
    _commit(candidate.get("commit"), "ST candidate")
    file_info = candidate.get("files")
    if not isinstance(file_info, dict):
        raise DeviceCatalogIntegrityError("missing pinned ST target/driver source blobs")
    for name, expected_path in {
        "h5_cfg": "tcl/target/stm32h5x.cfg",
        "h5_flash_driver": "src/flash/nor/stm32h5x.c",
        "c5_cfg": "tcl/target/stm32c5x.cfg",
        "c5_stldr_driver": "src/flash/nor/stldr_driver.c",
    }.items():
        obj = file_info.get(name)
        if not isinstance(obj, dict) or obj.get("path") != expected_path:
            raise DeviceCatalogIntegrityError(f"ST candidate source path missing/drifted: {name}")
        _commit(obj.get("blob"), f"ST candidate blob {name}")
    return upstream, gap


def _research_candidate(record: DeviceCatalogRecord, gap: dict[str, Any]) -> dict[str, Any] | None:
    if record.mapping_status != "no_mapping" or record.family not in {"STM32H5", "STM32C5"}:
        return None
    source = gap["candidate_st_fork"]
    is_h5 = record.family == "STM32H5"
    cfg = source["files"]["h5_cfg" if is_h5 else "c5_cfg"]
    driver = source["files"]["h5_flash_driver" if is_h5 else "c5_stldr_driver"]
    return {
        "status": "research_only_not_production_mapped",
        "provider_id": "openocd-st-h5-research" if is_h5 else "openocd-st-c5-stldr-research",
        "source_distribution": "STMicroelectronics/OpenOCD",
        "source_repository": "https://github.com/STMicroelectronics/OpenOCD.git",
        "source_commit": source["commit"],
        "target_config": cfg["path"],
        "target_config_git_blob": cfg["blob"],
        "flash_driver": "stm32h5x" if is_h5 else "stldr",
        "flash_driver_source_path": driver["path"],
        "flash_driver_git_blob": driver["blob"],
        "software_evidence": (
            "data/device-catalog/research/ST_H5_ARMV7_BUILD_V1.md"
            if is_h5 else
            "data/device-catalog/research/ST_C5_PS_BACKEND_STATIC_GATE_V11.md"
        ),
        "qualification_boundary": (
            "host_and_qemu_armv7_software_only" if is_h5 else "source_and_tcl_static_only"
        ),
        "loader_qualified": False if not is_h5 else None,
        "production_binding_authorized": False,
        "hardware_runtime_ready": False,
    }


def audit_record(
    record: DeviceCatalogRecord,
    upstream: dict[str, Any],
    gap: dict[str, Any],
) -> dict[str, Any]:
    """One exact ICPN, separating catalog routing, source and installed runtime."""
    if not record.production_admitted or record.identifier_kind != "manufacturer_part_number":
        raise DeviceCatalogIntegrityError("backend provenance audit accepts Production exact ICPNs only")
    if record.mapping_status not in {"mapped", "no_mapping"}:
        raise DeviceCatalogIntegrityError(f"unsupported mapping status: {record.identifier}")
    mapped = record.mapping_status == "mapped"
    if mapped and (not record.target_config or record.openocd_distribution != "upstream-openocd"):
        raise DeviceCatalogIntegrityError(f"unexpected mapped provider: {record.identifier}")
    if not mapped and record.target_config:
        raise DeviceCatalogIntegrityError(f"no_mapping has target config: {record.identifier}")
    return {
        "schema_version": 1,
        "manufacturer": record.vendor,
        "icpn": record.identifier,
        "family": record.family,
        "series": record.subfamily,
        "catalog_version": record.catalog_version,
        "catalog_revision_sha256": record.catalog_revision_sha256,
        "catalog_source": record.catalog_origin,
        "identity_evidence_reference": record.source_reference,
        "identity_evidence_status": record.verification_status,
        "mapping_status": record.mapping_status,
        "mapping_method": record.mapping_method,
        "production_binding": {
            "provider_id": "openocd-upstream" if mapped else None,
            "source_distribution": "openocd-org/openocd" if mapped else None,
            "source_repository": upstream["source_repository"] if mapped else None,
            "source_commit": upstream["source_commit"] if mapped else None,
            "source_tag": upstream.get("source_tag") if mapped else None,
            "source_version": upstream["version"] if mapped else None,
            "pinned_release_runtime_id": upstream["runtime_id"] if mapped else None,
            "target_config": record.target_config if mapped else None,
            # A route does not prove the per-IC driver, config blob, or deployed ELF.
            "target_config_git_blob": None,
            "flash_driver": None,
            "flash_driver_source_commit": None,
            "flash_driver_evidence_status": "not_independently_evidenced" if mapped else "unbound",
            "source_identity_evidence": "release/openocd.json" if mapped else None,
            "qualification_boundary": "catalog_mapping_only" if mapped else "unbound",
            "hardware_runtime_ready": False,
        },
        "research_candidate": _research_candidate(record, gap),
        "installed_runtime": {
            "runtime_id": None,
            "binary_sha256": None,
            "artifact_sha256": None,
            "status": "not_attested_by_catalog",
        },
        "physical_programming_qualified": False,
    }


def audit_snapshot(
    catalog: DeviceCatalog,
    upstream: dict[str, Any],
    gap: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any], bytes]:
    rows = [audit_record(r, upstream, gap) for r in catalog.records]
    rows.sort(key=lambda r: (r["manufacturer"], r["icpn"]))
    seen = {(r["manufacturer"], r["icpn"]) for r in rows}
    if len(seen) != catalog.size:
        raise DeviceCatalogIntegrityError("backend provenance audit has duplicate/missing exact ICPN")
    blob = (
        "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in rows)
        + "\n"
    ).encode("utf-8")
    counts = Counter(r["mapping_status"] for r in rows)
    candidates = Counter(r["family"] for r in rows if r["research_candidate"] is not None)
    summary: dict[str, Any] = {
        "schema_version": 1,
        "scope": "read_only_exact_icpn_backend_source_audit",
        "catalog_revision_sha256": catalog.revision_sha256,
        "total_exact_icpns": len(rows),
        "production_mapped": counts["mapped"],
        "production_no_mapping": counts["no_mapping"],
        "research_candidates_not_mapped": dict(sorted(candidates.items())),
        "upstream_pinned_source_commit": upstream["source_commit"],
        "st_candidate_pinned_source_commit": gap["candidate_st_fork"]["commit"],
        "records_jsonl_sha256": hashlib.sha256(blob).hexdigest(),
        "physical_programming_qualified": False,
        "production_mapping_modified": False,
    }
    if counts["mapped"] + counts["no_mapping"] != catalog.size:
        raise DeviceCatalogIntegrityError("mapping statuses do not partition the Production Catalog")
    return rows, summary, blob
