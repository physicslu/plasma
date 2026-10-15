"""STM32C5 source-pinned loader selection: SYNTHETIC HOST EVIDENCE ONLY.

No OpenOCD commands, file staging, network, device I/O, hardware, production
mapping or loader execution. A synthetic match never grants write permission.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .backend_candidate_registry import BackendCandidateRegistry, EXPECTED_C5
from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError
from .microchip_phase1_admission_guard import admitted_microchip_phase1_count

_ST_SOURCE_COMMIT = "c8d973bdad9a6fddb51459eda109b3b95d23b57a"
_DFP_SOURCE_COMMIT = "a5f65bc64535cfa723e9d25f58d7ce23d0937aed"


@dataclass(frozen=True, slots=True)
class C5SyntheticReads:
    idcode: int | None
    flash_size_kib: int | None
    idcode_state: str = "unobserved"
    flash_size_state: str = "unobserved"
    flash_size_origin: str = "unknown"


class C5HostLoaderGuard:
    """Inspect an exact C5 research candidate, never generate a flash plan."""

    def __init__(self, catalog: DeviceCatalog, registry: BackendCandidateRegistry):
        if (catalog.status != "production" or catalog.size != 4853 + admitted_microchip_phase1_count(catalog) or
                sum(r.vendor == "STMicroelectronics" for r in catalog.records) != 4629 or
                sum(r.vendor == "NXP" and r.family == "KL25" for r in catalog.records) != 12 or
                sum(r.vendor == "NXP" and r.family == "MCX" and
                    r.mapping_status == "no_mapping" for r in catalog.records) != 196 or
                sum(r.vendor == "NXP" and r.family == "K32L2" and
                    r.mapping_status == "no_mapping" for r in catalog.records) != 16 or
                not registry.evidence_available or registry.size != 362 or
                catalog.revision_sha256 != registry.catalog_revision_sha256):
            raise DeviceCatalogIntegrityError(
                "C5 loader guard requires source-locked matching Production registry"
            )
        self._catalog = catalog
        self._registry = registry

    @staticmethod
    def _result(icpn: object, status: str, reason: str,
                candidate: dict[str, Any] | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "icpn": icpn if isinstance(icpn, str) else None,
            "status": status,
            "reason": reason,
            "scope": "synthetic_host_only_no_runtime",
            "candidate_loader_source_path": None,
            "candidate_loader_sha256": None,
            "dfp_exact_variant_evidence": False,
            "real_device_id_verified": False,
            "real_flash_size_verified": False,
            "loader_staged": False,
            "loader_executed": False,
            "loader_ram_abi_verified": False,
            "vendor_binary_redistribution_approved": False,
            "security_state_verified": False,
            "hardware_runtime_ready": False,
            "production_write_authorized": False,
            "executable": False,
            "qualified_hardware_operations": [],
        }
        if candidate is not None and status == "synthetic_source_match_only":
            # Path and digest are SOURCE identifiers, never an installed file.
            result["candidate_loader_source_path"] = candidate["loader_source_path"]
            result["candidate_loader_sha256"] = candidate["loader_sha256"]
            result["dfp_exact_variant_evidence"] = True
        return result

    def evaluate(self, icpn: str, sample: C5SyntheticReads) -> dict[str, Any]:
        if not isinstance(icpn, str) or not icpn or icpn != icpn.strip():
            return self._result(icpn, "blocked", "invalid_exact_icpn")
        row = self._catalog.resolve("STMicroelectronics", icpn)
        if (row is None or row.identifier != icpn or row.family != "STM32C5"
                or not row.production_admitted or
                row.identifier_kind != "manufacturer_part_number" or
                row.mapping_status != "no_mapping" or row.target_config):
            return self._result(icpn, "blocked", "not_exact_unmapped_st_c5")
        c = self._registry.lookup(row)
        if (c is None or c.get("status") != "research_only" or
                c.get("provider_id") != "openocd-st-c5-stldr-research" or
                c.get("source_commit") != _ST_SOURCE_COMMIT or
                c.get("dfp_source_commit") != _DFP_SOURCE_COMMIT or
                c.get("flash_driver") != "stldr" or
                c.get("production_mapping_status") != "no_mapping" or
                c.get("executable") is not False or
                c.get("production_binding_authorized") is not False or
                c.get("hardware_runtime_ready") is not False or
                c.get("loader_installed") is not False or
                c.get("loader_qualified") is not False or
                c.get("flash_size_readback_kib") is not None or
                c.get("fork_default_workarea_bytes") != 32768):
            return self._result(icpn, "blocked", "invalid_candidate_source_or_authorization")
        dev_id = c.get("expected_device_id")
        group = EXPECTED_C5.get(dev_id)
        if group is None:
            return self._result(icpn, "blocked", "unknown_device_group")
        path, _, _, _, ram, max_bytes = group
        if (c.get("loader_source_path") != path or
                c.get("dfp_declared_algorithm_ram_bytes") != ram or
                c.get("driver_max_flash_kib") != max_bytes // 1024 or
                c.get("catalog_flash_kib") != int((row.flash_size or "0 KiB").split()[0]) or
                type(c.get("catalog_flash_kib")) is not int or
                not (0 < c["catalog_flash_kib"] <= max_bytes // 1024) or
                not isinstance(c.get("loader_sha256"), str) or
                len(c["loader_sha256"]) != 64 or
                any(ch not in "0123456789abcdef" for ch in c["loader_sha256"])):
            return self._result(icpn, "blocked", "loader_ram_geometry_or_sha_untrusted")
        if c.get("dfp_exact_variant_status") != "exact":
            return self._result(icpn, "blocked", "dfp_base_only_not_exact_loader_evidence")
        if not isinstance(sample, C5SyntheticReads):
            return self._result(icpn, "blocked", "missing_synthetic_sample")
        if sample.idcode_state != "ok" or sample.flash_size_state != "ok":
            return self._result(icpn, "blocked", "read_failure_or_unknown")
        if sample.flash_size_origin != "direct_register":
            return self._result(icpn, "blocked", "flash_size_fallback_or_override_untrusted")
        if type(sample.idcode) is not int or not 0 <= sample.idcode <= 0xFFFFFFFF:
            return self._result(icpn, "blocked", "invalid_device_id")
        if (sample.idcode & 0xFFF) != int(dev_id, 16):
            return self._result(icpn, "blocked", "device_id_mismatch")
        flash = sample.flash_size_kib
        if type(flash) is not int or not 0 < flash < 0xFFFF:
            return self._result(icpn, "blocked", "invalid_flash_size_register")
        if flash != c["catalog_flash_kib"]:
            return self._result(icpn, "blocked", "flash_size_mismatch_or_driver_max_fallback")
        # This means only that provided SYNTHETIC values agree with catalog/DFP.
        return self._result(icpn, "synthetic_source_match_only",
                            "no_installed_loader_or_runtime_authorized", c)
