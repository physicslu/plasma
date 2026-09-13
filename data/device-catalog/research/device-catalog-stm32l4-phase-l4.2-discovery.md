# STM32L4 Phase L4.2 Manufacturer-Authoritative Commercial Discovery

## Scope

Phase L4.2 converts the frozen STM32L4 L4.1 ordering-pattern research surface into a complete bounded Base Device commercial-identity research set using official ST evidence.

This phase is **research only**. It does not authorize canonical admission, Production publication, Flash/programming policy, option/security semantics, socket/electrical qualification, HIL qualification, algorithm equivalence, or runtime programming support.

## Frozen input boundary

- L4.1 OpenOCD source rows: 255
- L4.1 ordering patterns: 207
- CMSIS aliases: 48
- STM32L4 subfamilies: 24
- Deterministic L4.2 Base Devices: 138
- L4.1 representative continuity requirement: 24/24
- L4.1 foundation SHA-256: `3f85587e74f9af1ee93f59d53a05ea1d47201e6b8564b8e8a91cb91f378bd40f`
- OpenOCD catalog SHA-256: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- Frozen Production prestate SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`
- Frozen Production exact ICPNs before L4.2: 1272
- STM32L4 Production exact ICPNs before L4.2: 0

## Evidence authority

Commercial identity/lifecycle authority is:

`official_st_quality_and_reliability_exact_identity_plus_sample_and_buy_marketing_status_exact_set_join`

The evidence contract is deliberately dual-surface:

1. ST Quality & Reliability supplies exact Part Number identity.
2. ST Sample & Buy supplies Marketing Status.
3. The exact sets must join before lifecycle disposition is accepted.
4. OpenOCD is a research/routing diagnostic source only; it is not manufacturer commercial-identity authority.
5. Manufacturer evidence is not canonical or Production admission.

## Acquisition history

### Initial bounded acquisition

GitHub Actions run `34713341677` executed at Git SHA `8d45ed34bd1029055ba9a6fd035f23ea4f4ebb6f`.

- Artifact ID: `10304163363`
- Artifact SHA-256: `e04253546cfba83209bf0b55f8fe46de4b5e14110bbc1bb5b95aefcb46d984a4`
- Browser reuse: enabled
- Per-device global deadline: enabled
- Per-device timeout: 75 seconds
- Attempted: 138 Base Devices
- Successful: 123
- Timed out: 15

The 15 timeout Base Devices were exactly:

- `STM32L412CB`
- `STM32L412RB`
- `STM32L412T8`
- `STM32L451VC`
- `STM32L471QG`
- `STM32L471VG`
- `STM32L475RE`
- `STM32L496QG`
- `STM32L496VE`
- `STM32L4P5ZE`
- `STM32L4Q5CG`
- `STM32L4Q5RG`
- `STM32L4R9VG`
- `STM32L4S5ZI`
- `STM32L4S9ZI`

All 15 failed for the same bounded transport reason: the 75-second per-device global acquisition deadline was exceeded. They were not accepted as commercial identity evidence from the failed run.

### Targeted timeout recovery

GitHub Actions run `34741498287` executed at Git SHA `5a066ac1d9d2c92961bf2c09553b3658b89e8e6f`.

- Recovery artifact ID: `10313235102`
- Recovery artifact SHA-256: `940df5092918fb267fab4bea0921680b01851978557e8434261f0e9a0d10d214`
- Retry scope: fixed whitelist of the 15 timed-out Base Devices only
- Browser reuse: enabled
- Per-device global deadline: enabled
- Recovery timeout: 180 seconds
- Successful recovery: 15/15

The recovery did not rerun or replace the 123 successful identity records. The retained provenance explicitly records two acquisition runs and a disjoint `123 + 15 = 138` contribution partition.

## Final retained research result

The merged retained evidence is clean under the L4.2 research contract:

- Base Devices: 138/138 dispositioned
- Active Base Device candidates: 138
- Active exact ICPN candidates: 446
- Excluded non-Active exact Part Numbers: 5
- Manual-review targets: 0
- Acquisition failures: 0
- Source-unavailable exclusions: 0
- L4.1 representative continuity: 24/24 Active
- OpenOCD routing: 138 unique, 0 ambiguous, 0 unmapped
- Routing follow-up required: 0
- `bounded_discovery_clean`: `true`

The five excluded exact non-Active Part Numbers are:

- `STM32L452CET6P`
- `STM32L462CET6P`
- `STM32L462CEU3`
- `STM32L462CEU6F`
- `STM32L476VGY6PTR`

These exclusions are lifecycle research findings, not Production mutations.

## Immutable retained contracts

Retained evidence root:

`data/device-catalog/research/evidence/stm32l4-l4.2-official-st-discovery-live-2026-09-13/`

Retained repository files:

- `live-summary.json`
- `targets.json`
- `provenance.json`
- `leaf-digests.json`
- `retained-manifest.json`

The 138 full leaf records remain in the immutable Actions artifact; the repository retains the leaf digest map and aggregate evidence needed for deterministic replay and hard-lock validation.

Hard-lock SHA-256 values:

- live summary: `0c9279000bf69384ed167049c711bfe7b6fe4e1274288cc1bbd6b21e6bafc784`
- targets: `568726e2b285831b1d17d49bf1da78ae7fde12ff720d24190c5fb5dcd2cd44d9`
- provenance: `774f7391a45d4106d0fcbb019d4aa7ac31a3c72691586c55b489f3d63f234587`
- leaf digest map: `4231e22e22b646dc8aa2c859740ea778e84aca8f6b516fc3b5e93ac7dec7b47d`
- retained manifest: `b2809115666d6ed3afd1af50c62fcb7d95bcbdbfdb472080fa51cfa4b0f0b56e`

Set SHA-256 values:

- Base Device set: `d014a837f40cd2c4bebaa39ef92261cd3eb4a4f30f26aed1225f32d77c2c781d`
- Active exact ICPN set: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`
- excluded non-Active set: `72b21e849db53a724f7162394e1bfa3c5d7ff9f68726b6088e8cadae502e5e23`

## Validation boundary

The permanent L4.2 validator hard-locks and replays:

- deterministic 138-Base-Device manifest bytes;
- L4.1/OpenOCD/Production source bindings;
- two-run provenance and the exact 123+15 contribution partition;
- exact initial artifact identity and digest;
- exact targeted retry whitelist;
- 138 retained leaf digests reconstructed from summary rows;
- exact Active and excluded sets, including cross-set collision rejection;
- 24/24 L4.1 representative continuity;
- fail-closed unsupported claims;
- zero STM32L4 Production writes.

The permanent validator passed after the dual-run hard-lock was installed. Final Gate 2 qualification must still be performed against the then-current `main` and final PR head.

## Admission boundary

L4.2 produces a manufacturer-authoritative commercial discovery research candidate set only. The following remain false:

- canonical admission authorized;
- manufacturer evidence equals admission;
- Production write authorized;
- Flash geometry qualified;
- programming policy defined;
- programming algorithm equivalence established;
- option/security semantics qualified;
- physical/HIL qualification complete;
- runtime programming support claimed.

No later phase may infer any of those properties from L4.2 commercial discovery alone.
