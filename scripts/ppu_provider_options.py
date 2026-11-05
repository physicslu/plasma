"""Bounded, provider-owned Options Schema v1 validation (no code execution).

This is an intentionally small PLASMA grammar, *not* arbitrary JSON Schema.
Schemas are immutable Bundle files; no $ref, defaults, format callbacks,
remote resolution, regular expressions, or executable validation hooks exist.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any

SCHEMA = "plasma.ppu.provider-options.v1"
FILE = "config/plasma-provider-options.json"
MAX_SCHEMA_BYTES = 8192
MAX_OPTIONS_BYTES = 16384
_DEPTH = 12
_OBJECT_FIELDS = 64
_ARRAY_ITEMS = 128
_STRING_LENGTH = 4096
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\Z")
_TYPES = frozenset({"object", "array", "string", "integer", "number", "boolean", "null"})


class OptionsDenied(ValueError):
    """Deterministic failure code; never includes untrusted option values."""


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise OptionsDenied(code)


def _schema_node(node: Any, depth: int = 0) -> None:
    _need(depth <= _DEPTH and type(node) is dict, "OPTIONS_SCHEMA_INVALID")
    kind = node.get("type")
    _need(type(kind) is str and kind in _TYPES, "OPTIONS_SCHEMA_INVALID")
    allowed = {"type"}
    if kind == "object":
        allowed |= {"properties", "required"}
        properties = node.get("properties")
        required = node.get("required", [])
        _need(type(properties) is dict and len(properties) <= _OBJECT_FIELDS
              and type(required) is list and len(required) == len(set(
                  str(name) for name in required)), "OPTIONS_SCHEMA_INVALID")
        _need(all(type(name) is str and _NAME.fullmatch(name) is not None
                  for name in properties), "OPTIONS_SCHEMA_INVALID")
        _need(all(type(name) is str and name in properties for name in required),
              "OPTIONS_SCHEMA_INVALID")
        for child in properties.values():
            _schema_node(child, depth + 1)
    elif kind == "array":
        allowed |= {"items", "minItems", "maxItems"}
        _need("items" in node, "OPTIONS_SCHEMA_INVALID")
        _bounds(node, "minItems", "maxItems", _ARRAY_ITEMS, integer=True)
        _schema_node(node["items"], depth + 1)
    elif kind == "string":
        allowed |= {"minLength", "maxLength", "enum"}
        _bounds(node, "minLength", "maxLength", _STRING_LENGTH, integer=True)
        if "enum" in node:
            values = node["enum"]
            _need(type(values) is list and 0 < len(values) <= 64
                  and all(type(value) is str and len(value) <= _STRING_LENGTH for value in values)
                  and len(values) == len(set(values)), "OPTIONS_SCHEMA_INVALID")
    elif kind in ("integer", "number"):
        allowed |= {"minimum", "maximum"}
        _bounds(node, "minimum", "maximum", None, integer=(kind == "integer"))
    _need(set(node) <= allowed, "OPTIONS_SCHEMA_INVALID")


def _bounds(node: dict, low: str, high: str, cap: int | None, *, integer: bool) -> None:
    def good(value: Any) -> bool:
        return ((type(value) is int if integer else type(value) in (int, float))
                and (type(value) is int or math.isfinite(value))
                and (cap is None or 0 <= value <= cap))

    _need(all(good(node[name]) for name in (low, high) if name in node),
          "OPTIONS_SCHEMA_INVALID")
    _need(low not in node or high not in node or node[low] <= node[high],
          "OPTIONS_SCHEMA_INVALID")


def _value(node: dict, value: Any, depth: int = 0) -> None:
    _need(depth <= _DEPTH, "OPTIONS_TOO_DEEP")
    kind = node["type"]
    if kind == "object":
        _need(type(value) is dict, "OPTIONS_TYPE_MISMATCH")
        properties = node["properties"]
        _need(len(value) <= _OBJECT_FIELDS, "OPTIONS_TOO_LARGE")
        _need(all(type(key) is str and key in properties for key in value),
              "OPTIONS_UNKNOWN_FIELD")
        _need(all(key in value for key in node.get("required", [])),
              "OPTIONS_REQUIRED_MISSING")
        for key, child in value.items():
            _value(properties[key], child, depth + 1)
    elif kind == "array":
        _need(type(value) is list, "OPTIONS_TYPE_MISMATCH")
        _need(len(value) <= _ARRAY_ITEMS, "OPTIONS_TOO_LARGE")
        _need(node.get("minItems", 0) <= len(value) <= node.get("maxItems", _ARRAY_ITEMS),
              "OPTIONS_OUT_OF_RANGE")
        for child in value:
            _value(node["items"], child, depth + 1)
    elif kind == "string":
        _need(type(value) is str, "OPTIONS_TYPE_MISMATCH")
        _need(len(value) <= _STRING_LENGTH, "OPTIONS_TOO_LARGE")
        _need(node.get("minLength", 0) <= len(value) <= node.get("maxLength", _STRING_LENGTH),
              "OPTIONS_OUT_OF_RANGE")
        _need("enum" not in node or value in node["enum"], "OPTIONS_ENUM_MISMATCH")
    elif kind in ("integer", "number"):
        _need(type(value) is int if kind == "integer" else type(value) in (int, float),
              "OPTIONS_TYPE_MISMATCH")
        _need(type(value) is int or math.isfinite(value), "OPTIONS_TYPE_MISMATCH")
        _need(("minimum" not in node or value >= node["minimum"])
              and ("maximum" not in node or value <= node["maximum"]),
              "OPTIONS_OUT_OF_RANGE")
    else:
        _need(type(value) is bool if kind == "boolean" else value is None,
              "OPTIONS_TYPE_MISMATCH")


def validate(schema: Any, options: Any) -> bytes:
    """Return canonical immutable option bytes only after entire schema/values pass."""
    _need(type(schema) is dict, "OPTIONS_SCHEMA_INVALID")
    _need(schema.get("schema") == SCHEMA, "OPTIONS_SCHEMA_UNSUPPORTED")
    _need(set(schema) == {"schema", "options"}, "OPTIONS_SCHEMA_INVALID")
    _schema_node(schema["options"])
    _need(schema["options"]["type"] == "object", "OPTIONS_SCHEMA_INVALID")
    _value(schema["options"], options)
    try:
        raw = json.dumps(options, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError, UnicodeError) as exc:
        raise OptionsDenied("OPTIONS_NOT_JSON") from exc
    _need(len(raw) <= MAX_OPTIONS_BYTES, "OPTIONS_TOO_LARGE")
    return raw
