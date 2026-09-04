# PPU Site Configuration

Status: Phase 1 writable desired-state contract implemented in software; SWPC/CI acceptance required; physical Z2, PL, electrical, and real-IC behavior are separate qualification stages.

## Purpose

A Plasma PPU owns the desired configuration of each physical Site. The Control Station may request a change through Plasma Manager, but the Browser and Manager do not become configuration sources of truth.

Phase 1 makes these existing `SiteConfig` fields writable:

```text
enabled
interface
target
```

The design intentionally does not introduce a second Site schema or a Browser-side settings database.

## Ownership

```text
Browser
  └─ operator/engineer intent only
       ↓
Control Station BFF
       ↓
Plasma Manager
  └─ alias-scoped + explicit allowlist relay
       ↓
Plasma Gateway
  ├─ authentication / authorization when secure mode is enabled
  ├─ active-execution write gate
  ├─ authoritative Site validation
  └─ atomic persistence
       ↓
canonical PPU config/plasma.yaml
       ↓
Plasma Server on next process start
```

The canonical PPU configuration remains the desired-state source of truth. The running Plasma Server remains the source of actual execution state.

## REST contract

PPU-local Plasma Gateway:

```text
GET  /api/settings/sites
POST /api/settings/sites/{site_id}
```

Manager-managed path:

```text
GET  /api/ppus/{ppu_alias}/gateway/api/settings/sites
POST /api/ppus/{ppu_alias}/gateway/api/settings/sites/{site_id}
```

Browser same-origin BFF:

```text
GET  /api/manager/registry/{ppu_alias}/sites
POST /api/manager/registry/{ppu_alias}/sites/{site_id}
```

Manager does not expose a wildcard `/api/settings/*` relay. Only the Site collection GET and individual-Site POST routes are allowlisted.

### Write body

The write body is exact-field and fail-closed:

```json
{
  "enabled": true,
  "interface": "mock",
  "target": "STM32F103C8T6"
}
```

Phase 1 accepts the existing implementation interface identifiers:

```text
mock
openocd
fpga
```

Unknown or missing fields are rejected. `target` must be a non-empty trimmed identifier of at most 256 characters. Site identity is canonical 1-based identity and the Site must already exist in the PPU configuration.

The target string is configuration identity, not proof that a real IC/driver/hardware path has been qualified. Driver/device semantic qualification remains an execution and device-support responsibility.

## Persistence

A successful write updates only these fields for the selected Site:

```text
enabled
interface
target
```

Other Site attributes, including timeout/retry/mock settings, are preserved.

Persistence is atomic within the Gateway process:

```text
load canonical YAML
  ↓
validate write body
  ↓
build and validate candidate PlasmaConfig
  ↓
modify only selected Site writable fields
  ↓
write temporary YAML
  ↓
flush + fsync
  ↓
load_config(temporary file) validation
  ↓
os.replace(temporary, canonical)
```

A failed validation or failed persistence operation must not replace the canonical configuration.

One deployed Plasma Gateway process is assumed to own writes to a PPU configuration file. Cross-process concurrent writers are not a supported Phase 1 deployment model.

## Active-execution write gate

Site configuration changes are rejected while PPU execution is active.

The PPU-local Gateway checks actual runtime state immediately before persistence. It does not trust the Browser's or Manager's last Fleet snapshot as the write authority.

A write is rejected with the existing `PPU_BUSY` / HTTP 409 behavior when the runtime reports a busy PPU or an active Site/Job state.

This deliberately uses a PPU-wide write gate in Phase 1. Per-Site configuration changes during execution on sibling Sites are a future concurrency policy decision and must not be enabled accidentally without proving hardware/resource isolation.

## Desired versus actual state

Saving desired configuration does **not** mean the running Plasma Server has applied it.

Phase 1 intentionally does not restart Plasma Server from inside the HTTP request and does not extend Protocol v3.3 with a hidden hot-reconfiguration command.

The GET/write response therefore carries both domains:

```text
desired
  └─ canonical PPU YAML

actual
  └─ current Plasma Server status
```

Per-Site reconciliation values are:

```text
in_sync
restart_required
actual_unavailable
disabled_runtime_binding_unobservable
```

Overall PPU Site configuration reconciliation is one of:

```text
in_sync
restart_required
actual_unavailable
partially_observable
```

### Disabled Site observability

Protocol v3.3 reports `interface=null` and `target=null` for a disabled Site. Therefore the Gateway cannot prove whether the running process loaded the same dormant interface/target binding as desired.

It must not guess.

When desired and actual both say disabled, the effective disabled state is known, but the dormant binding is reported as:

```text
disabled_runtime_binding_unobservable
```

and the overall state may be `partially_observable`.

A later protocol revision may expose loaded dormant configuration explicitly. Until then, this ambiguity remains visible.

## Security

Read access uses the existing:

```text
settings.read
```

Write access uses a dedicated permission:

```text
settings.site.write
```

Default role policy:

```text
viewer    read only
operator  read only
engineer  read + Site desired-state write
admin     read + Site desired-state write
service   no Site settings write by default
```

In secure mode, a Site write also requires:

```text
valid Bearer principal
+ settings.site.write
+ matching Facility / PPU / Site scope
+ valid Idempotency-Key
+ durable command admission
```

The backend remains authoritative even if the UI disables controls.

## UI behavior

The Engineering PPU/Site Configuration page shows:

```text
Desired Enabled
Desired Interface
Desired Target
Actual runtime summary
Reconciliation
Save / Reset
```

Background polling must not overwrite a locally edited dirty Site row before Save.

Writes are disabled in the UI when the PPU is not commissioned or when Fleet state reports active execution. This is operator guidance only; the PPU-local Gateway independently enforces the authoritative busy gate.

## Phase 1 non-goals

Phase 1 does not provide:

- hot apply of Site configuration;
- automatic Plasma Server restart;
- configuration revision/CAS for multi-operator edit conflicts;
- per-Site live reconfiguration while sibling Sites execute;
- voltage/current/clock/reset/pinmux settings;
- automatic driver generation;
- proof that a target identifier is physically programmable;
- Z2/PL/electrical/real-IC qualification.

These omissions are intentional boundaries, not implied support.

## Acceptance criteria

Software acceptance must cover at least:

1. desired configuration read from canonical PPU config;
2. exact-field authoritative validation;
3. atomic persistence and restart round-trip;
4. failed validation/persistence leaves canonical config unchanged;
5. active execution rejects writes before persistence;
6. desired and actual are represented separately;
7. changed desired state reports `restart_required` while actual remains unchanged;
8. disabled runtime binding ambiguity is explicit, not guessed;
9. Manager relay remains alias-scoped and allowlisted;
10. secure role + Site-scope authorization and idempotency;
11. Browser uses same-origin BFF and does not own arbitrary PPU endpoint URLs;
12. UI polling preserves unsaved dirty drafts.

Passing these software checks does not prove physical Z2 networking, PS↔PL integration, FPGA timing/isolation, or real IC programming.
