"""The trusted per-Job execution context an interface may act on.

``RuntimeJobContext`` is the single channel through which SiteWorker hands one
Job attempt's authority to the selected interface. It is built only by the PPU
Runtime, never from ``JobRequest.metadata``: what the Manager claims reaches an
interface only after SiteManager has admitted it under the PPU execution lease.

Exactly one authorization source may be present:

``admitted_job_binding``
    The SiteManager-verified Job Binding (OpenOCD, Mock).
``trusted_provider``
    The Runtime-resolved trusted Provider Action (Package Provider).

The two are not interchangeable, and an interface handed an authorization
source it does not consume must refuse rather than execute. An operation that
requires a Binding and has none is likewise refused: a missing Binding is never
replaced by a default range or a default operations list.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError


def freeze(value: Any) -> Any:
    """Return a deep, read-only snapshot of ``value``.

    ``frozen=True`` protects only a dataclass's own attributes, so every nested
    container is copied and made read-only here. An interface therefore cannot
    mutate what the Runtime admitted, and a later change to the Runtime's own
    object cannot change what was already bound to the attempt.
    """
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value: Any) -> Any:
    """Return a plain mutable copy, for handing to code outside this boundary.

    The frozen snapshot is the interface's own view. Collaborators reached
    through a trusted callable (the C-3 Site Worker client, for example) are
    given ordinary containers so the snapshot cannot leak read-only proxies
    into code that does not expect them.
    """
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (bytes, bytearray, memoryview, str)):
        return value if isinstance(value, (bytes, str)) else bytes(value)
    if isinstance(value, (set, frozenset)):
        return {thaw(item) for item in value}
    if isinstance(value, Sequence):
        return [thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class RuntimeJobContext:
    """One Job attempt's trusted context. Built by the PPU Runtime only."""

    job_id: str
    site_id: int
    deadline_monotonic: float
    active_asset_set: Mapping[str, Any] | None = None
    admitted_job_binding: Mapping[str, Any] | None = None
    trusted_provider: Any | None = None

    def __post_init__(self) -> None:
        if type(self.job_id) is not str or not self.job_id:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                              "RUNTIME_CONTEXT_JOB_ID_INVALID")
        if type(self.site_id) is not int or self.site_id < 1:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                              "RUNTIME_CONTEXT_SITE_INVALID")
        if (type(self.deadline_monotonic) not in (int, float)
                or not math.isfinite(self.deadline_monotonic)):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT,
                              "RUNTIME_CONTEXT_DEADLINE_INVALID")
        if self.admitted_job_binding is not None and self.trusted_provider is not None:
            # A Job never carries two authorization sources. An admitted Job
            # Binding and a trusted Provider Action grant different things and
            # must never stand in for one another.
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "RUNTIME_CONTEXT_AUTHORIZATION_NOT_EXCLUSIVE")
        if (self.admitted_job_binding is not None
                and not isinstance(self.admitted_job_binding, Mapping)):
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "RUNTIME_CONTEXT_BINDING_INVALID")
        if self.active_asset_set is not None and not isinstance(self.active_asset_set, Mapping):
            raise PlasmaError(ErrorCode.OPERATION_UNSUPPORTED,
                              "RUNTIME_CONTEXT_ACTIVE_SET_INVALID")
        object.__setattr__(self, "active_asset_set", freeze(self.active_asset_set))
        object.__setattr__(self, "admitted_job_binding", freeze(self.admitted_job_binding))

    @property
    def has_authorization(self) -> bool:
        return self.admitted_job_binding is not None or self.trusted_provider is not None

    def matches(self, job_id: str, site_id: int) -> bool:
        """True only for the Job and Site this context was built for."""
        return self.job_id == job_id and self.site_id == site_id
