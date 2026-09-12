# STM32L0 Phase L0.2 — Manufacturer-Authoritative Commercial Discovery

## Purpose

L0.2 expands the frozen L0.1 STM32L0 ordering-pattern surface into the deterministic complete Base Device research set, then resolves exact commercial Part Numbers and lifecycle from official ST evidence.

This phase is research-only. It does not authorize canonical admission, Production publication, programming-policy equivalence, Flash/security qualification, socket/electrical qualification, HIL, or runtime programming support.

## Frozen input boundary

- L0.1 baseline SHA-256: `958572fa69a4457966256851a39badfdc38490e0c3ce155978155baf3ca9e488`
- OpenOCD catalog SHA-256: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- L0.1 research surface: 166 rows
- ordering patterns: 164
- CMSIS aliases: 2
- STM32L0 subfamilies: 16
- immutable Production prestate: 912 exact ICPNs; STM32L0 0

OpenOCD bounds the deterministic research surface and supplies routing diagnostics. It is not commercial identity or lifecycle authority.

## Deterministic discovery surface

Collapsing the 164 frozen ordering patterns to unique concrete Base Devices yields:

- 99 unique Base Devices
- 16/16 subfamilies covered
- all 16 L0.1 representatives retained

Counts by subfamily:

| Subfamily | Base Devices |
|---|---:|
| STM32L010 | 6 |
| STM32L011 | 10 |
| STM32L021 | 4 |
| STM32L031 | 10 |
| STM32L041 | 5 |
| STM32L051 | 8 |
| STM32L052 | 8 |
| STM32L053 | 4 |
| STM32L062 | 2 |
| STM32L063 | 2 |
| STM32L071 | 11 |
| STM32L072 | 9 |
| STM32L073 | 7 |
| STM32L081 | 3 |
| STM32L082 | 3 |
| STM32L083 | 7 |

## Manufacturer authority

Commercial identity/lifecycle authority is:

`official_st_quality_and_reliability_exact_identity_plus_sample_and_buy_marketing_status_exact_set_join`

- ST Quality & Reliability supplies exact Part Number identity.
- ST Sample & Buy supplies Marketing Status.
- Exact Part Number sets must join exactly before lifecycle disposition is accepted.
- Acquisition uses rendered Chromium DOM through the shared dual-surface adapter.

## Authoritative live acquisition

Workflow run: `34686132303`

Artifact: `10296507776`

Artifact ZIP SHA-256:

`5732782fce1911debe7360c07ccbae5ba03fd86cc097a975bc271fe9c6b334bd`

Acquisition source PR head:

`996489c8fe5e871310dd42c0d06c7b0302ca0750`

Executed pull-request merge ref:

`4423e029cea8ac541d25c87ea8612fae2a3e68ee`

Browser profile:

- Chromium `151.0.7922.34`
- Playwright `1.62.0`
- headed browser acquisition
- parser profile `stm32l0_l0_2_dual_surface_v1`

Observed acquisition interval: `2026-09-12T09:33:19Z` through `2026-09-12T11:07:23Z`.

## Discovery result

```text
Base Devices attempted:                 99
commercial identity verified:           99
Active-candidate Base Devices:           99
lifecycle-only Base Devices:              0
source unavailable:                       0
manual review:                            0
acquisition failures:                     0
Active exact ICPNs:                     360
excluded non-Active exact Part Numbers:  10
OpenOCD unique routing targets:           99
routing follow-up required:                0
L0.1 representative continuity:         PASS
bounded commercial discovery:           CLEAN
```

Active exact ICPN sorted-set SHA-256:

`8c7f0cc10829ff5e1ceb98cf6783247a5f685a9f1407dbd560a350348c0a521b`

Base Device sorted-set SHA-256:

`1c9dc41c8f8dc44a132e8303e0c88b2168dc3bbf745a6250aa7f382e57d5f8af`

Excluded non-Active exact Part Number sorted-set SHA-256:

`86be718862ed2641a3e857d0d7016aca459852d7dc3f210123893b28f66a6960`

Excluded exact Part Numbers:

- `STM32L011K4T7`
- `STM32L011K4U7`
- `STM32L021F4U7TR`
- `STM32L021G4U7`
- `STM32L021K4T7`
- `STM32L031F4P7`
- `STM32L071RZT7`
- `STM32L071VBT7`
- `STM32L071VZT7`
- `STM32L073V8T7`

## Retained evidence

Evidence root:

`data/device-catalog/research/evidence/stm32l0-l0.2-official-st-discovery-live-2026-09-12/`

The retained `live-summary.json` embeds the complete 99 evidence records. The original workflow artifact also contained one canonical JSON leaf per Base Device. To avoid duplicating the same evidence twice in Git, `leaf-digests.json` retains every original leaf SHA-256. The permanent validator reconstructs every leaf byte-for-byte from the embedded evidence record and checks the retained digest map.

Important retained digests:

- live summary: `c664e6458d00f169b2653021284acb56664b607c245e97f51bf13f4a232d51de`
- targets: `72350a146038c09b43516715f52cddf06ee5d05f1a4ab737a994744d43e166ed`
- acquisition provenance: `2e7379f865b0f5e23101517f58d7a53ec5076820a0240369d99cb34b1f08862c`
- leaf digest map: `79b562f6eb87081544cd409c399d68f3afa06f644501a243d272be37004c4502`
- retention provenance: `23bd258b75f687b01e43beb249f759b4d71a704ba56480ce170c054017cb635f`
- retained manifest: `66e4c248398e8986878538c3dde7cc3811df0f3f1a0fbbbd2b1f46c77a20e97a`

## Validation

Permanent validation includes:

- 9 negative/offline discovery controls;
- deterministic 99-Base-Device manifest replay;
- exact retained evidence manifest membership and digest validation;
- original workflow/artifact/provenance bindings;
- 99 reconstructed leaf evidence digests;
- 360-ICPN exact-set uniqueness and digest;
- 10 excluded-Part-Number uniqueness and digest;
- 99/99 OpenOCD routing observations to `tcl/target/stm32l0.cfg` while preserving non-gating semantics;
- L0.1 representative exact-set continuity;
- immutable 912-row Production prestate and STM32L0 Production count 0;
- fail-closed authority claims.

Qualification head `f166d000c08d2d1f2f2154d0ded4a470a2e7d8d7` passed:

- STM32L0 L0.2 discovery validation — run `34690722116`
- Repository contracts — run `34690722124`
- Device catalog validation — run `34690722134`
- Device catalog current validation — run `34690722146`

## Production boundary

L0.2 performs zero Production writes.

```text
Production exact ICPNs: 912 (delta 0)
Production Base Devices: 293 (delta 0)
Production STM32 families: 10 (delta 0)
STM32L0 Production exact ICPNs: 0
```

The 360 Active exact ICPNs are manufacturer-authoritative research candidates, not Production entries.
