# H021 — STM32L4 L4.3 Manufacturer-Authoritative Metadata Policy

## Transaction

- Phase: STM32L4 L4.3
- PR: #530
- Branch: `agent/device-catalog-stm32l4-phase-l43-metadata-policy`
- Gate 1: explicitly approved
- Gate 2: not yet approved
- Production publication: not authorized

## Input boundary

L4.3 consumes exactly the retained L4.2 commercial set:

- 138 Base Devices
- 446 Active exact ICPNs
- 5 excluded non-Active exact variants remain excluded
- L4.2 Active exact set SHA-256: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`

No new commercial identity discovery is performed in L4.3.

## Metadata authority

Primary authority is official ST datasheet Ordering Information:

- 24 STM32L4 series records
- 20 unique official ST datasheets
- package / pin / Flash code / temperature / option / packing semantics decoded fail-closed

Identity/lifecycle authority remains the immutable L4.2 official-ST dual-surface evidence.

## Exact-variant exception policy

The first complete replay produced 443 ready + 3 manual review. The three rows were manufacturer-side current-data inconsistencies/omissions, not parser guesses:

- `STM32L4A6RGT7`: temperature code 7 omitted by DS11584 Rev 14; official ST exact-part surface specifies -40..105 C.
- `STM32L4A6RGT7TR`: same, with tape-and-reel packing.
- `STM32L4S5QII3P`: option P omitted by DS12024 Rev 4; official ST exact-part surface identifies external SMPS.

The exception mechanism is exact-ICPN-only. It cannot authorize a fourth part or broaden a family grammar without changing the hard-locked exception set and evidence.

Final deterministic result:

- metadata-ready: 446
- manual review: 0
- reject: 0
- exact manufacturer exceptions: 3
- metadata rows SHA-256: `d67e27b641b295df697b804741b7be1abbb2ee26dd7a24e11482640306bef500`

## Permanent files

- `data/device-catalog/research/stm32l4-phase-l4.3-ordering-authority.json`
- `data/device-catalog/research/stm32l4-phase-l4.3-exact-variant-exceptions.json`
- `data/device-catalog/research/stm32l4_metadata_policy.py`
- `data/device-catalog/research/stm32l4_phase_l4_3_policy.py`
- `data/device-catalog/research/test_stm32l4_phase_l4_3_policy.py`
- `data/device-catalog/research/build_stm32l4_phase_l4_3_baseline.py`
- `data/device-catalog/research/stm32l4-phase-l4.3-policy-baseline.json`
- `data/device-catalog/research/validate_stm32l4_phase_l4_3_policy.py`
- `data/device-catalog/research/device-catalog-stm32l4-phase-l4.3-metadata-policy.md`
- `.github/workflows/device-catalog-stm32l4-l43-metadata-validation.yml`

## Hard locks

- L4.2 baseline: `eeb538cfac4ace738878ca5b60adad2ef122a46881565d3917d77078af8fe804`
- L4.2 Active exact set: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`
- L4.3 Ordering authority: `da0dd36a6f9a7d9ac75b5910d45bfb477c664c94c1bedc9d482292cd7bb479ec`
- L4.3 exact exception file: `d7514a5db450d36b6acbbfd8e6650074134f3637c2012047a549557149d6bc31`
- Production prestate: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

Permanent CI requires:

1. policy tests pass;
2. deterministic baseline rebuild matches the committed baseline byte-for-byte;
3. permanent L4.3 hard-lock passes;
4. PR transaction has zero `data/device-catalog/production` diff.

## Production boundary

Production remains unchanged:

- 1272 exact ICPNs
- 392 Base Devices
- 11 STM32 families
- STM32L4 Production exact ICPNs: 0

L4.3 does not claim canonical admission, Production publication, programming policy, Flash geometry equivalence, option/security programming qualification, physical/HIL qualification, or runtime programming support.

## Continuation

Before Gate 2:

1. recheck PR #530 current head and current `main`;
2. ensure all applicable final CI is green;
3. ensure PR mergeable and no review/comment blockers;
4. confirm zero Production writes;
5. obtain explicit Gate 2 merge approval.

After merge, do **not** start L4.4 without separate Gate 1 approval.
