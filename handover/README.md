# Plasma Engineering Handovers

This directory contains numbered engineering handover documents intended to let a new ChatGPT / Codex session recover the authoritative project state without relying on chat history.

## Index

| ID | Date | Topic | Status | Recommended continuation |
|---|---|---|---|---|
| [H001](H001-plasma-ic-evidence-canonical-pipeline-2026-09-06.md) | 2026-09-06 | IC Evidence, semantic extraction, relationship derivation, and canonical specification pipeline | Current | Memory Geometry Relationship Derivation Foundation |

## Usage

For a new session, ask the agent to read the relevant handover before proposing changes. Example:

```text
Read repo handover H001 and continue from its recommended continuation point.
```

A handover records engineering state; it does not override `AGENTS.md`, checked-in executable code, or current repository state. If a handover conflicts with newer code, tests, or contracts, the newer repository state is authoritative.
