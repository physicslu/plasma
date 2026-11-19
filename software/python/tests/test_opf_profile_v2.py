"""Host-only Gate 1 tests. No Provider processes, sockets, Site hardware or DUT.

The mock vendor Provider intentionally uses no OpenOCD/Tcl/Session model.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from plasma_opf.profile_v2 import (
    EXECUTION_CAPABILITIES_SCHEMA, HARDWARE_CAPABILITIES_SCHEMA, PLAN_SCHEMA,
    PROFILE_SCHEMA, ProfileV2Error, Snapshot, build_execution_plan,
    parse_hardware_action_capabilities, parse_profile_v2,
    parse_provider_execution_capabilities,
)

H = "a" * 64
B = "b" * 64


def profile(*, provider="mock-vendor", steps=None, settings=None, power="external"):
    return {
        "schema": PROFILE_SCHEMA,
        "identity": {"profile_id": "example-v2", "part_number": "LOCAL-001",
                     "manufacturer_icpn": "STM32F103C8T6"},
        "provider": {"id": provider, "settings": settings if settings is not None
                     else {"api_mode": "rom_isp"}},
        "hardware": {"power_source": power},
        "workflow": {"steps": steps if steps is not None else [
            {"id": "main", "type": "provider.execute", "procedure": "programming",
             "operations": ["erase", "program", "verify"]}]},
        "completion": {"post_program_reset": "none", "auto_run": False},
    }


def provider(*, name="mock-vendor", segmented=False, reset="none", auto_run=False):
    return {
        "schema": EXECUTION_CAPABILITIES_SCHEMA,
        "provider_id": name,
        "hardware_callback": False,
        "procedures": [
            {"id": "programming",
             "operations": ["erase", "program", "verify"],
             "segmented": segmented,
             "completion": {"post_program_reset": reset, "auto_run": auto_run}},
            {"id": "read", "operations": ["read"], "segmented": False,
             "completion": {"post_program_reset": "none", "auto_run": False}},
        ],
    }


def hardware():
    return {
        "schema": HARDWARE_CAPABILITIES_SCHEMA,
        "actions": ["power.set", "power.wait_good", "signal.set", "reset.set", "delay"],
        "power_domains": ["vdd"], "reset_ids": ["nrst"],
        "signal_ids": ["boot0"],
    }


def plan(p=None, c=None, hw=None):
    return build_execution_plan(
        parse_profile_v2(profile() if p is None else p),
        parse_provider_execution_capabilities(provider() if c is None else c),
        job_id="job-mock-1", site_id=1,
        job_binding_sha256=H, asset_set_sha256=B,
        hardware_capabilities=(parse_hardware_action_capabilities(hw)
                               if hw is not None else None),
    )


def denied(code, fn, *args, **kw):
    with pytest.raises(ProfileV2Error) as exc:
        fn(*args, **kw)
    assert exc.value.code == code


def test_host_only_single_call_vendor_provider_and_snapshot():
    record = profile()
    snap = parse_profile_v2(record)
    record["workflow"]["steps"][0]["operations"].clear()
    assert snap.data["workflow"]["steps"][0]["operations"] == ["erase", "program", "verify"]
    assert hashlib.sha256(snap.canonical_json).hexdigest() == snap.sha256
    assert parse_profile_v2(snap.canonical_json).sha256 == snap.sha256
    built = build_execution_plan(
        snap, parse_provider_execution_capabilities(provider()),
        job_id="job-mock-1", site_id=1,
        job_binding_sha256=H, asset_set_sha256=B)
    assert built.data["schema"] == PLAN_SCHEMA
    assert len(built.data["steps"]) == 1
    assert built.data["steps"][0]["type"] == "provider.execute"
    assert built.data["job"]["job_binding_sha256"] == H
    assert built.sha256 == build_execution_plan(
        snap, parse_provider_execution_capabilities(provider()),
        job_id="job-mock-1", site_id=1,
        job_binding_sha256=H, asset_set_sha256=B).sha256


def test_versioned_snapshot_changes_with_profile_and_job():
    p = profile()
    original = plan(p)
    p["provider"]["settings"]["api_mode"] = "different"
    updated = plan(p)
    assert original.sha256 != updated.sha256
    assert original.data["profile_snapshot_sha256"] != updated.data["profile_snapshot_sha256"]
    changed_binding = build_execution_plan(
        parse_profile_v2(p), parse_provider_execution_capabilities(provider()),
        job_id="job-mock-1", site_id=1, job_binding_sha256="c" * 64,
        asset_set_sha256=B)
    assert updated.sha256 != changed_binding.sha256


def test_same_contract_with_another_provider_and_no_opencd_required():
    vendor = profile(provider="independent-sdk", settings={"boot_method": "rom"})
    caps = provider(name="independent-sdk")
    built = plan(vendor, caps)
    assert built.data["provider_id"] == "independent-sdk"
    assert "tcl" not in built.canonical_json.decode().lower()
    assert "openocd" not in built.canonical_json.decode().lower()


def test_bad_profile_schema_and_fields_are_rejected():
    p = profile()
    p["schema"] = "plasma.programming-profile.v1"
    denied("PROFILE_SCHEMA_UNSUPPORTED", parse_profile_v2, p)
    p = profile()
    p["arbitrary_tcl"] = "shutdown"
    denied("PROFILE_FIELDS_INVALID", parse_profile_v2, p)
    p = profile()
    p["identity"]["approval"] = "required"
    denied("PROFILE_IDENTITY_INVALID", parse_profile_v2, p)


@pytest.mark.parametrize("ops", [
    [], ["verify", "erase"], ["erase", "erase"], ["erase", "verify"],
    ["read"], ["flash_cycle"], ["erase", "program", "verify", "read"]])
def test_invalid_operation_sequences(ops):
    p = profile()
    p["workflow"]["steps"][0]["operations"] = ops
    denied("OPERATIONS_INVALID", parse_profile_v2, p)


def test_duplicate_id_and_unknown_step_denied():
    p = profile()
    p["workflow"]["steps"].append(copy.deepcopy(p["workflow"]["steps"][0]))
    denied("WORKFLOW_STEP_ID_DUPLICATE", parse_profile_v2, p)
    p["workflow"]["steps"][1]["id"] = "second"
    p["workflow"]["steps"][1]["type"] = "raw.tcl"
    denied("STEP_TYPE_UNSUPPORTED", parse_profile_v2, p)


def test_duplicate_json_key_and_nonfinite_numbers_denied():
    raw = '{"schema":"one","schema":"two"}'
    denied("DUPLICATE_JSON_FIELD", parse_profile_v2, raw)
    p = profile()
    p["provider"]["settings"]["invalid"] = float("nan")
    denied("NON_JSON_VALUE", parse_profile_v2, p)


def test_no_auto_run_or_post_reset():
    p = profile()
    p["completion"]["auto_run"] = True
    denied("PROFILE_COMPLETION_UNSUPPORTED", parse_profile_v2, p)
    p = profile()
    p["completion"]["post_program_reset"] = "reset"
    denied("PROFILE_COMPLETION_UNSUPPORTED", parse_profile_v2, p)


def test_power_source_external_disallows_control_but_allows_provider_only():
    p = profile(steps=[
        {"id": "on", "type": "hardware.action", "action": "power.set",
         "domain_id": "vdd", "state": "on"},
        {"id": "run", "type": "provider.execute", "procedure": "programming",
         "operations": ["program"]}])
    denied("EXTERNAL_POWER_CONTROL_DENIED", parse_profile_v2, p)
    assert plan().data["provider_id"] == "mock-vendor"


def test_external_power_can_be_monitored_but_not_driven():
    p = profile(steps=[
        {"id": "sense", "type": "hardware.action",
         "action": "power.wait_good", "domain_id": "vdd", "timeout_ms": 1000},
        {"id": "program", "type": "provider.execute", "procedure": "programming",
         "operations": ["erase", "program", "verify"]}])
    assert [s["id"] for s in plan(p, hw=hardware()).data["steps"]] == [
        "sense", "program"]
    denied("HARDWARE_ACTION_UNSUPPORTED", plan, p)


def test_hw_before_after_mock_vendor_single_execute():
    p = profile(power="ppu", steps=[
        {"id": "on", "type": "hardware.action", "action": "power.set",
         "domain_id": "vdd", "state": "on"},
        {"id": "good", "type": "hardware.action", "action": "power.wait_good",
         "domain_id": "vdd", "timeout_ms": 1000},
        {"id": "program", "type": "provider.execute", "procedure": "programming",
         "operations": ["erase", "program", "verify"]},
        {"id": "off", "type": "hardware.action", "action": "power.set",
         "domain_id": "vdd", "state": "off"}])
    built = plan(p, hw=hardware())
    calls = []
    class MockVendor:
        def execute(self, procedure, operations):
            calls.append(("vendor-sdk", procedure, tuple(operations)))
            return "PASS"
    class MockHardware:
        def execute(self, action, config):
            calls.append(("hardware", action, config.get("state")))
            return "PASS"
    # Host-only test executor, NOT an installed PPU Runtime.
    sdk, fixture = MockVendor(), MockHardware()
    for step in built.data["steps"]:
        if step["type"] == "provider.execute":
            assert sdk.execute(step["procedure"], step["operations"]) == "PASS"
        else:
            assert fixture.execute(step["action"], step) == "PASS"
    assert calls == [
        ("hardware", "power.set", "on"),
        ("hardware", "power.wait_good", None),
        ("vendor-sdk", "programming", ("erase", "program", "verify")),
        ("hardware", "power.set", "off")]


def test_segmented_provider_with_interleaved_hardware_mock():
    steps = [
        {"id": "first", "type": "provider.execute", "procedure": "programming",
         "operations": ["erase"]},
        {"id": "reset", "type": "hardware.action", "action": "reset.set",
         "reset_id": "nrst", "state": "assert"},
        {"id": "second", "type": "provider.execute", "procedure": "programming",
         "operations": ["program", "verify"]},
    ]
    p = profile(steps=steps)
    denied("PROVIDER_SEGMENTATION_UNSUPPORTED", plan, p, provider(), hardware())
    assert [s["id"] for s in plan(p, provider(segmented=True), hardware()).data["steps"]] == [
        "first", "reset", "second"]


def test_provider_cannot_silently_ignore_reset_run_policy():
    denied("PROVIDER_COMPLETION_POLICY_CONFLICT", plan,
           profile(), provider(reset="reset"))
    denied("PROVIDER_COMPLETION_POLICY_CONFLICT", plan,
           profile(), provider(auto_run=True))


def test_missing_capabilities_and_cross_provider_substitution_denied():
    denied("PROVIDER_ID_MISMATCH", plan, profile(), provider(name="other"))
    p = profile(steps=[
        {"id": "gpio", "type": "hardware.action", "action": "signal.set",
         "signal_id": "boot0", "state": "active"},
        {"id": "run", "type": "provider.execute", "procedure": "programming"}])
    denied("HARDWARE_ACTION_UNSUPPORTED", plan, p)
    hw = hardware()
    hw["signal_ids"] = []
    denied("SIGNAL_UNSUPPORTED", plan, p, provider(), hw)
    p = profile()
    p["workflow"]["steps"][0]["procedure"] = "missing"
    denied("PROCEDURE_UNSUPPORTED", plan, p)


def test_hardware_action_invalid_and_missing_procedure():
    p = profile(steps=[{"id": "only", "type": "hardware.action",
                        "action": "delay", "duration_ms": 10}])
    denied("PROVIDER_STEP_REQUIRED", parse_profile_v2, p)
    p = profile(steps=[
        {"id": "step", "type": "hardware.action", "action": "delay", "duration_ms": 0},
        {"id": "run", "type": "provider.execute", "procedure": "programming"}])
    denied("HARDWARE_TIMEOUT_INVALID", parse_profile_v2, p)


def test_identity_incorrect_and_bool_not_integer():
    denied("JOB_BINDING_SHA_INVALID", build_execution_plan,
           parse_profile_v2(profile()),
           parse_provider_execution_capabilities(provider()),
           job_id="job-1", site_id=1,
           job_binding_sha256="not-a-sha", asset_set_sha256=B)
    denied("SITE_ID_INVALID", build_execution_plan,
           parse_profile_v2(profile()),
           parse_provider_execution_capabilities(provider()),
           job_id="job-1", site_id=True,
           job_binding_sha256=H, asset_set_sha256=B)


def test_caps_callback_runtime_denied_and_options_remain_opaque():
    caps = provider()
    caps["hardware_callback"] = True
    denied("HARDWARE_CALLBACK_NOT_IMPLEMENTED", parse_provider_execution_capabilities, caps)
    profile_doc = profile(settings={"vendor_mode": "special", "vendor_flags": [1, 2]})
    assert plan(profile_doc).data["provider_settings"] == profile_doc["provider"]["settings"]
    # The pure Plan cannot grant trusted Provider options schema validation.
    assert "site_lease_granted" not in plan(profile_doc).data


def test_forged_snapshots_fail_closed():
    good = parse_profile_v2(profile())
    forged = Snapshot(good.canonical_json, "0" * 64)
    caps = parse_provider_execution_capabilities(provider())
    denied("PROFILE_SNAPSHOT_CHANGED", build_execution_plan, forged, caps,
           job_id="job-mock-1", site_id=1, job_binding_sha256=H,
           asset_set_sha256=B)
    forged_caps = Snapshot(caps.canonical_json, "0" * 64)
    denied("CAPABILITIES_SNAPSHOT_CHANGED", build_execution_plan, good, forged_caps,
           job_id="job-mock-1", site_id=1, job_binding_sha256=H,
           asset_set_sha256=B)


def test_legacy_bundle_v3_and_binding_v1_are_not_replaced():
    from plasma_opf import bundle_v3
    assert bundle_v3.JOB_BINDING_SCHEMA == "plasma.opf.job-image-binding.v1"
    assert bundle_v3.PROGRAMMING == "programming"
    assert bundle_v3.normalize_operations(["erase", "program", "verify"]) == [
        "erase", "program", "verify"]
    assert plan().data["job"]["job_binding_sha256"] == H
