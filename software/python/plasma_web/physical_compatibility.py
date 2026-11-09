"""Reviewed, configuration-scoped physical HIL evidence for Catalog Level 3.

PPU/Site and Socket/Adapter are independent L3 routes. Neither route grants
execution permission or attests that the currently connected hardware is safe.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

from .device_catalog import DeviceCatalogIntegrityError
from .runtime_evidence_root import default_runtime_evidence_root, source_files_available


MANIFEST_REL = "release/physical-compatibility/l3-configurations-v1.json"
SCHEMA = "plasma.catalog.l3-configurations.v1"
TYPES = frozenset({"PPU_SITE", "SOCKET_ADAPTER"})


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise DeviceCatalogIntegrityError(f"L3 physical compatibility: {message}")


class PhysicalCompatibilityRegistry:
    """Immutable reviewed HIL configurations, never a device execution gate."""

    def __init__(self, records: list[dict[str, Any]], *, root: Path | None = None) -> None:
        self._by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
        identifiers: set[str] = set()
        for record in records:
            _require(isinstance(record, dict), "configuration must be an object")
            identity = record.get("identity")
            ppu = record.get("ppu_site")
            engine = record.get("engine")
            evidence = record.get("evidence")
            provenance = record.get("provenance")
            configuration_id = record.get("configuration_id")
            kind = record.get("verification_type")
            _require(isinstance(configuration_id, str) and configuration_id and configuration_id not in identifiers,
                     "configuration ID missing or duplicate")
            identifiers.add(configuration_id)
            _require(kind in TYPES and record.get("result") == "PASSED", "unreviewed type or HIL result")
            _require(isinstance(identity, dict)
                     and all(isinstance(identity.get(field), str) and identity[field]
                             for field in ("manufacturer", "icpn", "package", "pin_count")),
                     "exact manufacturer/ICPN/package/pin count required")
            _require(isinstance(engine, dict)
                     and all(isinstance(engine.get(field), str) and engine[field]
                             for field in ("provider_id", "provider_version", "target_config", "runtime_sha",
                                           "fpga_image_id", "abi")),
                     "engine, runtime, FPGA and ABI identity required")
            _require(isinstance(ppu, dict) and isinstance(ppu.get("model"), str)
                     and isinstance(ppu.get("ppu_id"), str)
                     and isinstance(ppu.get("device_id"), str) and ppu["device_id"]
                     and type(ppu.get("site_id")) is int and ppu["site_id"] > 0,
                     "versioned PPU and one-based Site required")
            if kind == "PPU_SITE":
                _require(record.get("connection_mode") == "DIRECT_WIRE"
                         and record.get("socket") is None,
                         "PPU-only evidence must not claim a Socket")
            else:
                socket = record.get("socket")
                _require(record.get("connection_mode") == "SOCKET_ADAPTER"
                         and isinstance(socket, dict)
                         and all(isinstance(socket.get(field), str) and socket[field]
                                 for field in ("model", "revision")),
                         "Socket route requires a versioned fixture")
            _require(isinstance(evidence, list) and evidence, "at least one physical receipt required")
            _require(isinstance(provenance, dict)
                     and all(isinstance(provenance.get(field), str) and provenance[field]
                             for field in ("manager_alias", "manager_journal", "manager_journal_sha256",
                                           "bootstrap_status", "bootstrap_status_sha256")),
                     "Manager and Bootstrap provenance required")
            if root is not None:
                for prefix in ("manager_journal", "bootstrap_status"):
                    rel = provenance[prefix]
                    _require(rel.startswith("docs/evidence/")
                             and not Path(rel).is_absolute() and ".." not in Path(rel).parts,
                             f"unsafe {prefix} path")
                    try:
                        raw = (root / rel).read_bytes()
                        decoded = json.loads(raw)
                    except (OSError, ValueError) as exc:
                        raise DeviceCatalogIntegrityError(f"L3 {prefix} unavailable/invalid") from exc
                    _require(isinstance(decoded, dict), f"invalid {prefix} top-level object")
                    _require(hashlib.sha256(raw).hexdigest() == provenance[prefix + "_sha256"],
                             f"{prefix} SHA256 mismatch")
                    if prefix == "manager_journal":
                        runs = decoded.get("runs")
                        _require(isinstance(runs, list), "Manager runs missing")
                    else:
                        bootstrap = decoded.get("bootstrap", {})
                        _require(isinstance(bootstrap, dict)
                                 and isinstance(bootstrap.get("identity"), dict)
                                 and isinstance(bootstrap.get("runtime"), dict),
                                 "invalid PPU Bootstrap identity/runtime")
                        _require(bootstrap.get("identity", {}).get("device_id") == ppu["device_id"]
                                 and bootstrap.get("runtime", {}).get("git_sha") == engine["runtime_sha"]
                                 and bootstrap.get("runtime", {}).get("state") == "runtime_active",
                                 "PPU Bootstrap identity/runtime does not match L3 record")
            for receipt in evidence:
                _require(isinstance(receipt, dict), "receipt must be an object")
                rel = receipt.get("path")
                digest = receipt.get("sha256")
                _require(isinstance(rel, str) and rel.startswith("docs/evidence/")
                         and not Path(rel).is_absolute() and ".." not in Path(rel).parts
                         and isinstance(digest, str) and len(digest) == 64
                         and all(c in "0123456789abcdef" for c in digest),
                         "unsafe receipt path or SHA256")
                if root is not None:
                    try:
                        raw = (root / rel).read_bytes()
                        job = json.loads(raw)["job"]
                        outcome = job["result"]
                        flash = outcome["details"]["flash_cycle"]
                    except (OSError, ValueError, KeyError, TypeError) as exc:
                        raise DeviceCatalogIntegrityError(f"L3 receipt unavailable/invalid: {rel}") from exc
                    _require(isinstance(job, dict) and isinstance(outcome, dict)
                             and isinstance(flash, dict), f"malformed Job result: {rel}")
                    _require(hashlib.sha256(raw).hexdigest() == digest
                             and job.get("state") == "success"
                             and outcome.get("state") == "success"
                             and outcome.get("attempts") == 1
                             and len(outcome.get("attempt_history", [])) == 1
                             and outcome.get("site_id") == ppu["site_id"]
                             and flash.get("site") == ppu["site_id"]
                             and flash.get("icpn") == identity["icpn"]
                             and flash.get("result") == "PASS"
                             and flash.get("safe_off") is True
                             and flash.get("bytes_verified") == outcome.get("image_size")
                             and flash.get("readback_sha256") == outcome.get("image_sha256")
                             and flash.get("opf_driver_abi") == engine["abi"]
                             and flash.get("adapter") == engine["adapter"]
                             and flash.get("opf_openocd_sha256") == engine["openocd_binary_sha256"]
                             and flash.get("target_config") == engine["target_config"],
                             f"receipt identity, readback, attempts or SAFE_OFF mismatch: {rel}")
                    _require(any(
                        run.get("ppu_alias") == provenance["manager_alias"]
                        and run.get("site_id") == ppu["site_id"]
                        and run.get("job_submission_count") == 1
                        and run.get("outcome") == "PASS"
                        and run.get("job", {}).get("job_id") == outcome.get("job_id")
                        for run in runs
                    ), f"Manager journal does not corroborate physical Job: {rel}")
                    if kind == "SOCKET_ADAPTER":
                        _require(flash.get("socket_model") == socket["model"]
                                 and flash.get("socket_revision") == socket["revision"],
                                 f"Socket fixture identity is not in physical receipt: {rel}")
            key = (identity["manufacturer"].casefold(), identity["icpn"].casefold())
            self._by_key.setdefault(key, []).append(deepcopy(record))

    def verified_for(self, manufacturer: str, icpn: str) -> list[dict[str, Any]]:
        return deepcopy(self._by_key.get((manufacturer.casefold(), icpn.casefold()), []))

    @property
    def exact_keys(self) -> set[tuple[str, str]]:
        return set(self._by_key)


@lru_cache(maxsize=1)
def get_default_physical_compatibility_registry() -> PhysicalCompatibilityRegistry:
    root = default_runtime_evidence_root()
    if not source_files_available(root, (MANIFEST_REL,)):
        # Slim/old Selector installations do not gain L3 from absent evidence.
        return PhysicalCompatibilityRegistry([])
    assert root is not None
    try:
        payload = json.loads((root / MANIFEST_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DeviceCatalogIntegrityError("L3 manifest unavailable or invalid") from exc
    _require(isinstance(payload, dict) and payload.get("schema") == SCHEMA
             and isinstance(payload.get("configurations"), list), "invalid manifest schema")
    return PhysicalCompatibilityRegistry(payload["configurations"], root=root)
