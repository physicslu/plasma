# PLASMA OPF — Open Provider Framework v1 Foundation

**Status:** Target contract / PR OPF-1; not a deployed runtime or qualified programming provider.
**Authority:** [Unified Bundle-driven Programming Decision (PR #1298)](unified-bundle-driven-programming-decision-2026-11-04.md).
**Scope:** Programming execution path only. Engineering and Production retain their separate Console authorization/release policies but use one programming execution pipeline.

## Architecture and boundaries

```text
Console / Manager (Bundle selection, ICPN research, L0–L2 policy, Job authorization)
  | authorized Job + exact selected Bundle v3 / Active Asset Set
  v
PPU trusted Bundle admission / identity / integrity / dependency / capability checks
  |
  v
OPF programming selection (Provider package, Profile package, timeout_ms, options)
  |
  v
PPU Site Session Manager (one owner and fence token per Site; one Job timeout)
  | safety/authority mediation; PPU-wide FPGA reload guard
  v
OPF Provider / Driver capability boundary (OpenOCD optional)
  |
  +--> Z2 PS / authorized transport --> optional FPGA PL / per-Site IP --> DUT
  +--> qualified PS-only transport ----------------------------------> DUT
```

- **Core is protocol-neutral:** it must not require a built-in manufacturer, ICPN, Catalog level, compiler registry, fixed FPGA Image ID, OpenOCD, or an existing source-tree target profile.
- **Selected Active Asset Set is exclusive:** Provider, Profile, Driver and FPGA Image must resolve from one authorized Bundle. No cross-Bundle or source-tree fallback.
- **PPU still checks reality:** authorized source, package hash, allowed executable, actual target memory range, selected device identity, hardware capabilities and ABI, Site concurrency, electrical safety, and uncertain outcome.
- **Provider is not a privilege owner:** it implements advertised programming operations behind a mediated interface. It must not manage Site locks, configure an FPGA without PPU authority, or claim SAFE_OFF merely because its own process exited.
- **Independent Sites:** only one active Session per Site, with fencing of stale Workers/Providers. A PPU-wide FPGA reload or shared-resource change must coordinate all affected Sites; retain the existing same-MCU/firmware concurrency policy unless separately revised.

## Minimal OPF programming selection (v1 proposal)

This is a **data descriptor carried by an authorized Bundle Package**, not new fields on the strict root Bundle v3 manifest. Exact descriptor-file discovery and Package-kind admission are **future integration work**; do not claim the current B2/B3 parser accepts this proposal. Names below are references to Package IDs in the same Active Asset Set, not filesystem paths.

```json
{
  "schema": "plasma.opf.programming.v1",
  "provider": "reference-provider",
  "profile": "target-profile",
  "timeout_ms": 1200000,
  "options": {"speed_khz": 2000}
}
```

**Only three universal programming selections:** `provider`, `profile`, and optional `timeout_ms`. `schema` identifies the contract version; `options` is an opaque Provider-specific JSON object, not a set of PPU Core knobs. The Provider declares a separate, versioned schema for its options and validates it **before** any hardware operation. Core must never interpret arbitrary Provider options as a waiver of a safety gate.

### Single timeout rule

- PPU supplies `default_timeout_ms` and an independently enforced local **safety ceiling**. The Bundle provides only optional `timeout_ms` (positive integer, milliseconds). Missing override means PPU default.
- If override is present and valid, use it; if it exceeds the PPU ceiling, **reject** the Job rather than silently clamp it. No operation-specific, erase, verify, heartbeat or lease timeout parameters are introduced into the Bundle contract.
- The effective timeout is a single monotonic-clock Job deadline covering normal Probe/Erase/Program/Verify/Readback work. Any pending SAFE_OFF/recovery obligations survive deadline expiry; time expiry never proves the DUT safe.
- Record source (`ppu_default` / `bundle_override`), effective timeout, start/deadline and observed elapsed duration in future execution evidence. This PR only validates the selection; it does not implement execution-time enforcement.

## One Site Session Manager

- Consolidate **Ownership / Lease / Lock** behind one atomic Site Session grant and one fencing generation/token. This is a *target state*, not a claim that today’s runtime has already been migrated.
- AVAILABLE → ACTIVE after resource admission. On normal completion, release only after verified safe termination. On timeout, cancelled/unknown operation, stale owner, or unverifiable SAFE_OFF: deny new operations, enter RECOVERY / SEALED as appropriate.
- `site<N>.sealed` is persistent safety evidence, not an expiring lease. It must not be deleted or ignored merely because the single Job deadline elapsed. Recovery uses the existing authorized operator procedure and independently verifies SAFE_OFF.
- PPU-wide image/reload guard remains separate in **scope**, but belongs to the same Resource/Safety authority; do not hand FPGA configuration authority to a Provider.

## OPF migration plan — independent PRs

| Phase | Deliverable | Hardware / operational impact |
| --- | --- | --- |
| **OPF-1 (this PR)** | Normative OPF design, standalone programming-selection validator and host-only negative tests | None; no Runtime route change |
| OPF-2 | Provider capability descriptor, registry/discovery from one verified Active Set, Provider-specific options-schema validation, two host-only test Providers | Host-only, no DUT |
| OPF-3 | Single Site Session Manager contract/integration and one bounded Job deadline; preserve existing SAFE_OFF, SEALED, Recovery and PPU reload guard | Host-only simulation first; isolate from current Site 2 HIL |
| OPF-4 | Wrap existing OpenOCD/ABI-v5 as a Reference Provider; route execution via verified selected Provider/Profile/Driver rather than static registries | Requires staged integration and later HIL |
| OPF-5 | Remove superseded static programming gates, prove non-OpenOCD/PS-only alternative and run real authorized Site HIL / regression | Explicitly bounded hardware acceptance |

OPF phases must not revive legacy compatibility layers or create a separate execution pipeline. Their boundaries can be adjusted as actual code reveals cross-layer dependencies. Upstream Catalog research and qualification remain available but are not PPU programming admission prerequisites.

## First PR acceptance / limitations

1. A minimal parser rejects absent/unknown schema, missing Provider/Profile references, unsupported fields, illegal Timeout, non-JSON `options`, and overrides beyond PPU policy.
2. It accepts a valid Bundle override or uses the PPU default when absent; accepts arbitrary *names* without built-in OpenOCD or brand allowlists.
3. No Provider code runs; no Profile is loaded, no Plugin sandbox/authorization is qualified, no Bundle v3 manifest/schema is modified, no Site Session Manager is replaced.
4. Focused host-only tests and PR CI are required. Mock PASS is not Z2/FPGA/DUT/HIL evidence.
5. Do not modify PR #1299, touch the Z2 installed release, clear `site2.sealed`, perform Flash POST, reload FPGA, merge this PR or change deployment.
