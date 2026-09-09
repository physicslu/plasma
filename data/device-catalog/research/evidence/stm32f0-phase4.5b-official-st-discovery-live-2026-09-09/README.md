# STM32F0 Phase 4.5B retained official-ST discovery evidence

This directory retains the decision evidence from the bounded STM32F0 Phase 4.5B
official-ST browser discovery executed on 2026-09-09.

## Decision boundary

The transaction establishes manufacturer-backed commercial identity and lifecycle
evidence for 13 deterministic STM32F0 Base Devices. It found 42 unique Active
exact ICPNs and no excluded non-Active part numbers.

OpenOCD routing is retained only as a historical observation. It does not gate
commercial ICPN identity, catalog selectability, PPU/SW capability, Socket
support, or physical programming qualification.

## Execution

- workflow run: `34315839031`
- branch head: `1fcdf8696bc4d334f6e5f092efc8200b65fc443e`
- GitHub PR checkout SHA: `95276ea5af83819351c7f9f4a2f32db0638842b9`
- artifact: `10090443968`
- artifact ZIP SHA-256: `a3c02afd6a1295a612d25e35031d8623da86c0ea76777acaab4caaaab51cb1aa`
- full live-summary SHA-256: `e96c9f09f4f57d2797cd9e3928664dcd67c72f3887eae3795df66aa1e75cbb76`
- Chromium: `151.0.7922.34`
- Playwright: `1.62.0`
- parser profile: `stm32f0_dual_surface_v1`
- mode: headed Chromium under Xvfb

## Retained projection

`pilot-summary.json` is a normalized decision projection containing the aggregate
result and the exact 42 Active ICPNs. Per-target evidence-section hashes,
rendered-DOM hashes, retrieval times and historical routing observations are
pinned in `stm32f0-phase4.5b-discovery-baseline.json`.

The original 16-file live artifact remains independently bound by its artifact
ID, ZIP digest and full `live-summary.json` digest.

## Claims intentionally not made

This package does not authorize canonical/Production admission and does not
claim OpenOCD, PPU, Socket, electrical, HIL, or physical programming support.

Evidence identity:

`stm32f0-phase4.5b-official-st-discovery-2026-09-09-retained-20260909T055900Z-1fcdf869`
