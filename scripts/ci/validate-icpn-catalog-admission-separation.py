#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/architecture/icpn-catalog-admission-policy.json"
PRODUCTION_README = ROOT / "data/device-catalog/production/README.md"
SUPPORT_ARCH = ROOT / "docs/architecture/device-support-validation.md"
SELECTOR_ARCH = ROOT / "docs/architecture/ic-selector.md"


def fail(message: str) -> None:
    raise SystemExit(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def main() -> int:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    require(policy.get("schema_version") == 1, "ICPN separation policy schema drifted")
    require(policy.get("policy_id") == "icpn-catalog-admission-separation", "ICPN separation policy id drifted")

    admission = policy.get("catalog_admission")
    require(isinstance(admission, dict), "catalog_admission policy missing")
    for key in (
        "requires_ppu_hil",
        "requires_socket_hil",
        "requires_physical_programming_success",
    ):
        require(admission.get(key) is False, f"catalog admission incorrectly depends on physical validation: {key}")
    require(admission.get("admits_not_verified_physical_state") is True, "Production catalog must permit not-verified physical state")

    physical = policy.get("physical_validation")
    require(isinstance(physical, dict), "physical_validation policy missing")
    require(physical.get("independent_from_catalog_admission") is True, "physical validation lost catalog separation")
    require(physical.get("ppu_status_is_independent") is True, "PPU validation dimension collapsed")
    require(physical.get("socket_status_is_independent") is True, "Socket validation dimension collapsed")
    require(physical.get("hardware_evidence_required_for_engineering_verified") is True, "engineering_verified lost hardware evidence requirement")

    execution = policy.get("execution_policy")
    require(isinstance(execution, dict), "execution_policy missing")
    require(execution.get("independent_from_catalog_admission") is True, "execution eligibility collapsed into catalog admission")
    require(execution.get("catalog_presence_does_not_authorize_target_execution") is True, "catalog membership must not authorize execution")

    expected_dimensions = [
        "catalog_verification",
        "backend_mapping",
        "ppu_physical_validation",
        "socket_physical_validation",
    ]
    require(policy.get("ui_status_dimensions") == expected_dimensions, "four independent ICPN status dimensions drifted")

    production_text = PRODUCTION_README.read_text(encoding="utf-8")
    require("It does **not** prove physical programming support." in production_text, "Production README lost physical-support separation")
    require("PPU and Socket validation remain separate evidence domains" in production_text, "Production README lost PPU/Socket separation")

    support_text = SUPPORT_ARCH.read_text(encoding="utf-8")
    require("Catalog resolution" in support_text, "device-support architecture missing catalog dimension")
    require("Engineering validation" in support_text, "device-support architecture missing engineering-validation dimension")
    require("Field-use evidence" in support_text, "device-support architecture missing field-use dimension")

    selector_text = SELECTOR_ARCH.read_text(encoding="utf-8")
    require(
        "Catalog identity, programming-backend mapping, and physical validation are independent dimensions." in selector_text,
        "IC Selector architecture lost catalog/mapping/physical separation",
    )

    print("ICPN catalog admission separation invariant: PASS")
    print("catalog_admission_requires_ppu_hil=false")
    print("catalog_admission_requires_socket_hil=false")
    print("catalog_admission_requires_physical_programming_success=false")
    print("admitted_not_verified_physical_state_allowed=true")
    print("status_dimensions=4")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
