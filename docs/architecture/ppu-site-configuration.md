# PPU Site Configuration

Status: Phase 1 writable desired-state contract, P1 optimistic concurrency, and P2 packaged-service persistence wiring implemented in software; physical Z2, PL, electrical, and real-IC behavior remain separate qualification stages.

## Purpose

A Plasma PPU owns the desired configuration of each physical Site. The Control Station may request a change through Plasma Manager, but the Browser and Manager do not become configuration sources of truth.

Phase 1 makes these existing `SiteConfig` fields writable:

```text
enabled
interface
target
```

P1 adds per-Site optimistic concurrency so a stale Browser Draft cannot silently overwrite a newer saved Desired state.

P2 closes the packaged-service path so Plasma Server and Plasma Gateway use the same explicit canonical PPU configuration and the Gateway has the minimum deployment write boundary required by atomic persistence.

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
  ├─ per-Site If-Match optimistic concurrency gate
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

### Read response and desired revision

Each Site returned by the collection carries a deterministic `desired_revision` in addition to Desired, Actual, and reconciliation state:

```text
sha256:<64 lowercase hex characters>
```

The digest is computed from the normalized canonical tuple:

```text
site_id
enabled
interface
target
```

It is deliberately derived rather than stored as a mutable YAML counter. Therefore the same Desired state has the same revision across Gateway process restarts, and changing SITE 2 does not invalidate a Draft for unchanged SITE 1.

The revision is concurrency identity only. It is not a configuration schema version, deployment revision, runtime generation, or proof that the target hardware has been applied.

### Write body

The write body remains exact-field and fail-closed:

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

### Write precondition

Every Site desired-state POST must include exactly one strong HTTP entity tag carrying the Draft baseline revision:

```http
If-Match: "sha256:<64 lowercase hex characters>"
```

The Gateway rejects a missing precondition with HTTP `428 Precondition Required`. A malformed, weak, wildcard, or multi-tag precondition is rejected rather than guessed.

Inside the same Site configuration lock used for persistence, the Gateway compares the supplied revision with the current normalized Desired state. If they differ, the write fails with HTTP `412 Precondition Failed` and error code:

```text
site_desired_conflict
```

The response includes the expected and current revisions for diagnosis, but it does not modify canonical configuration.

This produces the intended stale-write behavior:

```text
Browser Draft based on revision A
        ↓
other operator saves revision B
        ↓
first Browser sends If-Match A
        ↓
Gateway current revision is B
        ↓
412 — no persistence, no automatic merge, no silent overwrite
```

The Control Station BFF and Plasma Manager forward `If-Match` only through their existing explicit header allowlists. This does not create a generic header proxy.

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
compare current per-Site desired_revision with If-Match
  ↓
build and validate candidate PlasmaConfig
  ↓
modify only selected Site writable fields
  ↓
write temporary YAML in the canonical directory
  ↓
flush + preserve canonical file mode + fsync
  ↓
load_config(temporary file) validation
  ↓
os.replace(temporary, canonical)
```

A failed validation, stale revision, or failed persistence operation must not replace the canonical configuration. Atomic replacement preserves the canonical file mode rather than silently falling back to the temporary file's default mode.

One deployed Plasma Gateway process is assumed to own writes to a PPU configuration file. Cross-process concurrent writers are not a supported deployment model; P1 protects concurrent clients going through that authoritative Gateway process.

## P2 packaged-service operational closure

For system PPU deployments the canonical configuration path is explicit and shared:

```text
/etc/plasma/ppu.yaml
```

Both service command lines bind that same path:

```text
plasma-server.service -> server --config /etc/plasma/ppu.yaml
plasma-web.service    -> gateway --ppu-config /etc/plasma/ppu.yaml
```

The Gateway must create a temporary file in the same directory before `os.replace`, so file-only write permission is insufficient. P2 keeps `ProtectSystem=strict` and opens only the managed Plasma configuration root to `plasma-web.service`:

```text
/etc/plasma           root:plasma 0770
/etc/plasma/ppu.yaml  plasma:plasma 0640

plasma-server.service ReadWritePaths -> state + log only
plasma-web.service    ReadWritePaths -> state + log + /etc/plasma
```

This is the smallest write boundary compatible with the existing single-directory canonical path and same-filesystem atomic replacement. It does not make `/etc` writable, does not grant the Plasma Server configuration-write capability, and does not create a privileged generic configuration service.

The Z2 installer snapshots pre-existing configuration-directory metadata before migration. If service activation/readiness fails, rollback restores the previous release, configuration, units, and the previous configuration-directory mode/ownership. The SWPC Z2-like deployment surrogate carries the same operational contract and snapshots/restores its configuration-directory metadata during failed upgrade rollback.

The SWPC restricted Nginx ingress deliberately continues to return 404 for `/api/settings/sites`; P2 does not expose a new public configuration-write surface. Manager-to-PPU Site settings must use an explicitly registered/reachable Plasma Gateway path appropriate to the deployment security model.

P2 is persistence wiring only. It does not restart Plasma Server after a save, hot-apply configuration, or prove that Runtime now matches Desired.

## Active-execution write gate

Site configuration changes are rejected while PPU execution is active.

The PPU-local Gateway checks actual runtime state immediately before persistence. It does not trust the Browser's or Manager's last Fleet snapshot as the write authority.

A write is rejected with the existing `PPU_BUSY` / HTTP 409 behavior when the runtime reports a busy PPU or an active Site/Job state.

This deliberately uses a PPU-wide write gate in Phase 1. Per-Site configuration changes during execution on sibling Sites are a future concurrency policy decision and must not be enabled accidentally without proving hardware/resource isolation.

## Desired versus actual state

Saving desired configuration does **not** mean the running Plasma Server has applied it.

Phase 1/P1/P2 intentionally do not restart Plasma Server from inside the HTTP request and do not extend Protocol v3.3 with a hidden hot-reconfiguration command.

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

In secure mode, a Site write requires:

```text
valid Bearer principal
+ settings.site.write
+ matching Facility / PPU / Site scope
+ valid Idempotency-Key
+ valid If-Match desired revision
+ durable command admission
```

Security authorization remains authoritative before configuration data is exposed to unauthorized writers. An idempotent replay of an already-admitted command returns the durable first result rather than re-executing the write against a newer revision.

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

Background polling must not overwrite a locally edited dirty Site row before Save. When a row first becomes dirty, the Browser keeps the exact `desired_revision` that the Draft was based on. Later polling may observe a newer Desired state, but it must not silently advance that dirty Draft's baseline.

If Save returns HTTP 412, the UI keeps the local Draft, marks `Desired changed elsewhere`, disables stale Save, refreshes observed state, and requires an explicit Reset/re-edit before another write. It does not auto-merge hardware configuration fields or provide an `overwrite anyway` escape hatch.

Writes are disabled in the UI when the PPU is not commissioned or when Fleet state reports active execution. This is operator guidance only; the PPU-local Gateway independently enforces the authoritative busy and concurrency gates.

## Phase 1/P1/P2 non-goals

The current contract does not provide:

- hot apply of Site configuration;
- automatic Plasma Server restart;
- automatic merge of conflicting multi-operator Drafts;
- per-Site live reconfiguration while sibling Sites execute;
- voltage/current/clock/reset/pinmux settings;
- automatic driver generation;
- proof that a target identifier is physically programmable;
- public exposure of Site settings through the SWPC restricted ingress;
- Z2/PL/electrical/real-IC qualification.

These omissions are intentional boundaries, not implied support.

## Acceptance criteria

Software/deployment-contract acceptance must cover at least:

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
12. UI polling preserves unsaved dirty Drafts;
13. each Site read exposes a deterministic restart-stable `desired_revision`;
14. matching `If-Match` permits a valid write and yields a new revision when Desired state changes;
15. missing/malformed preconditions fail closed;
16. stale `If-Match` returns HTTP 412 and leaves canonical configuration unchanged;
17. changing one Site does not invalidate unchanged sibling-Site revisions;
18. BFF and Manager forward `If-Match` through explicit header allowlists only;
19. the Browser preserves the dirty baseline revision and surfaces a stale-write conflict instead of silently overwriting newer Desired state;
20. packaged Server and Gateway bind one explicit canonical PPU config path;
21. packaged Gateway has the bounded config-directory write path required for atomic persistence while Server does not;
22. canonical file mode survives Site Desired atomic replacement;
23. failed Z2 activation restores prior config-directory metadata in addition to prior release/config/units;
24. SWPC Z2-like install/deploy uses the same config-path and permission model and restores directory metadata on failed upgrade;
25. restricted SWPC ingress remains closed to Site settings.

Passing these software and deployment-contract checks does not prove physical Z2 networking, PS↔PL integration, FPGA timing/isolation, socket/electrical behavior, or real IC programming.