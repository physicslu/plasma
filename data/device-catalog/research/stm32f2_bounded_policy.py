#!/usr/bin/env python3
"""Generic deterministic policy engine for bounded STM32F2 evidence batches.

This layer owns repeatable batch mechanics: retained-evidence validation,
historical canonical-boundary reconstruction, deterministic candidate building,
metadata-contract application, Production snapshot reconstruction and policy
summary generation.  The JSON batch registry owns per-batch policy decisions.

It never writes the canonical dataset or Production manifest.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import (
    AdmissionError,
    build_admission_plan,
    file_sha256,
    plan_is_clean,
    read_csv,
    read_json,
)
from stm32f2_admission_policy import (
    CANONICAL_FIELDS,
    FAMILY,
    build_candidate_inputs,
    build_canonical_row,
)
from stm32f2_bounded_discovery import load_spec as load_discovery_spec
from stm32f2_bounded_evidence import validate as validate_bounded_evidence

HERE = Path(__file__).resolve().parent
DEFAULT_REGISTRY = HERE / "stm32f2-bounded-policy-batches.json"
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f2-commercial-icpn.csv"
DEFAULT_PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"


@dataclass(frozen=True)
class STM32F2PolicySpec:
    phase: str
    discovery_phase: str
    admission_phase: str
    adapter_id: str
    policy_baseline_path: Path
    expected_candidate_count: int
    expected_canonical_icpn_count_before: int
    historical_production_base_devices: frozenset[str]
    expected_production_exact_icpn_count: int
    expected_production_base_device_count: int
    expected_production_family_counts: dict[str, int]
    flash_by_code: dict[str, str]
    temperature_by_code: dict[str, str]
    package_by_code: dict[str, str]
    pins_by_combination: dict[tuple[str, str], str]
    option_suffixes: frozenset[str]
    target_config: str
    policy_evidence: dict[str, Any]
    summary_extra: dict[str, Any]

    @property
    def supported_base_devices(self) -> frozenset[str]:
        return _discovery_targets(self.discovery_phase)


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AdmissionError(f"{label} must be an object")
    return value


def _string_map(value: object, label: str) -> dict[str, str]:
    raw = _require_mapping(value, label)
    result: dict[str, str] = {}
    for key, item in raw.items():
        if not isinstance(key, str) or not isinstance(item, str) or not key or not item:
            raise AdmissionError(f"{label} must contain non-empty string pairs")
        result[key] = item
    return result


def _pins_map(value: object) -> dict[tuple[str, str], str]:
    raw = _string_map(value, "pins_by_combination")
    result: dict[tuple[str, str], str] = {}
    for key, pins in raw.items():
        parts = key.split("/")
        if len(parts) != 2 or any(len(part) != 1 for part in parts):
            raise AdmissionError(f"invalid STM32F2 pin/package key: {key}")
        result[(parts[0], parts[1])] = pins
    return result


def _discovery_targets(phase: str) -> frozenset[str]:
    if phase == "4.3B":
        # Historical first STM32F2 batch predates the bounded-discovery registry.
        from stm32f2_admission_policy import SUPPORTED_BASE_DEVICES

        return SUPPORTED_BASE_DEVICES
    spec = load_discovery_spec(phase)
    manifest = read_json(spec.manifest_path)
    targets = manifest.get("targets")
    if not isinstance(targets, list):
        raise AdmissionError(f"{phase}: discovery manifest targets are missing")
    bases = {
        item.get("base_device")
        for item in targets
        if isinstance(item, dict) and isinstance(item.get("base_device"), str)
    }
    if len(bases) != len(targets) or not bases:
        raise AdmissionError(f"{phase}: discovery manifest target identities are invalid")
    return frozenset(bases)


def _evidence_paths(phase: str) -> tuple[Path, Path]:
    if phase == "4.3B":
        from validate_stm32f2_phase4_3b_retained_evidence import (
            DEFAULT_BASELINE,
            DEFAULT_EVIDENCE_DIR,
        )

        return DEFAULT_EVIDENCE_DIR, DEFAULT_BASELINE
    spec = load_discovery_spec(phase)
    return spec.evidence_dir, spec.baseline_path


def _validate_retained(phase: str, evidence_dir: Path, baseline_path: Path) -> dict[str, Any]:
    if phase == "4.3B":
        from validate_stm32f2_phase4_3b_retained_evidence import validate

        return validate(evidence_dir=evidence_dir, baseline_path=baseline_path)
    return validate_bounded_evidence(
        phase=phase,
        evidence_dir=evidence_dir,
        baseline_path=baseline_path,
    )


def load_policy_spec(
    phase: str,
    *,
    registry_path: Path = DEFAULT_REGISTRY,
) -> STM32F2PolicySpec:
    registry = read_json(registry_path)
    if registry.get("schema_version") != 1 or registry.get("family") != FAMILY:
        raise AdmissionError("STM32F2 bounded policy registry header is invalid")
    batches = registry.get("batches")
    if not isinstance(batches, dict) or not isinstance(batches.get(phase), dict):
        raise AdmissionError(f"unregistered STM32F2 bounded policy phase: {phase}")
    raw = batches[phase]
    metadata = _require_mapping(raw.get("metadata_contract"), "metadata_contract")

    discovery_phase = raw.get("discovery_phase")
    admission_phase = raw.get("admission_phase")
    adapter_id = raw.get("adapter_id")
    baseline_name = raw.get("policy_baseline")
    if not all(isinstance(value, str) and value for value in (discovery_phase, admission_phase, adapter_id, baseline_name)):
        raise AdmissionError(f"{phase}: policy registry identity is incomplete")

    expected_candidate_count = raw.get("expected_candidate_count")
    expected_before = raw.get("expected_canonical_icpn_count_before")
    expected_exact = raw.get("expected_production_exact_icpn_count")
    expected_bases = raw.get("expected_production_base_device_count")
    if not all(isinstance(value, int) and value >= 0 for value in (expected_candidate_count, expected_before, expected_exact, expected_bases)):
        raise AdmissionError(f"{phase}: policy registry counts are invalid")

    historical = raw.get("historical_production_base_devices")
    if not isinstance(historical, list) or any(not isinstance(item, str) or not item for item in historical):
        raise AdmissionError(f"{phase}: historical Production Base Devices are invalid")
    if len(set(historical)) != len(historical):
        raise AdmissionError(f"{phase}: duplicate historical Production Base Device")

    family_counts_raw = _require_mapping(
        raw.get("expected_production_family_counts"),
        "expected_production_family_counts",
    )
    family_counts: dict[str, int] = {}
    for family, count in family_counts_raw.items():
        if not isinstance(family, str) or not isinstance(count, int) or count < 0:
            raise AdmissionError(f"{phase}: invalid expected Production family count")
        family_counts[family] = count

    allowed_suffixes = metadata.get("allowed_option_suffixes")
    if not isinstance(allowed_suffixes, list) or any(not isinstance(item, str) for item in allowed_suffixes):
        raise AdmissionError(f"{phase}: allowed option suffixes are invalid")
    target_config = metadata.get("openocd_target_config")
    if not isinstance(target_config, str) or not target_config:
        raise AdmissionError(f"{phase}: OpenOCD target config is invalid")

    policy_evidence = raw.get("policy_evidence", {})
    summary_extra = raw.get("summary_extra", {})
    if not isinstance(policy_evidence, dict) or not isinstance(summary_extra, dict):
        raise AdmissionError(f"{phase}: optional policy metadata is invalid")

    spec = STM32F2PolicySpec(
        phase=phase,
        discovery_phase=discovery_phase,
        admission_phase=admission_phase,
        adapter_id=adapter_id,
        policy_baseline_path=HERE / baseline_name,
        expected_candidate_count=expected_candidate_count,
        expected_canonical_icpn_count_before=expected_before,
        historical_production_base_devices=frozenset(historical),
        expected_production_exact_icpn_count=expected_exact,
        expected_production_base_device_count=expected_bases,
        expected_production_family_counts=family_counts,
        flash_by_code=_string_map(metadata.get("flash_by_code"), "flash_by_code"),
        temperature_by_code=_string_map(metadata.get("temperature_by_code"), "temperature_by_code"),
        package_by_code=_string_map(metadata.get("package_by_code"), "package_by_code"),
        pins_by_combination=_pins_map(metadata.get("pins_by_combination")),
        option_suffixes=frozenset(allowed_suffixes),
        target_config=target_config,
        policy_evidence=policy_evidence,
        summary_extra=summary_extra,
    )
    if spec.supported_base_devices & spec.historical_production_base_devices:
        raise AdmissionError(f"{phase}: policy targets overlap historical Production boundary")
    return spec


def _historical_canonical_rows(
    *,
    canonical_path: Path,
    spec: STM32F2PolicySpec,
) -> tuple[list[str], list[dict[str, str]]]:
    fields, rows = read_csv(canonical_path)
    if tuple(fields) != CANONICAL_FIELDS:
        raise AdmissionError("STM32F2 canonical CSV schema drifted")
    if any(row.get("family") != FAMILY for row in rows):
        raise AdmissionError("STM32F2 canonical CSV contains a foreign family")
    identities = [row.get("icpn", "") for row in rows]
    if len(identities) != len(set(identities)):
        raise AdmissionError("STM32F2 canonical CSV contains duplicate ICPNs")

    historical = [
        row for row in rows if row.get("base_device") in spec.historical_production_base_devices
    ]
    observed_bases = {row.get("base_device") for row in historical}
    if observed_bases != set(spec.historical_production_base_devices):
        raise AdmissionError(f"{spec.phase}: historical canonical Base Device boundary unavailable")
    if len(historical) != spec.expected_canonical_icpn_count_before:
        raise AdmissionError(f"{spec.phase}: historical canonical ICPN boundary unavailable")
    historical.sort(key=lambda row: (row["manufacturer"], row["base_device"], row["icpn"]))
    return fields, historical


def _production_snapshot(
    *,
    manifest_path: Path,
    historical_stm32f2_rows: list[dict[str, str]],
    spec: STM32F2PolicySpec,
) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise AdmissionError("Production manifest sources must be a list")

    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    saw_stm32f2 = False
    for source in sources:
        if not isinstance(source, dict):
            raise AdmissionError("Production manifest source must be an object")
        family = source.get("family")
        relative = source.get("path")
        declared = source.get("row_count")
        if not isinstance(family, str) or not isinstance(relative, str) or not isinstance(declared, int):
            raise AdmissionError("Production manifest source is incomplete")
        _, current_rows = read_csv((manifest_path.parent / relative).resolve())
        if len(current_rows) != declared or any(row.get("family") != family for row in current_rows):
            raise AdmissionError(f"{family}: Production source drifted")
        if family == FAMILY:
            saw_stm32f2 = True
            selected_rows = historical_stm32f2_rows
        else:
            selected_rows = current_rows
        if selected_rows:
            family_counts[family] = len(selected_rows)
            base_devices.update((family, row.get("base_device", "")) for row in selected_rows)

    if spec.expected_canonical_icpn_count_before > 0 and not saw_stm32f2:
        raise AdmissionError(f"{spec.phase}: current Production manifest lacks STM32F2 source")
    if family_counts != spec.expected_production_family_counts:
        raise AdmissionError(
            f"{spec.phase}: reconstructed Production family counts drifted: {family_counts}"
        )
    exact_count = sum(family_counts.values())
    if exact_count != spec.expected_production_exact_icpn_count:
        raise AdmissionError(f"{spec.phase}: reconstructed Production exact ICPN count drifted")
    if len(base_devices) != spec.expected_production_base_device_count:
        raise AdmissionError(f"{spec.phase}: reconstructed Production Base Device count drifted")
    return {
        "exact_icpn_count": exact_count,
        "base_device_count": len(base_devices),
        "family_exact_icpn_counts": family_counts,
        "stm32f2_exact_icpn_count": family_counts.get(FAMILY, 0),
    }


def _row_builder(spec: STM32F2PolicySpec):
    def build(candidate: dict[str, Any], fields: list[str]) -> dict[str, str]:
        return build_canonical_row(
            candidate,
            fields,
            supported_base_devices=spec.supported_base_devices,
            flash_by_code=spec.flash_by_code,
            package_by_code=spec.package_by_code,
            pins_by_combination=spec.pins_by_combination,
            temperature_by_code=spec.temperature_by_code,
            option_suffixes=spec.option_suffixes,
            target_config=spec.target_config,
        )

    return build


def build_policy_plan(
    *,
    phase: str,
    registry_path: Path = DEFAULT_REGISTRY,
    catalog_path: Path = DEFAULT_CATALOG,
    canonical_path: Path = DEFAULT_CANONICAL,
    production_manifest_path: Path = DEFAULT_PRODUCTION_MANIFEST,
) -> dict[str, Any]:
    spec = load_policy_spec(phase, registry_path=registry_path)
    evidence_dir, baseline_path = _evidence_paths(spec.discovery_phase)
    retained = _validate_retained(spec.discovery_phase, evidence_dir, baseline_path)
    if (
        retained.get("status") != "valid"
        or retained.get("active_exact_icpn_candidates") != spec.expected_candidate_count
    ):
        raise AdmissionError(f"{phase}: retained evidence is not policy-eligible")

    provenance = read_json(evidence_dir / "provenance.json")
    summary = read_json(evidence_dir / "pilot-summary.json")
    if provenance.get("scale_ready") is not True:
        raise AdmissionError(f"{phase}: retained evidence is not scale-ready")
    if provenance.get("canonical_dataset_admission") is not False:
        raise AdmissionError(f"{phase}: retained evidence unexpectedly authorizes admission")
    if provenance.get("production_admission_ready") is not False:
        raise AdmissionError(f"{phase}: retained evidence unexpectedly claims Production readiness")
    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError(f"{phase}: retained evidence requires evidence_id")

    _, catalog_rows = read_csv(catalog_path)
    fields, historical_rows = _historical_canonical_rows(
        canonical_path=canonical_path,
        spec=spec,
    )
    candidate_inputs = build_candidate_inputs(
        summary=summary,
        evidence_id=evidence_id,
        catalog_rows=catalog_rows,
        supported_base_devices=spec.supported_base_devices,
        expected_candidate_count=spec.expected_candidate_count,
    )
    plan = build_admission_plan(
        candidate_inputs=candidate_inputs,
        canonical_fields=fields,
        canonical_rows=historical_rows,
        source_provenance={
            "evidence_id": evidence_id,
            "repository": provenance.get("source_repository"),
            "executed_git_sha": provenance.get("executed_git_sha"),
            "workflow_run_id": provenance.get("workflow_run_id"),
            "artifact_id": provenance.get("artifact_id"),
            "artifact_zip_sha256": provenance.get("artifact_zip_sha256"),
            "evidence_manifest_sha256": file_sha256(evidence_dir / "manifest.json"),
        },
        input_bindings={
            "family_adapter": spec.adapter_id,
            "policy_registry": registry_path.name,
            "policy_registry_sha256": file_sha256(registry_path),
            "retained_evidence_directory": evidence_dir.name,
            "retained_evidence_baseline": baseline_path.name,
            "retained_evidence_baseline_sha256": file_sha256(baseline_path),
            "mapping_catalog": catalog_path.name,
            "mapping_catalog_sha256": file_sha256(catalog_path),
            "canonical_dataset": canonical_path.name,
            "production_manifest": production_manifest_path.name,
            "production_manifest_sha256": file_sha256(production_manifest_path),
        },
        row_builder=_row_builder(spec),
    )
    plan.update(
        {
            "phase": phase,
            "family": FAMILY,
            "adapter_id": spec.adapter_id,
            "discovery_phase": spec.discovery_phase,
            "admission_phase": spec.admission_phase,
            "canonical_dataset_admission": "deferred",
            "policy_ready_count": plan["decision_counts"]["admit"],
            "production_snapshot": _production_snapshot(
                manifest_path=production_manifest_path,
                historical_stm32f2_rows=historical_rows,
                spec=spec,
            ),
            "production_write_applied": False,
            "exact_icpn_admission_deferred": True,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_support_claimed": False,
            "full_stm32f2_surface_covered": False,
            "fail_closed": True,
        }
    )
    return plan


def policy_plan_is_clean(plan: dict[str, Any], *, spec: STM32F2PolicySpec) -> bool:
    candidates = plan.get("candidates")
    expected_decisions = {
        "admit": spec.expected_candidate_count,
        "already_present": 0,
        "manual_review_required": 0,
        "reject": 0,
    }
    return (
        plan_is_clean(plan)
        and plan.get("phase") == spec.phase
        and plan.get("family") == FAMILY
        and plan.get("adapter_id") == spec.adapter_id
        and plan.get("discovery_phase") == spec.discovery_phase
        and plan.get("admission_phase") == spec.admission_phase
        and plan.get("candidate_count") == spec.expected_candidate_count
        and plan.get("policy_ready_count") == spec.expected_candidate_count
        and plan.get("decision_counts") == expected_decisions
        and isinstance(candidates, list)
        and {item.get("base_device") for item in candidates} == set(spec.supported_base_devices)
        and plan.get("canonical_rows_before") == spec.expected_canonical_icpn_count_before
        and plan.get("canonical_dataset_admission") == "deferred"
        and plan.get("production_snapshot", {}).get("exact_icpn_count")
        == spec.expected_production_exact_icpn_count
        and plan.get("production_snapshot", {}).get("base_device_count")
        == spec.expected_production_base_device_count
        and plan.get("production_snapshot", {}).get("family_exact_icpn_counts")
        == spec.expected_production_family_counts
        and plan.get("production_write_applied") is False
        and plan.get("exact_icpn_admission_deferred") is True
        and plan.get("runtime_support_claimed") is False
        and plan.get("programming_algorithm_equivalence_claimed") is False
        and plan.get("fail_closed") is True
    )


def _metadata_contract(spec: STM32F2PolicySpec) -> dict[str, Any]:
    return {
        "flash_by_code": spec.flash_by_code,
        "temperature_by_code": spec.temperature_by_code,
        "package_by_code": spec.package_by_code,
        "pins_by_combination": {
            f"{pin}/{package}": pins
            for (pin, package), pins in sorted(spec.pins_by_combination.items())
        },
        "allowed_option_suffixes": sorted(spec.option_suffixes),
        "openocd_target_config": spec.target_config,
    }


def policy_summary(plan: dict[str, Any], *, spec: STM32F2PolicySpec) -> dict[str, Any]:
    candidates = plan["candidates"]
    summary: dict[str, Any] = {
        "schema_version": 1,
        "phase": spec.phase,
        "family": FAMILY,
        "adapter_id": spec.adapter_id,
        "evidence_id": plan["evidence_id"],
        "retained_evidence_directory": plan["inputs"]["retained_evidence_directory"],
        "candidate_count": plan["candidate_count"],
        "base_devices": sorted({item["base_device"] for item in candidates}),
        "policy_ready_exact_icpns": sorted(item["icpn"] for item in candidates),
        "decision_counts": plan["decision_counts"],
        "conflicts": plan["conflicts"],
        "metadata_contract": _metadata_contract(spec),
        "production_snapshot": plan["production_snapshot"],
        "production_write_applied": False,
        "exact_icpn_admission_deferred": True,
        "programming_algorithm_equivalence_claimed": False,
        "runtime_support_claimed": False,
        "full_stm32f2_surface_covered": False,
        "fail_closed": True,
    }
    if spec.policy_evidence:
        summary["policy_evidence"] = spec.policy_evidence
    summary.update(spec.summary_extra)
    return summary


def validate_policy(
    *,
    phase: str,
    baseline_path: Path | None = None,
    registry_path: Path = DEFAULT_REGISTRY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    spec = load_policy_spec(phase, registry_path=registry_path)
    plan = build_policy_plan(phase=phase, registry_path=registry_path)
    if not policy_plan_is_clean(plan, spec=spec):
        raise AdmissionError(f"{phase}: bounded policy plan is not clean")
    summary = policy_summary(plan, spec=spec)
    baseline_path = spec.policy_baseline_path if baseline_path is None else baseline_path
    if summary != read_json(baseline_path):
        raise AdmissionError(f"{phase}: policy baseline drifted")
    return plan, summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--skip-baseline-check",
        action="store_true",
        help="Generate a deterministic summary before the immutable policy baseline exists.",
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        spec = load_policy_spec(args.phase, registry_path=args.registry)
        plan = build_policy_plan(phase=args.phase, registry_path=args.registry)
        if not policy_plan_is_clean(plan, spec=spec):
            raise AdmissionError(f"{args.phase}: bounded policy plan is not clean")
        summary = policy_summary(plan, spec=spec)
        if not args.skip_baseline_check:
            baseline_path = spec.policy_baseline_path if args.baseline is None else args.baseline
            if summary != read_json(baseline_path):
                raise AdmissionError(f"{args.phase}: policy baseline drifted")
    except (AdmissionError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    payload = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
