# Device Catalog Phase 4.5B — STM32F0 official-ST commercial identity discovery

## Decision

Phase 4.5B establishes manufacturer-backed commercial identity and lifecycle
for the 13 deterministic STM32F0 Base Devices selected by Phase 4.5A.

This phase is an ICPN catalog transaction. It does not define PPU/SW runtime
support, programming algorithms, Socket support, electrical qualification or
physical programming readiness.

## Official-ST evidence surface

A one-target schema diagnostic on `STM32F030C6` confirmed the current ST product
page separates authority across two rendered-DOM surfaces:

- Quality and Reliability supplies exact commercial `Part Number` identity;
- Sample & Buy supplies `Marketing Status` lifecycle.

Phase 4.5B therefore uses the ST dual-surface extraction core with the
family-owned parser profile `stm32f0_dual_surface_v1`. Historical STM32F3
retained evidence remains bound to its original F3-specific profile and is not
reinterpreted.

## Live bounded discovery

The controlled live transaction executed 13 Base Devices with headed Chromium
under Xvfb:

- workflow run: `34315839031`;
- branch head: `1fcdf8696bc4d334f6e5f092efc8200b65fc443e`;
- artifact: `10090443968`;
- artifact ZIP SHA-256: `a3c02afd6a1295a612d25e35031d8623da86c0ea76777acaab4caaaab51cb1aa`;
- Chromium: `151.0.7922.34`;
- Playwright: `1.62.0`;
- acquisition success: 13/13;
- acquisition failure: 0;
- Active exact ICPNs: 42;
- excluded non-Active part numbers: 0;
- identity manual intervention: 0.

The separate workflow step `Enforce commercial identity acquisition result`
passed with exit code zero after artifact upload, preventing upload-only false
greens.

## Identity versus capability boundary

OpenOCD mapping is an orthogonal capability/routing observation. Phase 4.5B
records the historical result (13 unique, 0 ambiguous, 0 unmapped), but the
commercial-identity clean gate does not depend on it.

Permanent regression explicitly proves that a synthetic 13/13 unmapped routing
state still leaves complete manufacturer-backed commercial identity clean.

Therefore:

`ICPN exists/selectable` != `OpenOCD/PPU/Socket/runtime supported`.

Future OpenOCD catalog changes must not invalidate the historical ST commercial
identity established here.

## Retained evidence

The retained package binds:

- immutable evidence identity;
- live workflow, Git head and PR checkout SHA;
- artifact ID and ZIP digest;
- full live-summary digest;
- browser/parser versions;
- 42 exact Active ICPNs;
- ST lifecycle status;
- per-target evidence-section and rendered-DOM hashes;
- retrieval timestamps;
- discovery-time Production prestate: 502 exact ICPNs, STM32F0 = 0;
- discovery-time OpenOCD and manifest Git-blob identities.

Offline semantic replay validates these historical facts without comparing
future current Production or current OpenOCD routing against the historical
identity decision.

## Claims intentionally false

Phase 4.5B keeps all of the following false:

- canonical dataset admission;
- Production admission readiness;
- Production write authorization;
- programming policy defined;
- runtime support claimed.

## Next gate

The next ICPN gate is Phase 4.5C metadata policy for the 42 retained exact ICPNs.
Only after deterministic metadata policy and controlled admission planning are
clean may an independent publication transaction modify Production.
