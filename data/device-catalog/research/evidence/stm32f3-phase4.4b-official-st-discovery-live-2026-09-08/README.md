# STM32F3 Phase 4.4B retained official-ST discovery evidence

This package retains the successful bounded STM32F3 Phase 4.4B manufacturer-evidence run executed on 2026-09-08.

## Scope

Six deterministic Base Devices were selected from the guarded STM32F3 OpenOCD ordering-pattern surface:

- `STM32F301C6`
- `STM32F302C6`
- `STM32F303C6`
- `STM32F373C8`
- `STM32F334C4`
- `STM32F318C8`

The run produced 10 Active exact commercial ICPNs, zero non-active exclusions, and unique `tcl/target/stm32f3x.cfg` routing for every target/candidate.

## Evidence boundary

Current STM32F3 ST pages split the required authoritative facts across two official sections:

- **Quality and Reliability** supplies exact commercial Part Number identity.
- **Sample & Buy** supplies Marketing Status/lifecycle for the same exact identities.

The `stm32f3_dual_surface_v1` adapter accepts this join only when the exact Part Number sets are identical. Missing lifecycle rows, extra/foreign identities, duplicate identities, or missing required columns fail closed.

The retained evidence-section hash binds normalized Quality-and-Reliability identity evidence plus a canonical lifecycle projection. Full rendered-DOM SHA-256 values are retained separately.

## Execution

- Git SHA: `0ac86cbf8da4cfaad6e0201c278cc43cb4c52c75`
- GitHub Actions run: `34204938530`
- artifact: `10047381270`
- artifact ZIP SHA-256: `c40fcba4e35c3e193c9ca85e1433df352f42b91453d6b68c923fa2eafca4d9eb`
- transport: headed Chromium rendered DOM
- Playwright: `1.62.0`
- Chromium: `151.0.7922.34`

## Governance boundary

This evidence package does **not** authorize canonical or Production admission, does not define programming policy, and does not claim runtime or physical programming support. Phase 4.4C Policy remains a separate gate.
