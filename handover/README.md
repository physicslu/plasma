# Plasma Engineering Handovers

This directory contains numbered engineering handover documents intended to let a new ChatGPT / Codex session recover the authoritative project state without relying on chat history.

## Index

| ID | Date | Topic | Status | Recommended continuation |
|---|---|---|---|---|
| [H001](H001-plasma-ic-evidence-canonical-pipeline-2026-09-06.md) | 2026-09-06 | IC Evidence, semantic extraction, relationship derivation, and canonical specification pipeline | Current | Memory Geometry Relationship Derivation Foundation |
| [H002](H002-render-swpc-managed-ps-qualification-2026-09-07.md) | 2026-09-07 | Render / Cloudflare / SWPC managed PS qualification and browser Programming routing defect | Current | Fix managed Programming / Engineering same-origin routing |
| [H003](H003-nxp-kl25-evidence-applicability-foundation-2026-09-07.md) | 2026-09-07 | NXP KL25 evidence applicability foundation and admission state | Current | Confirm repository/PR state before continuing KL25 evidence work |
| [H004](H004-real-z2-managed-ps-control-station-2026-09-10.md) | 2026-09-10 | Real PYNQ-Z2 PS qualification, macOS Control Station Managed routing, PR #450, and CI cache follow-up | Current | Continue PR #451 or formal Plasma PS<->PL loopback qualification |
| [H005](H005-nxp-kl25-live-semantic-qualification-2026-09-10.md) | 2026-09-10 | NXP KL25 live bounded semantic qualification through Gate 5.7A | Current | Continue Gate 5.8 manufacturer-evidence semantic/citation review |
| [H006](H006-stm32-next-family-evidence-selection-2026-09-10.md) | 2026-09-10 | STM32 cross-family evidence accessibility, U0/C0 Ordering Information review, and historical next-family research selection | Superseded by H012/H013 | Retain as historical U0/C0 selection evidence |
| [H007](H007-vendor-neutral-ic-admission-handover-2026-09-10.md) | 2026-09-10 | Vendor-neutral admission architecture and NXP KL25 compatibility plan before PR-B/PR-C/PR-D closure | Superseded by H008 | Use H008 for current continuation state; retain H007 as history |
| [H008](H008-ic-support-architecture-freeze-v1-2026-09-11.md) | 2026-09-11 | Vendor-neutral IC Support Architecture Freeze v1 after PR-A/PR-B/PR-C/PR-D | Current | Define a bounded first real-hardware qualification Gate 1 for one exact target and narrow operation set |
| [H009](H009-stm32c0-c03-metadata-policy-2026-09-12.md) | 2026-09-12 | STM32C0 C0.3 manufacturer-authoritative metadata policy over the retained C0.2 commercial set | Superseded by H010 | Retain as C0.3 history |
| [H010](H010-stm32c0-c04-admission-plan-2026-09-12.md) | 2026-09-12 | STM32C0 C0.4 exact-ICPN read-only capability/admission plan | Superseded by H011 | Retain as C0.4 history |
| [H011](H011-stm32c0-c05-publication-2026-09-12.md) | 2026-09-12 | STM32C0 C0.5 controlled publication of 209 capability-admittable exact ICPNs | Superseded by H012; PR #503 merged | Retain as C0.5 publication history |
| [H012](H012-stm32-post-c0-evidence-selection-2026-09-12.md) | 2026-09-12 | Post-C0 L1/L0/L4 official-ST evidence comparison and deterministic STM32L0 selection | Complete; PR #504 merged | Retain as next-family selection history |
| [H013](H013-stm32l0-l01-foundation-2026-09-12.md) | 2026-09-12 | STM32L0 L0.1 bounded research foundation | Complete; PR #506 merged | Retain as L0.1 foundation history; use H014/H015/H016/H017/H018/H019 |
| [H014](H014-stm32l0-l02-commercial-discovery-2026-09-12.md) | 2026-09-12 | STM32L0 L0.2 manufacturer-authoritative commercial discovery | Complete; PR #509 merged | Retain as L0.2 discovery history; use H015/H016/H017/H018/H019 |
| [H015](H015-stm32l0-l03-metadata-policy-2026-09-12.md) | 2026-09-12 | STM32L0 L0.3 manufacturer-authoritative metadata policy | Complete; PR #513 merged | Retain as L0.3 metadata history; use H016/H017/H018/H019 |
| [H016](H016-stm32l0-l04-admission-plan-2026-09-12.md) | 2026-09-12 | STM32L0 L0.4 read-only capability/admission plan | Complete; PR #515 merged | Retain as L0.4 admission history; use H017/H018/H019 |
| [H017](H017-stm32l0-l05-publication-2026-09-12.md) | 2026-09-12 | STM32L0 L0.5 controlled publication of 360 capability-admittable exact ICPNs | Complete; PR #516 merged | Retain as L0.5 publication history; use H018/H019 |
| [H018](H018-stm32-post-l0-next-family-selection-2026-09-12.md) | 2026-09-12 | Post-L0 L1/L4 retained official-ST evidence replay and deterministic STM32L4 selection | Complete; PR #517 merged | Retain as STM32L4 selection history; use H019 |
| [H019](H019-stm32l4-l41-foundation-2026-09-13.md) | 2026-09-13 | STM32L4 L4.1 bounded research foundation | Current; Gate 1 implementation in progress | Open/validate L4.1 PR, then obtain Gate 2 merge approval |

## Usage

For a new STM32 Device Catalog session:

```text
Read repo handover H019 and AGENTS.md, verify the STM32L4 L4.1 PR current head/main/CI/reviews, then continue the gated transaction.
```

For IC Support Architecture / hardware qualification:

```text
Read repo handover H008 and the IC Support Architecture Freeze v1 document before proposing the next hardware/runtime qualification transaction.
```

A handover records engineering state; it does not override `AGENTS.md`, checked-in executable code, tests, or current repository state. If a handover conflicts with newer code, tests, or contracts, the newer repository state is authoritative.
