"""Deterministic STM32F1 retained-evidence canonical admission model."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f1_acquisition_pilot import catalog_mapping
from validate_stm32f1_retained_evidence import validate_retained_evidence

SCHEMA_VERSION = 1
MANUFACTURER = "STMicroelectronics"
TRANSPORT = "chromium_rendered_dom"
DECISIONS = {"admit", "already_present", "manual_review_required", "reject"}
BASE_RE = re.compile(r"^STM32F1\d{2}([CRVZ])([8BCE])$")
ICPN_RE = re.compile(r"^STM32F1[0-9A-Z]+$")
PACKAGE_BY_CODE = {"T": "LQFP", "U": "UFQFPN", "Y": "WLCSP64"}
PINS_BY_CODE = {"C": "48", "R": "64", "V": "100", "Z": "144"}
FLASH_BY_CODE = {"8": "64 KiB", "B": "128 KiB", "C": "256 KiB", "E": "512 KiB"}
TEMPERATURE_BY_CODE = {"6": "-40 to 85 C", "7": "-40 to 105 C"}


class AdmissionError(RuntimeError):
    pass


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path}: expected a JSON object")
    return value


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_csv_sha256(fields: list[str], rows: list[dict[str, str]]) -> str:
    payload = json.dumps(
        {"fields": fields, "rows": rows},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def proposed_canonical_row(
    *,
    icpn: str,
    base_device: str,
    source_url: str,
    evidence_id: str,
    mapping: dict[str, object],
    fields: list[str],
) -> dict[str, str]:
    base_match = BASE_RE.fullmatch(base_device)
    if base_match is None:
        raise AdmissionError(f"unsupported STM32F1 base-device identity: {base_device}")
    if not ICPN_RE.fullmatch(icpn) or not icpn.startswith(base_device) or icpn == base_device:
        raise AdmissionError(f"invalid exact commercial ICPN: {icpn}")
    suffix = icpn[len(base_device) :]
    if len(suffix) < 2:
        raise AdmissionError(f"ICPN lacks package/temperature codes: {icpn}")
    package_code, temperature_code = suffix[0], suffix[1]
    if package_code not in (set(PACKAGE_BY_CODE) | {"H"}) or temperature_code not in TEMPERATURE_BY_CODE:
        raise AdmissionError(f"unsupported package/temperature code: {icpn}")
    target_configs = mapping.get("target_configs")
    if mapping.get("status") != "unique" or not isinstance(target_configs, list) or len(target_configs) != 1:
        raise AdmissionError(f"base device lacks one unique OpenOCD mapping: {base_device}")
    identifier_kind = mapping.get("identifier_kind")
    if not isinstance(identifier_kind, str) or not identifier_kind:
        raise AdmissionError(f"base device lacks mapping identifier kind: {base_device}")
    pin_code, flash_code = base_match.groups()
    package = "TFBGA" if package_code == "H" and pin_code == "R" else (
        "LFBGA" if package_code == "H" else PACKAGE_BY_CODE[package_code]
    )
    values = {
        "manufacturer": MANUFACTURER,
        "icpn": icpn,
        "family": "STM32F1",
        "series": base_device[:9],
        "base_device": base_device,
        "package": package,
        "pin_count": PINS_BY_CODE[pin_code],
        "flash_size": FLASH_BY_CODE[flash_code],
        "temperature_grade": TEMPERATURE_BY_CODE[temperature_code],
        "option_suffix": suffix[2:],
        "cmsis_device_name": base_device,
        "existing_identifier": base_device,
        "existing_identifier_kind": identifier_kind,
        "mapping_status": "deterministic_pattern",
        "openocd_target_config": target_configs[0],
        "source_type": "official_st_product_page_retained_browser_evidence",
        "source_reference": f"{source_url}#plasma-evidence={evidence_id}",
        "source_authority": "STMicroelectronics official",
        "verification_status": "verified_direct_st_retained_browser_exact_icpn",
    }
    if set(values) != set(fields):
        raise AdmissionError("canonical CSV schema is not supported by the Phase 2.7 writer")
    return {field: values[field] for field in fields}


def build_admission_plan(
    *,
    evidence_dir: Path,
    canonical_path: Path,
    catalog_path: Path,
    baseline_path: Path,
) -> dict[str, Any]:
    retained = validate_retained_evidence(evidence_dir, baseline_path=baseline_path)
    provenance = read_json(evidence_dir / "provenance.json")
    summary = read_json(evidence_dir / "pilot-summary.json")
    fields, canonical_rows = read_csv(canonical_path)
    _, catalog_rows = read_csv(catalog_path)
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("retained provenance requires evidence_id")
    if retained.get("scale_ready") is not True or retained.get("canonical_dataset_admission") is not False:
        raise AdmissionError("retained evidence is not eligible for admission planning")

    canonical_by_icpn: dict[str, list[dict[str, str]]] = {}
    for row in canonical_rows:
        canonical_by_icpn.setdefault(row.get("icpn", ""), []).append(row)
    evidence_results = summary.get("results")
    if not isinstance(evidence_results, list):
        raise AdmissionError("retained pilot results must be a list")

    candidates: list[dict[str, Any]] = []
    seen_candidates: set[str] = set()
    for result in evidence_results:
        if not isinstance(result, dict):
            raise AdmissionError("retained pilot result must be an object")
        base_device = result.get("base_device")
        evidence = result.get("evidence")
        if not isinstance(base_device, str) or not isinstance(evidence, dict):
            raise AdmissionError("retained pilot result lacks base/evidence")
        source_url = evidence.get("source_url")
        if not isinstance(source_url, str):
            raise AdmissionError(f"{base_device}: missing source URL")
        try:
            validate_source_url(source_url)
        except AcquisitionError as exc:
            raise AdmissionError(f"{base_device}: source URL is not approved") from exc
        mapping = catalog_mapping(base_device, catalog_rows)
        raw_icpns = evidence.get("exact_icpns")
        if not isinstance(raw_icpns, list):
            raise AdmissionError(f"{base_device}: exact_icpns must be a list")
        for icpn in raw_icpns:
            issues: list[str] = []
            decision = "admit"
            proposed: dict[str, str] | None = None
            if not isinstance(icpn, str) or icpn in seen_candidates:
                decision = "reject"
                issues.append("duplicate or invalid retained candidate")
            else:
                seen_candidates.add(icpn)
                try:
                    proposed = proposed_canonical_row(
                        icpn=icpn,
                        base_device=base_device,
                        source_url=source_url,
                        evidence_id=evidence_id,
                        mapping=mapping,
                        fields=fields,
                    )
                except AdmissionError as exc:
                    decision = "manual_review_required" if "mapping" in str(exc) else "reject"
                    issues.append(str(exc))
            existing = canonical_by_icpn.get(str(icpn), [])
            if len(existing) > 1:
                decision = "manual_review_required"
                issues.append("canonical dataset already contains duplicate ICPN rows")
            elif len(existing) == 1 and proposed is not None:
                if existing[0] == proposed:
                    decision = "already_present"
                else:
                    decision = "manual_review_required"
                    issues.append("existing canonical row conflicts with proposed semantics")
            candidates.append(
                {
                    "manufacturer": MANUFACTURER,
                    "base_device": base_device,
                    "icpn": icpn,
                    "authoritative_evidence": {
                        "evidence_id": evidence_id,
                        "source_url": source_url,
                        "rendered_dom_sha256": evidence.get("rendered_dom_sha256"),
                        "evidence_section_sha256": evidence.get("evidence_section_sha256"),
                    },
                    "base_mapping": mapping,
                    "canonical_duplicate_count": len(existing),
                    "canonical_conflict": decision == "manual_review_required" and bool(existing),
                    "decision": decision,
                    "issues": issues,
                    "proposed_canonical_row": proposed,
                }
            )

    candidates.sort(key=lambda item: (item["manufacturer"], item["base_device"], item["icpn"]))
    counts = Counter(item["decision"] for item in candidates)
    unknown = set(counts) - DECISIONS
    if unknown:
        raise AdmissionError(f"unsupported decisions: {sorted(unknown)}")
    conflicts = sum(bool(item["canonical_conflict"]) for item in candidates)
    issues = sorted({issue for item in candidates for issue in item["issues"]})
    return {
        "schema_version": SCHEMA_VERSION,
        "evidence_id": evidence_id,
        "source_provenance": {
            "repository": provenance.get("source_repository"),
            "executed_git_sha": provenance.get("executed_git_sha"),
            "evidence_manifest_sha256": file_sha256(evidence_dir / "manifest.json"),
        },
        "inputs": {
            "retained_evidence_directory": evidence_dir.name,
            "canonical_dataset": canonical_path.name,
            "canonical_input_sha256": canonical_csv_sha256(fields, canonical_rows),
            "mapping_catalog": catalog_path.name,
            "mapping_catalog_sha256": file_sha256(catalog_path),
            "baseline": baseline_path.name,
            "baseline_sha256": file_sha256(baseline_path),
        },
        "candidate_count": len(candidates),
        "decision_counts": {decision: counts.get(decision, 0) for decision in sorted(DECISIONS)},
        "conflicts": conflicts,
        "canonical_rows_before": len(canonical_rows),
        "canonical_dataset_admission": "planned",
        "issues": issues,
        "candidates": candidates,
    }


def plan_is_clean(plan: dict[str, Any]) -> bool:
    counts = plan.get("decision_counts", {})
    return (
        plan.get("candidate_count") == 26
        and counts.get("manual_review_required") == 0
        and counts.get("reject") == 0
        and plan.get("conflicts") == 0
        and plan.get("issues") == []
    )


def write_canonical_dataset(
    *,
    plan: dict[str, Any],
    canonical_path: Path,
) -> dict[str, Any]:
    if not plan_is_clean(plan):
        raise AdmissionError("admission writer refuses a non-clean plan")
    fields, rows = read_csv(canonical_path)
    current_by_icpn = {row.get("icpn", ""): row for row in rows}
    admit_rows = [item["proposed_canonical_row"] for item in plan["candidates"] if item["decision"] == "admit"]
    if canonical_csv_sha256(fields, rows) != plan["inputs"]["canonical_input_sha256"]:
        if all(isinstance(row, dict) and current_by_icpn.get(row.get("icpn", "")) == row for row in admit_rows):
            return {"status": "no_op", "rows_before": len(rows), "rows_after": len(rows), "added": []}
        raise AdmissionError("canonical dataset changed after admission planning")
    existing = set(current_by_icpn)
    added = []
    for row in admit_rows:
        if not isinstance(row, dict) or set(row) != set(fields):
            raise AdmissionError("plan contains an invalid proposed canonical row")
        if row["icpn"] in existing:
            raise AdmissionError(f"writer refuses duplicate ICPN: {row['icpn']}")
        existing.add(row["icpn"])
        rows.append(row)
        added.append(row["icpn"])
    rows.sort(key=lambda row: (row["manufacturer"], row["base_device"], row["icpn"]))
    with canonical_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return {"status": "written", "rows_before": len(rows) - len(added), "rows_after": len(rows), "added": sorted(added)}
