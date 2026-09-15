# STM32U3 manufacturer identity discovery

## Purpose

Freeze a bounded, manufacturer-authoritative STM32U3 commercial identity snapshot under the merged STM32U3 security fence. This transaction identifies exact commercial part numbers only; it does not establish programming, debug, HIL, or Production support.

## Evidence boundary

Identity authority is STMicroelectronics only:

- STM32U3 series product selector for the currently exposed commercial base-device set;
- each selected base device's ST **Quality & Reliability** table for exact `Part Number` rows and the marketing status observed on 2026-09-15.

OpenOCD ordering patterns and CMSIS device names are not accepted as manufacturer exact-ICPN authority and are not used to synthesize part numbers.

## Bounded result

The current ST selector snapshot exposes:

- **33 base devices**;
- **106 exact commercial ICPNs** from ST Quality & Reliability rows;
- **100 Active** exact identities;
- **6 Evaluation** exact identities.

Evaluation identities remain retained as identity evidence because the manufacturer currently exposes those exact Part Number rows. `Evaluation` is not rewritten as `Active`, and this transaction does not decide later Production admission policy.

The commercial selector currently provides base-device observations in four of the eight upstream research subfamilies:

- STM32U375;
- STM32U385;
- STM32U3B5;
- STM32U3C5.

No current commercial base-device identity was observed in this bounded selector snapshot for:

- STM32U335;
- STM32U345;
- STM32U356;
- STM32U366.

That absence means only `no_current_manufacturer_commercial_identity_observed_in_bounded_selector_snapshot`. It must **not** be converted into an `unsupported` claim, because OpenOCD/CMSIS candidate metadata and manufacturer commercial identity are separate evidence dimensions.

## Security and support fence

Still blocked:

- Production admission;
- lifecycle permanence claims;
- security or OEM-key semantics support;
- option-byte/OEM-key operations;
- Flash geometry or programming-algorithm equivalence claims;
- runtime programming;
- HIL validation.

No Production catalog file is written by this transaction.

## Result

Status: bounded manufacturer identity discovery is clean.

Research identity scope: **106 exact STM32U3 ICPNs**.

Production catalog remains unchanged at **1,862 exact ICPNs**.

Next research gate: `stm32u3-metadata-policy`.
