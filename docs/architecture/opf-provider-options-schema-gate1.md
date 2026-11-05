# PLASMA P1-01 — Provider-owned Options Schema (Host-only Gate 1)

**Scope:** ChatGPT Direct, 2026-11-05. No Runtime route change, Provider
execution, Root grant, deployment, SWPC/Z2 access, FPGA reload, DUT operation,
or PR merge. This is an addition to the existing OPF-1 selection and
OPF-2 Bundle-bound Provider route, not a second route resolver.

## Identity and location

Every selectable `python` or `native-c` Provider Package in a verified Bundle v3
shall carry a non-executable file at the *fixed* Package-relative path
`config/plasma-provider-options.json`. It is not a root Manifest field. The
Provider Package's own `files[]` must record the exact relative path, size and
SHA-256. This file may not exceed 8192 bytes. It is a Provider-owned declarative
schema, not executable code, a URL, a dynamic import, or an authorization token.

The existing `programming-profile` descriptor still names exactly one
`provider_package`; that Package must be in the Profile's `requires` list.
The resolver checks the Active Set digest and staged bytes, resolves the exact
selected Profile/Provider and trusted hardware capability, and then validates
the supplied Job `options` against **that selected Provider Package's** schema.
No other Provider, Bundle, source-tree file or builtin default may supply it.
An omitted file is denied, including when the Job has empty options.

## Versioned grammar

`plasma.ppu.provider-options.v1` is deliberately **not a general JSON Schema
implementation**. Unsupported keywords (including `$ref`, `additionalProperties`,
`default`, `format`, regexes, `oneOf` and remote resolution) are denied. The
schema root has exactly `schema` and `options`, with the latter an `object` node.

```json
{
  "schema": "plasma.ppu.provider-options.v1",
  "options": {
    "type": "object",
    "properties": {
      "speed_khz": {"type": "integer", "minimum": 1, "maximum": 5000},
      "mode": {"type": "string", "enum": ["swd", "mock"]},
      "flags": {
        "type": "array", "items": {"type": "boolean"}, "maxItems": 4
      }
    },
    "required": []
  }
}
```

Supported node types: `object`, `array`, `string`, `integer`, `number`,
`boolean`, `null`. `object` must have `properties` (at most 64 names);
`required` is optional, and all unknown option fields are always denied.
`array` must have one `items` node and may declare `minItems`/`maxItems`.
`string` may declare `minLength`/`maxLength` or a unique string `enum`.
`integer` and finite `number` may declare `minimum`/`maximum`; booleans are
not integers. Optional fields are not synthesized or defaulted.

Global limits independent of Provider declarations: schema 8192 bytes,
canonical Job options 16384 bytes, nesting 12 levels, 64 object members,
128 array elements, and 4096 characters per string. Schema constraints
cannot widen these bounds. Duplicate JSON keys and unknown grammar keys fail
closed. The `options` parser in OPF-1 remains syntax-only; this separate step
is mandatory before any future Provider execution.

## Route result, evidence and security boundary

`ppu_provider_contract.resolve()` requires an explicit `options` argument.
The returned immutable `options_json` bytes are canonical UTF-8 JSON
(sorted keys, compact separators), paired with `options_sha256` and
`options_schema_sha256`. These are content-binding inputs for a future runtime
grant; they are **not** a runtime grant themselves. The resolver does not
execute any Provider code, open an MMIO device, change FPGA state or claim SAFE_OFF.

Generic PPU Core does not assign privileged meanings to Provider option keys.
For example, a Provider cannot use `options` to waive Site ownership, Root
permissions, the one Job Deadline, electrical checks or Recovery. Those
mechanisms remain independent mandatory gates.

## Host-only acceptance and outstanding work

- Positive: independent FPGA reference-style and PS-only mock routes select
  their own schemas from the same verified Active Set; Python and Native-C
  Provider Package shapes are admitted without running code.
- Negative: absent, altered, invalid or unsupported schema; unknown/missing
  options; wrong types (including bool-as-int and NaN); enum, length, range,
  nested object and array violations; cross-Provider option substitution.
- Future Runtime integration must bind these exact canonical bytes and both
  SHA identities to a Site Session and enforce execution-time validation.
- Real Provider execution, package Publisher trust, Runtime cutover,
  OpenOCD/ABI-v5 HIL, DUT results and SAFE_OFF remain **NOT_RUN**.
