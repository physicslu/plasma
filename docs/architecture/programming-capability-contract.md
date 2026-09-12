# Programming Capability Contract

## Purpose

Programming admission must be driven by explicit provider capabilities, never by provider names.

The canonical Browser-facing source is the Engineering target catalog:

```text
GET /api/engineering/targets
```

A provider that participates in PMode or EMode Programming advertises:

```json
{
  "programming_capabilities": {
    "synthetic_programming_image": false,
    "target_device_required": true
  }
}
```

Both fields are boolean contract fields. A missing object, a missing field, or a non-boolean field is treated as unknown capability and resolves fail-closed in the Web Console:

```text
synthetic_programming_image = false
target_device_required      = true
```

Provider identity such as `mock`, `configured_mock`, or any future real-hardware provider is descriptive identity only. It must not be used as a capability proxy.

## Current providers

| Provider | synthetic_programming_image | target_device_required | Meaning |
|---|---:|---:|---|
| Shared Image Engineering Mock | `true` | `false` | Mock Batch orchestration may create the deterministic synthetic Programming Image and does not require an explicit Browser Target IC. |
| Configured Mock | `false` | `false` | A real session Programming Asset is required, while target identity may come from canonical Site configuration. |
| Unknown / malformed catalog | `false` | `true` | Fail closed. No synthetic Image and explicit Target IC required. |

Future production providers must advertise both fields explicitly before Browser policy depends on them.

## PMode / EMode invariant

PMode and EMode consume the same capability resolver. Mode-specific code may apply policy and orchestration differences, but must not infer Image or Target IC requirements from provider names.

The capability object controls only Browser admission semantics. It does not prove an execution backend is physically ready. In particular, capability advertisement does not qualify PL, OpenOCD, Site power/reset, real IC programming, or multi-Site hardware concurrency.

## Compatibility policy

The previous Browser compatibility fallback for a catalog with `provider == "mock"` and no capability object has been removed. Old or malformed Gateways now receive the same fail-closed behavior as any unknown provider.

This is deliberate: compatibility must not silently grant synthetic-image behavior to a future provider merely because of a string identity.
