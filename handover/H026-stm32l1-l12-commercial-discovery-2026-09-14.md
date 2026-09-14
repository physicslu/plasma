# H026 — STM32L1 L1.2 Manufacturer-Authoritative Commercial Discovery

Date: 2026-09-14
Status: **Gate 1 implementation complete; Gate 2 merge approval required**
PR: #542 — `Device catalog: discover STM32L1 L1.2 commercial identities`
Branch: `agent/device-catalog-stm32l1-l12-commercial-discovery`

## 1. Approved Gate 1 scope

STM32L1 L1.2 performs bounded manufacturer-authoritative commercial discovery only:

- derive the complete bounded Base Device candidate set from the frozen 87 L1.1 STM32L1 ordering patterns;
- use official ST Quality & Reliability as exact Part Number identity authority;
- use official ST Sample & Buy Marketing Status as lifecycle authority;
- require exact-set joins before lifecycle disposition;
- apply TN1176 generation-aware handling: STM32L100/L151/L152 x6/x8/xB require canonical legacy plus Generation-A companion pages;
- retain provenance/evidence, deterministic negative controls, hard-lock validation, and permanent offline CI;
- keep Production read-only.

Explicitly outside scope: metadata policy, canonical admission/publication, Flash geometry, erase/program algorithms, option/security qualification, electrical/socket qualification, HIL, PPU deployment, and runtime programming support.

## 2. Frozen input boundary

L1.1 foundation:
- Git blob: `8da20cfc02c8106d5163338e85fb6425bc9ccdc9`
- OpenOCD catalog SHA-256: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- frozen ordering patterns: 87
- L1.1 representatives: `STM32L100C6`, `STM32L151C6`, `STM32L152C6`, `STM32L162QC`

Gate 1 Production manifest blob:
`1aa2311a25a69742c428147a402816ed5071e04e`

Production prestate and poststate remain:
- exact ICPNs: **1,718**
- Base Devices: **530**
- families: **12**
- STM32L1 Production exact ICPNs: **0**

## 3. Deterministic L1.2 discovery boundary

The 87 frozen ordering patterns collapse to:

- Base Devices: **59**
- official-ST evidence surfaces: **78**
- legacy + Generation-A paired targets: **19**
- subfamilies: STM32L100 / STM32L151 / STM32L152 / STM32L162

Base Device set SHA-256:
`a655af5a5063748a3e493ebe40c4a98d91722a1daa672e4965bcb4a105022595`

Deterministic target manifest SHA-256:
`ecedbe5da6ef960cbab049c728c027e6bc0fc55596727a514b20a8a9880a8eb8`

## 4. Browser acquisition correction

Early headless/global-deadline runs failed systemically and are not evidence authority.

The authoritative policy was established by headed calibration and uses:

- headed Chromium under Xvfb (`headless=false`)
- browser reuse enabled
- per-device global deadline disabled
- per-surface timeout: 90 seconds
- Playwright `1.62.0`
- Chromium `151.0.7922.34`
- four deterministic shards, maximum two concurrent

This preserves slow-but-valid ST page acquisition and avoids interpreting transport timeout as commercial identity evidence.

## 5. Authoritative live acquisition

Workflow run: **34765901513**, attempt 1
Executed SHA: `d0018aa512fc94127ad4bb1aab2ee8ab2ccdfc41`
Artifact ID: **10321123053**
Artifact name: `stm32l1-l12-live-34765901513-1`
Artifact SHA-256: `a659f1f6751cf9a249ac64e7d8d654497c40077ceac6bf6794c5f4eda21be9c0`
Raw live-summary SHA-256: `74ad8d3630874f0f6ffe8454a8970508882402fc7e57a2f754944d9dffd28624`
Raw target SHA-256: `ecedbe5da6ef960cbab049c728c027e6bc0fc55596727a514b20a8a9880a8eb8`

All four shards and aggregate completed successfully.

## 6. Commercial discovery result

- Active candidate Base Devices: **59**
- Active exact ICPNs: **144**
- excluded non-Active exact variants: **62**
- lifecycle-excluded Base Devices: **0**
- manual intervention: **0**
- acquisition failures: **0**
- source-unavailable exclusions: **0**
- OpenOCD routing: **59 unique / 0 ambiguous / 0 unmapped / 0 not-applicable**
- routing follow-up required: **0**
- L1.1 representative continuity: **PASS**
- `commercial_identity_clean = true`
- `bounded_discovery_clean = true`

Active exact ICPN set SHA-256:
`0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`

Excluded exact ICPN set SHA-256:
`c839c5063c990b62c4ea051aa15901070a6e38feb1c182f13cb2577b9ababa56`

## 7. Retained evidence and permanent validation

Retained evidence root:
`data/device-catalog/research/evidence/stm32l1-l1.2-official-st-discovery-live-2026-09-13/`

Retained files:
- `commercial-identity.json` — SHA-256 `b55695589ea47b84e6097725f68ac888d652ffd0865e8724066b3dda7fe81555`
- `leaf-digests.json` — SHA-256 `20fc8bb2faca2171d21966ee8930e1184012530ed8f30378c575ebce887bcd17`
- `provenance.json` — SHA-256 `180179f59d1c377870b78b3fcbe1a91f4fdb5785f69df0fb4ebd89033f1d79de`
- `retained-manifest.json` — SHA-256 `31562944157c9ea754f90adecf7018e7611d57a78f113d7f4e16ec4e2b6669e8`

Permanent validator:
`data/device-catalog/research/validate_stm32l1_phase_l1_2_retained_evidence.py`

Permanent offline workflow:
`.github/workflows/device-catalog-stm32l1-l12-retained-validation.yml`

The permanent workflow performs negative controls, deterministic boundary replay, retained evidence hard-lock, and Production zero-diff enforcement without contacting ST.

Temporary live/calibration/manifest workflows were removed before Gate 2 readiness.

## 8. Main synchronization and final CI

Evidence closure commit:
`157547913a6bd30f2bdd785ad48e29b33c4f32c1`

Latest main synchronized before final handover:
`79f13715319bd219b3bac9c43cbace58e8ad4704`

Final synchronized engineering head before this handover-only commit:
`f6b255082f2125473f825f30fc91a42e760dc337`

No catalog/research path overlap was found in the concurrent main changes incorporated during synchronization.

CI on `f6b255082f2125473f825f30fc91a42e760dc337`:
- STM32L1 L1.2 retained discovery validation — run `34799948232` — **SUCCESS**
- Device catalog validation — run `34799948265` — **SUCCESS**
- Device catalog current validation — run `34799948288` — **SUCCESS**
- Repository contracts — run `34799948214` — **SUCCESS**

The retained discovery validation includes a Production zero-diff guard and passed.

## 9. Governance disposition

L1.2 establishes manufacturer-authoritative commercial identity/lifecycle evidence only. The 144 Active exact ICPNs are **research candidates**, not Production admission.

No Production files are modified by PR #542.

Next governance action: **Gate 2 Merge approval for PR #542**. Merge must not occur without explicit approval.
