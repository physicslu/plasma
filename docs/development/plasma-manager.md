# PLASMA — Manager / Backend Engineering Contract

> Domain-specific contract. Read with [AGENTS.md](../../AGENTS.md) and [Common](plasma-development-common.md) for Plasma Manager, Controller, Gateway routing and REST backend.

## Scope
- Plasma Manager, Gateway/Controller/BFF, REST APIs, backend routing, deployment coordination and related service behavior.
- SWPC hosts Web/Controller/BFF; PPU/Z2 PS hosts the embedded programming runtime. Do not move live OpenOCD to SWPC.
- Preserve canonical one-based Site identity, Protocol v3.3 and Web REST v3 unless an approved change replaces the contract and all dependents together.
- Manager is bounded managed PPU routing, not an assumed universal scheduler. Inspect actual endpoints, process ownership and ports before edits.
- Changes to PPU-facing API also load [Embedded](plasma-embedded.md); changes to Web-facing API also load [Web](plasma-web.md).
- Update callers, tests, fixtures and documentation in the same change under Replace-by-Default.
