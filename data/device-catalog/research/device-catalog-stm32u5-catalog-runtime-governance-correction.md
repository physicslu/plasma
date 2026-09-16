# STM32U5 catalog/runtime governance correction

## Why this correction exists

The STM32U5 research sequence accidentally reintroduced an ordering that the merged ICPN admission governance had already removed: catalog publication was treated as if it had to continue through security/runtime/HIL gates.

That is incorrect. The governing rule remains:

- catalog identity admission is independent from PPU/Socket HIL;
- catalog identity admission is independent from physical programming success;
- catalog membership does not authorize target execution;
- runtime/security qualification is a separate track.

This correction preserves the historical research artifacts from PRs #608, #610, #611, and #612 for auditability, but supersedes their sequencing semantics where those semantics could be read as catalog prerequisites.

## Corrected PR interpretation

### PR #608 — canonical admission plan

The 265 Active metadata-ready exact ICPNs and their deterministic route bindings remain valid. Its historical `next_research_gate=stm32u5-security-state-admission-gate` is now explicitly classified as an **independent runtime/security research successor**, not a catalog prerequisite.

The Catalog track proceeds instead to:

`stm32u5-production-publication-gate`

### PR #610 — security-state model

The security model remains a valid fail-closed runtime safety contract. The historical field `hil_required_before_runtime_enablement=true` is superseded as wording: the invariant is **physical validation before any future target-execution enablement**, not a named HIL gate and not a Catalog gate.

### PR #611 — runtime enforcement

No correction is required. Its 105/105 target-operation DENY matrix remains a valid independent runtime safety contract and does not authorize Production admission or target execution.

### PR #612 — observer/debug contract

The passive observer/debug contract remains useful. Its historical next gate `stm32u5-hil-observer-debug-matrix-readiness-gate` is **canceled**. No successor software HIL gate is required.

### PR #613 — HIL readiness gate

The gate is retired. Its five repository artifacts are removed by this correction. The merge remains in Git history as an auditable event, but it no longer represents the current STM32U5 governance path.

## Current catalog boundary

- Active exact ICPNs eligible for publication: **265**
- quarantined Preview exact ICPN: `STM32U5G9ZJJ3Q`
- Production before publication: **2,017**
- expected Production after publication: **2,282**
- PPU HIL required for catalog admission: **false**
- Socket HIL required for catalog admission: **false**
- physical programming success required for catalog admission: **false**
- catalog membership authorizes target execution: **false**

## Current runtime/security boundary

The merged security/runtime contracts remain fail-closed. Runtime programming, security mutation, OEM-key operations, and debug attach remain unauthorized. Physical validation is a separate qualification concern if target execution is later enabled; it is not a prerequisite for publishing catalog identities.

## Next action

`stm32u5-production-publication-gate`
