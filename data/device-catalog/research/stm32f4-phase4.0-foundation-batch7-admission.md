# STM32F4 Phase 4.0 Foundation Batch 7 Admission

## Scope

This phase promotes retained official-ST evidence for two policy-ready STM32F4 base devices into the production Device Catalog. It does not change IC Support Programming Profiles, programming-algorithm equivalence, PS/PL runtime ownership, deployment, or hardware behavior.

Admission set:

- `STM32F439ZG`
- `STM32F439ZI`

Lifecycle control:

- `STM32F439VG`

New exact admitted commercial ICPNs: **7**.

## Fresh post-Batch6 inventory

The batch was selected from the merged Batch6 production state rather than from the prior cached gap list:

- OpenOCD ordering-pattern Base Devices: `149`
- production Base Devices: `41`
- STM32F4 production exact ICPNs: `133`
- remaining Base Device gaps: `108`
- policy-ready gaps: `15`
- policy-blocked gaps: `93`

`STM32F439ZG` and `STM32F439ZI` were selected as a bounded adjacent STM32F439 cluster already covered by the existing package/pin/flash admission policy. No policy expansion was required.

## Discovery and baseline freeze

Discovery workflow run: `33370308307`

Discovery artifact: `9749799501`

Discovery artifact ZIP SHA-256:

`f69cdfbdb3e9542aeba71c499900a386fcaa71d7efacd312299ffa171756f90c`

Discovery completed on the first bounded browser attempt with `3/3` targets clean. The observed Active exact ICPN surface was frozen as the Batch7 baseline:

- `STM32F439VG`: 1 lifecycle-control ICPN
- `STM32F439ZG`: 5 new candidate ICPNs
- `STM32F439ZI`: 2 new candidate ICPNs
- total Active exact ICPNs across control + candidates: `8`
- new admission candidates: `7`
- non-Active observations: `0`

The baseline explicitly sets `canonical_dataset_admission = false`. Discovery is acquisition input, not production authority.

## Formal live evidence and repository retention

Baseline-locked live evidence workflow run: `33370565000`

Retained evidence artifact: `9749987963`

Retained artifact ZIP SHA-256:

`64e14513f2c17dd2f1eaa1b793c86798f6334fdcfdcbaad1c1c5dd595f3ffa7a`

Retained evidence ID:

`stm32f4-phase4.0-foundation-batch7-2026-08-31-retained-20260831T080025Z-feef382`

Repository evidence directory:

`evidence/stm32f4-phase4.0-foundation-batch7-live-2026-08-31/`

Formal acquisition also completed on the first bounded attempt with `3/3` clean targets:

- candidate baseline drift: `0`
- non-Active lifecycle drift: `0`
- exact ICPN candidates: `8`
- deterministic OpenOCD ordering-pattern mapping: `3/3` Base Devices mapped to `tcl/target/stm32f4x.cfg`
- evaluator result: `scale_ready`
- canonical dataset admission during acquisition: `false`

After retention, the admission path is repository-local and does not depend on live ST access.

OpenOCD ordering-pattern mapping remains routing evidence only. It is not proof that these devices share one Programming Profile or one low-level flash algorithm.

## Read-only admission proposal

Proposal workflow run: `33371127532`

Proposal artifact: `9750084244`

Proposal artifact ZIP SHA-256:

`30a58d96549602e55ee0a6d91d5326b0f67d074b553873ec0101b91ee9b71b93`

The isolated proposal proved:

- `candidate_count = 7`
- `admit = 7`
- `already_present = 0`
- `manual_review_required = 0`
- `reject = 0`
- `conflicts = 0`
- STM32F4 canonical rows `133 -> 140`
- isolated proposed CSV passed the canonical validator

Immutable proposal bindings:

- admission plan SHA-256: `60866cf5ccc91952efea82953efca64137273cef614c173fa5ae00e666cff288`
- proposed/final STM32F4 CSV SHA-256: `f7fbf1d8b6bcc7728f20dcb30c0b261e4b315459f05f76d6123308621f66a0a7`
- final STM32F4 CSV Git blob: `34ad23b2e689bab51b1819ae015e0d334f63cd85`

Exact admitted ICPNs:

- `STM32F439ZGT6`
- `STM32F439ZGT6TR`
- `STM32F439ZGT7`
- `STM32F439ZGT7TR`
- `STM32F439ZGY6TR`
- `STM32F439ZIT6`
- `STM32F439ZIY6TR`

## Controlled publish

Before publish, `main` remained at the Batch6 merge commit `767484dc7dac808227faa04b5a5d679375b9148b`, and the production STM32F4 manifest still reported:

- rows: `133`
- CSV SHA-256: `4a6bf6ffbf384ce3d9c91d318b6793c710d621d6f9e11f0a6c5b50206a5acb2a`
- Git blob: `434443479cd8a7d5b87b723a9fde93806c4faddd`

The controlled publish transaction re-downloaded the exact proposal artifact, revalidated its ZIP/plan/CSV hashes, rebuilt the proposal from retained evidence, compared the rebuilt bytes with the proposal artifact, enforced the production precondition, then committed the canonical CSV, manifest, and admission audit as one promotion transaction.

Production result on the Batch7 branch:

- STM32F1 production exact ICPNs: `75`
- STM32F4 production exact ICPNs: `133 -> 140`
- total production exact admitted commercial ICPNs: `208 -> 215`

## Post-admission lifecycle proof

Offline regression requires:

1. retained evidence remains scale-ready and byte-valid;
2. current-state replanning returns `7/7 already_present` with zero new admits;
3. reconstructing the historical 133-row canonical dataset from pre-Batch7 evidence provenance reproduces the exact pre-write admission-plan SHA-256;
4. applying that historical plan yields `140` rows;
5. a second application is an explicit no-op;
6. regenerated canonical SHA-256 equals the checked-in 140-row production CSV;
7. the lifecycle-control ICPN `STM32F439VGT6` remains present;
8. the retained lifecycle audit remains empty because no non-Active part numbers were observed in this batch.

## Runtime and REST regression

The runtime catalog metadata is updated to `215` total admitted exact ICPNs with taxonomy `STM32F1=75` and `STM32F4=140`. Search-result limits remain capped at 100; metadata remains the source of truth for full family size.

`STM32F439ZGT7TR` is the Batch7 representative exact runtime/REST regression. It must resolve as an admitted `STM32F4` row with LQFP package, 144 pins, 1024 KiB flash, and `tcl/target/stm32f4x.cfg` routing.

## Final CI boundary

Temporary discovery, live-evidence, retention, admission-proposal, and controlled-publish workflows must be absent before merge. Final validation is offline/read-only and includes Device Catalog historical replay, production manifest/runtime checks, Python/PL regression, PPU release, Mock CD, browser runtime acceptance, and canonical terminology checks.
