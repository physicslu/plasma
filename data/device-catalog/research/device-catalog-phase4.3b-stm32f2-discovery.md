# Device Catalog Phase 4.3B — STM32F2 official-ST discovery

Phase 4.3B validates the first third-family evidence surface selected by Phase
4.3A. It is a bounded, read-only discovery and does not admit STM32F2 to
Production.

## Guarded scope

The OpenOCD source contains 47 STM32F2 ordering patterns across four
subfamilies. To test the official-ST identifier and lifecycle topology with the
smallest bounded surface, the discovery deterministically selects the
lexicographically first Base Device in each subfamily:

| Subfamily | Base Device | Official ST page |
|---|---|---|
| STM32F205 | STM32F205RB | `stm32f205rb.html` |
| STM32F207 | STM32F207IC | `stm32f207ic.html` |
| STM32F215 | STM32F215RE | `stm32f215re.html` |
| STM32F217 | STM32F217IE | `stm32f217ie.html` |

The selection is derived from the guarded 47-row OpenOCD surface; it is not a
claim that these four Base Devices cover every STM32F2 commercial order code.

## Observed official evidence

GitHub Actions run `34041745112` executed exact head
`a17d9e4d778bac9f2d5360f0f55fd396277db14f` with headed Chromium 151 and
Playwright 1.62.0. All four official ST Quality and Reliability tables loaded
successfully.

| Base Device | Active exact ICPNs | Non-Active exclusions | OpenOCD mapping |
|---|---:|---:|---|
| STM32F205RB | 3 | 0 | unique `stm32f2x.cfg` |
| STM32F207IC | 2 | 0 | unique `stm32f2x.cfg` |
| STM32F215RE | 2 | 0 | unique `stm32f2x.cfg` |
| STM32F217IE | 2 | 0 | unique `stm32f2x.cfg` |
| **Total** | **9** | **0** | **9/9 unique** |

The nine Active exact ICPNs are:

- `STM32F205RBT6`, `STM32F205RBT6TR`, `STM32F205RBT7`;
- `STM32F207ICH6`, `STM32F207ICT6`;
- `STM32F215RET6`, `STM32F215RET6TR`;
- `STM32F217IEH6`, `STM32F217IET6`.

## Governance boundary

The evidence proves that all four sampled subfamilies expose exact commercial
part numbers and explicit Active marketing status on official ST pages. It also
proves deterministic routing of these nine candidates to the existing OpenOCD
STM32F2 target configuration.

It does **not** prove full STM32F2 commercial coverage, package/temperature/
flash metadata policy, programming-algorithm equivalence, native PPU runtime
support, or Production admission readiness. Production therefore remains 459
exact ICPNs and 157 Base Devices: STM32F1 is 75/18 and STM32F4 is 384/139.

## Next gate

Phase 4.3C should define and test an STM32F2 family adapter and admission policy
against the retained nine-candidate evidence. It must fail closed on unsupported
package, temperature, flash, option, or mapping codes. No candidate may enter
Production until that policy and its negative regressions are separately
approved and complete.
