"""Canonical JSON integrity helpers for admission artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any


class DigestError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise DigestError("value is not canonical JSON") from exc


def canonical_digest(value: Mapping[str, Any], *, omit: Iterable[str] = ("artifact_digest",)) -> str:
    omitted = frozenset(omit)
    payload = {key: item for key, item in value.items() if key not in omitted}
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def verify_canonical_digest(
    value: Mapping[str, Any],
    *,
    field: str = "artifact_digest",
    omit: Iterable[str] | None = None,
) -> None:
    expected = value.get(field)
    excluded = tuple(omit) if omit is not None else (field,)
    actual = canonical_digest(value, omit=excluded)
    if expected != actual:
        raise DigestError(f"{field} mismatch")
