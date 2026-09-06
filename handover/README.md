# Plasma Engineering Handovers

This directory contains numbered engineering handover documents intended to let a new ChatGPT / Codex session recover the authoritative project state without relying on chat history.

## Index

| ID | Date | Topic | Status | Recommended continuation |
|---|---|---|---|---|
| [H001](H001-plasma-ic-evidence-canonical-pipeline-2026-09-06.md) | 2026-09-06 | IC Evidence, semantic extraction, relationship derivation, and canonical specification pipeline | Current | Memory Geometry Relationship Derivation Foundation |
| [H002](H002-z2-ps-deployment-release-identity-2026-09-06.md) | 2026-09-06 | PYNQ-Z2 PS-only deployment, Managed PS Loopback qualification, and Release Identity v2 | Active qualification / PR #382 in progress | Repair remaining SHA-qualified PPU acceptance naming, take PR #382 to Gate 2, then exact post-merge Mac + Z2 requalification and Managed PS Loopback |

## Usage

For a new session, ask the agent to read the relevant handover before proposing changes. Examples:

```text
Read repo handover H001 and continue from its recommended continuation point.
```

```text
Read AGENTS.md and repo handover H002, then continue PR #382 from its documented qualification blocker.
```

A handover records engineering state; it does not override `AGENTS.md`, checked-in executable code, or current repository state. If a handover conflicts with newer code, tests, or contracts, the newer repository state is authoritative.
