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
| [H006](H006-stm32-next-family-evidence-selection-2026-09-10.md) | 2026-09-10 | STM32 cross-family evidence accessibility, U0/C0 Ordering Information review, and historical next-family research selection | Superseded by H009 for current STM32 Device Catalog continuation | Retain as historical U0/C0 selection evidence; use H009 for current C0 work |
| [H007](H007-vendor-neutral-ic-admission-handover-2026-09-10.md) | 2026-09-10 | Vendor-neutral admission architecture and NXP KL25 compatibility plan before PR-B/PR-C/PR-D closure | Superseded by H008 | Use H008 for current continuation state; retain H007 as historical architecture context |
| [H008](H008-ic-support-architecture-freeze-v1-2026-09-11.md) | 2026-09-11 | Vendor-neutral IC Support Architecture Freeze v1 after PR-A/PR-B/PR-C/PR-D | Current | Define a bounded first real-hardware qualification Gate 1 for one exact target and narrow operation set |
| [H009](H009-stm32c0-c03-metadata-policy-2026-09-12.md) | 2026-09-12 | STM32C0 C0.3 manufacturer-authoritative metadata policy over the retained C0.2 commercial set | Current / Gate 2 pending | Verify PR #496 final-head CI/main drift, then Gate 2 merge; do not begin C0.4 under the C0.3 approval |

## Usage

For a new session, ask the agent to read the relevant handover before proposing or continuing changes. Examples:

```text
Read repo handover H008 and the IC Support Architecture Freeze v1 document before proposing the next hardware/runtime qualification transaction.
```

```text
Read repo handover H009 and AGENTS.md, verify PR #496 final-head CI and current main drift, then continue the STM32C0 C0.3 Gate 2 transaction. Do not begin C0.4 without a new Gate 1.
```

A handover records engineering state; it does not override `AGENTS.md`, checked-in executable code, or current repository state. If a handover conflicts with newer code, tests, or contracts, the newer repository state is authoritative.
