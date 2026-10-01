# STM32G4 Layer-1 Refresh v2.0

**Research-only proposal. No Production write is authorized by this work.**

The locked ST eStore Active exact-set audit from PR #685 reports:

- current STM32G4 Active exact MPNs: **273**
- current Production STM32G4 exact ICPNs: **25**
- Layer-1 Active identity gap: **248**
- normalized gap-set SHA-256: `d6b7f8dbec3869b9e71d414773305b2d7bc2d9a57eb7a2987a8114f14b5bd270`

## Metadata authority

All 248 gaps fall inside the same eight STM32G4 series already present in the historical G4 workstream:

`STM32G431`, `STM32G441`, `STM32G473`, `STM32G474`, `STM32G483`, `STM32G484`, `STM32G491`, `STM32G4A1`.

The v2.0 authority expands the prior retained-25 subset to the complete ordering codes needed by the current 273 Active exact identities, using official ST datasheet Ordering Information tables.

One exact metadata exception is explicit and bounded:

- `STM32G484PEI6`: DS12983 Rev 5 Table 123 declares `P = 121` but omits package code `I`; the same official datasheet Section 6.9 explicitly defines **UFBGA121**. The eStore exact identity supplies the `P/E/I/6` combination. No general package-code inheritance is allowed from this exception.

## Backend crosswalk

The current guarded 177-row STM32G4 OpenOCD ordering-pattern surface resolves:

- **247 / 248** additions to one unique `tcl/target/stm32g4x.cfg` ordering pattern;
- **1 / 248** as `no_mapping`: `STM32G491RCY6TR`.

The unmapped identity remains a valid Layer-1 Catalog candidate. This research does not synthesize an OpenOCD route for it.

## Support boundary

If later approved and published:

- STM32G4 Layer-1 Active identity coverage would become **273 / 273 = 100%**.
- The 247 positive routes are only backend mapping observations.
- The one `no_mapping` identity must remain backend-unroutable until independent route evidence exists.
- No Engineering Verified, pilot/production field evidence, PS/HIL, or programming-algorithm equivalence claim is created.
