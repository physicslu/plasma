# Device Catalog Phase 4.9B — STM32G4 Official-ST Discovery

## Status

Phase 4.9B retains official ST commercial identity/lifecycle evidence for the 11 deterministic STM32G4 targets selected in Phase 4.9A. It does not authorize canonical admission, Production writes, programming policy, HIL qualification, physical qualification, or runtime support.

The evidence boundary is disposition-aware. A canonical official ST product-page HTTP 404 is a current-source-unavailable exclusion, not a technical acquisition failure and not proof that a commercial identity never existed.

## Live acquisition

- GitHub Actions run: `34421443430`
- Executed Git SHA: `3c74395ae8771ccb8abfeb8fa7aeec671b9d6042`
- Artifact ID: `10131271123`
- Artifact ZIP SHA-256: `a10b34d4ea2f28a0e2ae19e1a54d36b684ec0581de5c79fc8d21c90b97989eb1`
- Live summary SHA-256: `4535807ed9c95bc825c7acf98d555fd599cff5dbd13e1989bc829d33dc1b51df`
- Playwright: `1.62.0`
- Chromium: `151.0.7922.34`
- Evidence profile: `stm32g4_dual_surface_v1`
- Browser mode: headed Chromium under Xvfb
- Manufacturer evidence acquisition window: `2026-09-10T00:29:39Z` to `2026-09-10T00:38:14Z`

## Manufacturer disposition

The bounded 11-target transaction completed without technical/manual failures:

- attempted targets: 11
- manufacturer acquisition success: 8
- technical acquisition failure: 0
- Active candidate targets: 8
- lifecycle-only targets: 0
- source-unavailable exclusions: 3
- dispositioned targets: 11
- manual review: 0
- Active exact ICPNs: 25
- non-Active exact part-number exclusions: 3
- `commercial_identity_clean = false`
- `bounded_discovery_clean = true`

The three canonical ST product pages that returned HTTP 404 are:

- `STM32G411C6`
- `STM32G414CB`
- `STM32G471CC`

These three targets remain in the deterministic Phase 4.9A/4.9B target set. They are not re-ranked away, replaced by a more convenient Base Device, or interpreted as historical nonexistence. Later evidence may resolve them, but Phase 4.9B does not invent identity data in their absence.

The eight verified-Active Base Devices and their exact Active counts are:

- `STM32G431C6`: 2
- `STM32G441CB`: 3
- `STM32G473CB`: 3
- `STM32G474CB`: 4
- `STM32G483CE`: 3
- `STM32G484CE`: 3
- `STM32G491CC`: 5
- `STM32G4A1CE`: 2

Total: 25 unique Active exact ICPNs.

## Lifecycle exclusions

Three exact identities were present on official ST evidence but were non-Active Proposal rows and are therefore excluded:

- `STM32G441CBT3`
- `STM32G441CBU3`
- `STM32G484CET3`

The temperature/package/order-code characters are not lifecycle authority by themselves. For example, other `T3` or `U3` identities in this same bounded evidence set are Active. Lifecycle admission is determined from the official ST Marketing Status surface for the exact identity, not inferred from suffix patterns.

## Routing is a separate authority

OpenOCD routing observed for the retained Phase 4.9B targets:

- unique target groups: 8
- ambiguous target groups: 0
- unmapped target groups: 0
- not-applicable groups: 3
- routing follow-up required: 0

The three not-applicable groups are the three source-unavailable targets. All 25 retained Active exact ICPNs from the eight verified targets map uniquely to `tcl/target/stm32g4x.cfg` under the historical OpenOCD source surface.

This does not make OpenOCD a commercial-identity authority. Manufacturer identity/lifecycle and OpenOCD routing remain orthogonal evidence domains, and `gates_commercial_identity = false` is hard-locked in retained evidence.

## CMSIS alias boundary

Phase 4.9A identified six `cmsis_device_name` aliases, located only under STM32G431, STM32G473, and STM32G491. They remain routing/name metadata only and do not participate in exact commercial ICPN selection in Phase 4.9B.

A future normalization step must not promote those aliases into commercial identity evidence merely because their text resembles a device name.

## Retention and immutable replay

The immutable raw browser evidence remains in GitHub Actions artifact `10131271123`. The repository stores a compact retained projection:

- `stm32g4-phase4.9b-discovery-baseline.json`
- `evidence/stm32g4-phase4.9b-official-st-discovery-live-2026-09-10/`

Hard locks:

- baseline SHA-256: `474dbe34de46d654262497d3a6bd306c94fb5157e5e6cffb0f4bc753b5d228e3`
- pilot summary SHA-256: `0310a888dadfa2cdabc8f16b59a177ecd6bb0cfc0344a73763d8a5ac264a960b`
- provenance SHA-256: `46943309c3755c4c9f1e8e78e05372e4eef07050bd61d15c80641cd50313e931`
- retained manifest SHA-256: `b9df96eeac45dfe051df8ea8e5d464e41d8e4136d65df2bdd44076ba2be81cfb`
- retained README SHA-256: `f06fa65c26b045252821a01057292ee20100b49e9e3d3b9c46939415ef50643a`

Historical source bindings are frozen to the acquisition transaction. The Production prestate was 610 exact ICPNs across STM32F0/F1/F2/F3/F4/F7/G0, with STM32G4 absent. Future Production growth must not rewrite this historical prestate.

## Evidence interpretation

The first-principles rule is:

1. official ST exact identity plus Marketing Status determines commercial identity/lifecycle disposition;
2. HTTP 404 determines only current canonical-source unavailability;
3. OpenOCD determines routing observations, not commercial existence;
4. CMSIS aliases determine neither exact identity nor lifecycle;
5. no missing evidence is filled by suffix inference, nearby-device analogy, or target re-ranking.

Therefore `bounded_discovery_clean = true` and `commercial_identity_clean = false` are simultaneously correct for this transaction.

## Next phase

Phase 4.9C may derive canonical metadata only for the 25 retained Active exact identities and only from explicit official manufacturer ordering-information or exact-product authority. It must preserve the three Proposal exclusions and the three source-unavailable Base Devices as exclusions unless new official evidence is deliberately acquired and separately governed.

Phase 4.9C must not write STM32G4 to Production. Capability/admission remains a later phase.
