# STM32L4 Phase L4.3 — Manufacturer-Authoritative Metadata Policy

## Status

Gate 1 scope is complete as a research-only metadata policy over the immutable L4.2 commercial set.

- Family: `STM32L4`
- Frozen input: 138 Base Devices / 446 Active exact ICPNs
- Metadata-ready: 446
- Manual review: 0
- Reject: 0
- Production writes: 0
- STM32L4 Production exact ICPNs: 0
- Existing Production total: 1272 exact ICPNs / 392 Base Devices / 11 STM32 families

L4.3 does **not** authorize canonical admission, Production publication, programming policy, Flash geometry equivalence, option/security programming semantics, physical/HIL qualification, or runtime programming support.

## Authority model

Identity and lifecycle remain governed by the immutable L4.2 official-ST dual-surface exact-set evidence.

Metadata is decoded from official ST datasheet **Ordering Information** across 24 STM32L4 series records covered by 20 unique datasheets. The deterministic fields are:

- series / Base Device
- package
- pin count
- Flash size code
- temperature grade
- option / packing suffix
- source authority / source reference / verification state

The policy is fail-closed. A retained Active ICPN that cannot be decoded from the authority model becomes `manual_review_required`; an identity outside the retained L4.2 Active set is rejected.

## Exact-part exceptions

The first full 446-ICPN replay produced 443 metadata-ready rows and exactly three manual-review rows. Investigation found current ST exact-part commercial surfaces that conflict with or extend the current datasheet Ordering Information tables:

1. `STM32L4A6RGT7`
   - DS11584 Rev 14 Ordering Information omits temperature code `7`.
   - Current official ST exact-part data identifies the part as Active and specifies `-40..105 C`.

2. `STM32L4A6RGT7TR`
   - Same temperature-code omission.
   - Current official ST exact-part data specifies `-40..105 C` and tape-and-reel packing.

3. `STM32L4S5QII3P`
   - DS12024 Rev 4 Ordering Information omits option `P`.
   - Current official ST exact-part data identifies the Active variant with external SMPS.

These are not family-wide grammar relaxations. They are an immutable exact-ICPN whitelist in:

`stm32l4-phase-l4.3-exact-variant-exceptions.json`

Any fourth exception fails validation until separately evidenced and reviewed.

## Frozen result

The final deterministic replay is:

- 446 / 446 metadata-ready
- 0 manual review
- 0 reject
- exact exception count: 3
- metadata-ready set SHA-256: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`
- metadata rows SHA-256: `d67e27b641b295df697b804741b7be1abbb2ee26dd7a24e11482640306bef500`

Distribution checks:

- Flash: 64 KiB 12, 128 KiB 58, 256 KiB 99, 512 KiB 94, 1 MiB 145, 2 MiB 38
- Temperature: -40..85 C 350, -40..105 C 23, -40..125 C 73
- Option suffix: blank 228, `TR` 165, `P` 35, `PTR` 9, `S` 3, `STR` 5, `MTR` 1

## Hard-lock bindings

- L4.2 Active exact set SHA-256: `cdb350bdf1513f51430808b98677948569740d230c45bd735f439142ab03eb45`
- L4.2 baseline SHA-256: `eeb538cfac4ace738878ca5b60adad2ef122a46881565d3917d77078af8fe804`
- L4.3 Ordering authority SHA-256: `da0dd36a6f9a7d9ac75b5910d45bfb477c664c94c1bedc9d482292cd7bb479ec`
- L4.3 exact-variant exception SHA-256: `d7514a5db450d36b6acbbfd8e6650074134f3637c2012047a549557149d6bc31`
- Production prestate SHA-256: `c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec`

Permanent validation rebuilds the baseline, compares it byte-for-byte with the committed baseline, revalidates L4.2 retained evidence, locks all authority digests, enforces the exact three-part exception whitelist, and requires zero Production diff in the PR transaction.

## Next phase boundary

L4.4 may define a bounded read-only capability/admission plan only after a separate Gate 1 approval. L4.3 itself does not admit any of the 446 ICPNs into Production.
