# H020 — STM32L4 L4.2 Manufacturer-Authoritative Commercial Discovery

Date: 2026-09-13

## Status

STM32L4 Phase L4.2 commercial discovery is technically complete as a bounded **research** transaction and is being finalized as PR #521 Gate 2 candidate.

Do not merge PR #521 and do not start L4.3 without explicit Gate 2 approval.

## Scope completed

L4.2 expands the frozen L4.1 STM32L4 ordering-pattern surface into the complete deterministic Base Device research set, then resolves exact commercial Part Number identity and lifecycle from official ST dual-surface evidence.

Nothing in L4.2 authorizes canonical admission, Production publication, Flash/programming policy, option/security semantics, socket/electrical/HIL qualification, algorithm equivalence, or runtime programming support.

## Frozen boundary

- L4.1 source rows: 255
- Ordering patterns: 207
- CMSIS aliases: 48
- STM32L4 subfamilies: 24
- Deterministic L4.2 Base Devices: 138
- L4.1 representatives required: 24/24
- L4.1 baseline SHA-256: `3f85587e74f9af1ee93f59d53a05ea1d47201e6b8564b8e8a91cb91f378bd40f`
- OpenOCD catalog SHA-256: `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- Frozen Production prestate SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`
- Production exact ICPNs before L4.2: 1272
- STM32L4 Production exact ICPNs before L4.2: 0

## Evidence authority

Authority string:

`official_st_quality_and_reliability_exact_identity_plus_sample_and_buy_marketing_status_exact_set_join`

Rules:

- ST Quality & Reliability = exact Part Number identity.
- ST Sample & Buy = Marketing Status/lifecycle.
- Exact sets must join before lifecycle disposition is accepted.
- OpenOCD is routing/research diagnostic only.
- Manufacturer evidence is not admission.

## Acquisition provenance

### Initial run

- GitHub Actions run: `34713341677`
- Executed SHA: `8d45ed34bd1029055ba9a6fd035f23ea4f4ebb6f`
- Artifact ID: `10304163363`
- Artifact SHA-256: `e04253546cfba83209bf0b55f8fe46de4b5e14110bbc1bb5b95aefcb46d984a4`
- Policy: serial, browser reuse, global per-device deadline, 75 seconds/device
- Result: 123 success + 15 timeout

The fixed 15 timeout set was:

`STM32L412CB`, `STM32L412RB`, `STM32L412T8`, `STM32L451VC`, `STM32L471QG`, `STM32L471VG`, `STM32L475RE`, `STM32L496QG`, `STM32L496VE`, `STM32L4P5ZE`, `STM32L4Q5CG`, `STM32L4Q5RG`, `STM32L4R9VG`, `STM32L4S5ZI`, `STM32L4S9ZI`.

All 15 failed only because the bounded 75-second global per-device deadline was exceeded.

### Targeted recovery

- GitHub Actions run: `34741498287`
- Executed SHA: `5a066ac1d9d2c92961bf2c09553b3658b89e8e6f`
- Recovery artifact ID: `10313235102`
- Recovery artifact SHA-256: `940df5092918fb267fab4bea0921680b01851978557e8434261f0e9a0d10d214`
- Scope: exact fixed 15-device whitelist only
- Policy: serial, same official-ST dual surface, browser reuse, global per-device deadline, 180 seconds/device
- Result: 15/15 success

The retained provenance is schema v2 and explicitly records two acquisition runs. It hard-locks a disjoint and complete `123 + 15 = 138` contribution partition. Do not rewrite this as a single acquisition run.

## Final retained result

- Base Devices: 138/138
- Active Base Device research candidates: 138
- Active exact ICPN research candidates: 446
- excluded non-Active exact Part Numbers: 5
- manual review: 0
- acquisition failures: 0
- source unavailable: 0
- L4.1 representative continuity: 24/24 Active
- routing: 138 unique, 0 ambiguous, 0 unmapped
- routing follow-up: 0
- bounded discovery clean: true

Exact excluded non-Active set:

- `STM32L452CET6P`
- `STM32L462CET6P`
- `STM32L462CEU3`
- `STM32L462CEU6F`
- `STM32L476VGY6PTR`

## Retained contracts

Research document:

`data/device-catalog/research/device-catalog-stm32l4-phase-l4.2-discovery.md`

Baseline:

`data/device-catalog/research/stm32l4-phase-l4.2-discovery-baseline.json`

Root deterministic manifest:

`data/device-catalog/research/stm32l4-phase-l4.2-discovery-manifest.json`

Retained evidence root:

`data/device-catalog/research/evidence/stm32l4-l4.2-official-st-discovery-live-2026-09-13/`

Permanent validation:

- `.github/workflows/device-catalog-stm32l4-l42-discovery-validation.yml`
- `data/device-catalog/research/validate_stm32l4_phase_l4_2_retained_evidence.py`

Permanent manual live acquisition workflow:

- `.github/workflows/device-catalog-stm32l4-l42-live-discovery.yml`

All temporary acquisition/recovery/postprocess workflows and the temporary recovery utility must be absent from the final Gate 2 head.

## Hard-lock values

Retained files:

- live summary: `0c9279000bf69384ed167049c711bfe7b6fe4e1274288cc1bbd6b21e6bafc784`
- targets: `568726e2b285831b1d17d49bf1da78ae7fde12ff720d24190c5fb5dcd2cd44d9`
- provenance: `774f7391a45d4106d0fcbb019d4aa7ac31a3c72691586c55b489f3d63f234587`
- leaf-digests: `4231e22e22b646dc8aa2c859740ea778e84aca8f6b516fc3b5e93ac7dec7b47d`
- retained manifest: `b2809115666d6ed3afd1af50c62fcb7d95bcbdbfdb472080fa51cfa4b0f0b56e`

Set digests:

- Base Device set: `d014a837f40cd2c4bebaa39ef92261cd3eb4a4f30f26aed1225f32d77c2c781d`
- Active exact ICPN set: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`
- excluded set: `72b21e849db53a724f7162394e1bfa3c5d7ff9f68726b6088e8cadae502e5e23`

## CI state before final main synchronization

The permanent L4.2 validation workflow passed on commit `9f93aca24284f1bf221e687a7f1c4cd9df06c6d3`:

- negative controls: PASS
- deterministic 138-Base-Device manifest replay: PASS
- retained manufacturer evidence hard-lock: PASS
- zero Production writes: PASS

That pass proves the dual-run retained contract itself. It does **not** replace the required final qualification against the then-current `main` after synchronization and cleanup.

## Gate 2 completion checklist

Before requesting merge approval for PR #521:

1. Synchronize the PR branch with the current `main` without dropping intervening main changes.
2. Confirm all temporary L4.2 recovery assets are absent.
3. Confirm the permanent L4.2 validator passes on the final PR head.
4. Confirm applicable repository CI and handover invariants pass on the final PR head.
5. Confirm the final diff contains zero Production writes and STM32L4 Production remains 0.
6. Recheck PR mergeability, reviews, and comments.
7. Update PR #521 description to the final 138 / 446 / 5 result and dual-run provenance.
8. Stop and obtain explicit Gate 2 merge approval.

## Next phase boundary

L4.3 is not authorized by completion of L4.2. If PR #521 is explicitly approved and merged, L4.3 must begin as a separate Gate 1 transaction with its own bounded scope and authorization.
