"""Host-only STM32H5 synthetic readback guard.

No I/O, OpenOCD command generation, device probe, hardware assertion,
backend selection, erase, write, or Production mapping. Successful synthetic
input only means the supplied integers agree with pinned research metadata.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .backend_candidate_registry import BackendCandidateRegistry
from .device_catalog import DeviceCatalog, DeviceCatalogIntegrityError
from .microchip_phase1_admission_guard import admitted_microchip_phase1_count

_ST_FORK_COMMIT = "c8d973bdad9a6fddb51459eda109b3b95d23b57a"
_SYNTHETIC_SCOPE = "host_supplied_synthetic_inputs_only"


@dataclass(frozen=True, slots=True)
class H5SyntheticReads:
    """Synthetic values, never a hardware sample or trusted attestation."""

    idcode: int | None
    flash_size_register_kib: int | None
    idcode_read_state: str
    flash_size_read_state: str
    flash_size_origin: str = "unknown"


class H5HostReadbackGuard:
    """Compare offline H5 inputs against the pinned exact-ICPN catalog.

    This class has no method for emitting or executing a target command.
    A positive comparison does not authorize any programming operation.
    """

    def __init__(self, catalog: DeviceCatalog, candidates: BackendCandidateRegistry):
        if (catalog.status != "production" or catalog.size != 4853 + admitted_microchip_phase1_count(catalog) or
                sum(r.vendor == "STMicroelectronics" for r in catalog.records) != 4629 or
                sum(r.vendor == "NXP" and r.family == "KL25" for r in catalog.records) != 12 or
                sum(r.vendor == "NXP" and r.family == "MCX" and
                    r.mapping_status == "no_mapping" for r in catalog.records) != 196 or
                sum(r.vendor == "NXP" and r.family == "K32L2" and
                    r.mapping_status == "no_mapping" for r in catalog.records) != 16 or
                candidates.catalog_revision_sha256 != catalog.revision_sha256 or
                candidates.size != 362 or not candidates.evidence_available):
            raise DeviceCatalogIntegrityError(
                "H5 host guard requires matching source-locked Production evidence"
            )
        self._catalog = catalog
        self._candidates = candidates

    @staticmethod
    def _result(icpn: object, reason: str, *, consistent: bool = False) -> dict[str, Any]:
        return {
            "icpn": icpn if isinstance(icpn, str) else None,
            "scope": _SYNTHETIC_SCOPE,
            "assessment": "synthetic_consistent" if consistent else "blocked",
            "reason": reason,
            "synthetic_geometry_consistent": consistent,
            "actual_silicon_device_id": None,
            "actual_flash_size_register_kib": None,
            "physical_readback_verified": False,
            "security_state_verified": False,
            "hardware_runtime_ready": False,
            "production_write_authorized": False,
            "executable": False,
            "qualified_hardware_operations": [],
        }

    def evaluate(self, icpn: str, sample: H5SyntheticReads) -> dict[str, Any]:
        """Fail closed on ambiguous reads, driver max fallback or bad geometry.

        Input cannot provide physical provenance. Even matched numbers never
        change Catalog mapping or become a real readback verification.
        """
        if not isinstance(icpn, str) or not icpn or icpn != icpn.strip():
            return self._result(icpn, "invalid_exact_icpn")
        row = self._catalog.resolve("STMicroelectronics", icpn)
        if (row is None or row.identifier != icpn or row.family != "STM32H5" or
                not row.production_admitted or
                row.identifier_kind != "manufacturer_part_number" or
                row.mapping_status != "no_mapping" or row.target_config):
            return self._result(icpn, "no_unmapped_exact_h5_catalog_identity")
        candidate = self._candidates.lookup(row)
        if (candidate is None or candidate.get("provider_id") != "openocd-st-h5-research" or
                candidate.get("source_commit") != _ST_FORK_COMMIT or
                candidate.get("flash_driver") != "stm32h5x" or
                candidate.get("status") != "research_only" or
                candidate.get("production_mapping_status") != "no_mapping" or
                candidate.get("flash_size_readback_kib") is not None or
                candidate.get("executable") is not False or
                candidate.get("production_binding_authorized") is not False or
                candidate.get("hardware_runtime_ready") is not False):
            return self._result(icpn, "candidate_not_source_locked_and_blocked")
        if not isinstance(sample, H5SyntheticReads):
            return self._result(icpn, "not_a_synthetic_read_sample")
        if sample.idcode_read_state != "ok" or sample.flash_size_read_state != "ok":
            return self._result(icpn, "read_failure_or_unknown")
        # Never accept the ST driver's maximum-capacity fallback or a caller
        # override, even when its numeric value equals the official SKU size.
        if sample.flash_size_origin != "direct_register":
            return self._result(icpn, "flash_size_not_direct_register")
        if type(sample.idcode) is not int or not (0 <= sample.idcode <= 0xFFFFFFFF):
            return self._result(icpn, "invalid_idcode_value")
        expected_id = candidate.get("expected_device_id")
        if not isinstance(expected_id, str) or (sample.idcode & 0xFFF) != int(expected_id, 16):
            return self._result(icpn, "device_id_group_mismatch")
        size = sample.flash_size_register_kib
        if type(size) is not int or not (0 < size < 0xFFFF):
            return self._result(icpn, "invalid_flash_size_register")
        catalog_size = candidate.get("catalog_flash_kib")
        driver_max = candidate.get("driver_max_flash_kib")
        if (type(catalog_size) is not int or type(driver_max) is not int or
                candidate.get("sector_size_kib_source_only") != 8 or
                candidate.get("write_alignment_bytes_source_only") != 16 or
                catalog_size <= 0 or catalog_size > driver_max or
                catalog_size % 8 or size > driver_max or size % 8 or
                size != catalog_size):
            return self._result(icpn, "flash_geometry_mismatch_or_untrusted")
        return self._result(icpn, "synthetic_catalog_and_driver_geometry_agree", consistent=True)
