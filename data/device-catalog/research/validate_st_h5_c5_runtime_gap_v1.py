#!/usr/bin/env python3
"""Read-only, exact-state v1 research gate. Does not contact hardware or vendors."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = HERE / "st-h5-c5-runtime-gap-v1.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
BLOCKED = HERE / "openocd-final-runtime-blocked-v6.31.csv"
RUNTIME = HERE / "openocd-production-runtime-capability-v6.31.json"
C5 = HERE / "st-c5-dfp-commercial-loader-crosswalk-v0.9.json"
C5_GATE = HERE / "st-c5-ps-backend-static-gate-v1.1.json"

def require(cond: bool, message: str) -> None:
    if not cond:
        raise ValueError(message)

def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))

def validate(evidence: dict | None = None) -> dict:
    e = read_json(EVIDENCE) if evidence is None else evidence
    require(e["schema_version"] == 1 and e["audit_id"] == "st-h5-c5-runtime-gap-v1", "identity drift")
    require(e["record_state"] == "SOURCE_RESEARCH_ONLY_NO_RUNTIME_PROMOTION", "unexpected promotion state")
    base = e["catalog_baseline"]
    manifest = read_json(MANIFEST)
    require(manifest["status"] == "production", "manifest is not Production")
    require(len(manifest["sources"]) == base["production_sources"] == 28, "Production source-count drift")

    all_rows: list[dict[str, str]] = []
    for source in manifest["sources"]:
        path = (MANIFEST.parent / source["path"]).resolve()
        rows = read_csv(path)
        require(len(rows) == source["row_count"], "Production source row-count drift")
        all_rows.extend(rows)
    require(len(all_rows) == base["total_exact_icpns"] == 4629, "exact Production population drift")
    require(len({r["icpn"] for r in all_rows}) == len(all_rows), "duplicate exact ICPN")

    mapped = [r for r in all_rows if r["mapping_status"] != "no_mapping"]
    unmapped = [r for r in all_rows if r["mapping_status"] == "no_mapping"]
    require((len(mapped), len(unmapped)) == (base["mapped"], base["no_mapping"]) == (4164, 465), "post-v6.31 mapping partition drift")
    blocked_rows = read_csv(BLOCKED)
    require(len(blocked_rows) == 465, "v6.31 blocked evidence drift")
    require({r["icpn"] for r in blocked_rows} == {r["icpn"] for r in unmapped}, "blocked exact cohort does not match Production")
    actual_by_family = dict(sorted(Counter(r["family"] for r in unmapped).items()))
    require(actual_by_family == base["remaining_blocked_family_counts"], "blocked family partition drift")
    require(actual_by_family == {"STM32C5":172,"STM32H5":190,"STM32N6":32,"STM32WB0":24,"STM32WL3":47}, "unexpected family-blocked count")
    for row in unmapped:
        require(not row["openocd_target_config"] and not row["existing_identifier"] and not row["existing_identifier_kind"], f"{row['icpn']}: blocked backend mutated")

    h5 = [r for r in unmapped if r["family"] == "STM32H5"]
    c5 = [r for r in unmapped if r["family"] == "STM32C5"]
    require((len(h5), len(c5)) == (190, 172), "H5/C5 exact count drift")
    require(dict(sorted(Counter(r["series"] for r in h5).items())) == base["h5_series_counts"], "H5 series group drift")
    require((base["active_openocd_routes"], base["active_denominator"]) == (4085, 4550), "v6.31 route baseline drift")

    rt = read_json(RUNTIME)
    packaged = e["packaged_runtime"]
    require((rt["runtime"]["source_commit"], rt["runtime"]["distribution"]) == (packaged["commit"], "upstream-openocd"), "packaged runtime authority drift")
    require(packaged["commit"] == "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c", "pinned upstream drift")
    require(rt["target_configs"]["STM32H5"]["present"] is False and rt["target_configs"]["STM32C5"]["present"] is False, "H5/C5 packaged runtime changed; rebaseline required")

    fork = e["candidate_st_fork"]
    require((fork["repository"], fork["commit"]) == ("STMicroelectronics/OpenOCD","c8d973bdad9a6fddb51459eda109b3b95d23b57a"), "vendor fork pin drift")
    for key, family in (("h5_cfg","STM32H5"), ("c5_cfg","STM32C5")):
        require(fork["files"][key]["blob"] == rt["observations"]["ST_fork"][family]["git_blob_sha"], f"{family}: CFG source identity drift")
    c5_report = read_json(C5)
    c5_gate = read_json(C5_GATE)
    require(c5_report["official_dfp_source"]["pinned_commit"] == c5_gate["dfp"]["commit"], "C5 DFP pin drift")
    require(c5_report["commercial_cohort"]["observed_public_estore_active_exact_mpns"] == 172, "C5 DFP cohort drift")
    require(c5_report["commercial_cohort"]["exact_pdsc_variant_matches"] == 139, "C5 exact DFP partition drift")
    require(c5_report["commercial_cohort"]["parent_dname_only_missing_exact_dfp_variant"] == 33, "C5 base-only partition drift")
    require(c5_gate["manufacturer_openocd_fork"]["target_cfg_blob_sha"] == fork["files"]["c5_cfg"]["blob"], "C5 static gate source drift")
    require(c5_gate["manufacturer_openocd_fork"]["stldr_driver_blob_sha"] == fork["files"]["c5_stldr_driver"]["blob"], "C5 STLDR pin drift")
    require(e["h5_source_observations"]["real_silicon_qualifications"] == 0, "unqualified H5 HIL claim")
    require(e["c5_source_observations"]["source_loader_table_empty"] is True, "C5 source claim drift")
    require(e["c5_source_observations"]["dfp_exact_variant_matches"] == 139, "C5 DFP evidence drift")
    require(e["c5_source_observations"]["dfp_base_only_variants"] == 33, "C5 exact variant gap drift")

    gates = e["production_gates"]
    require(gates and all(value is False for value in gates.values()), "research must fail closed for all runtime/physical/production gates")
    return {
        "audit_id": e["audit_id"],
        "status": "RESEARCH_ONLY_PASS",
        "mapped": len(mapped),
        "no_mapping": len(unmapped),
        "h5_runtime_blocked": len(h5),
        "c5_runtime_blocked": len(c5),
        "h5_c5_runtime_blocked_total": len(h5) + len(c5),
        "hardware_runtime_ready": False,
        "production_write_authorized": False,
    }

if __name__ == "__main__":
    print(json.dumps(validate(), indent=2, sort_keys=True))
    print("ST_H5_C5_RUNTIME_GAP_V1_RESEARCH_PASS")
