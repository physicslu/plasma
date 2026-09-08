"""Generic fail-closed mechanics for bounded device-catalog discovery batches.

This module owns batch-state mechanics that are independent of manufacturer/family
semantics: immutable batch-spec loading, historical Production-boundary binding,
lexicographic next-target selection, and manifest/selection drift checks.

Family adapters remain responsible for catalog-row qualification, identity parsing,
source authority, mapping rules, acquisition transport, and evidence extraction.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class BoundedDiscoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class BoundedBatchSpec:
    family: str
    phase: str
    scope: str
    manifest_path: Path
    baseline_path: Path
    evidence_dir: Path
    expected_production_bases: frozenset[str]
    expected_production_sha256: str


TTarget = TypeVar("TTarget")


def load_batch_spec(
    *,
    registry_path: Path,
    family: str,
    phase: str,
    root: Path,
) -> BoundedBatchSpec:
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise BoundedDiscoveryError("unsupported bounded-discovery registry schema_version")
    if payload.get("family") != family:
        raise BoundedDiscoveryError(f"bounded-discovery registry family mismatch: {family}")
    batches = payload.get("batches")
    if not isinstance(batches, dict):
        raise BoundedDiscoveryError("bounded-discovery registry requires batches")
    raw = batches.get(phase)
    if not isinstance(raw, dict):
        raise BoundedDiscoveryError(f"unknown bounded-discovery phase: {phase}")

    scope = raw.get("scope")
    manifest = raw.get("manifest")
    baseline = raw.get("baseline")
    evidence_dir = raw.get("evidence_dir")
    production_bases = raw.get("expected_production_bases")
    production_sha256 = raw.get("expected_production_sha256")
    if not isinstance(scope, str) or not scope.strip():
        raise BoundedDiscoveryError(f"{phase}: scope is required")
    if not all(isinstance(value, str) and value for value in (manifest, baseline, evidence_dir)):
        raise BoundedDiscoveryError(f"{phase}: manifest/baseline/evidence_dir are required")
    if not isinstance(production_bases, list) or not production_bases:
        raise BoundedDiscoveryError(f"{phase}: expected_production_bases are required")
    if not all(isinstance(value, str) and value for value in production_bases):
        raise BoundedDiscoveryError(f"{phase}: invalid expected_production_bases")
    if len(set(production_bases)) != len(production_bases):
        raise BoundedDiscoveryError(f"{phase}: duplicate expected Production Base Device")
    if not isinstance(production_sha256, str) or SHA256_RE.fullmatch(production_sha256) is None:
        raise BoundedDiscoveryError(f"{phase}: invalid expected_production_sha256")

    return BoundedBatchSpec(
        family=family,
        phase=phase,
        scope=scope.strip(),
        manifest_path=root / manifest,
        baseline_path=root / baseline,
        evidence_dir=root / evidence_dir,
        expected_production_bases=frozenset(production_bases),
        expected_production_sha256=production_sha256,
    )


def read_guarded_production_bases(
    path: Path,
    *,
    spec: BoundedBatchSpec,
    read_csv: Callable[[Path], tuple[list[str], list[dict[str, str]]]],
    canonical_csv_sha256: Callable[[list[str], list[dict[str, str]]], str],
    error_type: type[Exception] = BoundedDiscoveryError,
) -> set[str]:
    fields, rows = read_csv(path)
    identities = [row.get("icpn") for row in rows]
    if len(set(identities)) != len(identities):
        raise error_type("duplicate Production identity")

    historical = [
        row for row in rows if row.get("base_device") in spec.expected_production_bases
    ]
    observed_bases = {row.get("base_device", "") for row in historical}
    if observed_bases != set(spec.expected_production_bases):
        raise error_type(f"{spec.phase} Production Base Device boundary drifted")
    if canonical_csv_sha256(fields, historical) != spec.expected_production_sha256:
        raise error_type(f"{spec.phase} historical Production boundary is unavailable")
    return set(spec.expected_production_bases)


def deterministic_first_unadmitted_targets(
    *,
    family_rows: list[dict[str, str]],
    production_bases: set[str],
    expected_subfamilies: tuple[str, ...],
    base_from_row: Callable[[dict[str, str]], str],
    subfamily_from_row: Callable[[dict[str, str]], str],
    phase: str,
    error_type: type[Exception] = BoundedDiscoveryError,
) -> list[tuple[str, str]]:
    by_subfamily: dict[str, set[str]] = {}
    for row in family_rows:
        subfamily = subfamily_from_row(row)
        base = base_from_row(row)
        if base not in production_bases:
            by_subfamily.setdefault(subfamily, set()).add(base)

    observed_subfamilies = tuple(sorted(by_subfamily))
    if observed_subfamilies != expected_subfamilies:
        raise error_type(
            f"{phase} unadmitted subfamily set drifted: "
            f"expected={expected_subfamilies} observed={observed_subfamilies}"
        )
    return [
        (subfamily, sorted(by_subfamily[subfamily])[0])
        for subfamily in expected_subfamilies
    ]


def read_guarded_manifest(
    path: Path,
    *,
    spec: BoundedBatchSpec,
    expected_targets: list[tuple[str, str]],
    expected_subfamilies: tuple[str, ...],
    base_is_valid: Callable[[str], bool],
    validate_source_url: Callable[[str], None],
    source_url_for_base: Callable[[str], str],
    target_factory: Callable[[str, str, str, str], TTarget],
    error_type: type[Exception] = BoundedDiscoveryError,
) -> tuple[str, list[TTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION or payload.get("phase") != spec.phase:
        raise error_type(f"unsupported {spec.family} {spec.phase} discovery manifest")

    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise error_type(f"{spec.phase} discovery manifest requires pilot_id")
    if not isinstance(raw_targets, list) or len(raw_targets) != len(expected_subfamilies):
        raise error_type(
            f"{spec.phase} discovery requires exactly {len(expected_subfamilies)} targets"
        )

    targets: list[TTarget] = []
    observed: list[tuple[str, str]] = []
    for raw in raw_targets:
        if not isinstance(raw, dict):
            raise error_type(f"{spec.phase} target must be an object")
        subfamily = raw.get("subfamily")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if not isinstance(subfamily, str) or subfamily not in expected_subfamilies:
            raise error_type(f"invalid {spec.family} subfamily: {subfamily!r}")
        if not isinstance(base, str) or not base_is_valid(base):
            raise error_type(f"invalid {spec.family} base device: {base!r}")
        if not isinstance(source, str):
            raise error_type(f"{base}: source_url is required")
        validate_source_url(source)
        if source != source_url_for_base(base):
            raise error_type(f"{base}: source URL slug mismatch")
        if not isinstance(reason, str) or not reason.strip():
            raise error_type(f"{base}: selection_reason is required")
        observed.append((subfamily, base))
        targets.append(target_factory(subfamily, base, source, reason.strip()))

    if observed != expected_targets:
        raise error_type(
            f"{spec.phase} target selection drifted: expected={expected_targets} observed={observed}"
        )
    return pilot_id, targets


def decorate_discovery_summary(
    summary: dict[str, Any],
    *,
    spec: BoundedBatchSpec,
) -> dict[str, Any]:
    summary["phase"] = spec.phase
    summary["scope"] = spec.scope
    return summary


def discovery_is_clean(
    summary: dict[str, Any],
    *,
    spec: BoundedBatchSpec,
    base_clean: Callable[[dict[str, object]], bool],
) -> bool:
    return summary.get("phase") == spec.phase and base_clean(summary)
