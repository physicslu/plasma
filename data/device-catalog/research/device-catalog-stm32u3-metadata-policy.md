# STM32U3 metadata policy

## Purpose

Normalize manufacturer-observed STM32U3 exact commercial identities into deterministic catalog metadata without expanding identity scope or making runtime/security claims.

The retained identity set remains exactly the manufacturer-discovery snapshot:

- 33 Base Devices;
- 106 exact ICPNs;
- 100 `Active` observations;
- 6 `Evaluation` observations;
- exact-set SHA-256 `6ff4f01a009e28aff1a6ebf3f74544c973ce9e2a229bc72f4574f71c47ea4918`.

`Evaluation` is an observed manufacturer marketing status only. It does not authorize Production admission.

## Metadata authority

Official ST Ordering Information is bound per commercial STM32U3 series:

- STM32U375: DS14861 Rev 3;
- STM32U385: DS14830 Rev 3;
- STM32U3B5: DS15097 Rev 1;
- STM32U3C5: DS15096 Rev 1.

Decoded fields are package, pin count, Flash-size code, temperature grade, dedicated-pinout option, and packing.

The policy handles package-sensitive pin-count codes explicitly:

- STM32U375/U385 `C` is 48 pins normally and 52 balls for WLCSP;
- STM32U375/U385 `R` is 64 pins normally and 68 balls for WLCSP;
- STM32U3B5/U3C5 `V` is 100 pins normally and 99 balls for WLCSP.

STM32U375/U385 also distinguish dedicated suffix `G` from `Q`; `G` denotes the SMPS/GPIO-G dedicated pinout. `TR` remains packing only.

## Fail-closed rules

The metadata grammar never admits a new commercial identity. A syntactically plausible ICPN not present in the retained 106-row manufacturer snapshot is rejected.

Unknown package, temperature, Flash, pin-count, or suffix semantics require manual review. The generic ST programmed-parts wildcard is not an admission mechanism.

Still blocked:

- Production admission;
- security-state semantics;
- option-byte or OEM-key semantics;
- RDP/security mutation;
- Flash geometry/programming algorithm equivalence;
- runtime programming;
- HIL support.

## Result

Expected deterministic result:

- metadata-ready exact ICPNs: **106**;
- manual review: **0**;
- rejected retained identities: **0**;
- scope expansion: **0**;
- Production catalog writes: **0**.

**Exact Production ICPN count: 1,862.**

Next research gate: `stm32u3-canonical-admission-plan-under-security-fence`.
