"""Deployment-root contract for optional, immutable OpenOCD research evidence.

The installed Python wheel is NOT a data directory. Full Render deployments
declare PLASMA_RUNTIME_EVIDENCE_ROOT; source checkouts can derive a canonical
repository root from the Production Manifest. Slim installed PPU kits may
legitimately omit ALL source-only evidence, but partial/explicitly-required
evidence must never silently disappear.

This controls display metadata only, never programming/Job admission.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from .device_catalog import DeviceCatalogIntegrityError, default_catalog_manifest_path

RUNTIME_EVIDENCE_ROOT_ENV = "PLASMA_RUNTIME_EVIDENCE_ROOT"
_CANONICAL_MANIFEST_TAIL = ("data", "device-catalog", "production", "icpn-v1-manifest.json")


def default_runtime_evidence_root() -> Path | None:
    """Return an explicit full-evidence root or a validated source-tree root.

    Never infer a root from this module's __file__ (site-packages is unrelated
    to checkout paths). A noncanonical manifest layout requires an explicit
    evidence-root setting instead of a guessed parent directory.
    """
    configured = os.environ.get(RUNTIME_EVIDENCE_ROOT_ENV, "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise DeviceCatalogIntegrityError(
                f"{RUNTIME_EVIDENCE_ROOT_ENV} must be an absolute path"
            )
        return path.resolve()
    manifest = default_catalog_manifest_path().expanduser().resolve()
    if tuple(manifest.parts[-4:]) != _CANONICAL_MANIFEST_TAIL or not manifest.is_file():
        return None
    return manifest.parents[3]


def source_files_available(root: Path | None, files: Iterable[str]) -> bool:
    """Check complete source set; absent slim bundle is legal, partial is not.

    An explicitly configured root promises a full source-only environment.
    Its absence is always an error, not a quiet 'no candidate' interpretation.
    """
    required = tuple(files)
    if not required or len(required) != len(set(required)):
        raise DeviceCatalogIntegrityError("invalid required OpenOCD evidence file set")
    explicit = os.environ.get(RUNTIME_EVIDENCE_ROOT_ENV, "").strip()
    explicit_root = Path(explicit).expanduser().resolve() if explicit else None
    if root is None:
        if explicit_root is not None:
            raise DeviceCatalogIntegrityError(
                f"{RUNTIME_EVIDENCE_ROOT_ENV} is configured but root is unavailable"
            )
        return False
    statuses = []
    for rel in required:
        part = Path(rel)
        if part.is_absolute() or ".." in part.parts or "." in part.parts:
            raise DeviceCatalogIntegrityError("unsafe OpenOCD evidence path")
        statuses.append((rel, (root / part).is_file()))
    missing = tuple(name for name, present in statuses if not present)
    if missing and (len(missing) != len(required) or root == explicit_root):
        raise DeviceCatalogIntegrityError(
            "incomplete OpenOCD runtime evidence: " + ", ".join(missing)
        )
    return not missing
