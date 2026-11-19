"""Host-only, provider-neutral Programming Profile v2 and execution-plan contract.

This module does not admit a Bundle, execute a Provider, grant a Site lease,
control hardware or authorize any production use. The existing Runtime remains
the execution authority. In particular, a digest is identity, not approval.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Mapping

PROFILE_SCHEMA = "plasma.programming-profile.v2"
EXECUTION_CAPABILITIES_SCHEMA = "plasma.opf.provider-execution-capabilities.v1"
HARDWARE_CAPABILITIES_SCHEMA = "plasma.opf.hardware-action-capabilities.v1"
PLAN_SCHEMA = "plasma.opf.execution-plan.v1"
MAX_PROFILE_BYTES = 16384
MAX_PLAN_BYTES = 32768
MAX_STEPS = 32
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_OPERATIONS = ("erase", "program", "verify")
_HARDWARE_ACTIONS = {
    "power.set": {"domain_id", "state"},
    "power.wait_good": {"domain_id", "timeout_ms"},
    "reset.set": {"reset_id", "state"},
    "signal.set": {"signal_id", "state"},
    "signal.read": {"signal_id"},
    "delay": {"duration_ms"},
}


class ProfileV2Error(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise ProfileV2Error(code)


def _id(value: object, code: str) -> str:
    _need(type(value) is str and _ID.fullmatch(value) is not None, code)
    return value


def _sha(value: object, code: str) -> str:
    _need(type(value) is str and _SHA.fullmatch(value) is not None, code)
    return value


def _exact(obj: object, keys: set[str], code: str, optional: set[str] = frozenset()) -> dict:
    _need(type(obj) is dict and keys <= set(obj) and set(obj) <= keys | optional, code)
    return obj


def _pairs(items: list[tuple[str, Any]]) -> dict:
    result: dict = {}
    for key, value in items:
        _need(key not in result, "DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _json(value: Any, *, maximum: int) -> bytes:
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"),
                            ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise ProfileV2Error("NON_JSON_VALUE") from exc
    _need(len(result) <= maximum, "DOCUMENT_TOO_LARGE")
    # A depth bound prevents an accidental or hostile deeply nested settings tree.
    def check(item: Any, depth: int) -> None:
        _need(depth <= 12, "JSON_DEPTH_EXCEEDED")
        if type(item) is dict:
            _need(len(item) <= 64 and all(type(k) is str and len(k) <= 128
                                          for k in item), "JSON_OBJECT_INVALID")
            for child in item.values():
                check(child, depth + 1)
        elif type(item) is list:
            _need(len(item) <= 128, "JSON_ARRAY_TOO_LONG")
            for child in item:
                check(child, depth + 1)
        elif type(item) is str:
            _need(len(item) <= 4096, "JSON_STRING_TOO_LONG")
        else:
            _need(item is None or type(item) in (bool, int, float), "NON_JSON_VALUE")
    check(value, 0)
    return result


def _input(value: Mapping[str, Any] | bytes | str) -> dict:
    if isinstance(value, (str, bytes)):
        _need(len(value) <= MAX_PLAN_BYTES, "DOCUMENT_TOO_LARGE")
        try:
            value = json.loads(value, object_pairs_hook=_pairs,
                               parse_constant=lambda _: (_need(False, "NON_JSON_VALUE")))
        except (ValueError, UnicodeError, TypeError) as exc:
            if isinstance(exc, ProfileV2Error):
                raise
            raise ProfileV2Error("INVALID_JSON") from exc
    _need(type(value) is dict, "DOCUMENT_NOT_OBJECT")
    return value


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Frozen canonical bytes; callers cannot mutate data after hashing."""
    canonical_json: bytes
    sha256: str

    @property
    def data(self) -> dict:
        return json.loads(self.canonical_json)


def _snapshot(data: dict, *, maximum: int) -> Snapshot:
    raw = _json(data, maximum=maximum)
    return Snapshot(raw, hashlib.sha256(raw).hexdigest())


def _operations(raw: object) -> list[str]:
    _need(type(raw) is list and bool(raw)
          and all(type(x) is str for x in raw)
          and raw == [x for x in _OPERATIONS if x in raw]
          and raw != ["erase", "verify"], "OPERATIONS_INVALID")
    return raw


def _hardware_step(step: dict) -> None:
    action = step.get("action")
    _need(type(action) is str and action in _HARDWARE_ACTIONS, "HARDWARE_ACTION_UNKNOWN")
    _exact(step, {"id", "type", "action"} | _HARDWARE_ACTIONS[action],
           "HARDWARE_ACTION_FIELDS_INVALID")
    if action in ("power.set", "power.wait_good"):
        _id(step["domain_id"], "POWER_DOMAIN_INVALID")
    if action == "reset.set":
        _id(step["reset_id"], "RESET_ID_INVALID")
        _need(step["state"] in ("assert", "release")
              and type(step["state"]) is str, "RESET_STATE_INVALID")
    if action in ("signal.set", "signal.read"):
        _id(step["signal_id"], "SIGNAL_ID_INVALID")
    if action == "signal.set":
        _need(type(step["state"]) is str and step["state"] in
              ("active", "inactive", "high_z"), "SIGNAL_STATE_INVALID")
    if action == "power.set":
        _need(type(step["state"]) is str and step["state"] in ("on", "off"),
              "POWER_STATE_INVALID")
    if action in ("delay", "power.wait_good"):
        key = "duration_ms" if action == "delay" else "timeout_ms"
        _need(type(step[key]) is int and 0 < step[key] <= 60000,
              "HARDWARE_TIMEOUT_INVALID")


def parse_profile_v2(raw: Mapping[str, Any] | bytes | str) -> Snapshot:
    """Validate a saved local configuration. No approval or qualification gate."""
    data = _input(raw)
    _exact(data, {"schema", "identity", "provider", "workflow", "completion"},
           "PROFILE_FIELDS_INVALID", {"hardware"})
    _need(data["schema"] == PROFILE_SCHEMA, "PROFILE_SCHEMA_UNSUPPORTED")
    identity = _exact(data["identity"],
                      {"profile_id", "part_number", "manufacturer_icpn"},
                      "PROFILE_IDENTITY_INVALID")
    for value in identity.values():
        _id(value, "PROFILE_IDENTITY_INVALID")
    provider = _exact(data["provider"], {"id", "settings"}, "PROFILE_PROVIDER_INVALID")
    _id(provider["id"], "PROFILE_PROVIDER_INVALID")
    _need(type(provider["settings"]) is dict, "PROVIDER_SETTINGS_INVALID")
    completion = _exact(data["completion"], {"post_program_reset", "auto_run"},
                        "PROFILE_COMPLETION_INVALID")
    # v2's present contractual default: no post-job reset/run. This does not
    # prohibit a Provider's documented reset during programming.
    _need(completion["post_program_reset"] == "none"
          and completion["auto_run"] is False, "PROFILE_COMPLETION_UNSUPPORTED")
    hardware = data.get("hardware", {"power_source": "external"})
    _exact(hardware, {"power_source"}, "PROFILE_HARDWARE_INVALID")
    _need(type(hardware["power_source"]) is str and hardware["power_source"]
          in ("external", "ppu", "fixture"), "POWER_SOURCE_INVALID")
    flow = _exact(data["workflow"], {"steps"}, "WORKFLOW_INVALID")
    steps = flow["steps"]
    _need(type(steps) is list and 0 < len(steps) <= MAX_STEPS, "WORKFLOW_LENGTH_INVALID")
    seen: set[str] = set()
    provider_count = 0
    for step in steps:
        _need(type(step) is dict and "id" in step and "type" in step,
              "WORKFLOW_STEP_INVALID")
        sid = _id(step["id"], "WORKFLOW_STEP_ID_INVALID")
        _need(sid not in seen, "WORKFLOW_STEP_ID_DUPLICATE")
        seen.add(sid)
        if step["type"] == "provider.execute":
            _exact(step, {"id", "type", "procedure"}, "PROVIDER_STEP_INVALID",
                   {"operations"})
            _id(step["procedure"], "PROCEDURE_INVALID")
            if "operations" in step:
                _operations(step["operations"])
            provider_count += 1
        elif step["type"] == "hardware.action":
            _hardware_step(step)
            _need(not (hardware["power_source"] == "external"
                       and step["action"].startswith("power.")),
                  "EXTERNAL_POWER_CONTROL_DENIED")
        else:
            raise ProfileV2Error("STEP_TYPE_UNSUPPORTED")
    _need(provider_count > 0, "PROVIDER_STEP_REQUIRED")
    return _snapshot(data, maximum=MAX_PROFILE_BYTES)


def parse_provider_execution_capabilities(raw: Mapping[str, Any] | bytes | str) -> Snapshot:
    """Procedure descriptions complement, never replace, existing Bundle v3 capabilities."""
    data = _input(raw)
    _exact(data, {"schema", "provider_id", "procedures", "hardware_callback"},
           "CAPABILITIES_FIELDS_INVALID")
    _need(data["schema"] == EXECUTION_CAPABILITIES_SCHEMA, "CAPABILITIES_SCHEMA_UNSUPPORTED")
    _id(data["provider_id"], "CAPABILITIES_PROVIDER_INVALID")
    _need(data["hardware_callback"] is False, "HARDWARE_CALLBACK_NOT_IMPLEMENTED")
    items = data["procedures"]
    _need(type(items) is list and 0 < len(items) <= 32, "PROCEDURES_INVALID")
    ids: set[str] = set()
    for proc in items:
        _exact(proc, {"id", "operations", "segmented", "completion"},
               "PROCEDURE_FIELDS_INVALID")
        pid = _id(proc["id"], "PROCEDURE_ID_INVALID")
        _need(pid not in ids, "PROCEDURE_ID_DUPLICATE")
        ids.add(pid)
        _need(type(proc["operations"]) is list
              and all(type(o) is str and o in (*_OPERATIONS, "read")
                      for o in proc["operations"])
              and len(set(proc["operations"])) == len(proc["operations"]),
              "PROCEDURE_OPERATIONS_INVALID")
        _need(type(proc["segmented"]) is bool, "PROCEDURE_SEGMENTED_INVALID")
        final = _exact(proc["completion"], {"post_program_reset", "auto_run"},
                       "PROCEDURE_COMPLETION_INVALID")
        _need(type(final["post_program_reset"]) is str
              and final["post_program_reset"] in ("none", "reset")
              and type(final["auto_run"]) is bool, "PROCEDURE_COMPLETION_INVALID")
    return _snapshot(data, maximum=MAX_PROFILE_BYTES)


def parse_hardware_action_capabilities(raw: Mapping[str, Any] | bytes | str) -> Snapshot:
    """Declarative mock capability input, not trusted physical hardware evidence."""
    data = _input(raw)
    _exact(data, {"schema", "actions", "power_domains", "reset_ids", "signal_ids"},
           "HARDWARE_CAPABILITIES_INVALID")
    _need(data["schema"] == HARDWARE_CAPABILITIES_SCHEMA, "HARDWARE_SCHEMA_UNSUPPORTED")
    for key, permitted in (("actions", set(_HARDWARE_ACTIONS)),
                           ("power_domains", None), ("reset_ids", None),
                           ("signal_ids", None)):
        value = data[key]
        _need(type(value) is list and len(value) <= 64
              and all(type(x) is str and _ID.fullmatch(x) for x in value)
              and len(set(value)) == len(value)
              and (permitted is None or set(value) <= permitted),
              "HARDWARE_CAPABILITIES_INVALID")
    return _snapshot(data, maximum=MAX_PROFILE_BYTES)


def build_execution_plan(
    profile: Snapshot, provider_capabilities: Snapshot, *,
    job_id: str, site_id: int, job_binding_sha256: str,
    asset_set_sha256: str, hardware_capabilities: Snapshot | None = None,
) -> Snapshot:
    """Pure plan: does not resolve/trust Bundle bytes, claim hardware or execute."""
    _id(job_id, "JOB_ID_INVALID")
    _need(type(site_id) is int and 1 <= site_id <= 8, "SITE_ID_INVALID")
    _sha(job_binding_sha256, "JOB_BINDING_SHA_INVALID")
    _sha(asset_set_sha256, "ASSET_SET_SHA_INVALID")
    verified_profile = parse_profile_v2(profile.canonical_json)
    verified_caps = parse_provider_execution_capabilities(provider_capabilities.canonical_json)
    _need(verified_profile.sha256 == profile.sha256, "PROFILE_SNAPSHOT_CHANGED")
    _need(verified_caps.sha256 == provider_capabilities.sha256,
          "CAPABILITIES_SNAPSHOT_CHANGED")
    profile_obj = verified_profile.data
    caps = verified_caps.data
    _need(caps["provider_id"] == profile_obj["provider"]["id"], "PROVIDER_ID_MISMATCH")
    procs = {p["id"]: p for p in caps["procedures"]}
    verified_hw = (parse_hardware_action_capabilities(hardware_capabilities.canonical_json)
                   if hardware_capabilities is not None else None)
    if verified_hw is not None:
        _need(verified_hw.sha256 == hardware_capabilities.sha256,
              "HARDWARE_SNAPSHOT_CHANGED")
    hardware = verified_hw.data if verified_hw is not None else None
    steps = profile_obj["workflow"]["steps"]
    provider_steps = [s for s in steps if s["type"] == "provider.execute"]
    if len(provider_steps) > 1:
        _need(all(procs.get(s["procedure"], {}).get("segmented") is True
                  for s in provider_steps), "PROVIDER_SEGMENTATION_UNSUPPORTED")
    for step in steps:
        if step["type"] == "provider.execute":
            proc = procs.get(step["procedure"])
            _need(proc is not None, "PROCEDURE_UNSUPPORTED")
            _need("operations" not in step or set(step["operations"]) <= set(proc["operations"]),
                  "PROCEDURE_OPERATIONS_UNSUPPORTED")
            _need(proc["completion"]["post_program_reset"] == "none"
                  and proc["completion"]["auto_run"] is False,
                  "PROVIDER_COMPLETION_POLICY_CONFLICT")
        else:
            _need(hardware is not None and step["action"] in hardware["actions"],
                  "HARDWARE_ACTION_UNSUPPORTED")
            action = step["action"]
            if action.startswith("power."):
                _need(step["domain_id"] in hardware["power_domains"],
                      "POWER_DOMAIN_UNSUPPORTED")
            elif action == "reset.set":
                _need(step["reset_id"] in hardware["reset_ids"], "RESET_UNSUPPORTED")
            elif action.startswith("signal."):
                _need(step["signal_id"] in hardware["signal_ids"], "SIGNAL_UNSUPPORTED")
    document = {
        "schema": PLAN_SCHEMA,
        "job": {"job_id": job_id, "site_id": site_id,
                "job_binding_sha256": job_binding_sha256,
                "asset_set_sha256": asset_set_sha256},
        "profile_snapshot_sha256": profile.sha256,
        "provider_capabilities_sha256": provider_capabilities.sha256,
        "hardware_capabilities_sha256":
            hardware_capabilities.sha256 if hardware_capabilities is not None else None,
        "provider_id": profile_obj["provider"]["id"],
        "provider_settings": profile_obj["provider"]["settings"],
        "steps": steps,
        "completion": profile_obj["completion"],
    }
    return _snapshot(document, maximum=MAX_PLAN_BYTES)
