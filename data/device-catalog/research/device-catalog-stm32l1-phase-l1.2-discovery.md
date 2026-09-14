# STM32L1 Phase L1.2 — Manufacturer-Authoritative Commercial Discovery

Status: **commercial discovery complete; research evidence retained; Production unchanged**

## Scope

L1.2 expands the frozen L1.1 STM32L1 ordering-pattern surface into the complete bounded commercial research set and observes exact manufacturer part-number identity and lifecycle from official ST product pages.

Identity authority:
- ST **Quality & Reliability** exact Part Number identity.
- ST **Sample & Buy** Marketing Status.
- Exact-set join is required before lifecycle disposition.
- `TN1176` controls legacy versus Generation-A handling for STM32L100/L151/L152 x6/x8/xB devices.
- OpenOCD is routing/research evidence only and does not establish commercial identity.

## Deterministic boundary

- Frozen L1.1 ordering patterns: 87
- Unique STM32L1 Base Devices: **59**
- Official-ST evidence surfaces: **78**
- Legacy + Generation-A pairs: **19**
- Subfamilies: STM32L100, STM32L151, STM32L152, STM32L162

The deterministic target manifest replay SHA-256 is:

`ecedbe5da6ef960cbab049c728c027e6bc0fc55596727a514b20a8a9880a8eb8`

## Authoritative acquisition

Authoritative full run:
- GitHub Actions run: `34765901513`, attempt 1
- Executed SHA: `d0018aa512fc94127ad4bb1aab2ee8ab2ccdfc41`
- Artifact ID: `10321123053`
- Artifact: `stm32l1-l12-live-34765901513-1`
- Artifact SHA-256: `a659f1f6751cf9a249ac64e7d8d654497c40077ceac6bf6794c5f4eda21be9c0`
- Playwright: `1.62.0`
- Chromium: `151.0.7922.34`
- Browser policy: headed Chromium under Xvfb, browser reuse enabled, per-device global deadline disabled, 90-second per-surface timeout
- Shards: 4 deterministic shards, maximum 2 concurrent

All four live shards and the aggregate job passed.

## Result

- Active candidate Base Devices: **59**
- Active exact ICPNs: **144**
- Excluded non-Active exact variants: **62**
- Lifecycle-excluded Base Devices: **0**
- Manual intervention: **0**
- Acquisition failures: **0**
- Source unavailable exclusions: **0**
- OpenOCD routing: **59 unique / 0 ambiguous / 0 unmapped**
- Routing follow-up required: **0**
- L1.1 representative continuity: **PASS**
- `commercial_identity_clean = true`
- `bounded_discovery_clean = true`

Exact-set digests:
- Base Device set: `a655af5a5063748a3e493ebe40c4a98d91722a1daa672e4965bcb4a105022595`
- Active exact ICPN set: `0fcc20ca062da9c7e564b141b38c529c2c3a27a6ca781a2473f9f617e2886a12`
- Excluded exact ICPN set: `c839c5063c990b62c4ea051aa15901070a6e38feb1c182f13cb2577b9ababa56`

## Retained evidence

Repository retention root:

`data/device-catalog/research/evidence/stm32l1-l1.2-official-st-discovery-live-2026-09-13/`

Retained material includes:
- exact Active/non-Active commercial identity disposition by Base Device;
- immutable source artifact and raw-summary/target digests;
- all 59 full leaf-record SHA-256 digests;
- acquisition/browser provenance;
- a retained manifest binding the evidence files.

Permanent CI performs deterministic offline replay and hard-lock validation. It does not contact ST.

## Production boundary

L1.2 remains research-only.

Production stays:
- exact ICPNs: **1,718**
- Base Devices: **530**
- families: **12**
- STM32L1 Production exact ICPNs: **0**

No metadata policy, canonical admission, publication, Flash geometry, erase/program algorithm, option/security qualification, socket/electrical qualification, HIL, PPU deployment, or runtime programming support is claimed.

## Methodology correction retained from requalification

Lifecycle is an **exact-variant/page-generation property**, not a subfamily-level property. Legacy canonical pages can be NRND while the corresponding Generation-A companion page contains Active orderable variants. L1.2 therefore never collapses Generation-A identity into legacy identity.
