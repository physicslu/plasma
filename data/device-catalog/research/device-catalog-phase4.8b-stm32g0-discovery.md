# Device Catalog Phase 4.8B — STM32G0 Official-ST Discovery

## Status

Phase 4.8B retains official ST commercial identity/lifecycle evidence for the 12 deterministic STM32G0 targets selected in Phase 4.8A. It does not authorize canonical admission, Production writes, programming policy, HIL qualification, or runtime support.

## Live acquisition

- GitHub Actions run: `34369661142`
- Executed Git SHA: `233e9300bfac96f868e4d4c372246a3e02ff541b`
- Artifact ID: `10111790513`
- Artifact ZIP SHA-256: `2d261efb10ec0840208337edf8a3d2ebd1d0dc3aeb5effd78af735dd30dac36f`
- Playwright: `1.62.0`
- Chromium: `151.0.7922.34`
- Evidence profile: `stm32g0_dual_surface_v1`
- Browser mode: headed Chromium under Xvfb

## Manufacturer disposition

All 12 bounded targets produced official ST identity/lifecycle evidence:

- attempted: 12
- manufacturer acquisition success: 12
- technical acquisition failure: 0
- Active candidate targets: 12
- lifecycle-only targets: 0
- source-unavailable exclusions: 0
- manual review: 0
- Active exact ICPNs: 49
- non-Active exact part-number exclusions: 3
- `commercial_identity_clean = true`
- `bounded_discovery_clean = true`

The three non-Active identities are all Proposal rows under `STM32G0C1CC`:

- `STM32G0C1CCT6`
- `STM32G0C1CCT6N`
- `STM32G0C1CCU6N`

They remain excluded even though the same Base Device also has Active `STM32G0C1CCU6` and `STM32G0C1CCU6TR` identities.

## Routing is a separate authority

OpenOCD routing observed:

- unique target groups: 11
- unmapped target groups: 1
- ambiguous: 0
- routing follow-up required: 1

The unresolved group is `STM32G0B1CB`. Official ST evidence includes two Active N-suffix identities:

- `STM32G0B1CBT6N`
- `STM32G0B1CBU6N`

The current OpenOCD ordering-pattern surface does not match those two N-suffix commercial identities. The other Active `STM32G0B1CB` identities route to `tcl/target/stm32g0x.cfg`.

This is intentionally retained as a routing-policy gap. The N-suffix identities must not be deleted, normalized away, or downgraded merely to make routing appear complete. Manufacturer commercial identity and OpenOCD capability are orthogonal evidence domains.

## CMSIS alias boundary

Phase 4.8A identified 39 `cmsis_device_name` rows in the STM32G0 OpenOCD-derived source. They remain routing/name aliases only. They are not used as manufacturer exact commercial identity evidence in Phase 4.8B.

## Retention

The immutable raw browser evidence remains in the GitHub Actions artifact. The repository stores a compact retained projection:

- `stm32g0-phase4.8b-discovery-baseline.json`
- `evidence/stm32g0-phase4.8b-official-st-discovery-live-2026-09-09/`

Hard locks:

- baseline SHA-256: `ef059c3226b506aa0ff739abf8c6bf3e0f525ceaefb571693458dad6b706f10a`
- pilot summary SHA-256: `061922f1a1af9a71a0614dc4f19c9f56c6823503b20d076ab0f6d4a742e45594`
- provenance SHA-256: `b5ea18c91af8b8166901bd44879944cb95e0f8cfe22712c757c6991dceb692c8`
- retained manifest SHA-256: `ff90c6ab4b3adb8bf9c87d5b0321ec3b29eab32f9854b38e566c09d7ffb39469`
- live summary SHA-256: `9b7cd31d1b0b37cb2960f34edef980159133028c0df9916909be8a0833eaf50d`

Historical Production prestate is 563 exact ICPNs across STM32F0/F1/F2/F3/F4/F7, with STM32G0 absent.

## Next phase

Phase 4.8C may derive metadata only from official manufacturer ordering-information authority. It must preserve all 49 Active identities and all three Proposal exclusions. The N-suffix routing gap is an explicit input to later admission/capability policy and cannot be resolved by silently changing commercial identity evidence.
