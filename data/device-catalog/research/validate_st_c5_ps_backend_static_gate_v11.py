#!/usr/bin/env python3
"""Fail-closed STM32C5 PS/OpenOCD source gate v1.1.

No device I/O, backend enablement, OpenOCD execution, remote loader download,
vendor-binary redistribution or Production catalog write. An optional
manufacturer source byte replay proves provenance and can emit a *host-only*
Tcl semantics fixture, never a deployable .cfg.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import validate_st_c5_dfp_loader_crosswalk_v09 as v09
import preflight_st_c5_local_loader_candidate_v10 as v10

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
REPORT = HERE / "st-c5-ps-backend-static-gate-v1.1.json"

EXPECTED_FORK_CFG = "03bce02b166b669ca0d7515656bca68ff4db8b84"
EXPECTED_FORK_DRIVER = "99d51e696cd5cfa64948e479102472fb126afafa"
EXPECTED_FORK_REGISTRY = "219dfa9a4a87a96d43b5e7496cbab47092f77b7a"
EXPECTED_PLASMA_EXECUTOR = "062fefa79926535e8c89dddcd55bee95b65b22c3"
EXPECTED_PLASMA_INTERFACE = "3d12cc658b6d71adf8b8dfc14ea07ac4a0c5cab7"
EXPECTED_PLASMA_ROUTER = "6ce78bb4421448327a844171d97ffe7995ca8fbd"
EXPECTED_FALLBACK_BYTES = {
    "0x44E": 0x200 * 1024,
    "0x44F": 0x100 * 1024,
    "0x45A": 0x400 * 1024,
}
EXPECTED_ALGORITHM_RAM_BYTES = {
    "Flash/STM32C5[34]x.xldr": 0x10000,
    "Flash/STM32C5[56]x.xldr": 0x20000,
    "Flash/STM32C5[9A]x.xldr": 0x40000,
}
# Deliberately keep this fixed and empty: source-only research does not stage
# or configure any vendor loader in a production target script.
REPLACEMENTS = (
    ("set die_max_flash_size {", "array set die_max_flash_size {"),
    ("set dev_id_loader {\n}", "array set dev_id_loader {\n}"),
)


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def verify_source_bytes(path: Path, expected_blob: str, description: str) -> str:
    raw = path.read_bytes()
    require(v09.git_blob(raw) == expected_blob, f"{description}: Git blob/source provenance mismatch")
    return raw.decode("utf-8")


def patch_in_memory(cfg_bytes: bytes) -> str:
    """Accept only the exact pinned vendor cfg; change precisely two Tcl keywords.

    Return research candidate text in memory for host-only parsing. The loader
    table stays EMPTY. This is not a runtime OpenOCD target configuration.
    """
    require(v09.git_blob(cfg_bytes) == EXPECTED_FORK_CFG,
            "non-pinned or modified upstream OpenOCD target configuration")
    original = cfg_bytes.decode("utf-8")
    result = original
    for scalar, array in REPLACEMENTS:
        require(original.count(scalar) == 1, f"upstream Tcl anchor missing/ambiguous: {scalar}")
        result = result.replace(scalar, array, 1)
    require(result != original and
            result.count("array set die_max_flash_size {") == 1 and
            result.count("array set dev_id_loader {\n}") == 1,
            "source-only proposal did not yield exactly two Tcl array repairs")
    require("array set dev_id_loader {\n}\n" in result and
            "stldr set_loader $i $dev_id_loader($dev_id)" in result,
            "source-only loader lookup must remain unpopulated and gated")
    require(original.count("0x44E 0x200") == 1 and
            original.count("0x44F 0x100") == 1 and
            original.count("0x45A 0x400") == 1,
            "unreviewed manufacturer fallback flash geometry")
    return result


def host_only_tcl_semantics(candidate: str) -> str:
    """Extract ONLY the flash-size proc and empty loader array for tclsh.

    The full vendor target cfg is never sourced; it contains target/adapter
    declarations and must not be run as part of a source-research test.
    """
    start = candidate.index("proc stm32c5x_get_size { dev_id } {")
    end = candidate.index("# Set DEV_ID loader_file", start)
    proc = candidate[start:end].strip()
    require(proc.count("array set die_max_flash_size {") == 1 and
            proc.count("0x08FFF80C") == 1 and
            candidate.count("array set dev_id_loader {\n}") == 1,
            "unreviewed corrected Tcl procedure")
    return (
        '# Research-only host Tcl test. NO target/adapter/flash operation.\n'
        'proc mrh {address} {\n'
        '  if {$address ne "0x08FFF80C"} {error "unexpected fake read address"}\n'
        '  return $::fake_flash_kib\n'
        '}\n'
        'proc echo args {}\n'
        'proc shutdown {} {error "BLOCKED_UNKNOWN_DEVICE_ID"}\n\n'
        + proc + '\n\n'
        + 'array set dev_id_loader {\n}\n'
        + r'''
if {![array exists dev_id_loader] || [array size dev_id_loader] != 0} {
  error "candidate must have an EMPTY loader table"
}
foreach {id max_bytes} {
  0x44E 524288
  0x44F 262144
  0x45A 1048576
} {
  if {[info exists dev_id_loader($id)]} {
    error "empty candidate must NOT have an executable loader mapping"
  }
  foreach bad_register {0 0xFFFF} {
    set ::fake_flash_kib $bad_register
    if {[stm32c5x_get_size $id] != $max_bytes} {
      error "array-set flash-size fallback incorrect for $id"
    }
  }
  set ::fake_flash_kib 128
  if {[stm32c5x_get_size $id] != 131072} {
    error "valid FLASH_SIZE register was incorrectly overridden for $id"
  }
}
set ::fake_flash_kib 0
if {[catch {stm32c5x_get_size 0xAAA} msg] != 1 ||
    $msg ne "BLOCKED_UNKNOWN_DEVICE_ID"} {
  error "unknown die must be blocked on invalid size register"
}
puts "ST_C5_PINNED_CFG_TCL_ARRAY_FIX_V11_HOST_ONLY_PASS"
'''
    )


def validate_source_repo_boundary() -> dict:
    info = json.loads(REPORT.read_text(encoding="utf-8"))
    require(info.get("schema_version") == 1 and
            info.get("audit_id") == "st-c5-ps-backend-static-gate-v1.1" and
            info.get("research_only") is True, "research evidence schema/scope drift")
    fork = info["manufacturer_openocd_fork"]
    require(fork["pinned_commit"] == "c8d973bdad9a6fddb51459eda109b3b95d23b57a" and
            fork["target_cfg_blob_sha"] == EXPECTED_FORK_CFG and
            fork["stldr_driver_blob_sha"] == EXPECTED_FORK_DRIVER and
            fork["registry_blob_sha"] == EXPECTED_FORK_REGISTRY and
            fork["source_tcl_defect"]["loader_table_remains_empty_in_research_fix"] is True and
            fork["source_tcl_defect"]["candidate_is_not_production_target_cfg"] is True and
            fork["target_default_workarea_bytes"] == 32768 and
            fork["fallback_die_flash_bytes"] == EXPECTED_FALLBACK_BYTES,
            "unreviewed vendor fork target/driver/flash fallback")
    defect = fork["source_tcl_defect"]
    require(defect["replacements_must_match_each_exactly_once"] is True and
            tuple((defect[a], defect[b]) for a, b in (
                ("flash_fallback_original", "flash_fallback_candidate"),
                ("loader_table_original", "loader_table_candidate"),
            )) == REPLACEMENTS, "unsafe or non-minimal candidate Tcl patch")
    dfp = info["dfp"]
    require(dfp["commit"] == "a5f65bc64535cfa723e9d25f58d7ce23d0937aed" and
            dfp["pdsc_blob_sha"] == v09.EXPECTED_DFP_BLOB and
            dfp["loader_family_alg_ram_bytes"] == EXPECTED_ALGORITHM_RAM_BYTES and
            dfp["ram_size_field_is_pack_declared_algorithm_footprint_not_proven_runtime_requirement"] is True and
            dfp["workarea_needs_independent_backend_and_hardware_confirmation"] is True,
            "incorrect DFP declared RAM or overclaimed device memory gate")
    base = v09.validate()
    candidates = v10.load_and_reconcile()
    require((base["observed_c5_exact_active_cohort"],
             base["official_DFP_exact_variant_observations"],
             base["parent_only_not_exact"], base["production_unchanged"]) ==
            (172, 139, 33, 2683) and len(candidates) == 172,
            "frozen commercial and catalog source replay unexpectedly changed")
    with v09.CROSSWALK.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rams: dict[str, set[int]] = {}
    for row in rows:
        name = row["candidate_xldr_path"]
        rams.setdefault(name, set()).add(int(row["dfp_loader_ram_bytes"]))
        require(row["plasma_route_ready"] == "false", "source-only row became executable")
    require({name: next(iter(values)) for name, values in rams.items()} ==
            EXPECTED_ALGORITHM_RAM_BYTES and
            all(len(v) == 1 for v in rams.values()),
            "official RAM algorithm group no longer uniquely matches pinned DFP")
    ps = info["plasma_source"]
    sources = (
        ("openocd_executor_path", "openocd_executor_blob_sha", EXPECTED_PLASMA_EXECUTOR),
        ("openocd_interface_path", "openocd_interface_blob_sha", EXPECTED_PLASMA_INTERFACE),
        ("site_router_path", "site_router_blob_sha", EXPECTED_PLASMA_ROUTER),
    )
    text = {}
    for field_path, field_sha, expected_sha in sources:
        require(ps[field_sha] == expected_sha, "Plasma PS source-lock digest drift")
        path = ROOT / ps[field_path]
        require(path.is_file(), "Plasma selected PS source file absent")
        text[field_path] = verify_source_bytes(path, expected_sha, field_path)
    executor = text["openocd_executor_path"]
    interface = text["openocd_interface_path"]
    router = text["site_router_path"]
    require("process_launcher: ProcessLauncher | None = None" in executor and
            "self._process_launcher = process_launcher" in executor and
            "if self._process_launcher is None:" in executor and
            "OpenOCD compiled-plan executor has no software-validation process launcher" in executor,
            "real execution might be reachable without explicit launcher")
    require("def _raise_hardware_runtime_not_ready()" in interface and
            interface.count("self._raise_hardware_runtime_not_ready()") >= 4 and
            "OpenOCD hardware runtime is not enabled" in interface,
            "OpenOCD direct hardware path may be newly enabled")
    require('"backend_implementation_state": "plan_compiled_not_executable"' in router and
            '"hardware_runtime_ready": False' in router and
            'if route.get("hardware_runtime_ready") is not True:' in router,
            "PS runtime router admission contract has changed")
    require(ps["executor_no_default_process_launcher"] is True and
            ps["interface_direct_erase_program_verify_read_are_blocked"] is True and
            ps["backend_implementation_state"] == "plan_compiled_not_executable" and
            ps["hardware_runtime_ready"] is False and
            ps["real_ps_openocd_version_sha256_and_stldr_build_not_observed"] is True and
            ps["real_z2_hil_did_not_run"] is True,
            "source-only findings were promoted to runtime or HIL readiness")
    crosswalk = info["crosswalk"]
    require((crosswalk["observed_public_estore_exact_active"],
             crosswalk["exact_dfp_variant_observed"],
             crosswalk["base_device_only"],
             crosswalk["fixed_production_st_icpns"],
             crosswalk["fixed_production_st_families"]) ==
            (172, 139, 33, 2683, 23) and
            crosswalk["all_172_loader_routes_remain_closed"] is True,
            "Production/C5 source cohort or route drift")
    gates = info["gates"]
    require(gates["manufacturer_tcl_scalar_array_fix_proposal_only"] is True and
            gates["isolated_tcl_host_fallback_probe_required"] is True and
            gates["three_local_xldr_source_sha256_pinned"] is True and
            all(gates[k] is False for k in (
                "official_vendor_binary_license_approved",
                "stldr_compiled_in_plasma_chosen_binary_verified",
                "plasma_target_cfg_deployed_and_loader_map_populated",
                "pinned_loader_ram_compatibility_hil_verified",
                "real_dev_id_flash_geometry_readback_verified",
                "source_only_candidate_executable",
                "production_catalog_update_authorized",
                "production_programming_authorized",
            )), "unsupported runtime, legal, HIL or Production claim")
    return {
        "status": "RESEARCH_PS_SOURCE_BOUNDARY_PASS",
        "c5_commercial_active_exact": 172,
        "exact_dfp_variant": 139,
        "missing_exact_dfp_variant": 33,
        "source_pinned_plasma_executor_no_launcher": True,
        "source_pinned_plasma_direct_openocd_disabled": True,
        "st_fork_target_default_workarea_bytes": 32768,
        "dfp_declared_algorithm_ram_bytes": EXPECTED_ALGORITHM_RAM_BYTES,
        "real_ps_binary_installed_and_qualified": False,
        "production_icpns_unchanged": 2683,
        "hardware_runtime_ready": False,
    }


def validate_vendor_inputs(cfg: Path, driver: Path, registry: Path,
                           loader_dir: Path | None = None,
                           host_tcl_output: Path | None = None) -> dict:
    source = cfg.read_bytes()
    candidate = patch_in_memory(source)
    driver_text = verify_source_bytes(driver, EXPECTED_FORK_DRIVER, "ST stldr driver")
    registry_text = verify_source_bytes(registry, EXPECTED_FORK_REGISTRY,
                                        "ST flash-driver registry")
    require(all(re.search(r'\{\s*FUNC_ID_' + name +
                          r',\s*"' + sym + r'",\s*STLDR_FUNC_MANDATORY\s*\}', driver_text)
                for name, sym in (("INIT", "Init"), ("SECTOR_ERASE", "SectorErase"),
                                  ("WRITE", "Write"))) and
            'strcmp("StorageInfo", symbol_name)' in driver_text and
            "SHT_SYMTAB" in driver_text,
            "ST STLDR expects unobserved mandatory ELF symbols or storage descriptor")
    require("&stldr_flash," in registry_text, "stldr registry source is absent at pinned fork")
    if loader_dir is not None:
        # This checks manufacturer source bytes and basic ELF32 provenance,
        # not machine-code operation, legal redistribution or target RAM fit.
        v09.validate(loader_dir=loader_dir)
    if host_tcl_output is not None:
        require(host_tcl_output.suffix == ".tcl" and
                host_tcl_output.parent.is_dir() and
                not host_tcl_output.exists() and
                not host_tcl_output.is_symlink(),
                "host-only Tcl fixture output must be a fresh .tcl path")
        host_tcl_output.write_text(host_only_tcl_semantics(candidate),
                                   encoding="utf-8")
    return {
        "vendor_source_replay": "PASS_ONLY_PINNED_VENDOR_SOURCE",
        "original_cfg_git_blob_sha": EXPECTED_FORK_CFG,
        "scalar_to_array_keyword_fixes_in_memory": 2,
        "no_real_loader_mapped": True,
        "stldr_driver_and_registry_source_replayed": True,
        "three_xldr_source_bytes_replayed": loader_dir is not None,
        "host_only_tcl_fixture_created": host_tcl_output is not None,
        "plasma_runtime_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fork-cfg", type=Path)
    parser.add_argument("--stldr-driver", type=Path)
    parser.add_argument("--driver-registry", type=Path)
    parser.add_argument("--loader-dir", type=Path)
    parser.add_argument("--host-tcl-output", type=Path)
    args = parser.parse_args()
    base = validate_source_repo_boundary()
    given = (args.fork_cfg, args.stldr_driver, args.driver_registry)
    require(all(x is not None for x in given) or not any(x is not None for x in given),
            "all three pinned vendor sources are required together")
    require(all(x is not None for x in given) or
            (args.loader_dir is None and args.host_tcl_output is None),
            "loader/host test input requires full pinned ST source set")
    if all(x is not None for x in given):
        base["source_replay"] = validate_vendor_inputs(
            args.fork_cfg, args.stldr_driver, args.driver_registry,
            args.loader_dir, args.host_tcl_output)
    print(json.dumps(base, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
