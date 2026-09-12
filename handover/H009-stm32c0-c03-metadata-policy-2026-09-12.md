# H009 — STM32C0 C0.3 Metadata Policy Handover

**Date:** 2026-09-12
**Status:** C0.3 implementation complete; PR #496 merge-ready candidate pending Gate 2
**Primary workstream:** Device Catalog / STM32C0
**Repository:** `physicslu/plasma`
**C0.3 branch:** `agent/device-catalog-stm32c0-phase-c03-metadata-policy`
**PR:** `#496`

## 1. Transaction boundary

C0.3 is a manufacturer-authoritative commercial metadata-policy transaction over exactly the STM32C0 identities retained by C0.2:

- 50 Base Devices;
- 220 unique Active exact ICPNs;
- one excluded non-Active exact part remains excluded: `STM32C091KBT3` (`Preview`);
- OpenOCD routing is observation only and cannot gate commercial identity or metadata;
- CMSIS aliases are not commercial identity or metadata authority.

Commercial identity/lifecycle authority remains the retained C0.2 official-ST Quality & Reliability exact identity plus Sample & Buy Marketing Status exact-set join. C0.3 metadata authority is official ST datasheet Ordering Information.

C0.3 does not authorize canonical admission, Production publication, programming-policy or algorithm equivalence, Flash-controller qualification, option/security qualification, HIL/electrical qualification, or runtime support.

## 2. Production boundary

C0.3 freezes the transaction prestate at:

```text
Production exact ICPNs:    703
Production Base Devices:   243
Production STM32 families: 9
Production STM32C0 ICPNs:  0
```

The C0.3 Production prestate is byte-identical to:

- Git blob: `89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc`;
- SHA-256: `903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0`.

Both identities are enforced by the C0.3 planner/tests. Production itself is not modified by this transaction.

## 3. Official Ordering Information authority

Current official ST document revisions were revalidated on 2026-09-12:

| Series | ST document | Revision | Ordering page |
| --- | --- | ---: | ---: |
| STM32C011 | DS13866 | 5 | 93 |
| STM32C031 | DS13867 | 4 | 100 |
| STM32C051 | DS14721 | 2 | 107 |
| STM32C071 | DS14693 | 2 | 128 |
| STM32C091 | DS14720 | 3 | 121 |
| STM32C092 | DS14720 | 3 | 121 |

No revision drift was observed. C091 and C092 legitimately share DS14720, but remain distinct manufacturer series.

C071 semantics are explicitly hard-locked:

- `N` = N product version;
- `TR` = tape-and-reel packing;
- `NTR` = N product version plus tape-and-reel packing;
- these suffixes must not be collapsed or normalized away;
- C071 `F/P` resolves to TSSOP20 while `F/Y` resolves to WLCSP19, so pin count is package-dependent.

## 4. Implemented C0.3 assets

The transaction adds or updates:

- `data/device-catalog/research/stm32c0_metadata_policy.py`;
- `data/device-catalog/research/stm32c0_phase_c0_3_policy.py`;
- `data/device-catalog/research/test_stm32c0_phase_c0_3_policy.py`;
- `data/device-catalog/research/stm32c0-phase-c0.3-ordering-authority.json`;
- `data/device-catalog/research/stm32c0-phase-c0.3-production-manifest-prestate.json`;
- `data/device-catalog/research/stm32c0-phase-c0.3-policy-baseline.json`;
- `data/device-catalog/research/device-catalog-stm32c0-phase-c0.3-metadata-policy.md`;
- `.github/workflows/device-catalog-stm32c0-c03-metadata-validation.yml`;
- centralized `stm32c0` family-CI profile and trigger routing.

The temporary runner-only baseline-generation step was used only to obtain deterministic output and was removed before merge readiness. Final C0.3 validation is read-only replay.

## 5. Deterministic closure

The synchronized PR merge candidate replayed C0.1, C0.2, and C0.3 successfully. The C0.3 test suite contains 15 negative/boundary tests and the centralized STM32C0 profile contains six deterministic entrypoints.

Observed C0.3 result:

```text
candidate_count:        220
base_device_count:      50
metadata_ready:         220
manual_review_required: 0
reject:                 0
```

Frozen metadata-row SHA-256:

`94ebe11fda28cb6d7b68c13c7edb4bf8341887f6146d52f72461bc6ef35bee19`

Frozen exact-ICPN-set SHA-256:

`b116f624e971a3be5c947e107589bdb4d1bf5f5b0585ecae71e743cfb7a2649a`

Metadata distributions:

- Flash: 16 KiB=20, 32 KiB=51, 64 KiB=49, 128 KiB=55, 256 KiB=45;
- package: LQFP=77, SO8N=7, TSSOP=31, UFBGA=7, UFQFPN=97, WLCSP=1;
- pin count: 8=7, 19=1, 20=36, 28=31, 32=63, 48=57, 64=25;
- temperature: -40..85 C=127, -40..105 C=54, -40..125 C=39;
- option suffix: blank=121, `TR`=80, `N`=16, `NTR`=3.

These are observed deterministic runner results, not targets forced by the policy.

## 6. Fail-closed controls

C0.3 validation covers:

- retained C0.2 evidence and exact 220/50 scope;
- all 220 metadata decodes;
- C071 `N`, `TR`, and `NTR` separation;
- C071 package-dependent `F/P` versus `F/Y` pin count;
- C091/C092 shared authority without series collapse;
- official Ordering Information revision drift;
- excluded Preview `STM32C091KBT3` rejection;
- syntactically plausible but unretained exact identity rejection;
- CMSIS-shaped identity rejection;
- removal of C071 `N` authority failing closed;
- Production prestate Git-blob and SHA-256 identity;
- Production and runtime/capability claims remaining false.

## 7. Merge-readiness state

Current `main` was merge-forwarded into the C0.3 branch through PR #497 without rebase, force-push, or history rewrite. The synchronized branch has merge base exactly current `main` (`222d052a6442c7f7230e69b03cd290cbdf179c57`) and was 19 commits ahead / 0 behind at qualification.

On the synchronized implementation head, all applicable PR workflows passed:

- STM32C0 C0.3 metadata validation;
- STM32 family validation, including F0/F2/F3/F7/G0/G4/U0/C0;
- Device Catalog validation;
- Device Catalog current validation;
- Repository contracts.

PR #496 had no submitted reviews, no inline review threads, and GitHub reported it mergeable. This handover/index status update is documentation-only; final-head CI must remain green before Gate 2 is presented.

## 8. Next action

If final-head CI remains green and `main` has not advanced again, the only next gate is **Gate 2 — Merge Approval for PR #496**.

Do not start C0.4 or C0.5 under the C0.3 Gate 1 approval. C0.4 is a separate read-only admission-plan transaction and requires a new Gate 1 after C0.3 is merged.
