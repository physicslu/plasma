# STM32 cross-family research prioritization

Status: read-only research governance baseline

## Purpose

The legacy STM32 next-family policy intentionally covered only `STM32F\d+` series. After the admitted F-line families were exhausted and STM32G0/STM32G4 were published, that historical policy correctly returned no selected family. This document defines a separate post-G4 cross-family research shortlist policy without modifying or reinterpreting the historical F-line transaction.

This policy is not a device-support admission policy. It does not establish exact commercial identity, lifecycle status, flash geometry, programming algorithm equivalence, option/security semantics, physical qualification, HIL qualification, or runtime programming support.

## Frozen transaction boundary

The prioritization snapshot is replayed against:

- Production prestate: `stm32-cross-family-prioritization-production-manifest-prestate.json`
- Production prestate SHA-256: `93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d`
- Production state represented by that prestate: 635 exact ICPNs, 217 Base Devices, eight STM32 series
- Frozen prioritization baseline: `stm32-cross-family-prioritization-baseline.json`
- Frozen baseline SHA-256: `9a99865865f048e6a7636efd82cb17958fdc593240a329e18e3b68d8b0f862f9`

Historical replay always uses the frozen Production prestate. Future Production growth must not rewrite this snapshot or cause its replay to be regenerated against a later global catalog state.

## Candidate inventory

At the frozen boundary the remaining STM32 OpenOCD candidate inventory contains:

- 15 candidate series
- 1,369 total source rows
- 970 `ordering_pattern` rows
- five structurally shortlist-eligible standard non-wireless series

The policy keeps `ordering_pattern` and `cmsis_device_name` meanings separate. CMSIS aliases are routing/name metadata and are never promoted into commercial identity evidence.

## Architecture-risk cohorts

The policy separates structural researchability from architecture scope. Candidates are assigned to explicit cohorts:

- `standard_nonwireless_research`: 5
- `trustzone_requires_security_scope`: 3
- `wireless_requires_dedicated_scope`: 6
- `high_complexity_requires_partitioned_scope`: 1

Wireless, TrustZone, and high-complexity families are not rejected. They are withheld from the first research shortlist because their evidence and qualification scope is materially different and requires a dedicated governance transaction.

## Deterministic first shortlist

The structural gate requires:

1. at least one `ordering_pattern` row;
2. exactly one OpenOCD target configuration;
3. complete non-blank mapping metadata; and
4. the expected `upstream-openocd / mapping_candidate / not_verified` source contract.

Within the standard non-wireless cohort, the ordering is deterministic:

1. fewest ordering-pattern rows;
2. fewest total source rows;
3. highest ordering-pattern fraction; and
4. lexical series name as the final tie-break.

The frozen research shortlist is therefore:

| Rank | Series | Ordering patterns | Source rows | Ordering fraction | Target config |
| ---: | --- | ---: | ---: | ---: | --- |
| 1 | STM32U0 | 42 | 48 | 0.875000 | `tcl/target/stm32u0x.cfg` |
| 2 | STM32C0 | 73 | 95 | 0.768421 | `tcl/target/stm32c0x.cfg` |
| 3 | STM32L1 | 87 | 132 | 0.659091 | `tcl/target/stm32l1.cfg` |

This ranking minimizes the bounded manufacturer-evidence probe surface. It is not a market-priority score and it is not a statement that these families share programming behavior with STM32G0 or STM32G4.

## Selection boundary

`selected_next_research_family` remains `null`.

Each shortlist entry requires the next independent gate:

`bounded_official_manufacturer_evidence_accessibility_probe`

That gate must evaluate official manufacturer identity/lifecycle evidence accessibility before a family may be selected for a discovery phase. OpenOCD row count alone cannot authorize a family selection.

## Explicit non-claims

The frozen report keeps all of these claims false:

- Production write authorized
- exact ICPN claimed from OpenOCD
- marketing/lifecycle claimed from OpenOCD
- programming policy defined
- programming algorithm equivalence claimed
- next research family selected
- shortlist admission-ready
- runtime programming support claimed

## Validation

Run:

```bash
python data/device-catalog/research/test_stm32_cross_family_prioritization.py
python data/device-catalog/research/test_stm32_cross_family_prioritization_replay.py
```

The permanent GitHub Actions workflow is:

`.github/workflows/device-catalog-stm32-cross-family-prioritization-validation.yml`

The replay validator locks the historical bytes while allowing the current Production catalog to grow monotonically. It must not regenerate historical conclusions from future Production state.
