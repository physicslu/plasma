# STM32C0 Phase C0.0 — post-U0 next-family evidence selection

Status: research-selection transaction; read-only with respect to Production

Date: 2026-09-11

## Decision

The next STM32 Device Catalog research family is **STM32C0**.

This decision authorizes only the next bounded research transaction. It does not admit any STM32C0 commercial part number to Production and does not establish programming, Flash-controller, option/security, HIL, electrical, socket, or runtime support.

## Post-U0 decision boundary

The transaction starts from the Production state created by STM32U0 U0.5:

- 703 exact ICPNs
- 243 Base Devices
- nine STM32 Production families
- STM32U0: 68 exact ICPNs

The current cross-family shortlist is:

1. STM32C0
2. STM32L1
3. STM32L0

The shortlist itself is not selection evidence. Each family must first pass a bounded official-manufacturer commercial identity/lifecycle evidence gate.

## Deterministic bounded surface

OpenOCD data is used only to bound the research surface. It is not commercial identity or lifecycle authority.

One lexical-min concrete Base Device is selected per guarded `ordering_pattern` subfamily:

- STM32C0: 6 representatives from 95 source rows / 73 ordering-pattern rows
- STM32L1: 4 representatives from 132 source rows / 87 ordering-pattern rows
- STM32L0: 16 representatives from 166 source rows / 164 ordering-pattern rows
- total: 26 representatives

CMSIS aliases are not promoted to commercial identities.

## Manufacturer evidence authority

The retained authoritative live run is GitHub Actions run `34560484391`.

For this transaction, manufacturer commercial identity/lifecycle authority is:

- exact Part Number identity from the official ST **Quality & Reliability** surface; and
- Marketing Status from the official ST **Sample & Buy** surface only when the exact Part Number sets match fail-closed.

The retained evidence surface is therefore:

`quality_and_reliability_identity_plus_sample_and_buy_lifecycle`

This is a manufacturer-authoritative exact-set join, not a Sample & Buy-only identity claim.

The authoritative run dispositioned all 26 targets with zero manual review and zero source-unavailable results:

| Series | Representatives | Active representatives | Lifecycle-only representatives | Active exact ICPNs observed |
| --- | ---: | ---: | ---: | ---: |
| STM32C0 | 6 | 6 | 0 | 21 |
| STM32L1 | 4 | 1 | 3 | 1 |
| STM32L0 | 16 | 16 | 0 | 44 |

STM32L1 is therefore deprioritized for the next-family transaction due to lifecycle, but it is **not rejected for future support**.

## Q&R-only method diagnostic

A second bounded live run, `34561677731`, tested whether exact Part Number and Marketing Status could be required to co-locate in Quality & Reliability for all three families.

That method worked for STM32L0 and STM32L1 but failed for all six STM32C0 representatives with the same readiness condition: the C0 Quality & Reliability surface did not expose the required Part Number / Marketing Status pair.

This is treated as a **method/layout diagnostic**, not as negative STM32C0 family evidence. The diagnostic does not participate in family scoring or selection.

This finding prevents a UI-layout assumption from being mistaken for a manufacturer evidence-quality difference.

## Ordering Information comparison

Because both STM32C0 and STM32L0 had complete active commercial-identity coverage, both entered the independent Ordering Information comparison.

Official ST Ordering Information authority is complete for:

- STM32C0: 6 representatives, 5 unique datasheets, no revision drift
- STM32L0: 16 representatives, 16 unique datasheets, no revision drift

The required schema is complete for both families:

- device family
- product type
- device subfamily
- pin count
- Flash memory size
- package
- temperature range
- packing/options

Important L0 semantics retained for future work include:

- STM32L031 `S` is an official UFQFPN28 one-power-pair option and must not be normalized away.
- STM32L010 has a narrower ordering grammar and does not expose the general L0 `D` BOR option used by many other L0 subfamilies.

The required Ordering Information evidence quality is therefore equivalent between STM32C0 and STM32L0.

## Selection rule

The selection policy is fixed before interpreting the final decision:

1. require complete manufacturer commercial identity/lifecycle evidence;
2. deprioritize lifecycle-heavy families without rejecting them for future support;
3. compare official ST Ordering Information completeness for the remaining active candidates;
4. if required evidence quality is equivalent, apply the current deterministic cross-family shortlist order.

The remaining equivalent candidates are:

1. STM32C0
2. STM32L0

Therefore the selected next research family is **STM32C0**.

Frozen selection artifact:

`data/device-catalog/research/stm32-post-u0-next-family-selection.json`

Frozen selection SHA-256:

`f2bc4d955952cc8c25362ca5568e944470f7a1b43bf41dee2fcca9516e9c8773`

## Explicit non-claims

All of the following remain false:

- canonical admission authorized
- Production write authorized
- programming policy defined
- programming-algorithm equivalence
- Flash geometry/controller qualification
- option/security semantics qualification
- physical/electrical/HIL qualification
- runtime programming support

The correct next transaction after C0.0 is **STM32C0 C0.1 — Foundation**, which must independently freeze the selected C0 bounded surface and retained evidence before any discovery expansion.

## Validation

Permanent validation must replay:

```bash
python data/device-catalog/research/test_stm32_post_u0_evidence_probe.py
python data/device-catalog/research/test_stm32_post_u0_selection.py
python data/device-catalog/research/freeze_stm32_post_u0_selection.py --check
python data/device-catalog/research/validate_stm32_post_u0_selection.py
```

Historical post-G4 U0/C0/L1 selection artifacts remain immutable and are not rewritten by this transaction.
