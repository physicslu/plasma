# STM32L5 — Manufacturer-Authoritative Metadata Policy

Status: **49 retained exact ICPNs metadata-ready; research-only; Production unchanged**

## Purpose

This transaction converts the merged STM32L5 manufacturer identity set into deterministic catalog metadata without expanding commercial identity scope and without changing the STM32L5 security/runtime support boundary.

Commercial identity remains authoritative from the retained ST Quality & Reliability observation set:

- Base Devices: **17**
- exact ICPNs: **49**
- retained lifecycle observation: **49 Active** on 2026-09-14
- exact ICPN set SHA-256: `f9a74a7badfb39f8fc52753fc3904cd63a8b3e0a2e4dcc37dee759809aaa68b1`

A datasheet ordering grammar is metadata authority only. It is **not** allowed to invent or admit an exact Part Number that is absent from the retained manufacturer commercial set.

## Ordering Information authority

Two official ST datasheet records cover the retained set:

| Series | Authority | Ordering page | Retained Base Devices | Retained exact ICPNs |
|---|---|---:|---:|---:|
| STM32L552 | DS12737 Rev 6 | 334 | 11 | 26 |
| STM32L562 | DS12736 Rev 5 | 334 | 6 | 23 |

The policy deterministically decodes only catalog metadata fields already used by Plasma:

- series / Base Device;
- package;
- pin count;
- Flash-size ordering code;
- temperature grade;
- exact option suffix;
- manufacturer source reference and verification status.

The decoder preserves the exact manufacturer ICPN literally.

## Suffix governance

The ST ordering scheme distinguishes package, temperature, dedicated SMPS pinout (`P` / `Q`) and tape-and-reel (`TR`). The retained exact set currently uses only:

`""`, `P`, `Q`, `TR`, `PTR`, `QTR`.

ST also documents a generic programmed-parts `xxx` concept. Plasma does **not** treat that wildcard as permission to synthesize commercial identities. `programmed_parts_wildcard_admission_authorized=false` is permanent for this transaction.

## Result

Offline replay over all retained identities yields:

- metadata-ready exact ICPNs: **49**
- manual review required: **0**
- rejected retained identities: **0**
- scope expansion: **0**

Representative decodes are frozen in `stm32l5-metadata-policy-baseline.json` to cover both device lines, both Flash-size codes used by STM32L552, temperature suffix `3`, packages LQFP/UFBGA/WLCSP, dedicated-pinout tails, and tape-and-reel tails.

## Security and capability boundary

This transaction does **not** authorize or validate:

- Production catalog admission;
- TZEN or option-byte writes;
- RDP regression or mass erase;
- TrustZone/security semantics;
- Flash geometry;
- erase/program algorithm equivalence;
- debug-connect behavior by security state;
- runtime programming;
- HIL/PPU/socket/electrical support.

The existing STM32L5 security-scope foundation remains authoritative and fail-closed.

## Next gate

The next bounded transaction is **STM32L5 canonical admission planning under the security fence**.

That gate may establish catalog-only routing/admission readiness, but a positive catalog result must not be presented as physical-programming or security-state support.
