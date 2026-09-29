#!/usr/bin/env python3
"""Fail-closed research gate for C5 route candidate, NOT a programming qualification."""
from __future__ import annotations
import json
from pathlib import Path
import validate_st_c5_estore_evidence_lock_v07 as evidence

HERE = Path(__file__).resolve().parent
REPORT = HERE / "st-c5-backend-source-boundary-v0.8.json"
CONFIG_BLOB = "03bce02b166b669ca0d7515656bca68ff4db8b84"
DRIVER_BLOB = "99d51e696cd5cfa64948e479102472fb126afafa"
REGISTRY_BLOB = "219dfa9a4a87a96d43b5e7496cbab47092f77b7a"
FORK_COMMIT = "c8d973bdad9a6fddb51459eda109b3b95d23b57a"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def validate(report=None):
    info = json.loads(REPORT.read_text(encoding="utf-8")) if report is None else report
    prior = evidence.validate()
    require(info["audit_id"] == "st-c5-backend-source-boundary-v0.8" and
            info["reference_date_utc"] == "2026-09-29", "route research record drift")
    source = info["observed_research_input"]
    require(source["c5_official_estore_category_exact_active_candidates"] == 172 and
            source["exact_set_sha256"] == evidence.EXPECTED_SET_SHA and
            source["only_bounded_category_evidence"] is True and
            prior["combined_bounded_unpublished_minimum"] == 191, "source exact set drift")
    fork = info["st_openocd_fork"]
    require(fork["repository"] == "STMicroelectronics/OpenOCD" and
            fork["pinned_commit"] == FORK_COMMIT and
            fork["branch_reference"] == "openocd-cubeide-r7", "upstream fork lock changed")
    config = fork["target_config"]
    require(config["path"] == "tcl/target/stm32c5x.cfg" and
            config["git_blob_sha"] == CONFIG_BLOB and
            config["flash_bank_driver"] == "stldr" and
            config["flash_bank_base"] == "0x08000000" and
            config["loader_table_has_pinned_paths"] is False and
            config["on_missing_device_loader"].startswith(
                "Error : No STLDR loader file found for device ID"),
            "unqualified backend candidate declared complete or source drifted")
    driver = fork["linked_flash_driver"]
    require(driver["path"] == "src/flash/nor/stldr_driver.c" and
            driver["git_blob_sha"] == DRIVER_BLOB and
            driver["registry_git_blob_sha"] == REGISTRY_BLOB and
            driver["source_presence_is_not_algorithm_or_loader_qualification"] is True,
            "stldr driver lock/admission boundary drift")
    require(fork["official_upstream_submission"]["upstream_main_target_file_verified_available"] is False,
            "upstream official integration claim needs new explicit evidence")
    alternate = info["alternate_tool_boundary"]
    require(alternate["official_st_c5_support_release"] == "2.22.0" and
            alternate["production_use_approved_by_tool_license"] is False and
            alternate["may_be_treated_as_plasma_production_backend"] is False,
            "unlicensed production dependency enabled")
    gate = info["gate_state"]
    require(gate["frozen_production_st_icpns"] == 2683 and
            gate["frozen_production_st_families"] == 23 and
            all(gate[key] is False for key in (
                "complete_per_device_id_loader_mapping_reviewed",
                "actual_plasma_backend_stldr_compiled_verified",
                "per_mpn_metadata_route_qualified",
                "runtime_flash_erase_verify_qualified",
                "security_mutation_authorized",
                "catalog_admission_ready",
                "production_write_authorized",
                "hardware_hil_qualified",
            )), "backend still has missing STLDR loader and no Production authority")
    return {
        "result": "ST_C5_BACKEND_ROUTE_BLOCKED_AS_SOURCE_PINNED",
        "observed_exact_C5_codes": 172,
        "target_script": "STM32C5x: pinned ST fork cfg candidate only",
        "required_next": "DEV_ID-to-loader mapping; legal loader/version; backend compile; metadata/route review",
        "production_ST_unchanged": 2683,
    }


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
