#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
FOUNDATION = HERE / "stm32l5-security-scope-foundation.json"
UPSTREAM = HERE / "stm32-trustzone-cohort-gate1-qualification.json"

REQUIRED_CONTROLS = {
    "TZEN",
    "RDP",
    "secure_nonsecure_execution_state",
    "debug_interface_state",
}
REQUIRED_FALSE = {
    "production_admission_allowed",
    "security_semantics_supported",
    "option_byte_writes_allowed",
    "rdp_regression_allowed",
    "mass_erase_allowed",
    "flash_geometry_validated",
    "programming_algorithm_equivalence",
    "runtime_programming_supported",
    "external_flash_under_tzen_runtime_claim_allowed",
    "incremental_programming_under_trustzone_runtime_claim_allowed",
    "hil_validated",
}
REQUIRED_TRUE = {
    "manufacturer_identity_discovery_allowed",
    "commercial_icpn_discovery_allowed",
}


def _fail(message: str) -> None:
    raise ValueError(message)


def validate(foundation: dict, upstream: dict) -> None:
    if foundation.get("schema_version") != 1:
        _fail("schema_version must be 1")
    if foundation.get("transaction") != "stm32l5-security-scope-foundation":
        _fail("unexpected transaction")
    if foundation.get("authority") != "research_only":
        _fail("authority must remain research_only")
    if foundation.get("series") != "STM32L5":
        _fail("series must be STM32L5")
    if foundation.get("subfamily_scope") != ["STM32L5x2"]:
        _fail("subfamily scope drifted")
    if foundation.get("device_line_scope") != ["STM32L552", "STM32L562"]:
        _fail("device-line scope drifted")

    if upstream.get("selected_for_next_research") != "STM32L5":
        _fail("upstream TrustZone qualification no longer selects STM32L5")
    if upstream.get("authority") != "research_only":
        _fail("upstream authority drifted")

    sources = foundation.get("manufacturer_sources")
    if not isinstance(sources, list) or len(sources) < 3:
        _fail("manufacturer evidence set is incomplete")
    source_ids: set[str] = set()
    observations: list[str] = []
    for source in sources:
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id or source_id in source_ids:
            _fail("manufacturer source ids must be unique and nonblank")
        source_ids.add(source_id)
        if source.get("authority") != "STMicroelectronics":
            _fail(f"{source_id}: source authority must be STMicroelectronics")
        url = source.get("url")
        if not isinstance(url, str) or urlparse(url).scheme != "https":
            _fail(f"{source_id}: source URL must be HTTPS")
        host = (urlparse(url).hostname or "").lower()
        if host not in {"www.st.com", "st.com", "wiki.st.com"}:
            _fail(f"{source_id}: source is not an ST-controlled host")
        source_observations = source.get("observations")
        if not isinstance(source_observations, list) or not source_observations:
            _fail(f"{source_id}: observations missing")
        observations.extend(str(item).lower() for item in source_observations)

    joined = "\n".join(observations)
    for token in ("stm32l552", "stm32l562", "trustzone", "tzen", "rdp", "debug"):
        if token not in joined:
            _fail(f"manufacturer evidence does not cover required token: {token}")

    controls = set(foundation.get("security_sensitive_controls") or [])
    if not REQUIRED_CONTROLS.issubset(controls):
        _fail("security-sensitive control set is incomplete")

    partition = foundation.get("research_partition")
    if not isinstance(partition, dict):
        _fail("research_partition missing")
    for key in REQUIRED_TRUE:
        if partition.get(key) is not True:
            _fail(f"{key} must remain true")
    for key in REQUIRED_FALSE:
        if partition.get(key) is not False:
            _fail(f"{key} must remain false")

    if foundation.get("status") != "eligible_for_identity_discovery_under_security_fence":
        _fail("unexpected foundation status")
    if foundation.get("next_research_gate") != "stm32l5-manufacturer-identity-discovery":
        _fail("unexpected next research gate")


def main() -> int:
    foundation = json.loads(FOUNDATION.read_text(encoding="utf-8"))
    upstream = json.loads(UPSTREAM.read_text(encoding="utf-8"))
    validate(foundation, upstream)
    print("STM32L5 security-scope foundation: PASS")
    print("next_research_gate=stm32l5-manufacturer-identity-discovery")
    print("runtime_programming_supported=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
