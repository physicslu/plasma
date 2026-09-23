#!/usr/bin/env python3
"""Reconcile STM32WBA5X research identifiers with current official commercial ordering scope."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from stm32_post_u0_evidence_probe import base_from_ordering_pattern

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE / "openocd-parts-canonical.csv"
REMEDIATION_GATE = HERE / "stm32wba5x-evidence-remediation-gate.json"
PRESTATE = HERE / "stm32wba5x-commercial-scope-production-prestate.json"

EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_REMEDIATION_GATE_BLOB = "d25b1bb32fe23a4eff89e33cd9fcc11be34fa5dc"
EXPECTED_PRODUCTION_BLOB = "6e0fc69bec067259a1c52e150a313591cf4523e8"
EXCLUDED = {
    ("STM32WBA50KEUx", "ordering_pattern"),
    ("STM32WBA50KEUxT", "cmsis_device_name"),
}
EXPECTED_BASES = (
    "STM32WBA50KG",
    "STM32WBA52CE", "STM32WBA52CG", "STM32WBA52KE", "STM32WBA52KG",
    "STM32WBA54CE", "STM32WBA54CG", "STM32WBA54KE", "STM32WBA54KG",
    "STM32WBA55CE", "STM32WBA55CG", "STM32WBA55HE", "STM32WBA55HG", "STM32WBA55UE", "STM32WBA55UG",
    "STM32WBA5MMG",
)

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RuntimeError(msg)

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git_blob_sha(path: Path) -> str:
    data=path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data,usedforsecurity=False).hexdigest()

def load_json(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value,dict),f"{path.name}: expected object")
    return value

def render() -> dict[str, Any]:
    req(sha256(SOURCE)==EXPECTED_SOURCE_SHA256,"candidate source digest drifted")
    req(git_blob_sha(REMEDIATION_GATE)==EXPECTED_REMEDIATION_GATE_BLOB,"remediation gate blob drifted")
    req(git_blob_sha(PRESTATE)==EXPECTED_PRODUCTION_BLOB,"Production prestate blob drifted")

    remediation=load_json(REMEDIATION_GATE)
    req(remediation.get("decision")=="remediation_success_exact_discovery_reopened","remediation decision drifted")
    req(remediation.get("evidence_accessibility_ready") is True,"remediation accessibility not ready")
    req(remediation.get("catalog_admission_ready") is False,"remediation prematurely admitted catalog")

    prod=load_json(PRESTATE)
    sources=prod.get("sources")
    req(isinstance(sources,list) and sum(int(x["row_count"]) for x in sources)==2604 and len(sources)==21,"Production boundary drifted")
    req(all(x.get("family")!="STM32WBA5X" for x in sources),"STM32WBA5X unexpectedly in Production")

    with SOURCE.open(newline="",encoding="utf-8") as handle:
        rows=[
            row for row in csv.DictReader(handle)
            if row.get("vendor")=="STMicroelectronics" and row.get("plasma_series")=="STM32WBA5X"
        ]
    req(len(rows)==34,"STM32WBA5X source row count drifted")
    req(Counter(row["identifier_kind"] for row in rows)==Counter({"ordering_pattern":17,"cmsis_device_name":17}),"source identifier mix drifted")

    found_excluded={(row["part_number"],row["identifier_kind"]) for row in rows if (row["part_number"],row["identifier_kind"]) in EXCLUDED}
    req(found_excluded==EXCLUDED,"expected WBA50KE research candidates missing")
    retained=[row for row in rows if (row["part_number"],row["identifier_kind"]) not in EXCLUDED]
    req(len(retained)==32,"reconciled retained row count drifted")
    req(Counter(row["identifier_kind"] for row in retained)==Counter({"ordering_pattern":16,"cmsis_device_name":16}),"reconciled identifier mix drifted")

    bases=tuple(sorted(base_from_ordering_pattern(row) for row in retained if row["identifier_kind"]=="ordering_pattern"))
    req(bases==EXPECTED_BASES,f"reconciled Base Device set drifted: {bases}")
    req(any(row["part_number"]=="STM32WBA50KGUx" for row in retained),"WBA50KG ordering pattern missing")
    req(any(row["part_number"]=="STM32WBA50KGUxT" for row in retained),"WBA50KG CMSIS route missing")

    return {
    "claims": {
        "catalog_admission_ready": False,
        "debug_attach_supported": False,
        "excluded_candidates_never_existed": False,
        "full_exact_icpn_discovery_completed": False,
        "hil_required_for_catalog_admission": False,
        "icpn_admission_authorized": False,
        "physical_validation_claimed": False,
        "production_write_authorized": False,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_programming_support_claimed": False,
        "security_mutation_authorized": False,
        "target_execution_authorized": False,
        "wireless_radio_operation_authorized": False,
        "wireless_security_operation_authorized": False
    },
    "decision": "current_commercial_scope_reconciled",
    "excluded_research_candidates": [
        {
            "identifier_kind": "ordering_pattern",
            "part_number": "STM32WBA50KEUx",
            "reason": "not_supported_by_current_official_stm32wba50kg_ordering_information"
        },
        {
            "identifier_kind": "cmsis_device_name",
            "part_number": "STM32WBA50KEUxT",
            "reason": "not_supported_by_current_official_stm32wba50kg_ordering_information"
        }
    ],
    "family": "STM32WBA5X",
    "manufacturer": "STMicroelectronics",
    "next_gate": "stm32wba5x-bounded-exact-icpn-discovery-gate",
    "official_manufacturer_evidence": {
        "constrained_fields": {
            "device_subfamily": "A50",
            "flash_memory_size": "G",
            "optional_packing": "TR",
            "package": "U",
            "pin_count": "K",
            "temperature_range": "6"
        },
        "datasheet_url": "https://www.st.com/resource/en/datasheet/stm32wba50kg.pdf",
        "document": "DS14688",
        "observed_active_exact_icpns": [
            "STM32WBA50KGU6",
            "STM32WBA50KGU6TR"
        ],
        "ordering_example": "STM32 WBA50 K G U 6 TR",
        "ordering_information_pdf_page": 108,
        "product": "STM32WBA50KG",
        "product_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32wba50kg.html",
        "revision": "Rev 2"
    },
    "production_boundary": {
        "exact_icpns": 2604,
        "families": 21,
        "frozen_manifest_git_blob_sha": EXPECTED_PRODUCTION_BLOB,
        "wba5x_published": False
    },
    "reconciled_surface": {
        "base_device_count": 16,
        "base_devices": [
            "STM32WBA50KG",
            "STM32WBA52CE",
            "STM32WBA52CG",
            "STM32WBA52KE",
            "STM32WBA52KG",
            "STM32WBA54CE",
            "STM32WBA54CG",
            "STM32WBA54KE",
            "STM32WBA54KG",
            "STM32WBA55CE",
            "STM32WBA55CG",
            "STM32WBA55HE",
            "STM32WBA55HG",
            "STM32WBA55UE",
            "STM32WBA55UG",
            "STM32WBA5MMG"
        ],
        "cmsis_device_name_rows": 16,
        "ordering_pattern_rows": 16,
        "retained_rows": 32
    },
    "reconciliation_id": "stm32wba5x-current-commercial-scope-reconciliation-v1",
    "schema_version": 1,
    "scope": "research_only",
    "source_surface": {
        "cmsis_device_name_rows": 17,
        "ordering_pattern_rows": 17,
        "source_rows": 34,
        "source_sha256": EXPECTED_SOURCE_SHA256
    },
    "upstream": {
        "remediation_decision": "remediation_success_exact_discovery_reopened",
        "remediation_gate_git_blob_sha": EXPECTED_REMEDIATION_GATE_BLOB,
        "remediation_gate_id": "stm32wba5x-bounded-official-st-evidence-remediation-v1"
    }
}

def main() -> int:
    print(json.dumps(render(),indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
