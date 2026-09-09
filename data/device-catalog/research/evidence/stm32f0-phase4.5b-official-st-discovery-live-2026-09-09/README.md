# STM32F0 Phase 4.5B retained official-ST discovery evidence

This directory retains the decision evidence from the bounded STM32F0 Phase 4.5B
official-ST browser discovery executed on 2026-09-09.

## Decision boundary

The retained transaction establishes manufacturer-backed commercial identity and
lifecycle evidence for 13 deterministic STM32F0 Base Devices selected by Phase
4.5A. It found 42 unique Active exact ICPNs and no excluded non-Active part
numbers.

OpenOCD routing is retained only as a historical observation. It does not gate
commercial ICPN identity, catalog selectability, PPU/SW capability, Socket
support, or physical programming qualification.

## Execution

- workflow run: `34315839031`
- branch head: `1fcdf8696bc4d334f6e5f092efc8200b65fc443e`
- GitHub PR checkout SHA: `95276ea5af83819351c7f9f4a2f32db0638842b9`
- artifact: `10090443968`
- artifact ZIP SHA-256: `a3c02afd6a1295a612d25e35031d8623da86c0ea76777acaab4caaaab51cb1aa`
- browser: Chromium `151.0.7922.34`
- Playwright: `1.62.0`
- mode: headed Chromium under Xvfb
- parser profile: `stm32f0_dual_surface_v1`

## Result

- attempted targets: 13
- acquisition success: 13
- acquisition failure: 0
- Active exact ICPNs: 42
- excluded non-Active ICPNs: 0
- identity manual intervention: 0
- commercial identity clean: true
- historical OpenOCD routing: 13 unique / 0 ambiguous / 0 unmapped
- routing gates commercial identity: false

The exact per-target ICPN lists, lifecycle status, rendered-DOM hashes and
evidence-section hashes are retained in a normalized `pilot-summary.json`
decision projection and pinned by the Phase 4.5B discovery baseline. The
original live artifact is independently bound by its ZIP digest and full
live-summary SHA-256.

## Claims intentionally not made

This evidence package does not authorize canonical/Production admission and does
not claim OpenOCD, PPU, Socket, electrical, HIL, or physical programming support.

Evidence identity:

`stm32f0-phase4.5b-official-st-discovery-2026-09-09-retained-20260909T055900Z-1fcdf869`
