# STM32C0 Active Gap Lock + Metadata Replay v5.4

Research-only delta refresh against the locked **2026-10-01 ST eStore Active universe**.

## Exact delta

- STM32C0 current Active exact set: **226**
- STM32C0 Production prestate: **209**
- exact gap: **17**
- gap SHA-256: `03b7202842b52aaa6362386864d60c62f64d9cefea74d2d039691ea170b79097`

The set is derived from the locked v1.4 Active artifact, not from an unconstrained live re-scrape.

## Metadata replay

All **17/17** identities decode from the existing C0 Ordering Information authority plus two package-dependent additions already present in current official ST datasheets:

- STM32C011 `D/Y` → **WLCSP12**
- STM32C051 `D/Y` → **WLCSP15**

The remaining 15 identities use ordering semantics already present in the C0.3 authority.

One lifecycle delta is explicit:

- `STM32C091KBT3`: retained C0.2 state was Preview; the 2026-10-01 locked eStore state is **Active**.

## Boundary

This transaction does not change Production and does not claim backend mapping, Programming Profile support, Engineering Verified, field evidence, or PS/HIL qualification.

Next gate: prepare a **17-row Layer-1 admission proposal**, preferably keeping backend state unbound unless separately evaluated.
