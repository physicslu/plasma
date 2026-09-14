# H027 — STM32L1 L1.3 Manufacturer-Authoritative Metadata Policy

Date: 2026-09-14
Status: **Gate 1 implementation complete; Gate 2 merge approval required**
PR: #550 — `Device catalog: define STM32L1 L1.3 metadata policy`
Branch: `agent/device-catalog-stm32l1-l13-metadata-policy`

## 1. Approved Gate 1 scope

L1.3 consumes the merged L1.2 manufacturer-authoritative commercial result and defines a research-only metadata policy.

Approved work:
- freeze L1.2 59 Base Devices / 144 Active exact ICPNs / 62 excluded non-Active variants;
- complete official ST datasheet Ordering Information authority for all retained Active exact ICPNs;
- decode deterministic commercial metadata;
- preserve legacy and Generation-A identity separation under TN1176;
- fail closed on authority ambiguity/omission;
- permit only exact-ICPN exceptions if independently evidenced;
- retain a frozen baseline, negative controls, permanent offline validation, and zero-Production-diff guard.

Explicitly outside scope: canonical admission/publication, Flash geometry, erase/program algorithms, option/security programming qualification, electrical/socket qualification, HIL, PPU deployment, and runtime programming support.

## 2. Frozen input

L1.2:
- Base Devices: **59**
- Active exact ICPNs: **144**
- excluded non-Active exact variants: **62**
- Active exact set SHA-256: `0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`
- L1.2 baseline SHA-256: `2f44e54dfac6904cc9af485e14eeb54e2d1a564f1cb633668fdf8f3a78ab4f92`

Production prestate/poststate:
- exact ICPNs: **1,718**
- Base Devices: **530**
- families: **12**
- STM32L1 Production exact ICPNs: **0**
- manifest Git blob: `1aa2311a25a69742c428147a402816ed5071e04e`

## 3. Manufacturer metadata authority

The representative requalification authority was insufficient for complete metadata decoding.

L1.3 expands the authority model to **10 deterministic official ST Ordering Information records / 10 unique datasheets**:
- L100 Generation-A x6/x8/xB
- L100 xC
- L151/L152 Generation-A x6/x8/xB
- L151/L152 xC low-pin C/U
- L151/L152 xC high-pin R/V/Q/Z
- L151/L152 xD
- L151/L152 xE
- L162 xC
- L162 xD
- L162 xE

The L151/L152 xC low/high split is mandatory because the retained devices span different official Ordering Information tables. The records are intentionally non-overlapping.

TN1176 remains the migration authority keeping legacy and Generation-A commercial identities distinct.

Ordering authority SHA-256:
`c689e848a58a45e3b1d855e56f9a4bba5fb953a89a9565091c687fc7bb392bc9`

## 4. Full 144-ICPN replay

Calibration run:
- workflow: `STM32L1 L1.3 metadata baseline calibration`
- run: **34804382409**
- executed head: `6d66dad8de6fbf2c7450afd4c959c51c5909e20b`
- result: **SUCCESS**

Replay result:
- metadata-ready: **144**
- manual review: **0**
- reject: **0**
- exact metadata exceptions: **0**
- metadata-ready set SHA-256: `0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`
- metadata rows SHA-256: `c794a21a63e72d805170034defe4af4e749ce456966f9083efe2f4abfa4fe247`
- manual/reject sets: empty

The initial calibration run failed before replay because the unittest invocation did not include the research directory on Python's module search path. This was an execution-wrapper defect, not metadata evidence failure. The workflow invocation was corrected without changing authority or grammar.

## 5. Exception policy

`stm32l1-phase-l1.3-exact-variant-exceptions.json` is empty.

Exception file SHA-256:
`1b2c4bba21169e1351185d094b0da984ed2c0f03b4fb5ddf1edb431b9e74a763`

No family-wide grammar relaxation was required. Permanent validation rejects any non-empty exception whitelist in this phase.

## 6. Permanent validation

Frozen baseline:
`data/device-catalog/research/stm32l1-phase-l1.3-policy-baseline.json`

Baseline SHA-256:
`6da49ceda71a3611244e1961e6aca3809d5809f8f7106834123c6ae48e726e62`

Permanent validator:
`data/device-catalog/research/validate_stm32l1_phase_l1_3_policy.py`

Permanent CI:
`.github/workflows/device-catalog-stm32l1-l13-metadata-policy-validation.yml`

Validation requirements:
- L1.2 retained evidence remains valid;
- 10 authority records / 10 unique datasheets;
- exact exception whitelist remains empty;
- deterministic baseline rebuild equals committed baseline;
- 144 metadata-ready / 0 manual / 0 reject;
- metadata-ready set equals the L1.2 Active exact set;
- metadata-row hash remains fixed;
- Production remains 1,718 / 530 / 12 / STM32L1=0;
- no canonical admission/publication or programming/runtime claims escape.

## 7. Governance disposition

L1.3 establishes metadata policy only. It does **not** establish canonical admission or Production publication.

The next possible phase is L1.4 read-only capability/admission planning, which requires a separate Gate 1 after L1.3 merges.

Current governance action: **Gate 2 Merge approval for PR #550 is required after final synchronized CI passes.**
