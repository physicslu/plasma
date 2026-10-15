# Microchip original MCP × DFP identity archive — ADR-0002 classification correction

> **Correction to merged PR #909 (2026-10-15):** the legacy filename here
> contains `P1_DFP_DISCOVERY` for historical traceability. It is **not**
> an authoritative P1 research-priority designation. Original source evidence
> is preserved; the ADR-0002 P0/P1/P2 classification is clarified below.

## Why PR #909's terminology needed correction

[ADR-0002](../../../docs/adr/0002-openocd-software-qualified-catalog-visibility.md)
defines P1 as **bounded OpenOCD candidate** with a credible Target/Driver
family lead; a Microchip original MCP exact commercial part number joined only
to an original publisher DFP support name is **not** an OpenOCD Target/Driver
lead. Therefore the previously reported **2,191 "combined P1"** was a
misleading aggregate of non-equivalent evidence categories, **not** the
ADR-0002 P1 count.

The 2,065 manufacturer-original source records remain valid *DFP identity
research*, classified **P2 archive-only within this pinned OpenOCD
source-lock** until a credible P1 lead is independently shown. This is **not**
an `UNSUPPORTED`, discontinued, non-programmable or negative hardware
qualification decision. The owner has deferred new CFG discovery, new
manufacturer ordering-code acquisition, and individual Phase 2 investigations.

## Correct source-locked counts

| Non-overlapping ADR-0002 Research cohort | Exact commercial ICPNs |
|---|---:|
| **P0: source-backed OpenOCD family research leads (unchanged)** | **2,437** |
| **P1: bounded OpenOCD Target-only family research candidates (unchanged)** | **126** |
| **P2: archive-only remainder in source-replayed subset** | **20,713** |
| — Includes **DFP-only identity subcohort** from PR #909 (NOT extra P1) | **2,065** |
| — Other P2 archival Research rows | **18,648** |
| **Total distinct original-MCP exact ICPNs in this research subset** | **23,276** |

The P2 DFP-only 2,065 subset covers **340 distinct publisher DFP Base Device
names**. The source-replayed partition is **2,437 + 126 + 20,713 = 23,276**;
the P2 DFP subcohort is **part of** 20,713, never added on top.
The historical broader 24,051 Research count in the ADR is a separate
source-cohort denominator and must not be mixed with these 23,276 observations.

## Evidence and archive boundaries

Inputs are the SHA-replayed original-MCP 23,276 commercial `partNumber` /
manufacturer `basePartNumber` records and the original Microchip DFP
`index.html` SHA-256
`9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0`.

Every one of the 2,065 archived DFP-only records retains exact commercial
ICPN, manufacturer Base, DFP support name, pack/version, MCP source SHA-256
references, DFP original source SHA and explicit **absent reviewed OpenOCD
Target/Driver evidence**. No software `SUPPORTED`, Catalog identity
admission, Product IC Selector publication or Phase 2/3 capability follows.

The original GitHub Actions run [38680931140](https://github.com/physicslu/plasma/actions/runs/38680931140)
established 2,065 exact order codes and 340 Base Device joins; the successor
workflow enforces corrected ADR-0002 priority semantics with fail-closed
replay. Historical PR #909's original output/CI descriptions are immutable
history, not a live accepted P1 classification.

Top DFP-only archived manufacturer packs: PIC32MZ-EF_DFP **463**,
PIC32CM-JH_DFP **217**, PIC32MZ-DA_DFP **208**, PIC32MK-GP_DFP **105**,
PIC32MK-MC_DFP **101**, PIC32CM-PL_DFP **94**. All remain P2 archived
identity observations unless independently reclassified.

## Deliberate implementation limit

The generated report is **schema_version=2**; the historical PR #909
schema v1 output has been superseded and cannot be compared by key name
without this explicit classification migration.

The existing script / test / CI file names containing `p1_dfp_discovery_v1`
are retained as references to PR #909; **their result schema has corrected
`adr0002_p1_openocd_candidate_exact_icpns`, `adr0002_p2_archive_exact_icpns`,
`dfp_only_p2_archive_exact_icpn_subset` and record
`adr0002_research_priority: P2`**. Obsolete combined-P1 counts and
`p1_research_state` are removed from current generated reports.

No modification to ADR-0002, Production Manifest, API, IC Selector, runtime,
hardware, physical HIL, Programming Profile or manufacturer source records
is authorized by this correction.
