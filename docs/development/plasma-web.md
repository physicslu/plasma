# PLASMA — Web / Frontend Engineering Contract

> Domain-specific contract. Read with [AGENTS.md](../../AGENTS.md) and [Common](plasma-development-common.md) for UI and frontend API work.

## Scope
- Web UI, frontend state, Web REST v3 client behavior, frontend build, lint and unit tests.
- Inspect actual software/web manifests and implementation; do not assume a framework, WebSocket or undocumented Gateway endpoint.
- Preserve one-based Site identity, independent Site execution and explicit Erase/Program/Verify/Read semantics.
- Changes to backend REST schema or API also load [Manager](plasma-manager.md) and validate affected client/server compatibility.
- Use affected frontend tests and build checks. UI simulation does not prove real PPU or DUT operation.

## Migrated detailed clauses from shared contract

## 7. Web environment

Web project:

```text
software/web/
```

Use `package.json` as source of truth for stack/versions. The project uses React + TypeScript and currently includes Next.js/Vinext and Vite tooling.

Normal checks:

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

The Web Console must discover PPU/Site topology from canonical status rather than hard-code an eight-Site product assumption. Job requests send one-based `site_id` only.

Engineering Programming uses Web REST v3 Programming Asset routes. Browser source-input terminology must not be confused with the Normalized Image carried by Protocol v3.3.

Do not assume production Z2 needs Node.js, npm, or the development server merely because the integration host uses them for development/build/demo work.

## Current Web contract boundaries

4. Web stack includes React/TypeScript plus Next.js/Vinext and Vite tooling; inspect `package.json` before stack assumptions.
5. Web REST v3 and Protocol v3.3 are canonical-only development contracts; there is no legacy compatibility requirement.

## Web validation commands

Web:

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

