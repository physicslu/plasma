"""Host-only OPF admission into the existing C-3 Site Session boundary.

The trusted Runtime supplies the Job and device-side observation. This module
does not select an executor or switch the production Flash route.
"""
from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

from plasma_opf import TimeoutPolicy, parse_programming_selection

import ppu_provider_contract


@dataclass(frozen=True)
class BoundSession:
    session_id: str
    job_id: str
    route: ppu_provider_contract.ProviderRoute
    timeout_ms: int
    timeout_source: str
    deadline_monotonic: float


def open_provider_job_session(
    client: Any, *, product_root: Path, asset_set_sha256: str,
    selection: Mapping[str, Any], policy: TimeoutPolicy,
    job_id: str, target: str, operation: str, site_id: int,
    image_size: int, hardware: Mapping[str, Any],
    job_deadline_monotonic: float, job_timeout_s: float,
) -> BoundSession:
    """Resolve once, then pin the exact route and the Job's existing deadline.

    A caller must already own the PPU Job lease. The C-3 Worker checks that
    lease, per-Site ownership, FPGA identity and safety state at admission.
    """
    selected = parse_programming_selection(selection, policy=policy)
    route = ppu_provider_contract.resolve(
        product_root, asset_set_sha256=asset_set_sha256, target=target,
        provider=selected.provider, profile=selected.profile,
        operation=operation, site_id=site_id, image_size=image_size,
        hardware=hardware, options=selected.options)
    if (not math.isfinite(job_deadline_monotonic)
            or job_timeout_s != selected.timeout_ms / 1000.0):
        raise ValueError("JOB_TIMEOUT_BINDING_MISMATCH")
    deadline = job_deadline_monotonic
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ValueError("JOB_DEADLINE_EXPIRED")
    # C-3's integer max is only an admission ceiling; its effective expiry is
    # the same absolute monotonic deadline used by the PPU Job.
    route_wire = {key: value for key, value in asdict(route).items()
                  if key != "options_json"}
    opened = client.open_job_session(
        job_id=job_id, sites=[site_id], max_runtime_s=math.ceil(remaining),
        provider_route=route_wire,
        deadline_monotonic=deadline)
    if (opened.get("provider_route") != route_wire
            or opened.get("deadline_monotonic") != deadline):
        if isinstance(opened.get("session_id"), str):
            client.call("close_session", session_id=opened["session_id"])
        raise ValueError("SESSION_BINDING_MISMATCH")
    return BoundSession(opened["session_id"], job_id, route,
                        selected.timeout_ms, selected.timeout_source, deadline)
