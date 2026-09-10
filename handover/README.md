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

## Usage

For a new session, ask the agent to read the relevant handover before proposing changes. Example:

```text
Read repo handover H005 and continue NXP KL25 Gate 5.8.
```

A handover records engineering state; it does not override `AGENTS.md`, checked-in executable code, or current repository state. If a handover conflicts with newer code, tests, or contracts, the newer repository state is authoritative.
