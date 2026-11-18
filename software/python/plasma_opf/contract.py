"""Strict, side-effect-free OPF programming-selection contract.

Never infer executable Provider approval, hardware readiness or SAFE_OFF from
this parser. Bundle-source authorization and capability resolution are separate
future runtime gates (see docs/architecture/opf-architecture.md).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import math
import re
from typing import Any, Mapping

OPF_PROGRAMMING_SCHEMA = "plasma.opf.programming.v1"
_ALLOWED_KEYS = frozenset({"schema", "provider", "profile", "timeout_ms", "options"})
_PACKAGE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class OpfContractError(ValueError):
    """OPF programming descriptor is invalid; no executable grant is issued."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _positive_ms(value: object, code: str) -> int:
    if type(value) is not int or value <= 0:
        raise OpfContractError(code)
    return value


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    """PPU-owned timeout defaults; only one timeout is configurable by Bundle."""

    default_timeout_ms: int
    maximum_timeout_ms: int

    def __post_init__(self) -> None:
        default = _positive_ms(self.default_timeout_ms, "PPU_DEFAULT_TIMEOUT_INVALID")
        maximum = _positive_ms(self.maximum_timeout_ms, "PPU_MAXIMUM_TIMEOUT_INVALID")
        if default > maximum:
            raise OpfContractError("PPU_DEFAULT_EXCEEDS_MAXIMUM")


@dataclass(frozen=True, slots=True)
class ProgrammingSelection:
    """Validated syntax only; Package existence/trust is not established."""

    provider: str
    profile: str
    timeout_ms: int
    timeout_source: str
    options: Mapping[str, Any]


def _package_ref(value: object, code: str) -> str:
    if not isinstance(value, str) or not _PACKAGE_REF.fullmatch(value):
        raise OpfContractError(code)
    return value


def _json_value(value: object, *, depth: int = 0) -> None:
    """Restrict opaque Provider options to ordinary finite JSON values."""
    if depth > 32:
        raise OpfContractError("OPTIONS_JSON_DEPTH_EXCEEDED")
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise OpfContractError("OPTIONS_NON_JSON_VALUE")
        return
    if type(value) is list:
        for item in value:
            _json_value(item, depth=depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise OpfContractError("OPTIONS_NON_JSON_KEY")
            _json_value(item, depth=depth + 1)
        return
    raise OpfContractError("OPTIONS_NON_JSON_VALUE")


def parse_programming_selection(
    payload: Mapping[str, Any], *, policy: TimeoutPolicy
) -> ProgrammingSelection:
    """Parse a candidate selection without installing/running any Provider.

    The Runtime must still verify the exact authorized Active Asset Set,
    selected Package identities, per-Provider options schema, capabilities,
    Site resource fencing and real hardware state before an execution grant.
    """
    if not isinstance(payload, Mapping):
        raise OpfContractError("SELECTION_NOT_OBJECT")
    if any(type(key) is not str for key in payload):
        raise OpfContractError("SELECTION_KEY_INVALID")
    if set(payload) - _ALLOWED_KEYS:
        raise OpfContractError("SELECTION_UNKNOWN_FIELD")
    if payload.get("schema") != OPF_PROGRAMMING_SCHEMA:
        raise OpfContractError("SELECTION_SCHEMA_UNSUPPORTED")

    provider = _package_ref(payload.get("provider"), "PROVIDER_REF_INVALID")
    profile = _package_ref(payload.get("profile"), "PROFILE_REF_INVALID")

    source = "bundle_override" if "timeout_ms" in payload else "ppu_default"
    timeout = (
        _positive_ms(payload["timeout_ms"], "TIMEOUT_INVALID")
        if source == "bundle_override"
        else policy.default_timeout_ms
    )
    if timeout > policy.maximum_timeout_ms:
        raise OpfContractError("TIMEOUT_EXCEEDS_PPU_POLICY")

    options = payload.get("options", {})
    if type(options) is not dict:
        raise OpfContractError("OPTIONS_NOT_OBJECT")
    _json_value(options)
    return ProgrammingSelection(
        provider=provider,
        profile=profile,
        timeout_ms=timeout,
        timeout_source=source,
        options=deepcopy(options),
    )
