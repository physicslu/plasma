#!/usr/bin/env python3
"""ADR-0002 Microchip Core/Transport/Target/Flash-driver Research gate.

P0/P1/P2 are research PRIORITIES, not qualified ICPN support decisions.
This tool never imports or changes Production, runtime, or user-visible Catalog.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from microchip_dfp_index_inventory_v1 import archived_inventory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE_LOCK = HERE / "microchip-openocd-first-source-lock-v1.json"
OPENOCD_RELEASE = ROOT / "release/openocd.json"
OBSERVATION = HERE / "microchip-openocd-core-first-observation-v1.json"
PINNED_COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
PINNED_DFP_SOURCE = "9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0"
ARCHIVAL_LANES = frozenset(("excluded_mpu_candidate", "unclassified_or_non_mcu_pack"))
ACCESSORY_PACKS = frozenset(("PIC-8bitAC_DFP", "PIC-16bitAC_DFP"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def blob_sha(data: bytes) -> str:
    """Git blob SHA-1: the audited source identity, not a file-content SHA-256."""
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii")
                        + b"\0" + data).hexdigest()


def validate_registry(lock, release):
    require(lock["schema_version"] == 2
            and lock["manufacturer"] == "Microchip"
            and lock["policy"] == "ADR-0002/Issue-851"
            and lock["scope"] == "read_only_openocd_first_source_capability_research",
            "research schema / policy is not the pinned contract")
    p = lock["provider"]
    require(p["commit"] == release["source_commit"] == PINNED_COMMIT
            and p["release"] == release["source_tag"] == "v0.12.0"
            and p["version"] == release["version"] == "0.12.0"
            and p["runtime_id"] == release["runtime_id"],
            "OpenOCD source/release version mismatch")
    for flag in ("production_write_authorized", "catalog_publication_authorized",
                 "ppu_hil_claimed", "socket_hil_claimed"):
        require(lock.get(flag) is False, f"Research cannot authorize {flag}")
    require(lock["global_active_denominator"] is None
            and lock["qualified_exact_icpn_count"] is None
            and lock["p0_source_leads_are_not_software_supported"] is True
            and lock["counted_research_icpn_candidates_retained"] == 24051,
            "invalid Research population/support boundary")
    p0, p1 = lock["p0_research_leads"], lock["p1_bounded_leads"]
    require(len(p0) == 9 and len(p1) == 2, "unexpected Research cohort")
    ids = set()
    for g in p0 + p1:
        require(g["id"] not in ids, "duplicate Research lead")
        ids.add(g["id"])
        require(g["core_architecture"] in
                {"ARM", "MIPS", "AVR", "AVR32", "OTHER", "UNKNOWN"},
                "invalid core architecture")
        require(isinstance(g["core_model"], str) and g["core_model"],
                "missing core model (use UNKNOWN when uncertain)")
        require(isinstance(g["debug_transports"], list) and
                g["debug_transports"] and
                set(g["debug_transports"]) <= {"SWD", "JTAG", "OTHER", "UNKNOWN"},
                "missing/invalid debug transport")
        require(g["core_is_support_evidence"] is False
                and g["device_applicability_reviewed"] is False
                and g["qualification_state"] == "UNKNOWN"
                and g["exact_icpn_software_qualified"] is False
                and g["openocd_supported_asserted"] is False,
                "source lead incorrectly promoted to Software SUPPORTED")
        require(g["matcher"].startswith("^") and
                not g["matcher"].startswith("^.*"), "unbounded family matcher")
        re.compile(g["matcher"], re.IGNORECASE)
        require(g["target"].startswith("tcl/target/")
                and g["target"].endswith(".cfg")
                and re.fullmatch("[0-9a-f]{40}", g["target_sha"]),
                "invalid target source lock")
        if g in p0:
            require(g["priority"] == "P0_SOURCE_BACKED"
                    and g["driver_operations_declared"] ==
                    ["erase", "write", "probe", "read"]
                    and g["driver_source"].startswith("src/flash/nor/")
                    and g["driver_source"].endswith(".c")
                    and re.fullmatch("[0-9a-f]{40}", g["driver_sha"]),
                    "P0 missing source-backed flash operations")
        else:
            require(g["id"] in {"sam-l1x-target-only", "avr32-target-only"}
                    and "driver" not in g
                    and "driver_source" not in g,
                    "P1 must remain bounded to target-only evidence")
    require(any(g["core_architecture"] == "MIPS" for g in p0)
            and any(g["core_architecture"] == "AVR" for g in p0)
            and any(g["core_architecture"] == "ARM" for g in p0),
            "ARM-only filter would erase supported-source research leads")
    return {"p0_source_lead_groups": len(p0), "p1_target_only_groups": len(p1),
            "exact_icpn_software_supported_count": None,
            "research_only": True}


def verify_upstream_source(lock, source_root: Path):
    """Check full Git blobs and direct Tcl Flash Banks against pinned v0.12.0.

    This checks existence of driver *source implementation*, not actual
    target identification, per-device geometry or HIL programming success.
    """
    source_root = Path(source_root)
    observed = {}
    for priority, groups in (("P0", lock["p0_research_leads"]),
                             ("P1", lock["p1_bounded_leads"])):
        for g in groups:
            paths = [(g["target"], g["target_sha"])]
            if priority == "P0":
                paths.append((g["driver_source"], g["driver_sha"]))
            sources = {}
            for path, expected in paths:
                data = (source_root / path).read_bytes()
                observed_sha = blob_sha(data)
                require(observed_sha == expected,
                        f"upstream Git blob mismatch: {path}")
                sources[path] = data.decode("utf-8")
                observed[path] = expected
            target_text = sources[g["target"]]
            if priority == "P0":
                driver = re.escape(g["driver"])
                require(re.search(r"(?m)^\s*flash\s+bank\s+\S+\s+"
                                  + driver + r"\s", target_text) is not None,
                        f"missing direct Flash Bank for {g['id']}")
                source_text = sources[g["driver_source"]]
                require(re.search(r"const\s+struct\s+flash_driver\s+\w+\s*=",
                                  source_text) is not None and
                        re.search(r"\.name\s*=\s*\"" + driver + r"\"",
                                  source_text) is not None,
                        f"Flash Driver missing from {g['id']}")
                for op in g["driver_operations_declared"]:
                    require(re.search(r"\." + op + r"\s*=\s*[a-zA-Z_]\w*",
                                      source_text) is not None,
                            f"Driver source has no {op} handler: {g['id']}")
            else:
                require(re.search(r"(?m)^\s*flash\s+bank\s", target_text) is None,
                        f"P1 direct Flash Bank changed; requires reclassification {g['id']}")
    return {"upstream_blob_checks": len(observed),
            "pinned_commit": lock["provider"]["commit"],
            "source_checks_only": True}


def triage_names(lock, inventory):
    """Classify DFP *device support names*, never commercial exact ICPNs."""
    require(inventory["manufacturer"] == "Microchip"
            and inventory["source_bytes_sha256"] == PINNED_DFP_SOURCE
            and inventory["population_boundary_validated"] is False
            and inventory["production_write_authorized"] is False
            and inventory["device_support_list_is_complete_commercial_sku_inventory"] is False,
            "unverified DFP inventory")
    require(inventory["manufacturer_device_pack_count"] == len(inventory["device_packs"])
            and inventory["observed_manufacturer_device_support_names"] ==
            sum(len(p["device_names"]) for p in inventory["device_packs"]),
            "DFP inventory cardinality mismatch")
    leads = [(g, re.compile(g["matcher"], re.IGNORECASE))
             for g in lock["p0_research_leads"] + lock["p1_bounded_leads"]]
    counts = Counter()
    core = Counter()
    examples = {}
    seen = set()
    for pack in inventory["device_packs"]:
        restricted = (pack["discovery_lane"] in ARCHIVAL_LANES
                      or pack["pack_name"] in ACCESSORY_PACKS)
        for name in pack["device_names"]:
            require(name not in seen, f"duplicate DFP device support name {name}")
            seen.add(name)
            matches = [] if restricted else [g for g, rx in leads if rx.match(name)]
            require(len(matches) <= 1,
                    f"overlapping bounded family matchers on {name}")
            if matches:
                g = matches[0]
                priority = "P0" if g in lock["p0_research_leads"] else "P1"
                key = f"{priority}:{g['id']}"
                core[(priority, g["core_architecture"])] += 1
            else:
                key, priority = "P2:archive_only", "P2"
                core[("P2", "UNKNOWN")] += 1
            counts[key] += 1
            examples.setdefault(key, [])
            if len(examples[key]) < 3:
                examples[key].append(name)
    require(len(seen) == inventory["observed_distinct_device_support_names"],
            "DFP observed distinct-device population mismatch")
    return {
        "classification_unit": "original Microchip DFP device support name (NOT exact ICPN)",
        "provider_commit": lock["provider"]["commit"],
        "source_dfp_sha256": PINNED_DFP_SOURCE,
        "observed_dfp_names": len(seen),
        "by_research_group": dict(sorted(counts.items())),
        "by_priority_and_core": {f"{p}:{c}": n for (p, c), n in sorted(core.items())},
        "examples_not_commercial_identity_evidence": examples,
        "exact_icpn_qualified_supported": None,
        "microchip_global_openocd_supported_denominator": None,
        "all_counts_research_only": True,
        "p2_does_not_mean_openocd_unsupported": True,
    }



def validate_frozen_observation(lock, observation, dfp_report=None):
    """Reconcile archived DFP counts without promoting any ICPN into support."""
    require(observation["schema_version"] == 1
            and observation["policy"] == "ADR-0002/Issue-851"
            and observation["openocd_source_commit"] == lock["provider"]["commit"]
            and observation["dfp_original_index_sha256"] == PINNED_DFP_SOURCE
            and observation["research_classification_unit"] ==
            "DFP device support name, not exact manufacturer commercial ICPN",
            "frozen Research observation source/scope mismatch")
    require(observation["archived_microchip_research_icpn_candidate_count"] ==
            lock["counted_research_icpn_candidates_retained"]
            and observation["openocd_source_blob_checks"] == 20,
            "incorrect Research lineage/source check baseline")
    for key in ("exact_icpn_software_supported_count",
                "microchip_global_openocd_supported_denominator"):
        require(observation[key] is None, f"unsupported count promoted: {key}")
    for key in ("manufacturer_population_complete",
                "arm_majority_supported_icpn_claimed",
                "p0_is_supported_claimed",
                "hardware_programming_qualified",
                "socket_hil_claimed",
                "production_write_authorized",
                "catalog_publication_authorized"):
        require(observation[key] is False, f"Research boundary breached: {key}")
    total = observation["observed_original_dfp_support_names"]
    priorities = observation["dfp_research_priority_counts"]
    groups = observation["dfp_by_research_group"]
    cores = observation["dfp_by_priority_and_core"]
    require(total == sum(priorities.values()) ==
            sum(groups.values()) == sum(cores.values()),
            "frozen Research counts do not reconcile")
    for priority in ("P0", "P1", "P2"):
        require(priorities[priority] ==
                sum(v for k, v in groups.items() if k.startswith(priority + ":")) ==
                sum(v for k, v in cores.items() if k.startswith(priority + ":")),
                f"frozen {priority} Research counts disagree")
    if dfp_report is not None:
        require(dfp_report["observed_dfp_names"] == total
                and dfp_report["source_dfp_sha256"] == PINNED_DFP_SOURCE
                and dfp_report["provider_commit"] == lock["provider"]["commit"]
                and dfp_report["by_research_group"] == groups
                and dfp_report["by_priority_and_core"] == cores
                and dfp_report["exact_icpn_qualified_supported"] is None,
                "original DFP replay differs from frozen source observation")
    return {"frozen_observation_reconciled": True,
            "observed_dfp_names": total,
            "software_supported_exact_icpns": None}

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--openocd-source-root", type=Path,
                    help="local checkout at pinned upstream OpenOCD commit")
    ap.add_argument("--dfp-evidence-root", type=Path,
                    help="original archived DFP index.html + manifest.json")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    lock = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))
    release = json.loads(OPENOCD_RELEASE.read_text(encoding="utf-8"))
    report = {"source_lock_validation": validate_registry(lock, release)}
    observation = json.loads(OBSERVATION.read_text(encoding="utf-8"))
    report["observation_validation"] = validate_frozen_observation(lock, observation)
    if args.openocd_source_root:
        report["upstream"] = verify_upstream_source(lock, args.openocd_source_root)
    if args.dfp_evidence_root:
        report["dfp"] = triage_names(lock, archived_inventory(args.dfp_evidence_root))
        report["observation_validation"] = validate_frozen_observation(
            lock, observation, report["dfp"])
    if args.output:
        out = args.output.resolve()
        require("production" not in (p.lower() for p in out.parts),
                "Production output forbidden")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
