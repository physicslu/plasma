# OpenOCD Tier-A Tail Closure v6.30

v6.30 handles the final three Tier-A residual identities after v6.29.

## STM32L4 — two exact rows are write-ready

Exact scope:

- `STM32L496WGY6PST`
- `STM32L496WGY6PTR`

The route inventory already contains the unique route identifier `STM32L496WGYxP` as a `cmsis_device_name` targeting `tcl/target/stm32l4x.cfg`.

The bounded resolver is exact-set only:

- `STM32L496WGY6PTR`: remove terminal packing code `TR` only → `STM32L496WGY6P`
- `STM32L496WGY6PST`: remove terminal packing code `ST` only → `STM32L496WGY6P`

Both then full-match `STM32L496WGYxP` with `x=6`.

No generic non-terminal-`x` resolver or generic suffix-stripping rule is authorized.

If later approved, only five backend fields of these two Production rows change. Expected state:

- mapped: **4,059 → 4,061**
- no_mapping: **570 → 568**
- Active OpenOCD route: **3,980 → 3,982 / 4,550 = 87.5165%**

## STM32G4 — one exact row remains blocked

`STM32G491RCY6TR` is manufacturer-authoritative WLCSP (`Y`). The current route inventory contains same-base `STM32G491RCIx` and `STM32G491RCTx`, both targeting `stm32g4x.cfg`, but contains no `STM32G491RCYx` identifier.

The common target config is not treated as permission to invent a package substitution. G4 therefore remains `no_mapping`.

## Boundary

Owner approval was received. The exact frozen L4 and manifest Production postimages have been applied on the PR branch. Historical v6.2 replay remains protected through the exact backend rewind helper, and G4 remains blocked. Production is not changed until explicit owner approval.

No Programming Profile, erase/program/verify, Engineering Verified, or HIL claim is made.

## Frozen postimages

- L4 Git blob: `b72cbbbd7dae14d3073272f1b019b51d78d092f8`
- L4 SHA256: `e8d1611d7d8a2dad6710cd9ed4b8944f4ce7454efd0c0d0d43526a7bed2a268a`
- Manifest Git blob: `e3455db5d4098d3d0906fab1c36831de56161bdd`
- Manifest SHA256: `a864d22e39f3f0beb72d747a3e7404c672bd29267a3a21717db4d0a215d19a94`

## Applied write

The approved frozen L4 Production write was applied in commit `e2d7809ed7c3f22354a9d62f28b4d5a57a4ed6df`. Merge remains conditional on fully green postwrite CI and the final lease check.
