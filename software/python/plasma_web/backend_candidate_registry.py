"""Read-only, exact-ICPN Backend Candidate Registry.

This is not the Production Device Catalog, an executable backend registry,
a Programming Profile, or a hardware qualification report. Evidence is joined
against Production exact identities, never used to resolve/program a target.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any

from .backend_provenance import load_source_authorities
from .device_catalog import (
    DeviceCatalog, DeviceCatalogIntegrityError, DeviceCatalogRecord,
    get_default_device_catalog,
)

ROOT = Path(__file__).resolve().parents[3]
H5_FACTS = "data/device-catalog/research/st-h5-offline-flash-matrix-v1.json"
C5_CROSSWALK = "data/device-catalog/research/st-c5-dfp-commercial-loader-crosswalk-v0.9.csv"
C5_DFP_REPORT = "data/device-catalog/research/st-c5-dfp-commercial-loader-crosswalk-v0.9.json"
C5_STATIC_GATE = "data/device-catalog/research/st-c5-ps-backend-static-gate-v1.1.json"

# Immutable Git blob identities of existing reviewed research artifacts.
H5_FACTS_BLOB = "63481c91b587ea41d110b68d61023a9d38eebdc5"
C5_CROSSWALK_BLOB = "8aed12306c4898dab869608217296bed92cdbdb8"
C5_DFP_REPORT_BLOB = "6e484f5e2f2aa292612fad922224c61d43125d47"
C5_STATIC_GATE_BLOB = "4cae6f754c66001092a322b846811c6799ab2458"

EXPECTED_H5 = {
    "STM32H50xx": ("0x474", 14, 128, ("STM32H503",)),
    "STM32H52/H53xx": ("0x478", 53, 512, ("STM32H523", "STM32H533")),
    "STM32H54/H55xx": ("0x47C", 6, 1024, ("STM32H543", "STM32H553")),
    "STM32H56/H57xx": ("0x484", 82, 2048, ("STM32H562", "STM32H563", "STM32H573")),
    "STM32H5E/H5Fxx": ("0x47A", 35, 4096, ("STM32H5E4", "STM32H5E5", "STM32H5F4", "STM32H5F5")),
}
EXPECTED_C5 = {
    "0x44F": ("Flash/STM32C5[34]x.xldr", 63, 48, 15, 65536, 262144),
    "0x44E": ("Flash/STM32C5[56]x.xldr", 60, 46, 14, 131072, 524288),
    "0x45A": ("Flash/STM32C5[9A]x.xldr", 49, 45, 4, 262144, 1048576),
}
C5_SERIES = {
    "C53": "0x44F", "C54": "0x44F", "C55": "0x44E",
    "C56": "0x44E", "C59": "0x45A", "C5A": "0x45A",
}


def _ensure(ok: bool, reason: str) -> None:
    if not ok:
        raise DeviceCatalogIntegrityError(f"backend candidate registry: {reason}")


def _locked_bytes(root: Path, name: str, expected_blob: str) -> bytes:
    try:
        data = (root / name).read_bytes()
    except OSError as exc:
        raise DeviceCatalogIntegrityError(f"backend candidate registry: missing {name}") from exc
    # Git blob hash pins the exact bytes. No runtime network or moving branch.
    got = hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()
    _ensure(got == expected_blob, f"source lock mismatch: {name}")
    return data


def _locked_json(root: Path, name: str, blob: str) -> dict[str, Any]:
    try:
        value = json.loads(_locked_bytes(root, name, blob))
    except (ValueError, UnicodeDecodeError) as exc:
        raise DeviceCatalogIntegrityError(f"backend candidate registry: invalid JSON {name}") from exc
    _ensure(isinstance(value, dict), f"{name} must be object")
    return value


def _catalog_family(catalog: DeviceCatalog, family: str, expected: int) -> list[DeviceCatalogRecord]:
    rows = [r for r in catalog.records if r.family == family]
    _ensure(len(rows) == expected, f"{family} exact count mismatch")
    _ensure(len({r.identifier for r in rows}) == expected, f"{family} duplicate ICPNs")
    for row in rows:
        _ensure(row.production_admitted and row.identifier_kind == "manufacturer_part_number"
                and row.vendor == "STMicroelectronics" and row.icpn is not None,
                f"unadmitted exact identity in {family}")
        _ensure(row.mapping_status == "no_mapping" and not row.target_config,
                f"candidate must not inherit a Production route: {row.identifier}")
    return rows


class BackendCandidateRegistry:
    """Immutable read-only candidate lookup; never accepted as execution input."""

    def __init__(self, catalog: DeviceCatalog, root: Path = ROOT):
        self.catalog_revision_sha256 = catalog.revision_sha256
        self._by_icpn: dict[str, dict[str, Any]] = {}
        if not any(r.family in {"STM32H5", "STM32C5"} for r in catalog.records):
            return  # Alternate catalog without the candidate cohorts: no candidates.
        _ensure(catalog.status == "production", "requires a Production Catalog")
        _ensure(catalog.size == 4629, "unexpected Production Catalog size")
        upstream, gap = load_source_authorities(root)
        _ensure(upstream["source_commit"] == gap["packaged_runtime"]["commit"],
                "OpenOCD release mismatch")
        fork = gap["candidate_st_fork"]
        commit = fork["commit"]

        self._add_h5(_catalog_family(catalog, "STM32H5", 190), root, fork, commit)
        self._add_c5(_catalog_family(catalog, "STM32C5", 172), root, fork, commit)
        _ensure(len(self._by_icpn) == 362, "candidate coverage must be 362 exact identities")
        _ensure(Counter(x["family"] for x in self._by_icpn.values()) ==
                {"STM32H5": 190, "STM32C5": 172}, "unexpected candidate family count")

    def _add(self, row: DeviceCatalogRecord, candidate: dict[str, Any]) -> None:
        _ensure(row.identifier not in self._by_icpn, f"duplicate candidate: {row.identifier}")
        _ensure(candidate["status"] == "research_only" and
                candidate["production_binding_authorized"] is False and
                candidate["executable"] is False and candidate["hardware_runtime_ready"] is False and
                candidate["physical_programming_qualified"] is False,
                "candidate permission boundary must remain closed")
        self._by_icpn[row.identifier] = candidate

    def _base(self, row: DeviceCatalogRecord, commit: str,
              cfg: dict[str, str], driver: dict[str, str]) -> dict[str, Any]:
        return {
            "family": row.family,
            "status": "research_only",
            "production_mapping_status": row.mapping_status,
            "provider_id": "openocd-st-h5-research" if row.family == "STM32H5"
                           else "openocd-st-c5-stldr-research",
            "source_repository": "https://github.com/STMicroelectronics/OpenOCD.git",
            "source_commit": commit,
            "target_config_source_path": cfg["path"],
            "target_config_git_blob": cfg["blob"],
            "flash_driver": "stm32h5x" if row.family == "STM32H5" else "stldr",
            "flash_driver_source_path": driver["path"],
            "flash_driver_git_blob": driver["blob"],
            "executable": False,
            "production_binding_authorized": False,
            "hardware_runtime_ready": False,
            "physical_programming_qualified": False,
        }

    def _add_h5(self, rows: list[DeviceCatalogRecord], root: Path,
                fork: dict[str, Any], commit: str) -> None:
        facts = _locked_json(root, H5_FACTS, H5_FACTS_BLOB)
        src = facts["source"]
        _ensure(src["commit"] == commit and
                src["target_config_git_blob"] == fork["files"]["h5_cfg"]["blob"] and
                src["driver_git_blob"] == fork["files"]["h5_flash_driver"]["blob"] and
                facts["candidate_status"] == "RESEARCH_ONLY_NOT_PRODUCTION_MAPPED" and
                facts["flash_sector_kib"] == 8 and facts["flash_write_alignment_bytes"] == 16 and
                facts["driver_flash_size_failure_falls_back_to_max"] is True,
                "H5 static source authority mismatch")
        groups = facts["device_groups"]
        _ensure(len(groups) == 5, "H5 must have 5 source groups")
        by_series: dict[str, dict] = {}
        for group in groups:
            group_id = group["group"]
            _ensure(group_id in EXPECTED_H5, f"unrecognized H5 group {group_id}")
            dev_id, expected_count, max_kib, series = EXPECTED_H5[group_id]
            _ensure((group["expected_device_id"], group["expected_icpns"],
                     group["max_flash_kib"], tuple(group["series"])) ==
                    (dev_id, expected_count, max_kib, series),
                    f"H5 group identity or capacity drift: {group_id}")
            for family_series in series:
                _ensure(family_series not in by_series, "duplicate H5 series")
                by_series[family_series] = group
        counts: Counter[str] = Counter()
        for row in rows:
            group = by_series.get(row.subfamily)
            _ensure(group is not None, f"unexpected H5 exact series {row.identifier}")
            match = re.fullmatch(r"([0-9]+) KiB", row.flash_size or "")
            _ensure(match is not None, f"H5 official flash size missing: {row.identifier}")
            flash = int(match.group(1))
            _ensure(flash > 0 and flash <= group["max_flash_kib"] and flash % 8 == 0,
                    f"H5 Flash exceeds source driver's constraints: {row.identifier}")
            counts[group["group"]] += 1
            record = self._base(row, commit, fork["files"]["h5_cfg"], fork["files"]["h5_flash_driver"])
            record.update({
                "expected_device_id": group["expected_device_id"],
                "device_id_evidence": "inferred_from_pinned_driver_family_not_silicon",
                "catalog_flash_kib": flash,
                "driver_max_flash_kib": group["max_flash_kib"],
                "flash_size_readback_kib": None,
                "sector_size_kib_source_only": 8,
                "write_alignment_bytes_source_only": 16,
                "loader_source_path": None,
                "loader_sha256": None,
                "dfp_exact_variant_status": None,
                "blockers": [
                    "candidate_st_fork_not_installed_or_admitted",
                    "actual_device_id_flash_geometry_and_security_unverified",
                    "fpga_swd_and_electrical_profile_unverified",
                    "erase_program_verify_unqualified",
                ],
            })
            self._add(row, record)
        _ensure(counts == {name: group[1] for name, group in EXPECTED_H5.items()},
                "H5 exact group counts changed")

    def _add_c5(self, rows: list[DeviceCatalogRecord], root: Path,
                fork: dict[str, Any], commit: str) -> None:
        report = _locked_json(root, C5_DFP_REPORT, C5_DFP_REPORT_BLOB)
        gate = _locked_json(root, C5_STATIC_GATE, C5_STATIC_GATE_BLOB)
        _ensure(report["official_dfp_source"]["pinned_commit"] ==
                "a5f65bc64535cfa723e9d25f58d7ce23d0937aed" and
                report["commercial_cohort"]["exact_pdsc_variant_matches"] == 139 and
                report["commercial_cohort"]["parent_dname_only_missing_exact_dfp_variant"] == 33,
                "C5 DFP source snapshot mismatch")
        st = gate["manufacturer_openocd_fork"]
        _ensure(st["pinned_commit"] == commit and
                st["target_cfg_blob_sha"] == fork["files"]["c5_cfg"]["blob"] and
                st["stldr_driver_blob_sha"] == fork["files"]["c5_stldr_driver"]["blob"] and
                st["source_tcl_defect"]["loader_table_remains_empty_in_research_fix"] is True and
                st["target_default_workarea_bytes"] == 32768 and
                gate["gates"]["stldr_compiled_in_plasma_chosen_binary_verified"] is False and
                gate["gates"]["production_programming_authorized"] is False,
                "C5 Tcl/driver runtime boundary mismatch")
        available = {r["path"]: r for r in report["official_dfp_source"]["loader_files"]}
        raw = _locked_bytes(root, C5_CROSSWALK, C5_CROSSWALK_BLOB)
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
        by_icpn = {r.identifier: r for r in rows}
        counts: Counter[str] = Counter()
        exact: Counter[str] = Counter()
        seen: set[str] = set()
        for candidate in reader:
            icpn = candidate["icpn"]
            _ensure(icpn not in seen and icpn in by_icpn, f"C5 crosswalk unknown/duplicate: {icpn}")
            seen.add(icpn)
            row = by_icpn[icpn]
            family = candidate["series"]
            dev_id = C5_SERIES.get(family)
            _ensure(dev_id is not None and row.subfamily and row.subfamily[5:8] == family,
                    f"C5 family or series mismatch: {icpn}")
            loader, total, exact_count, base_count, ram, fallback = EXPECTED_C5[dev_id]
            _ensure(candidate["candidate_dev_id"] == dev_id and
                    candidate["candidate_xldr_path"] == loader and
                    candidate["dfp_parent_dname"] == row.base_device and
                    candidate["plasma_route_ready"] == "false",
                    f"C5 DFP candidate identity/route mismatch: {icpn}")
            match = re.fullmatch(r"([0-9]+) KiB", row.flash_size or "")
            _ensure(match is not None, f"C5 official flash missing: {icpn}")
            flash_kib = int(match.group(1))
            is_exact = candidate["dfp_evidence_state"] == "EXACT_DFP_VARIANT"
            _ensure(candidate["dfp_evidence_state"] in
                    {"EXACT_DFP_VARIANT", "BASE_DEVICE_ONLY_NOT_EXACT"} and
                    candidate["exact_variant_flash_bytes"] ==
                    (str(flash_kib * 1024) if is_exact else "") and
                    int(candidate["parent_flash_bytes"]) == flash_kib * 1024 and
                    flash_kib * 1024 <= fallback and
                    int(candidate["dfp_loader_ram_bytes"]) == ram,
                    f"C5 official catalog/DFP flash or RAM mismatch: {icpn}")
            loader_info = available.get(loader)
            _ensure(loader_info is not None and loader_info["dev_id"] == dev_id and
                    re.fullmatch("[a-f0-9]{64}", loader_info["sha256"]) is not None,
                    f"C5 pinned loader SHA absent: {icpn}")
            counts[dev_id] += 1
            if is_exact:
                exact[dev_id] += 1
            record = self._base(row, commit, fork["files"]["c5_cfg"], fork["files"]["c5_stldr_driver"])
            record.update({
                "expected_device_id": dev_id,
                "device_id_evidence": "inferred_from_pinned_dfp_family_not_silicon",
                "catalog_flash_kib": flash_kib,
                "driver_max_flash_kib": fallback // 1024,
                "flash_size_readback_kib": None,
                "sector_size_kib_source_only": None,
                "write_alignment_bytes_source_only": None,
                "loader_source_path": loader,
                "loader_sha256": loader_info["sha256"],
                "dfp_source_commit": report["official_dfp_source"]["pinned_commit"],
                "dfp_exact_variant_status": "exact" if is_exact else "base_device_only",
                "dfp_declared_algorithm_ram_bytes": ram,
                "fork_default_workarea_bytes": 32768,
                "loader_installed": False,
                "loader_qualified": False,
                "blockers": [
                    "candidate_st_fork_not_installed_or_admitted",
                    "tcl_scalar_array_defects_and_empty_loader_table",
                    "local_loader_staging_license_and_ram_abi_unverified",
                    "actual_device_id_flash_geometry_and_security_unverified",
                    "fpga_swd_and_electrical_profile_unverified",
                    "erase_program_verify_unqualified",
                ] + ([] if is_exact else ["exact_dfp_dvariant_missing"]),
            })
            self._add(row, record)
        _ensure(len(seen) == len(rows) == 172 and
                {k: (counts[k], exact[k], counts[k] - exact[k]) for k in EXPECTED_C5} ==
                {k: values[1:4] for k, values in EXPECTED_C5.items()},
                "C5 172 / 139 exact / 33 base-only cohort drift")

    @property
    def size(self) -> int:
        return len(self._by_icpn)

    def lookup(self, row: DeviceCatalogRecord) -> dict[str, Any] | None:
        """Only use for displaying a previously Production-resolved exact identity."""
        if not row.production_admitted or row.mapping_status != "no_mapping":
            return None
        return self._by_icpn.get(row.identifier)


@lru_cache(maxsize=1)
def get_default_backend_candidate_registry() -> BackendCandidateRegistry:
    return BackendCandidateRegistry(get_default_device_catalog())
