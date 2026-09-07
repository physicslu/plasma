# Device Catalog Phase 4.3H — third bounded STM32F2 discovery

Phase 4.3H continues STM32F2 coverage from the guarded Phase 4.3G Production
baseline. It is a bounded, read-only official-ST discovery and does not admit
any exact ICPN to Production.

## Guarded selection

The OpenOCD source still contains 47 STM32F2 ordering patterns across four
subfamilies. Production contains 22 STM32F2 exact ICPNs across eight Base
Devices. The deterministic selector removes those eight admitted Base Devices
and chooses the lexicographically first remaining Base Device in every
subfamily:

| Subfamily | Base Device | Official ST page |
|---|---|---|
| STM32F205 | STM32F205RE | `stm32f205re.html` |
| STM32F207 | STM32F207IF | `stm32f207if.html` |
| STM32F215 | STM32F215VE | `stm32f215ve.html` |
| STM32F217 | STM32F217VE | `stm32f217ve.html` |

The discovery contract binds the complete historical Phase 4.3G STM32F2
Production content. It fails closed if an admitted identity changes, the source
surface drifts, a target is selected out of order, or an exact ICPN no longer
maps uniquely to `tcl/target/stm32f2x.cfg`.

## Observed official evidence

The exact source commit `52a8e1981a392602db256434567b2c52a3401a05`
executed the acquisition locally with headed Chromium 151 and Playwright
1.62.0. This avoids adding a phase-only GitHub Actions workflow. All four
official ST Quality and Reliability tables loaded successfully.

| Base Device | Active exact ICPNs | Non-Active exclusions | OpenOCD mapping |
|---|---:|---:|---|
| STM32F205RE | 5 | 0 | unique `stm32f2x.cfg` |
| STM32F207IF | 3 | 0 | unique `stm32f2x.cfg` |
| STM32F215VE | 1 | 0 | unique `stm32f2x.cfg` |
| STM32F217VE | 2 | 0 | unique `stm32f2x.cfg` |
| **Total** | **11** | **0** | **11/11 unique** |

The eleven Active exact ICPNs are:

- `STM32F205RET6`, `STM32F205RET6TR`, `STM32F205RET7`,
  `STM32F205RET7TR`, `STM32F205REY6TR`;
- `STM32F207IFH6`, `STM32F207IFH6TR`, `STM32F207IFT6`;
- `STM32F215VET6`;
- `STM32F217VET6`, `STM32F217VET6TR`.

## Governance boundary

The retained package binds source URLs, retrieval times, rendered-DOM and
evidence-section SHA-256 digests, lifecycle records, browser versions, exact
source commit, and reproducible OpenOCD mappings. The package explicitly records
that no GitHub workflow run or workflow artifact was used.

This evidence does not define a package/temperature/flash/option policy, prove
programming-algorithm equivalence, authorize Production admission, or establish
native PPU, socket, electrical, or real-target readiness. Production therefore
remains 481 exact ICPNs and 165 Base Devices: STM32F1 is 75/18, STM32F2 is 22/8,
and STM32F4 is 384/139.

## Next gate

Phase 4.3I may define and negatively test a bounded STM32F2 admission policy for
the eleven retained candidates. Unsupported package, temperature, flash,
option, lifecycle, or mapping topology must remain fail-closed. No Production
write is authorized by Phase 4.3H.
