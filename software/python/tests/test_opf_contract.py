"""OPF-1 host-only contract checks (not a runtime/physical HIL test)."""
from __future__ import annotations

import pytest

from plasma_opf import (
    OPF_PROGRAMMING_SCHEMA,
    OpfContractError,
    TimeoutPolicy,
    parse_programming_selection,
)

POLICY = TimeoutPolicy(default_timeout_ms=60000, maximum_timeout_ms=3600000)


def selection(**overrides):
    descriptor = {
        "schema": OPF_PROGRAMMING_SCHEMA,
        "provider": "third-party-provider",
        "profile": "custom-target",
    }
    descriptor.update(overrides)
    return descriptor


def test_ppu_default_when_bundle_omits_timeout():
    parsed = parse_programming_selection(selection(), policy=POLICY)
    assert (parsed.timeout_ms, parsed.timeout_source) == (60000, "ppu_default")
    assert parsed.provider == "third-party-provider"
    assert parsed.profile == "custom-target"
    assert parsed.options == {}


def test_bundle_timeout_override_and_opaque_provider_options():
    original = selection(timeout_ms=1200000, options={"spi_mode": 3, "sequence": [1, True, None]})
    parsed = parse_programming_selection(original, policy=POLICY)
    assert (parsed.timeout_ms, parsed.timeout_source) == (1200000, "bundle_override")
    assert parsed.options == original["options"]
    original["options"]["sequence"].append("changed")
    assert parsed.options["sequence"] == [1, True, None]


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"schema": "plasma.opf.programming.v2"}, "SELECTION_SCHEMA_UNSUPPORTED"),
        ({"schema": None}, "SELECTION_SCHEMA_UNSUPPORTED"),
        ({"provider": ""}, "PROVIDER_REF_INVALID"),
        ({"provider": "../etc/passwd"}, "PROVIDER_REF_INVALID"),
        ({"profile": ""}, "PROFILE_REF_INVALID"),
        ({"profile": "/absolute/path"}, "PROFILE_REF_INVALID"),
        ({"timeout_ms": 0}, "TIMEOUT_INVALID"),
        ({"timeout_ms": -3}, "TIMEOUT_INVALID"),
        ({"timeout_ms": True}, "TIMEOUT_INVALID"),
        ({"timeout_ms": 1000.0}, "TIMEOUT_INVALID"),
        ({"timeout_ms": "1000"}, "TIMEOUT_INVALID"),
        ({"timeout_ms": 3600001}, "TIMEOUT_EXCEEDS_PPU_POLICY"),
        ({"options": []}, "OPTIONS_NOT_OBJECT"),
        ({"options": {"invalid": float("nan")}}, "OPTIONS_NON_JSON_VALUE"),
        ({"options": {"invalid": object()}}, "OPTIONS_NON_JSON_VALUE"),
        ({"options": {"nested": {4: "not a JSON key"}}}, "OPTIONS_NON_JSON_KEY"),
        ({"unknown_gate": False}, "SELECTION_UNKNOWN_FIELD"),
    ],
)
def test_invalid_descriptor_fails_closed(changes, code):
    with pytest.raises(OpfContractError) as exc:
        parse_programming_selection(selection(**changes), policy=POLICY)
    assert exc.value.code == code


@pytest.mark.parametrize("value", [None, [], "x", 3])
def test_nonobject_descriptor_is_rejected(value):
    with pytest.raises(OpfContractError, match="SELECTION_NOT_OBJECT"):
        parse_programming_selection(value, policy=POLICY)


@pytest.mark.parametrize(
    ("default", "maximum", "code"),
    [
        (0, 100, "PPU_DEFAULT_TIMEOUT_INVALID"),
        (True, 100, "PPU_DEFAULT_TIMEOUT_INVALID"),
        (100, -1, "PPU_MAXIMUM_TIMEOUT_INVALID"),
        (100, 50, "PPU_DEFAULT_EXCEEDS_MAXIMUM"),
    ],
)
def test_invalid_ppu_timeout_policy(default, maximum, code):
    with pytest.raises(OpfContractError) as exc:
        TimeoutPolicy(default_timeout_ms=default, maximum_timeout_ms=maximum)
    assert exc.value.code == code


def test_options_excessive_nesting_is_rejected():
    opts = {}
    p = opts
    for _ in range(34):
        nested = {}
        p["next"] = nested
        p = nested
    with pytest.raises(OpfContractError, match="OPTIONS_JSON_DEPTH_EXCEEDED"):
        parse_programming_selection(selection(options=opts), policy=POLICY)


def test_selection_cannot_imply_hardware_authorization():
    """Parsing is only syntax/default resolution: no plugin is invoked."""
    result = parse_programming_selection(
        selection(provider="a-different-engine", profile="another-ic"), policy=POLICY
    )
    assert result.provider == "a-different-engine"
    assert not hasattr(result, "execute")
    assert not hasattr(result, "safe_off_verified")
