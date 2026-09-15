# STM32L5 — Runtime-Enforcement Admission Gate

Status: **runtime enforcement contract defined; target-plane remains fully blocked; research-only**

## Purpose

The preceding security-state gate models seven STM32L5 TrustZone/RDP states and their destructive/irreversible boundaries. This transaction converts that model into a deterministic software authorization contract.

The first-principles boundary is explicit:

- **control-plane** operations resolve catalog identity, manufacturer metadata, or backend routing on the host and perform no device I/O;
- **target-plane** operations interact with the physical IC and therefore require validated state observation, backend enforcement, programming semantics, and HIL evidence before any allow decision can exist.

Catalog presence is not runtime support.

## Contract

Host-only control-plane operations currently allowed:

- `catalog_resolve`
- `metadata_resolve`
- `route_resolve`

Target-plane operations modeled and denied:

- security-state read
- debug attach
- Flash read/program/verify/erase
- option-byte writes
- TZEN changes
- RDP changes/regression
- mass erase
- entry into RDP2

Across 7 modeled security states and 12 target-plane operations, the frozen decision surface is **84/84 deny**.

Additional invariants:

1. unknown operation => deny;
2. unknown or unobserved security state => deny;
3. RDP2 states => terminal target-access deny;
4. no force/bypass override exists;
5. control-plane rules may never perform device I/O;
6. all security mutation remains prohibited;
7. Production admission, runtime programming support, and HIL qualification remain false.

## Why this gate does not enable programming

The enforcement model can now answer what must be denied, but Plasma still lacks validated evidence that it can reliably observe the target security state and enforce debug/connect behavior on physical STM32L5 devices. Flash geometry and programming-algorithm correctness also remain separate gates.

Therefore this transaction is a software/governance boundary, not engineering validation.

## Next gate

The next bounded transaction is **`stm32l5-security-state-observer-and-debug-validation-gate`**.

That gate must validate how the runtime determines security state and how debug/connect behavior changes by state before any target-plane allow policy can be considered. Physical/HIL evidence remains mandatory for claims about real-device behavior.
