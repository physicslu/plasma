#!/usr/bin/env python3
"""NXP ADR-0002 Phase 2 — KL25 12 exact-ICPN provider-lock blocker audit.

Cross-check the *current* NXP Phase1/Phase2 canonical source and current pinned
OpenOCD provider with the separately frozen, exact-ICPN KL25 Software Executor
prototype. Nothing here admits Programming, Production, Job/Batch or HIL.
Historical KL25 artifacts retain their own OpenOCD backend source revision.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

import nxp_adr0002_phase1_phase2_canonical_v1 as canonical

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = Path("data/device-catalog/research")
BENCH = Path("data/ic-support/benchmarks/nxp-kl25")
FILES = {
    "kl25_official": (RESEARCH/"nxp-kl25-commercial-icpn.csv",
                      "53087e9082445e7948f88e688ecd890b0454d788"),
    "executor_backend": (BENCH/"backend-implementation-lock.json",
                         "9b87a1a53df7ce9d361927608b72661327ef6310"),
    "executor_contract": (BENCH/"vendor-neutral-admission-adapter-contract-v1.json",
                          "aa8424d05e5ac913dffa5f774befd284a0aa0776"),
    "runtime": (Path("release/openocd.json"),
                "08c884b1bf6f5999c6d34c090992a8b59d85971d"),
    "upstream_delta": (RESEARCH/"nxp-kl25-openocd-provider-delta-v1.json",
                       "b79ecd5f1f82a125bdedc3218d439db88bc30aa2"),
}
EXACT_PROTOTYPE = "MKL25Z128VLK4"
LEGACY_COMMIT = "56b8d93fbe61a78dc903d770820d6d896b6d8134"
APPROVED_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
EXPECTED_ICPN_SUFFIXES = ("VFM4", "VFT4", "VLH4", "VLK4")
FLASH_KIB = (32, 64, 128)
ALLOWED_PHASE2 = {"CANDIDATE"}
OPS_ADMITTED_SOFTWARE_ONLY = ("READ","VERIFY","PROGRAM","ERASE_SECTOR")
BLOCKED_OPS = (
    "ERASE_ALL_BLOCKS","MDM_MASS_ERASE","BACKDOOR_KEY",
    "SECURITY_STATE_MODIFICATION","FLASH_CONFIGURATION_FIELD_PROGRAM",
    "FLASH_CONFIGURATION_FIELD_SECTOR_ERASE","UNPROTECT",
    "IMPLICIT_DESTRUCTIVE_SECURITY_WORKFLOW",
)

def require(ok: bool, why: str) -> None:
    if not ok:
        raise ValueError("NXP KL25 Phase2 ADR-0002: " + why)

def gitblob(raw: bytes) -> str:
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def checked_bytes(key: str, *, root: Path=ROOT) -> bytes:
    file, sha = FILES[key]
    raw=(root/file).read_bytes()
    require(gitblob(raw)==sha,"source evidence Git blob mismatch: "+str(file))
    return raw

def materials(*, root: Path=ROOT) -> list[dict[str,str]]:
    rows=list(csv.DictReader(io.StringIO(checked_bytes("kl25_official",root=root).decode("utf-8"))))
    require(len(rows)==12 and len({r["icpn"] for r in rows})==12,
            "exact 12 commercial ICPNs missing/duplicated")
    for row in rows:
        icpn=row["icpn"]
        require(row["manufacturer"]=="NXP" and row["family"]=="KL25"
                and row["openocd_target_config"]=="tcl/target/kl25.cfg"
                and row["mapping_status"]=="deterministic_ordering_pattern"
                and row["source_authority"]=="https://www.nxp.com/docs/en/data-sheet/KL25P80M48SF0.pdf",
                "exact manufacturer identity/CFG source mismatch: "+icpn)
        require(row["pin_count"] in ("32","48","64","80")
                and row["package"] in ("HVQFN","LQFP"),
                "manufacturer package evidence missing: "+icpn)
    expected={
        "MKL25Z"+str(size)+suffix
        for size in FLASH_KIB for suffix in EXPECTED_ICPN_SUFFIXES
    }
    require({r["icpn"] for r in rows}==expected,
            "source-locked KL25 exact 32/64/128KiB SKU families drifted")
    for row in rows:
        icpn=row["icpn"]
        size=int(row["flash_size"].split(" ")[0])
        suffix=next(s for s in EXPECTED_ICPN_SUFFIXES if icpn.endswith(s))
        pins={"VFM4":"32","VFT4":"48","VLH4":"64","VLK4":"80"}[suffix]
        expected_pkg="HVQFN" if suffix in ("VFM4","VFT4") else "LQFP"
        require(size in FLASH_KIB
                and icpn.startswith("MKL25Z"+str(size))
                and row["base_device"]=="MKL25Z"+str(size)
                and row["pin_count"]==pins and row["package"]==expected_pkg,
                "exact package/Flash geometry mismatch: "+icpn)
    return rows

def review_provider_boundary(backend: dict, adapter: dict, release: dict) -> dict:
    require(backend["artifact_type"]=="kl25_openocd_backend_implementation_lock"
            and backend["commit"]==LEGACY_COMMIT
            and adapter["target"]=={"vendor_id":"NXP","icpn":EXACT_PROTOTYPE}
            and adapter["legacy_release"]["openocd_commit"]==LEGACY_COMMIT
            and adapter["legacy_release"]["backend_lock_digest"]==backend["lock_digest"],
            "frozen exact-prototype Backend Lock/Review target does not match")
    require(adapter["gate58"]["qualification_status"]=="REJECTED_REVIEW"
            and adapter["expected_counts"]["admitted_operations"]==4
            and adapter["expected_counts"]["blocked_operations"]==8,
            "Gate 5.8 historical review must not be silently promoted")
    ops=adapter["operation_mapping"]
    require(all(ops[name]==("ERASE" if name=="ERASE_SECTOR" else name)
                for name in OPS_ADMITTED_SOFTWARE_ONLY)
            and all(name in ops for name in BLOCKED_OPS),
            "reviewed operation scope was broadened or corrupted")
    constraints=backend["admitted_constraints"]
    require(constraints["target_config"]=="target/kl25.cfg"
            and constraints["program_start_alignment_bytes"]==4
            and constraints["program_implicit_erase"] is False
            and constraints["erase_requires_exact_sector_range"] is True
            and constraints["flash_configuration_field_start"]=="0x00000400"
            and constraints["flash_configuration_field_size_bytes"]==16
            and constraints["flash_configuration_field_sector_start"]=="0x00000400"
            and constraints["flash_configuration_field_sector_size_bytes"]==1024,
            "FCF/flash-erase/program safety constraints not preserved")
    trust=backend["trust_boundary"]
    require(trust["software_executor_evidence"] is True
            and trust["hardware_behavior_validated"] is False
            and trust["production_admission"] is False
            and trust["destructive_security_operation_admission"] is False,
            "legacy software-only versus hardware/Production trust boundary changed")
    require(release["engine"]=="openocd"
            and release["version"]=="0.12.0"
            and release["source_commit"]==APPROVED_COMMIT
            and release["hardware_runtime_ready"] is False,
            "approved PLASMA OpenOCD Release pin/availability changed")
    mismatch = backend["commit"] != release["source_commit"]
    # A future equality cannot, by itself, approve re-use; the source files
    # and change semantics must be re-reviewed under a new provider lock.
    return {
        "benchmark_backend_commit": backend["commit"],
        "approved_provider_commit": release["source_commit"],
        "backend_commit_mismatch": mismatch,
        "software_executor_prototype": EXACT_PROTOTYPE,
        "prototype_qualified_under_current_provider": False,
        "requires_provider_requalification": True,
        "requires_exact_silicon_and_geometry_review": True,
        "unqualified_reason": (
            "PINNED_BACKEND_COMMIT_MISMATCH_AND_NO_CURRENT_PROVIDER_REVIEW"
            if mismatch else "NEW_PIN_MATCH_ALONE_DOES_NOT_GRANT_PROGRAMMING_SUPPORT"
        ),
        "reviewed_software_only_operation_names": list(OPS_ADMITTED_SOFTWARE_ONLY),
        "prohibited_security_and_destructive_operations": list(BLOCKED_OPS),
        "real_ic_execution_evidenced_here": False,
    }


def review_upstream_delta(delta: dict, boundary: dict) -> dict:
    require(delta["schema_version"]==1
            and delta["original_source_repository"]=="openocd-org/openocd"
            and delta["prior_software_prototype_commit"]==LEGACY_COMMIT
            and delta["current_plasma_openocd_commit"]==APPROVED_COMMIT,
            "upstream source-provenance provider commit mismatch")
    expected={
        "tcl/target/kl25.cfg":
            ("916edf6853c3f26a004d2ca5a2f0e08f43a24093",
             "916edf6853c3f26a004d2ca5a2f0e08f43a24093",True),
        "tcl/target/klx.cfg":
            ("b4014ba5b6de75e236e0a6b8780cf6448c991c2",
             "cd236b3395e42310f1475f3b64580758a7f3b9ea",False),
        "src/flash/nor/kinetis.c":
            ("266b447c04376b529c44ac11cd9fd6acc31e0e8c",
             "7137b4aa078719af31122f8276494f006589e8ab",False),
    }
    reviewed=delta["per_file"]
    require(len(reviewed)==3 and len({r["path"] for r in reviewed})==3
            and {r["path"] for r in reviewed}==set(expected),
            "upstream source include/driver file set changed")
    for row in reviewed:
        old,current,same=expected[row["path"]]
        require((row["prototype_git_blob"],row["current_git_blob"],
                 row["identical_bytes"])==(old,current,same),
                "reviewed OpenOCD source Git blob evidence mismatch: "+row["path"])
    c=delta["conclusions"]
    require(c["exact_cfg_file_unchanged"] is True
            and c["tcl_dependency_changed"] is True
            and c["flash_driver_source_changed"] is True
            and c["can_transfer_software_profile_admission"] is False
            and c["source_semantic_equivalence_proven"] is False
            and c["current_provider_exact_operations_qualified"] is False
            and delta["no_execution_no_production_no_hil"] is True
            and boundary["prototype_qualified_under_current_provider"] is False,
            "same CFG cannot bypass changed Tcl dependency/Flash driver review")
    return {"source_graph_reviewed":3,
            "byte_identical_files":1,
            "changed_files":2,
            "changed_paths":["tcl/target/klx.cfg","src/flash/nor/kinetis.c"],
            "source_semantics_requalified":False,
            "current_provider_software_supported":False}

def build(*, root: Path=ROOT):
    # The canonical validator is the *only* Phase 1/Phase 2 state authority.
    phase2 = canonical.build(root=root)
    current = {r["icpn"]:r for r in phase2}
    release=json.loads(checked_bytes("runtime",root=root))
    backend=json.loads(checked_bytes("executor_backend",root=root))
    adapter=json.loads(checked_bytes("executor_contract",root=root))
    boundary=review_provider_boundary(backend,adapter,release)
    upstream=review_upstream_delta(
        json.loads(checked_bytes("upstream_delta",root=root)),boundary)
    rows=[]
    for r in materials(root=root):
        exact=r["icpn"]
        require(exact in current and current[exact]["phase1"]=="IDENTIFIED"
                and current[exact]["phase2"] in ALLOWED_PHASE2,
                "KL25 source identity may not cross canonical Phase1/2 state: "+exact)
        c=current[exact]
        require(c["target_cfg"]=="tcl/target/kl25.cfg" and c["driver"]=="kinetis"
                and c["provider_commit"]==APPROVED_COMMIT,
                "source-only KL25 target/driver/provider authority drift: "+exact)
        prototype=(exact==EXACT_PROTOTYPE)
        # Do NOT spread the single 128KiB/80pin software prototype to the
        # other 11 parts. Identical OpenOCD Tcl and FTFA family != reviewed
        # exact silicon/flash security and operation applicability.
        rows.append({
            "manufacturer":"NXP", "icpn":exact,
            "phase1":"IDENTIFIED", "phase2":"CANDIDATE",
            "phase1_base_device":r["base_device"],
            "flash_kib_manufacturer":int(r["flash_size"].split(" ")[0]),
            "package":r["package"], "pin_count":int(r["pin_count"]),
            "target_cfg_source_only":c["target_cfg"],
            "flash_driver_source_only":c["driver"],
            "existing_exact_software_prototype":prototype,
            "prototype_benchmark_commit":LEGACY_COMMIT if prototype else None,
            "approved_openocd_source_commit":APPROVED_COMMIT,
            "source_only_programming_profile_reusable":False,
            "current_provider_operations_qualified":False,
            "phase2_supported":False,
            "software_prototype_scope_only":(
                list(OPS_ADMITTED_SOFTWARE_ONLY) if prototype else []
            ),
            "phase3_hil":"NOT_AUDITED",
            "next_required_evidence":(
                ["CURRENT_PROVIDER_CODE_DIFF_AND_FCF_SECURITY_REVIEW",
                 "PINNED_RUNTIME_MATCHING_EXACT_SILICON_REVISION_AND_FLASH_GEOMETRY",
                 "CURRENT_PROVIDER_FOUR_OPERATIONS_PROFILE_REVIEW"]
                if prototype else
                ["EXACT_VARIANT_PROFILE_NOT_REVIEWED",
                 "CURRENT_PROVIDER_SILICON_ID_REVISION_AND_FLASH_GEOMETRY",
                 "CURRENT_PROVIDER_PROGRAM_ERASE_READ_VERIFY_AND_SECURITY"]
            ),
        })
    validate(rows,boundary)
    return {"rows":sorted(rows,key=lambda x:x["icpn"]),
            "provider_boundary":boundary,
            "upstream_source_diff":upstream,
            "phase1_identified_global_nxp":297,
            "phase2_candidate_global_nxp":28,
            "phase2_supported_newly_qualified_by_this_review":0,
            "phase3_newly_qualified":0,
            "production_or_ic_selector_mutated":False}

def validate(rows: list[dict],boundary: dict) -> None:
    require(len(rows)==12 and len({r["icpn"] for r in rows})==12,
            "KL25 exact commercial coverage must be 12")
    require(sum(r["existing_exact_software_prototype"] for r in rows)==1
            and [r["icpn"] for r in rows if r["existing_exact_software_prototype"]]
                 ==[EXACT_PROTOTYPE],
            "only one exact software-prototype IC is reviewed")
    require(boundary["requires_provider_requalification"] is True
            and boundary["prototype_qualified_under_current_provider"] is False,
            "old backend software prototype cannot qualify today's Provider")
    require(all(r["phase1"]=="IDENTIFIED"
                and r["phase2"]=="CANDIDATE"
                and r["phase2_supported"] is False
                and r["current_provider_operations_qualified"] is False
                and r["source_only_programming_profile_reusable"] is False
                and r["phase3_hil"]=="NOT_AUDITED"
                and bool(r["next_required_evidence"]) for r in rows),
            "fabricated current-provider software support/Phase3 or missing blockers")
    require(all(not r["software_prototype_scope_only"] for r in rows
                if r["icpn"] != EXACT_PROTOTYPE),
            "cannot inherit reviewed 128KiB/80pin prototype operations to 11 variants")
    require(Counter(r["flash_kib_manufacturer"] for r in rows)=={32:4,64:4,128:4},
            "Flash sizes must remain exact manufacturer variants")

if __name__=="__main__":
    result=build()
    print("NXP_KL25_PHASE2_BACKEND_LOCK_PASS exact=12 prototype_exact=1 "
          "legacy_commit_mismatch=1 S2_CANDIDATE=12 S2_SUPPORTED_NEW=0 "
          "OTHER_NXP_CANDIDATES=16 HIL=NOT_AUDITED")
    print(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True))
