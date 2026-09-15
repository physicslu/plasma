# STM32L5 — Canonical Admission Plan Under Security Fence

Status: **canonical row plan clean; research-only; Production admission still blocked**

## Result

The merged manufacturer identity and metadata transactions retain **49 exact ICPNs** across **17 Base Devices**. This transaction adds deterministic read-only routing evidence sufficient to build a canonical catalog row plan for all 49 identities.

Frozen routing result:

- retained exact ICPNs: **49**
- frozen OpenOCD route-evidence rows: **38**
- route evidence: 15 `ordering_pattern` + 23 `cmsis_device_name`
- unique exact-to-route assignments: **49/49**
- assigned route kinds: 27 `ordering_pattern` + 22 `cmsis_device_name`
- unresolved / ambiguous: **0**
- target config: `tcl/target/stm32l5x.cfg`
- exact-to-route binding SHA-256: `c54c0eb049c4d60808540cb5608047b6c2b74a451d8fad2e3a41f56ea1e4d46c`

## Why mixed identifier kinds are accepted

STM32L5 upstream mapping evidence contains both identifier kinds. The `x` placeholder is matched as exactly one alphanumeric character against the commercial core after transport packing suffix (`TR`/`TT`) removal. Matching is a full-string match; prefix-only routing is not accepted.

This avoids two errors:

1. treating a syntactically similar but different part as the same route;
2. discarding valid L5 route evidence merely because upstream classified the identifier as `cmsis_device_name` instead of `ordering_pattern`.

Both kinds remain **mapping candidates only**. Neither is manufacturer authority for commercial identity, programming algorithm equivalence, Flash geometry, or security semantics.

## Historical-CI boundary

The 38 L5 route rows are retained in `stm32l5-admission-route-evidence.csv`. Permanent validation replays this frozen evidence instead of binding the historical transaction to a mutable global OpenOCD catalog. This prevents future catalog maintenance from invalidating a completed research gate.

## Security boundary

The merged STM32L5 security foundation still has `production_admission_allowed=false`. Therefore this transaction does **not** authorize:

- Production writes or publication;
- TZEN / option-byte writes;
- RDP regression or mass erase;
- TrustZone/security-state support;
- Flash geometry or programming-algorithm equivalence;
- runtime programming support;
- HIL qualification.

A clean canonical-row plan is a data-governance result, not a hardware-programming support result.

## Next gate

The next bounded transaction is **STM32L5 security-state admission gate**. It must decide which security states and operations can be admitted, refused, or remain HIL-blocked before Production admission can be considered.
