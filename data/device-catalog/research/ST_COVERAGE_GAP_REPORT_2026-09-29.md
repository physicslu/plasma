# STM32 Portfolio Coverage Gap Audit — v0.2 (bounded baseline)

**Reference date:** 2026-09-29

**Record state:** Research-only. Not an admission, device support, software programming, or physical qualification claim.

## Executive finding

The integrity-bound Plasma Production ST subset contains **2,683 unique exact ICPNs across 23 catalog families**. The audit reads **all 23 admitted CSV sources**, checks each source's frozen Git blob, SHA-256, row count, normalized `icpn` field and global uniqueness. It compares **five independently identified Active manufacturer exact-MPN sentinels** against those actual Production rows. All five are absent, and their five portfolio families have no Production entry.

This proves a **minimum observed gap of five exact Active manufacturer MPNs in five unrepresented STM32 series**, not the size of ST's complete gap. A single sentinel does not stand in for all commercial variants of its family.

ST's official MCU/MPU portfolio page advertises STM32 MCUs as having **more than 4,500 commercial part numbers**: <https://www.st.com/en/microcontrollers-microprocessors.html>. Because that is a descriptive, non-enumerated portfolio count, and no same-date, same-lifecycle exact-MPN population has been acquired for all products, **actual current Active exact-ICPN coverage and the real missing-MPN count are both UNKNOWN**. `2,683 / 4,500 = 59.62%` is only an *illustrative inventory scale comparison* using the stated floor; it is **not** Plasma Active Coverage, a statistically inferred coverage interval, or an exact Active gap calculation.

## Frozen ST Production baseline

Original main manifest Git blob: `c8012b211a28b0a7811bfe978e7e697bc169c6f3`. Additional non-ST Production sources added later do not change the frozen ST-only scope, provided all ST source bindings remain byte-for-byte equal to the snapshot.

| STM32 grouping | Admitted exact ICPNs |
| --- | ---: |
| Mainstream: F0/F1/F3/G0/G4/C0 | 408 |
| High performance: F2/F4/F7/H7/H7RS | 663 |
| Ultra-low power: L0/L1/L4/L5/U0/U3/U5 | 1,438 |
| Wireless: WBA2X/WLX/WBX/WBA5X/WBA6X | 174 |
| **Total / 23 manifest families** | **2,683** |

## Official manufacturer Active sentinels absent from Production

One complete commercial ordering identity was selected per unrepresented series. All five manufacturer webpages or official eStore listings showed **Active** as inspected on 2026-09-29. These references are public source leads, **not yet a retained, complete manufacturer exact-inventory acquisition**. The validator tests exact intersection against all integrity-bound Production `icpn` columns.

| Unrepresented STM32 series | Official Active exact MPN | Evidence surface | Gap handling |
| --- | --- | --- | --- |
| H5 | [`STM32H503CBT6`](https://www.st.com/en/microcontrollers-microprocessors/stm32h503cb.html) | ST Quality and Reliability exact row | Fresh backend, identity and metadata research |
| C5 | [`STM32C531CBT6`](https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-mainstream-mcus/stm32c5-series.html) | ST eStore exact Active listing | Fresh backend, identity and metadata research |
| N6 | [`STM32N657A0H3Q`](https://estore.st.com/en/products/microcontrollers-microprocessors/stm32-32-bit-arm-cortex-mcus/stm32-high-performance-mcus/stm32n6-series.html?p=3) | ST eStore exact Active listing | **Separate programming profile / external-memory exception**. The pinned research OpenOCD `stm32n6x.cfg` did not establish the ordinary internal-Flash admission path. Do not infer backend support from identity. |
| WB0 | [`STM32WB05KZV6TR`](https://www.st.com/en/microcontrollers-microprocessors/stm32wb05kz.html) | ST Quality and Reliability exact row | Fresh backend, identity and metadata research |
| WL3 | [`STM32WL33CCV6`](https://www.st.com/en/microcontrollers-microprocessors/stm32wl33cc.html) | ST Quality and Reliability exact row | Fresh backend, identity and metadata research |

**Not counted as confirmed current Active gaps:** STM32W108 (retained historical structural exception), unexamined variants in the already admitted 23 families, any extrapolated package/grade/TR combinations, non-Active products, products outside the STM32 MCU/wireless scope, and parts with only CMSIS device-name evidence.

## What is still unknown

1. The complete, dated ST exact commercial-MPN inventory and its **same-row marketing status**; the 4,500+ number cannot replace this.
2. How many of today's ST Active exact MPNs were already admitted in the 23 families, and whether any admitted historical entries have since changed lifecycle.
3. Missing Active package, temperature grade, memory-density, order and packing variants *within* existing Plasma families. Zero-families alone are not a sufficient full coverage audit.
4. Which newly identified identities have an independently qualified backend and safe programming profile; OpenOCD debug reachability alone is not Flash programming evidence.

## Next gate: reproducible ST Active Exact Set Difference

- Acquire a manufacturer-authoritative, dated complete product-selector/eStore exact-MPN dump or an equivalently complete paginated enumeration, storing raw response, source URL, timestamp, pagination, counts and integrity digest. Exclude dev boards and unrelated product categories.
- Normalize ordering identities only with explicit manufacturer alias/packaging policy; preserve TR, temperature and security suffixes instead of inventing missing combinations. Retain exact marketing lifecycle per row, and distinguish duplicate page echoes from distinct SKUs.
- Compare `Active ST exact set - Plasma Production exact set`, and separately calculate `Production - current Active ST exact set`; retain unresolved/missing-lifecycle evidence separately.
- Group every missing record into **Identity / Metadata / Backend / Lifecycle / Physical evidence** states. Do not auto-publish an Active identity without admission and one deterministic backend route.
- Publish a real coverage KPI only after the above population and date alignment is verified. Changes to Production ICPNs remain behind the explicit Production merge gate.

**Replay:** `python data/device-catalog/research/audit_st_portfolio_coverage_gap.py` validates all 23 source integrity bindings and the five official Active exact-MPN sentinels against the frozen report. The companion `st-portfolio-gap-source-2026-09-29.json` records official reference URLs, classifications and baseline source digests; `st-portfolio-coverage-gap-v0.2.json` is the machine-readable output.
