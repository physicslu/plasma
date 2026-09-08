#!/usr/bin/env python3
"""Compare a live STM32F2 bounded-discovery shadow run with retained evidence.

This tool separates source-data drift from software/contract regression. It never
writes canonical Production, registry state, baselines, or retained evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from stm32f2_bounded_discovery import HERE, load_spec, main_for_phase
from stm32f2_phase4_3b_discovery import TARGET_CONFIG

EVIDENCE_ROOT = (HERE / "evidence").resolve()


class ShadowValidationError(RuntimeError):
    pass


def _require_dict(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShadowValidationError(message)
    return value


def _require_list(value: object, message: str) -> list[Any]:
    if not isinstance(value, list):
        raise ShadowValidationError(message)
    return value


def _string_set(value: object, message: str) -> set[str]:
    items = _require_list(value, message)
    if not all(isinstance(item, str) and item for item in items):
        raise ShadowValidationError(message)
    return set(items)


def _excluded_part_numbers(evidence: dict[str, Any]) -> set[str]:
    raw = _require_list(
        evidence.get("excluded_non_active_part_numbers"),
        "excluded_non_active_part_numbers must be a list",
    )
    values: set[str] = set()
    for item in raw:
        if isinstance(item, str) and item:
            values.add(item)
            continue
        if isinstance(item, dict):
            for key in ("icpn", "part_number"):
                value = item.get(key)
                if isinstance(value, str) and value:
                    values.add(value)
                    break
            else:
                values.add(json.dumps(item, sort_keys=True))
            continue
        raise ShadowValidationError("invalid excluded lifecycle record")
    return values


def _result_index(
    summary: dict[str, Any],
) -> tuple[list[tuple[str, str]], dict[tuple[str, str], dict[str, Any]]]:
    results = _require_list(summary.get("results"), "summary results are missing")
    order: list[tuple[str, str]] = []
    index: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in results:
        result = _require_dict(raw, "summary result must be an object")
        subfamily = result.get("subfamily")
        base_device = result.get("base_device")
        if not isinstance(subfamily, str) or not isinstance(base_device, str):
            raise ShadowValidationError("summary result identity is invalid")
        key = (subfamily, base_device)
        if key in index:
            raise ShadowValidationError(f"duplicate shadow result: {key}")
        order.append(key)
        index[key] = result
    return order, index


def compare_shadow_summaries(
    *,
    phase: str,
    live: dict[str, Any],
    retained: dict[str, Any],
) -> dict[str, Any]:
    structural_errors: list[str] = []
    source_drift: list[dict[str, Any]] = []

    if live.get("phase") != phase:
        structural_errors.append("live phase mismatch")
    if retained.get("phase") != phase:
        structural_errors.append("retained phase mismatch")

    try:
        live_order, live_index = _result_index(live)
        retained_order, retained_index = _result_index(retained)
    except ShadowValidationError as exc:
        return {
            "status": "software_regression",
            "phase": phase,
            "structural_errors": [str(exc)],
            "source_drift": [],
            "production_admission_ready": False,
        }

    if live_order != retained_order:
        structural_errors.append(
            f"target order/identity drift: retained={retained_order} live={live_order}"
        )
    if live.get("acquisition_transport") != "chromium_rendered_dom":
        structural_errors.append("live acquisition transport is not Chromium rendered DOM")

    claims = live.get("claims")
    if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
        structural_errors.append("live discovery authority claims are not all false")

    mapping_summary = live.get("canonical_mapping")
    if (
        not isinstance(mapping_summary, dict)
        or mapping_summary.get("ambiguous") != 0
        or mapping_summary.get("unmapped") != 0
        or mapping_summary.get("unique") != len(live_order)
    ):
        structural_errors.append("live aggregate OpenOCD mapping is not uniquely bounded")

    live_active_total = 0
    live_excluded_total = 0

    for key in retained_order:
        retained_result = retained_index[key]
        live_result = live_index.get(key)
        if live_result is None:
            continue
        if live_result.get("acquisition_status") != "success":
            structural_errors.append(f"{key[1]} acquisition did not succeed")
            continue
        if live_result.get("source_url") != retained_result.get("source_url"):
            structural_errors.append(f"{key[1]} authoritative source URL drifted")

        live_mapping = live_result.get("canonical_mapping")
        if (
            not isinstance(live_mapping, dict)
            or live_mapping.get("status") != "unique"
            or live_mapping.get("target_configs") != [TARGET_CONFIG]
        ):
            structural_errors.append(f"{key[1]} target mapping is not uniquely bounded")

        try:
            live_evidence = _require_dict(
                live_result.get("evidence"), f"{key[1]} live evidence is missing"
            )
            retained_evidence = _require_dict(
                retained_result.get("evidence"), f"{key[1]} retained evidence is missing"
            )
            live_active = _string_set(
                live_evidence.get("exact_icpns"), f"{key[1]} live exact ICPNs are invalid"
            )
            retained_active = _string_set(
                retained_evidence.get("exact_icpns"),
                f"{key[1]} retained exact ICPNs are invalid",
            )
            live_excluded = _excluded_part_numbers(live_evidence)
            retained_excluded = _excluded_part_numbers(retained_evidence)
            mappings = _require_list(
                live_result.get("candidate_mappings"),
                f"{key[1]} live candidate mappings are missing",
            )
        except ShadowValidationError as exc:
            structural_errors.append(str(exc))
            continue

        live_active_total += len(live_active)
        live_excluded_total += len(live_excluded)

        mapped_icpns: set[str] = set()
        for mapping_raw in mappings:
            if not isinstance(mapping_raw, dict):
                structural_errors.append(f"{key[1]} invalid candidate mapping")
                continue
            mapping = mapping_raw
            icpn = mapping.get("icpn")
            if not isinstance(icpn, str) or not icpn:
                structural_errors.append(f"{key[1]} candidate mapping lacks ICPN")
                continue
            mapped_icpns.add(icpn)
            if (
                mapping.get("status") != "unique"
                or mapping.get("target_configs") != [TARGET_CONFIG]
            ):
                structural_errors.append(f"{icpn} no longer maps uniquely to STM32F2")
        if mapped_icpns != live_active:
            structural_errors.append(
                f"{key[1]} live exact ICPNs and mapping set disagree"
            )

        added_active = sorted(live_active - retained_active)
        removed_active = sorted(retained_active - live_active)
        added_excluded = sorted(live_excluded - retained_excluded)
        removed_excluded = sorted(retained_excluded - live_excluded)
        if added_active or removed_active or added_excluded or removed_excluded:
            source_drift.append(
                {
                    "subfamily": key[0],
                    "base_device": key[1],
                    "active_exact_icpns_added": added_active,
                    "active_exact_icpns_removed": removed_active,
                    "non_active_part_numbers_added": added_excluded,
                    "non_active_part_numbers_removed": removed_excluded,
                }
            )

    if live.get("active_exact_icpn_candidates") != live_active_total:
        structural_errors.append("live aggregate active ICPN count is inconsistent")
    if live.get("excluded_non_active_part_numbers") != live_excluded_total:
        structural_errors.append("live aggregate lifecycle exclusion count is inconsistent")

    classification = (
        "software_regression"
        if structural_errors
        else "source_drift"
        if source_drift
        else "clean"
    )
    return {
        "status": classification,
        "phase": phase,
        "target_count": len(live_order),
        "structural_errors": structural_errors,
        "source_drift": source_drift,
        "production_admission_ready": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ShadowValidationError(f"{path}: expected JSON object")
    return payload


def _ensure_shadow_output(path: Path) -> None:
    resolved = path.resolve()
    if resolved == EVIDENCE_ROOT or EVIDENCE_ROOT in resolved.parents:
        raise ShadowValidationError(
            "live shadow output must not be written under retained evidence/"
        )


def run_live_shadow(
    *,
    phase: str,
    output: Path,
    report_path: Path | None = None,
    timeout: float = 75.0,
    delay: float = 2.0,
    headless: bool = False,
) -> tuple[int, dict[str, Any]]:
    spec = load_spec(phase)
    _ensure_shadow_output(output)
    if report_path is not None:
        _ensure_shadow_output(report_path)

    argv = [
        "--output",
        str(output),
        "--timeout",
        str(timeout),
        "--delay",
        str(delay),
    ]
    if headless:
        argv.append("--headless")
    acquisition_status = main_for_phase(phase, argv)
    if not output.exists():
        raise ShadowValidationError("live shadow acquisition produced no summary")

    live = _read_json(output)
    retained = _read_json(spec.evidence_dir / "pilot-summary.json")
    report = compare_shadow_summaries(phase=phase, live=live, retained=retained)
    report["acquisition_exit_code"] = acquisition_status
    if acquisition_status != 0 and report["status"] != "software_regression":
        report["status"] = "software_regression"
        report["structural_errors"].append(
            f"generic discovery exited with status {acquisition_status}"
        )

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if report["status"] == "clean":
        return 0, report
    if report["status"] == "source_drift":
        return 2, report
    return 1, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an STM32F2 live shadow against retained evidence."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--phase", required=True)
    compare_parser.add_argument("--live-summary", type=Path, required=True)
    compare_parser.add_argument("--retained-summary", type=Path)
    compare_parser.add_argument("--report", type=Path)

    acquire_parser = subparsers.add_parser("acquire")
    acquire_parser.add_argument("--phase", required=True)
    acquire_parser.add_argument("--output", type=Path, required=True)
    acquire_parser.add_argument("--report", type=Path)
    acquire_parser.add_argument("--timeout", type=float, default=75.0)
    acquire_parser.add_argument("--delay", type=float, default=2.0)
    acquire_parser.add_argument("--headless", action="store_true")

    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.command == "compare":
            spec = load_spec(args.phase)
            retained_path = (
                args.retained_summary
                if args.retained_summary is not None
                else spec.evidence_dir / "pilot-summary.json"
            )
            report = compare_shadow_summaries(
                phase=args.phase,
                live=_read_json(args.live_summary),
                retained=_read_json(retained_path),
            )
            if args.report is not None:
                _ensure_shadow_output(args.report)
                args.report.parent.mkdir(parents=True, exist_ok=True)
                args.report.write_text(
                    json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0 if report["status"] == "clean" else 2 if report["status"] == "source_drift" else 1

        status, report = run_live_shadow(
            phase=args.phase,
            output=args.output,
            report_path=args.report,
            timeout=args.timeout,
            delay=args.delay,
            headless=args.headless,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return status
    except (OSError, json.JSONDecodeError, ShadowValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
