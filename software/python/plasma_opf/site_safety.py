"""Structured C-3 Site Worker safety evidence: the ONE judgment.

``scripts/ppu_site_worker.py`` (``_safety``) states what happened to a Site
when a Job ended without a PASS (docs/architecture/site-safety-evidence-v1.md).
The PPU Runtime (``plasma_server.site_manager``, Reservation release) and the
Manager (``plasma_manager.programming``, Receipt) judge that statement with
this function, so the two can never disagree about which statement is trusted.
"""
from __future__ import annotations

from typing import Any

SITE_SAFETY_SCHEMA = "plasma.ppu.site-safety.v1"
PRE_HARDWARE_DENIED = "PRE_HARDWARE_DENIED"
FAILED_SAFE_OFF_VERIFIED = "FAILED_SAFE_OFF_VERIFIED"
_SITE_SAFETY_PREFIX = {PRE_HARDWARE_DENIED: "TRANSPORT_DENIED:",
                       FAILED_SAFE_OFF_VERIFIED: "OPERATION_FAILED_SAFE:"}


def site_safety_class(context: Any, *, job_id: Any, site_id: Any,
                      operation: Any) -> str | None:
    """PRE_HARDWARE_DENIED / FAILED_SAFE_OFF_VERIFIED, or None (unproven).

    Trusted only when the Worker's structured statement names exactly this
    Job, Site, operation and the ``run`` stage, the outcome is explicitly
    known, and the refusal code matches the statement's class. A code text
    alone (e.g. ``TRANSPORT_DENIED:``) proves nothing.
    """
    if not isinstance(context, dict) or context.get("outcome_unknown") is not False:
        return None
    safety = context.get("site_worker_safety")
    if not isinstance(safety, dict) or safety.get("schema") != SITE_SAFETY_SCHEMA:
        return None
    kind, code = safety.get("class"), safety.get("code")
    prefix = _SITE_SAFETY_PREFIX.get(kind) if type(kind) is str else None
    if (prefix is None or type(code) is not str or not code
            or context.get("site_worker_code") != prefix + code):
        return None
    if context.get("site_worker_stage") != "run" or safety.get("stage") != "run":
        return None
    if (type(job_id) is not str or safety.get("job_id") != job_id
            or context.get("job_id") != job_id):
        return None
    if (type(site_id) is not int or type(safety.get("site")) is not int
            or safety.get("site") != site_id or context.get("site_id") != site_id):
        return None
    if (type(operation) is not str or safety.get("operation") != operation
            or context.get("operation") != operation):
        return None
    touched, safe_off = safety.get("hardware_touched"), safety.get("safe_off")
    if kind == PRE_HARDWARE_DENIED:
        return kind if touched is False and safe_off is None else None
    return kind if touched is True and safe_off is True else None
