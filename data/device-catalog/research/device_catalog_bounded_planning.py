"""Generic planning/materialization mechanics for bounded discovery batches.

Planning is read-only with respect to canonical Production. Materialization may only
write research registry/manifest state after rebuilding the plan against current
inputs and proving that the plan has not drifted.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable

PLAN_SCHEMA_VERSION = 1
PHASE_RE = re.compile(r"^[0-9]+(?:\.[0-9]+)+[A-Z][A-Z0-9]*$")


class BoundedPlanningError(RuntimeError):
    pass


def validate_phase(phase: str) -> str:
    if not isinstance(phase, str) or PHASE_RE.fullmatch(phase) is None:
        raise BoundedPlanningError(f"invalid bounded-discovery phase: {phase!r}")
    return phase


def validate_acquisition_date(value: str) -> str:
    if not isinstance(value, str):
        raise BoundedPlanningError("acquisition date must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise BoundedPlanningError("acquisition date must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise BoundedPlanningError("acquisition date must be canonical YYYY-MM-DD")
    return value


def read_registry_payload(path: Path, *, family: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoundedPlanningError(f"{path}: cannot read bounded-discovery registry") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise BoundedPlanningError("unsupported bounded-discovery registry schema_version")
    if payload.get("family") != family:
        raise BoundedPlanningError(f"bounded-discovery registry family mismatch: {family}")
    if not isinstance(payload.get("batches"), dict):
        raise BoundedPlanningError("bounded-discovery registry requires batches")
    return payload


def require_phase_available(registry: dict[str, Any], *, phase: str) -> None:
    validate_phase(phase)
    batches = registry.get("batches")
    if not isinstance(batches, dict):
        raise BoundedPlanningError("bounded-discovery registry requires batches")
    if phase in batches:
        raise BoundedPlanningError(f"bounded-discovery phase is already registered: {phase}")


def _relative_path(value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise BoundedPlanningError(f"plan {field} must be a non-empty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise BoundedPlanningError(f"plan {field} escapes the research root")
    return path


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def read_plan(path: Path, *, family: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BoundedPlanningError(f"{path}: cannot read bounded-discovery plan") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise BoundedPlanningError("unsupported bounded-discovery plan schema_version")
    if payload.get("family") != family:
        raise BoundedPlanningError(f"bounded-discovery plan family mismatch: {family}")
    validate_phase(payload.get("phase"))
    validate_acquisition_date(payload.get("acquisition_date"))
    if not isinstance(payload.get("scope"), str) or not payload["scope"].strip():
        raise BoundedPlanningError("bounded-discovery plan requires scope")
    if not isinstance(payload.get("registry_entry"), dict):
        raise BoundedPlanningError("bounded-discovery plan requires registry_entry")
    if not isinstance(payload.get("manifest"), dict):
        raise BoundedPlanningError("bounded-discovery plan requires manifest")
    return payload


PlanRebuilder = Callable[..., dict[str, Any]]


def materialize_plan(
    *,
    plan_path: Path,
    registry_path: Path,
    root: Path,
    family: str,
    rebuild_plan: PlanRebuilder,
) -> dict[str, Any]:
    """Materialize research registry/manifest state after a current-state replay.

    This function never writes canonical Production. It deliberately writes the
    manifest before the registry; if interrupted, a retry can recover from an
    identical orphan manifest while a mismatched orphan fails closed.
    """

    plan = read_plan(plan_path, family=family)
    phase = str(plan["phase"])
    acquisition_date = str(plan["acquisition_date"])
    scope = str(plan["scope"])

    expected = rebuild_plan(
        phase=phase,
        acquisition_date=acquisition_date,
        scope=scope,
        registry_path=registry_path,
    )
    if plan != expected:
        raise BoundedPlanningError(
            f"{phase} plan no longer matches current Production/catalog/registry state"
        )

    registry = read_registry_payload(registry_path, family=family)
    require_phase_available(registry, phase=phase)
    entry = plan["registry_entry"]
    manifest = plan["manifest"]
    manifest_rel = _relative_path(entry.get("manifest"), field="manifest")
    baseline_rel = _relative_path(entry.get("baseline"), field="baseline")
    evidence_rel = _relative_path(entry.get("evidence_dir"), field="evidence_dir")
    manifest_path = root / manifest_rel
    baseline_path = root / baseline_rel
    evidence_dir = root / evidence_rel

    if baseline_path.exists():
        raise BoundedPlanningError(f"{phase} baseline path already exists: {baseline_path}")
    if evidence_dir.exists():
        raise BoundedPlanningError(f"{phase} evidence directory already exists: {evidence_dir}")

    if manifest_path.exists():
        try:
            observed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BoundedPlanningError(
                f"{phase} existing manifest is unreadable: {manifest_path}"
            ) from exc
        if observed_manifest != manifest:
            raise BoundedPlanningError(
                f"{phase} existing manifest conflicts with the planned transaction"
            )
    else:
        write_json_atomic(manifest_path, manifest)

    updated_registry = dict(registry)
    updated_batches = dict(registry["batches"])
    updated_batches[phase] = entry
    updated_registry["batches"] = updated_batches
    write_json_atomic(registry_path, updated_registry)

    return {
        "status": "materialized",
        "family": family,
        "phase": phase,
        "registry": str(registry_path),
        "manifest": str(manifest_path),
        "canonical_dataset_admission": False,
    }
