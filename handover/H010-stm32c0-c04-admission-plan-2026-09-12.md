# H010 — STM32C0 C0.4 Read-only Admission Plan Handover

**Date:** 2026-09-12
**Status:** C0.4 implementation complete; PR #500 Gate 2 pending
**Primary workstream:** Device Catalog / STM32C0
**Repository:** `physicslu/plasma`
**C0.4 branch:** `agent/device-catalog-stm32c0-phase-c04-admission-plan`
**PR:** `#500`

## 1. Transaction boundary

C0.4 is a deterministic **read-only capability/admission-planning transaction** over exactly the STM32C0 identities closed by C0.2 and metadata-qualified by C0.3:

- 50 retained Base Devices;
- 220 manufacturer-verified Active exact ICPNs;
- 220 metadata-ready exact ICPNs;
- no new commercial identity discovery;
- no metadata reinterpretation;
- no canonical dataset write;
- no Production publication;
- no programming-algorithm, Flash-geometry, option/security, HIL, physical-target, or runtime-support claim.

C0.4 applies OpenOCD routing only as an independent **capability gate for admission planning**. It does not allow OpenOCD routing to redefine commercial identity or manufacturer metadata.

## 2. C0.3 input closure

C0.4 hard-binds the retained C0.3 policy result:

- metadata rows SHA-256: `94ebe11fda28cb6d7b68c13c7edb4bf8341887f6146d52f72461bc6ef35bee19`;
- policy-ready exact ICPN set SHA-256: `b116f624e971a3be5c947e107589bdb4d1bf5f5b0585ecae71e743cfb7a2649a`;
- C0.3 policy baseline Git blob: `4272a441f072433b0dfe726f1d97459bbad957f3`.

C071 `N`, `TR`, `NTR`, package-dependent `F/P` versus `F/Y`, and C091/C092 series separation remain C0.3 manufacturer-authoritative semantics. Routing cannot rewrite them.

## 3. Exact-ICPN capability replay

The OpenOCD mapping catalog is hard-bound to Git blob:

`0ef056e3363e20bb527590c4a4cc1cc0d7afb810`

This is byte-identical to the historical catalog retained by C0.2. C0.4 nevertheless replays the current mapping for all 220 exact ICPNs.

A candidate is capability-admittable only when it has one deterministic ordering-pattern mapping to:

`tcl/target/stm32c0x.cfg`

The important modeling correction is that the C0.2 aggregate `44 unique / 6 unmapped` was a **Base Device** summary. Six Base Devices contain mixed exact-ICPN routing results, so C0.4 gates at exact-ICPN level rather than excluding each whole Base Device.

## 4. Deterministic closure

Observed C0.4 result:

```text
manufacturer-verified exact ICPNs: 220
metadata-ready exact ICPNs:        220
unique OpenOCD routes:             209
ambiguous routes:                  0
unmapped routes:                   11
capability-admittable:             209
capability-unresolved:             11
identity rejects:                  0
```

The exact unresolved set is:

- `STM32C051K8U3`
- `STM32C051K8U3TR`
- `STM32C051K8U6`
- `STM32C051K8U6TR`
- `STM32C051K8U7`
- `STM32C051K8U7TR`
- `STM32C071FBY6TR`
- `STM32C071R8I6N`
- `STM32C071RBI6N`
- `STM32C091RBI6`
- `STM32C092RBI6`

Frozen unresolved exact-set SHA-256:

`32698be0aee4f95360a1b27ddfecd1034d7627e0b223dd8873153b5d96ec5601`

These 11 identities remain **manufacturer-verified Active and metadata-ready**. Their exclusion is capability-routing fail-closed behavior, not a commercial identity rejection.

The six mixed Base Devices are:

- `STM32C051K8`
- `STM32C071FB`
- `STM32C071R8`
- `STM32C071RB`
- `STM32C091RB`
- `STM32C092RB`

Uniquely routed exact ICPNs inside those Base Devices remain among the 209 admittable identities.

## 5. Production boundary

Production remains unchanged:

```text
Production exact ICPNs:    703
Production Base Devices:   243
Production STM32 families: 9
Production STM32C0 ICPNs:  0
```

Production manifest binding:

- Git blob: `89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc`;
- SHA-256: `903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0`.

No file under `data/device-catalog/production/` is modified by C0.4.

## 6. Implemented C0.4 assets

The transaction adds or updates:

- `data/device-catalog/research/stm32c0_admission_policy.py`;
- `data/device-catalog/research/stm32c0_phase_c0_4_admission.py`;
- `data/device-catalog/research/test_stm32c0_phase_c0_4_admission.py`;
- `data/device-catalog/research/validate_stm32c0_phase_c0_4_admission_plan.py`;
- `data/device-catalog/research/stm32c0-phase-c0.4-admission-plan.json`;
- `data/device-catalog/research/device-catalog-stm32c0-phase-c0.4-admission-plan.md`;
- `.github/workflows/device-catalog-stm32c0-c04-admission-validation.yml`;
- centralized STM32C0 family-CI profile and trigger routing.

The C0.4 negative/boundary suite covers exact-set closure, mixed Base Device behavior, C071 metadata preservation, CMSIS-shaped route rejection, catalog drift, Production drift, non-empty canonical prestate, frozen-plan replay, and non-claim boundaries.

## 7. Branch synchronization and validation

C0.4 began from C0.3 merge commit `99d7b24a66db6b3a581cf8cef604a85bf8bd621f`.

While C0.4 was being implemented, `main` advanced to `0f1123a23a5b6cdc0e97a21014cb40bc535aa38c` through unrelated Plasma Python gateway/tests. The drift was reviewed and merge-forwarded through PR #501 without rebase, force-push, or history rewrite.

PR #501 merge commit on the C0.4 branch:

`fae09c692b646bb6e5fe350d8036664b4046f365`

On that synchronized implementation head, these applicable workflows passed:

- STM32C0 C0.4 admission validation — run `34671094048` — SUCCESS;
- STM32 family validation — run `34671094043` — SUCCESS;
- Device catalog validation — run `34671094067` — SUCCESS;
- Device catalog current validation — run `34671094052` — SUCCESS;
- Repository contracts — run `34671094084` — SUCCESS.

Final-head CI and `main` drift must still be checked immediately before Gate 2 merge approval is acted on.

## 8. What C0.4 does not prove

A clean C0.4 plan does not prove that OpenOCD can physically program every admitted device. It does not qualify:

- Flash-controller or Flash-geometry equivalence;
- erase/program/verify behavior;
- option bytes or security transitions;
- PPU runtime support;
- Z2/FPGA/SWD electrical behavior;
- real-IC HIL.

Those require separate IC Support/runtime/HIL evidence chains.

## 9. Next action

If PR #500 final-head CI remains green and `main` is synchronized, the next gate is **Gate 2 — Merge Approval for PR #500**.

C0.5 is out of scope. A future C0.5 transaction may perform controlled publication of the **209 capability-admittable identities only**. The 11 unresolved identities must remain excluded until a separate reviewed routing-evidence transaction resolves them. C0.5 requires a new Gate 1 approval.
