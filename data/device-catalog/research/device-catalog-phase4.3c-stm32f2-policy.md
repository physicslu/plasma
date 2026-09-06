# Device Catalog Phase 4.3C — bounded STM32F2 admission policy

Phase 4.3C defines the first STM32F2 family adapter and evaluates it against the
immutable Phase 4.3B official-ST evidence. It is a policy closure, not a
Production admission.

## Evidence-bound scope

The adapter accepts exactly the four Base Devices and nine Active exact ICPNs
retained by Phase 4.3B:

| Base Device | Exact ICPNs | Metadata policy |
|---|---|---|
| `STM32F205RB` | `STM32F205RBT6`, `STM32F205RBT6TR`, `STM32F205RBT7` | LQFP64, 128 KiB, temperature codes 6/7 |
| `STM32F207IC` | `STM32F207ICH6`, `STM32F207ICT6` | UFBGA176 or LQFP176, 256 KiB, temperature code 6 |
| `STM32F215RE` | `STM32F215RET6`, `STM32F215RET6TR` | LQFP64, 512 KiB, temperature code 6 |
| `STM32F217IE` | `STM32F217IEH6`, `STM32F217IET6` | UFBGA176 or LQFP176, 512 KiB, temperature code 6 |

All nine candidates resolve uniquely to the existing OpenOCD ordering-pattern
surface and `tcl/target/stm32f2x.cfg`. The only accepted post-temperature option
suffixes in this bounded scope are the empty suffix and `TR`.

## Fail-closed boundary

The adapter rejects unsupported commercial identity, package, temperature, and
option codes. Unsupported flash-size codes, pin/package combinations, ambiguous
or missing ordering-pattern mappings, foreign target configurations, and
unexpected identifier kinds require manual review. It also requires the exact
official-ST source URL, retained evidence identity, rendered-DOM digest, and
evidence-section digest.

The fixed Phase 4.3C evaluation is:

- 9 policy-ready;
- 0 already present;
- 0 manual review;
- 0 reject;
- 0 conflict.

Negative regressions prove that each unsupported metadata or mapping condition
fails closed. The checked-in policy baseline binds the retained evidence,
OpenOCD mapping catalog, Production manifest, exact candidates, and metadata
contract.

## Governance boundary

No canonical STM32F2 CSV is created, no admission writer is called, and no
Production, IC Support, runtime, REST, or Web content changes. Production remains
459 exact ICPNs and 157 Base Devices: STM32F1 is 75/18, STM32F4 is 384/139,
and STM32F2 is 0/0.

This policy does not prove programming-algorithm equivalence, PPU runtime
support, socket/electrical behavior, real-target programming, or full STM32F2
commercial coverage.

## Next gate

Phase 4.3D may build a bounded, read-only admission plan for the nine
policy-ready candidates. It must keep the canonical and Production write paths
disabled until its own evidence, conflict, lifecycle, and regression gates are
complete.
