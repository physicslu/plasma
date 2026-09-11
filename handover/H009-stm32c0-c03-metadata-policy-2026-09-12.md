# H009 — STM32C0 C0.3 Metadata Policy Handover

**Date:** 2026-09-12
**Status:** C0.3 Gate 1 approved; implementation and CI qualification in progress
**Primary workstream:** Device Catalog / STM32C0
**Repository:** `physicslu/plasma`
**C0.3 branch:** `agent/device-catalog-stm32c0-phase-c03-metadata-policy`
**Draft PR:** `#496`

## 1. Transaction boundary

C0.3 is a manufacturer-authoritative commercial metadata-policy transaction over exactly the STM32C0 identities retained by C0.2:

- 50 Base Devices;
- 220 unique Active exact ICPNs;
- one excluded non-Active exact part remains excluded: `STM32C091KBT3` (`Preview`);
- OpenOCD routing is observation only and cannot gate commercial identity or metadata;
- CMSIS aliases are not commercial identity or metadata authority.

Commercial identity/lifecycle authority remains the retained C0.2 official-ST Quality & Reliability exact identity plus Sample & Buy Marketing Status exact-set join. C0.3 metadata authority is official ST datasheet Ordering Information.

C0.3 does not authorize canonical admission, Production publication, programming-policy or algorithm equivalence, Flash-controller qualification, option/security qualification, HIL/electrical qualification, or runtime support.

## 2. Current Production boundary

C0.3 freezes the transaction prestate at:

```text
Production exact ICPNs:    703
Production Base Devices:   243
Production STM32 families: 9
Production STM32C0 ICPNs:  0
```

The C0.3 Production prestate is byte-identical to Git blob `89cbaa8807daf8f9c55bc8c1ca0bc1c05eaec1fc`. Production itself is not modified by this transaction.

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

Current branch contains:

- `data/device-catalog/research/stm32c0_metadata_policy.py`
- `data/device-catalog/research/stm32c0_phase_c0_3_policy.py`
- `data/device-catalog/research/test_stm32c0_phase_c0_3_policy.py`
- `data/device-catalog/research/stm32c0-phase-c0.3-ordering-authority.json`
- `data/device-catalog/research/stm32c0-phase-c0.3-production-manifest-prestate.json`
- `data/device-catalog/research/stm32c0-phase-c0.3-policy-baseline.json`
- `.github/workflows/device-catalog-stm32c0-c03-metadata-validation.yml`

The temporary runner-only baseline generation step was used only to obtain deterministic output, then removed. Final C0.3 validation is read-only replay.

## 5. Deterministic runner result

GitHub Actions C0.3 run #2 executed the retained C0.2 validator, 14 C0.3 negative/boundary tests, and the planner successfully.

Observed deterministic closure:

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

These are observed runner results, not targets forced by policy.

## 6. Negative controls already passing

The current C0.3 tests cover:

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
- Production and runtime/capability claims remaining false.

## 7. Remaining work before Gate 2

The transaction is not merge-ready yet. Remaining work is routine Gate-1 execution:

1. integrate C0.3 into the centralized `stm32c0` family-CI profile;
2. add/finalize the C0.3 transaction documentation;
3. resolve the branch-only H009 whitespace regression and verify `git diff --check`;
4. review current `main` drift and merge-forward without rebase/history rewrite if needed;
5. run final PR workflows on the synchronized head;
6. inspect PR diff, reviews, mergeability, and CI;
7. mark PR Ready when merge-ready, then stop for Gate 2 Merge Approval.

Do not start C0.4 or C0.5 under this Gate 1 approval.
