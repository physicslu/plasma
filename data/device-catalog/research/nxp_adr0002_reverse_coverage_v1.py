#!/usr/bin/env python3
"""Bounded NXP OpenOCD v0.12.0 reverse coverage; no software promotion.

Read-only replay of one 501-exact NXP v10 research ledger, one 353 Active
official-page observation, and a review-locked *filename-selected* subset of
upstream OpenOCD target source blobs. No execution or new qualification.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
V10 = HERE / "nxp-501-adr0002-core-transport-qualification-v10.csv"
ACTIVE = HERE / "nxp-official-bounded-snapshot-2026-10-13-v1.json"
SOURCE = HERE / "nxp-openocd-reverse-target-lock-v1.json"
PREVIOUS = HERE / "nxp-adr0002-openocd-source-v9.json"
RELEASE = ROOT / "release/openocd.json"
OUTPUT = HERE / "nxp-openocd-reverse-coverage-v1.json"
COMMIT = "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"

# Independent immutable source/input blob pins, checked against bytes on disk.
PINS = {
    V10: "9f0397fe6062356fd04cd5eb73133969e75d9bfb",
    ACTIVE: "710032217ffe1b6876a8b94a24af57bdd0dadef4",
    PREVIOUS: "e9ccb5af0c4649541955cbd0608340dfd2758856",
    RELEASE: "08c884b1bf6f5999c6d34c090992a8b59d85971d",
}
EXPECTED_PRIORITY = {"P0": 27, "P1": 38, "P2": 436}
EXPECTED_ACTIVE_PRIORITY = {"P0": 12, "P1": 20, "P2": 321}
EXPECTED_SOURCE_CLASSES = {
    "previously_reviewed_chain": 5,
    "legacy_target_without_exact_sample": 26,
    "imx_app_processor_not_imx_rt": 16,
    "rt600_dsp_debug_only": 1,
}
EXPECTED_FILES = frozenset((
    "imx.cfg imx21.cfg imx25.cfg imx27.cfg imx28.cfg imx31.cfg imx35.cfg "
    "imx51.cfg imx53.cfg imx6.cfg imx6sx.cfg imx6ul.cfg imx7.cfg "
    "imx7ulp.cfg imx8m.cfg imx8qm.cfg k40.cfg k60.cfg kl25.cfg "
    "kl46.cfg klx.cfg kx.cfg lpc11xx.cfg lpc12xx.cfg lpc13xx.cfg "
    "lpc17xx.cfg lpc1850.cfg lpc1xxx.cfg lpc2103.cfg lpc2124.cfg "
    "lpc2129.cfg lpc2148.cfg lpc2294.cfg lpc2378.cfg lpc2460.cfg "
    "lpc2478.cfg lpc2900.cfg lpc2xxx.cfg lpc3131.cfg lpc3250.cfg "
    "lpc40xx.cfg lpc4350.cfg lpc4357.cfg lpc4370.cfg lpc84x.cfg "
    "lpc8nxx.cfg lpc8xx.cfg xtensa-core-nxp_rt600.cfg"
).split())
REVIEWED_CHAINS = frozenset({
    "kl25.cfg", "klx.cfg", "lpc84x.cfg", "lpc8xx.cfg", "lpc1xxx.cfg",
})
# Source-only family leads outside the 501 exact set; these do NOT prove
# additional exact ICPNs. Prefix match is deliberately conservative.
UNSAMPLED_LEGACY_PREFIXES = (
    "MK40", "MK60", "MKL46", "LPC11", "LPC12", "LPC13",
    "LPC17", "LPC18", "LPC2", "LPC31", "LPC32",
    "LPC40", "LPC43", "LPC8N",
)
PINNED_LEGACY = {
    "k40.cfg": "33e8235460aed85fb18addc4533c5ea5eb02661b",
    "k60.cfg": "3b89102babbe072cf3e11d6d27647d5a88a2e8f1",
    "kl46.cfg": "bf6b244d87072d00bfe04dc4b0f20670ea29f626",
    "lpc11xx.cfg": "d288e2a32b08b5e9ad26b7c86fb7035e8e08b1b6",
    "lpc17xx.cfg": "35d8badea416e641babe6ccad3fd8503f3de7cae",
    "lpc40xx.cfg": "f0be5a1e40979b2484f9f8edec0c4dfa49a65069",
    "imx6.cfg": "c9b6acf79d7d3eb9ac12b549f93f38595904590a",
}
P0_FAMILIES = {"KL25": 12, "LPC844": 7, "LPC845": 8}


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("NXP reverse coverage: " + message)


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"{path.name}: expected JSON object")
    return data


def source_class(name: str) -> str:
    if name in REVIEWED_CHAINS:
        return "previously_reviewed_chain"
    if name.startswith("imx"):
        return "imx_app_processor_not_imx_rt"
    if name == "xtensa-core-nxp_rt600.cfg":
        return "rt600_dsp_debug_only"
    return "legacy_target_without_exact_sample"


def confirm_target_index(evidence: dict, previous: dict, upstream_root: Path | None) -> None:
    require(evidence.get("schema_version") == 1 and
            evidence.get("scope") == "SOURCE_ONLY_BOUNDED_NXP_REVERSE_LOOKUP_NO_SUPPORT_PROMOTION" and
            evidence.get("provider") == "openocd-upstream" and
            evidence.get("release") == "0.12.0" and
            evidence.get("source_commit") == COMMIT and
            evidence.get("target_root_listing_entries") == 309,
            "review source scope or upstream target entry count changed")
    entries = evidence.get("target_files")
    require(isinstance(entries, list) and len(entries) == len(EXPECTED_FILES),
            "target source index size drift")
    names = {}
    for entry in entries:
        require(isinstance(entry, dict) and set(entry) == {"path", "git_blob", "review_class"},
                "target evidence row shape drift")
        path = entry["path"]
        require(isinstance(path, str) and path.startswith("tcl/target/") and
                path.count("/") == 2, "unsafe or unexpected source path")
        name = path.split("/")[-1]
        require(name not in names, "duplicate source path")
        require(entry["review_class"] == source_class(name), f"{name}: evidence class drift")
        require(isinstance(entry["git_blob"], str) and len(entry["git_blob"]) == 40 and
                all(ch in "0123456789abcdef" for ch in entry["git_blob"]),
                f"{name}: Git blob must be SHA1")
        names[name] = entry["git_blob"]
    require(set(names) == EXPECTED_FILES, "unreviewed NXP candidate target additions/deletions")
    for name, sha in PINNED_LEGACY.items():
        require(names[name] == sha, "source anchor drift: " + name)
    for name in REVIEWED_CHAINS:
        upstream_path = "tcl/target/" + name
        require(names[name] == previous["upstream_git_blobs"][upstream_path],
                "previously reviewed Tcl file hash changed: " + name)
    require(evidence["verified_baseline_driver_blobs"] == {
        name: previous["upstream_git_blobs"][name]
        for name in ("src/flash/nor/kinetis.c", "src/flash/nor/lpc2000.c")
    }, "pinned Flash Driver SHA drift")
    require(Counter(e["review_class"] for e in entries) == EXPECTED_SOURCE_CLASSES,
            "target evidence category count drift")
    if upstream_root is not None:
        for entry in entries:
            path = upstream_root / entry["path"]
            require(path.is_file() and blob(path.read_bytes()) == entry["git_blob"],
                    f"upstream original-source blob mismatch: {entry['path']}")
        for rel, sha in evidence["verified_baseline_driver_blobs"].items():
            path = upstream_root / rel
            require(path.is_file() and blob(path.read_bytes()) == sha,
                    f"upstream original-driver blob mismatch: {rel}")
        actual_names = {
            path.name for path in (upstream_root / "tcl/target").iterdir()
            if path.is_file() and path.suffix == ".cfg" and
            (path.name.startswith(("imx", "lpc")) or
             path.name in {"k40.cfg", "k60.cfg", "kx.cfg", "kl25.cfg",
                           "kl46.cfg", "klx.cfg", "xtensa-core-nxp_rt600.cfg"})
        }
        require(actual_names == EXPECTED_FILES,
                "pinned upstream root target-name inventory differs")


def build(*, upstream_root: Path | None = None) -> dict:
    require(set(PINS) == {V10, ACTIVE, PREVIOUS, RELEASE},
            "immutable input path contract changed")
    for path, expected in PINS.items():
        require(blob(path.read_bytes()) == expected, "immutable input drift: " + path.name)
    release, previous, evidence = (
        read_json(RELEASE), read_json(PREVIOUS), read_json(SOURCE)
    )
    require(release["version"] == "0.12.0" and
            release["source_commit"] == previous["source_commit"] == COMMIT,
            "OpenOCD release and previous review source diverged")
    confirm_target_index(evidence, previous, upstream_root)

    with V10.open(encoding="utf-8", newline="") as stream:
        records = list(csv.DictReader(stream))
    require(len(records) == 501, "501 research denominator changed")
    lookup = {}
    for row in records:
        sku = row["icpn"]
        require(sku and sku not in lookup and row["manufacturer"] == "NXP",
                "invalid or duplicated research exact ICPN")
        require(row["openocd_source_commit"] == COMMIT and
                row["research_priority"] in EXPECTED_PRIORITY and
                row["software_support_qualification"] != "SUPPORTED" and
                row["exact_icpn_applicability"] == "UNVERIFIED" and
                row["public_catalog_visibility_authorized"] == "false",
                f"{sku}: unreviewed P0/P1 or software visibility change")
        lookup[sku] = row
    prio = Counter(row["research_priority"] for row in records)
    require(dict(prio) == EXPECTED_PRIORITY, "historical priority baseline changed")

    snapshot = read_json(ACTIVE)
    require(snapshot["snapshot_schema_version"] == 1 and
            snapshot["scope_limits"]["source_population_complete"] is False and
            snapshot["scope_limits"]["global_nxp_active_denominator"] is None and
            snapshot["scope_limits"]["runtime_programming_qualified"] is False,
            "official bounded snapshot erroneously upgraded to global/software authority")
    active = snapshot["reconciliation"]["observed_active_icpns"]
    require(isinstance(active, list) and len(active) == len(set(active)) == 353,
            "official Active exact set changed")
    unknown = sorted(set(active) - lookup.keys())
    require(not unknown, "new official Active exact ICPNs require separate review")
    active_priority = Counter(lookup[sku]["research_priority"] for sku in active)
    require(dict(active_priority) == EXPECTED_ACTIVE_PRIORITY,
            "active subset priority changed")
    unmatched_legacy = sorted(
        sku for sku in lookup if sku.startswith(UNSAMPLED_LEGACY_PREFIXES)
    )
    require(not unmatched_legacy, "legacy NXP Target family intersects 501 cohort; re-review before P0 closure")
    family_counts = Counter(
        "KL25" if sku.startswith("MKL25") else
        "LPC844" if sku.startswith("LPC844") else
        "LPC845" if sku.startswith("LPC845") else "other"
        for sku, row in lookup.items() if row["research_priority"] == "P0"
    )
    require({k: family_counts[k] for k in P0_FAMILIES} == P0_FAMILIES and
            family_counts.get("other", 0) == 0, "P0 family membership changed")

    return {
        "schema_version": 1,
        "scope": "NXP_ADR0002_REVERSE_COVERAGE_BOUNDED_501_AND_353",
        "openocd_provider": "openocd-upstream",
        "openocd_version": release["version"],
        "openocd_commit": COMMIT,
        "pinned_target_directory_entries": evidence["target_root_listing_entries"],
        "selected_filename_target_evidence_entries": len(evidence["target_files"]),
        "source_evidence_class_counts": dict(sorted(Counter(
            row["review_class"] for row in evidence["target_files"]
        ).items())),
        "existing_nxp_exact_reviewed": len(lookup),
        "official_active_observed_bounded": len(active),
        "official_active_already_in_review": len(active) - len(unknown),
        "official_active_new_to_review": len(unknown),
        "older_review_without_current_active_observation": len(lookup) - len(active),
        "review_priority_existing": EXPECTED_PRIORITY,
        "active_observed_priority": EXPECTED_ACTIVE_PRIORITY,
        "not_observed_active_priority": dict(sorted(
            (name, prio[name] - active_priority[name])
            for name in EXPECTED_PRIORITY
        )),
        "p0_existing_exact_families": P0_FAMILIES,
        "new_p0_exact_attested_by_reverse_check": 0,
        "additional_exact_matches_to_legacy_target_family_leads": len(unmatched_legacy),
        "extra_target_leads": [
            "k40.cfg", "k60.cfg", "kl46.cfg",
            "lpc11xx.cfg", "lpc17xx.cfg", "lpc40xx.cfg",
        ],
        "non_equivalence": [
            "imx-app-processor-target-does-not-equal-mimxrt-cross-over-mcu",
            "rt600-xtensa-dsp-config-is-not-exact-mcu-flash-driver-proof",
            "cfg-or-driver-family-source-does-not-qualify-exact-icpn",
            "not-found-in-bounded-cohort-is-not-vendor-wide-unsupported",
        ],
        "research_priority_scope_complete": True,
        "nxp_entire_active_portfolio_complete": False,
        "new_software_supported_exact": 0,
        "production_catalog_changed": False,
        "programming_or_hil_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-root", type=Path,
                        help="Optional checkout of *pinned* OpenOCD commit for full Git-blob replay")
    parser.add_argument("--check", action="store_true",
                        help="Require committed reverse-coverage JSON to equal regenerated values")
    args = parser.parse_args()
    output = build(upstream_root=args.upstream_root)
    if args.check:
        require(read_json(OUTPUT) == output, "reverse coverage report is not reproducible")
        print("NXP REVERSE COVERAGE PASS: 501 reviewed, 353 subset, "
              "P0=27, new P0=0, upstream 48 filename-selected source leads")
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
