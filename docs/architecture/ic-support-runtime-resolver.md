# Runtime Capability Resolver and Execution Binding

Status: **Current SW/PPU runtime contract**

> Historical filename retained for link compatibility. This document no longer treats `data/ic-support/` as a software runtime source.

## 1. Purpose

Plasma separates three authorities:

```text
ICPN
  exact commercial identity / user-selectable catalog

AI IC Support
  manufacturer-evidence research / candidate programming methods

SW/PPU Runtime Capability
  product-owned executable capability and qualification state
```

The executable runtime may consume only an explicitly supplied **SW/PPU-owned runtime capability source**. It must not auto-promote AI IC Support research artifacts.

## 2. Current runtime state

There is currently **no Production-promoted runtime capability package**.

Therefore the default product state is deliberately:

```text
promoted runtime capability records: 0
hardware-runtime-ready exact ICPNs:   0
native PPU runtime-ready exact ICPNs: 0
```

This does not change the ICPN Production catalog. Commercial ICPN selectability and runtime capability are independent.

Software unit/regression tests exercise F103-like routing, geometry and OpenOCD planning using a synthetic SW-owned fixture under `software/python/tests/`. That fixture is test input only and creates no support/qualification claim.

## 3. Explicit promotion boundary

The only valid AI-research-to-runtime path is an explicit transaction:

```text
AI IC Support retained evidence
        -> reviewed candidate programming method/profile
        -> explicit promotion decision
        -> SW/PPU-owned runtime capability artifact/implementation
        -> software tests
        -> backend/PPU integration
        -> HIL / physical qualification
```

A research profile, Evidence Pack, benchmark PASS or semantic extraction result is not itself executable product configuration.

## 4. Resolver contract

`software/python/plasma_core/ic_support.py` retains the historical `ICSupportResolver` / `ResolvedICSupport` names for compatibility, but the authority has changed:

- `ICSupportResolver.from_root(root)` loads only a **caller-selected** root;
- there is no repository-relative `data/ic-support/` default;
- there is no `PLASMA_IC_SUPPORT_ROOT` research-data environment fallback;
- there is no `get_default_ic_support_resolver()`;
- malformed explicit capability data still fails closed.

The caller is responsible for provenance and for proving that the supplied root belongs to the SW/PPU workstream.

Resolution alone does not imply runtime readiness.

## 5. SiteManager ownership

`SiteManager` accepts an optional resolver through explicit dependency injection:

```text
SiteManager(..., ic_support_resolver=<SW-owned resolver>)
```

It never creates a resolver from AI IC Support research data.

For Mock Sites, no runtime capability resolver is needed.

For non-Mock Sites with no explicit resolver:

```text
SiteManager can initialize/start
        -> Job route resolution requested
        -> CONFIG_INVALID
        -> no JobRegistry insertion
        -> no PPU execution lease
        -> no SiteWorker queue insertion
        -> no hardware access
```

This is an intentional fail-closed state while no promoted capability package exists.

## 6. Route resolution and compatibility metadata

`software/python/plasma_server/execution_router.py` owns the runtime route boundary.

The historical metadata key:

```text
resolved_ic_support
```

is temporarily retained for wire/log compatibility. It now represents a **server-resolved SW/PPU runtime capability route**, not direct AI IC Support research state.

Runtime decisions remain separate:

```text
resolve promoted capability
        -> Can SW/PPU resolve an explicitly supplied capability record?

compile backend plan
        -> Can software derive deterministic operation intent?

admit execution
        -> Is the selected backend implementation runtime-ready?
```

No earlier PASS implies a later PASS.

## 7. OpenOCD plan compiler and executor

`software/python/plasma_interfaces/openocd_plan.py` remains a software mechanism for deterministic plan construction.

Its F103 programming-profile identifier and geometry behavior are exercised using the SW-owned synthetic fixture. The tests prove software mechanics such as:

- target-config normalization/matching;
- 64 KiB vs 128 KiB geometry handling;
- erase/program/verify/read plan construction;
- image-size and memory-boundary rejection;
- artifact binding;
- subprocess materialization and cleanup;
- timeout/cancellation handling;
- tampered-plan rejection.

They do **not** prove that an equivalent AI research profile has been promoted, that OpenOCD is hardware-ready, or that a real IC can be programmed.

## 8. Plasma Native / FPGA path

Plasma Native / FPGA programming remains a separate SW/PPU implementation track.

Current route state remains fail-closed until an actual backend implementation and promoted capability source exist. AI IC Support research may inform a future implementation, but it is not a runtime dependency.

## 9. Capability dimensions

A target's state should be represented orthogonally:

```text
ICPN selectable:             yes/no
runtime capability promoted: yes/no
OpenOCD plan available:      yes/no
OpenOCD execution qualified: yes/no
Plasma native implemented:   yes/no
PPU qualified:               yes/no
Socket qualified:            yes/no
Electrical qualified:        yes/no
HIL / real IC passed:        yes/no
```

Do not compress these into one `supported=true` flag.

## 10. Invariants

1. `data/ic-support/` is AI IC Support research, not runtime configuration.
2. `SiteManager` does not auto-load research data.
3. No repository/environment fallback may silently bridge research into runtime.
4. Runtime capability requires explicit SW/PPU ownership and injection.
5. Missing promoted capability fails before queue/hardware access.
6. Synthetic software fixtures are not product-support evidence.
7. ICPN catalog growth is independent from runtime capability count.
8. AI research success is independent from runtime/PPU/HIL qualification.

## 11. Future promotion mechanism

A later SW/PPU task may define a signed/versioned runtime capability package, code-generated implementation, or another product-owned representation. That mechanism must define at minimum:

- promotion authority;
- input evidence/review requirements;
- immutable identity/versioning;
- provenance back to research evidence without runtime-reading the research tree;
- backend implementation compatibility;
- rollback/revocation behavior;
- CI and HIL gates.

Until such a mechanism is implemented and qualified, the Production runtime capability set remains empty by default.
