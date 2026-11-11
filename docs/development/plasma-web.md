# PLASMA — Web / Frontend Engineering Contract

> Domain-specific contract. Read with [AGENTS.md](../../AGENTS.md) and [Common](plasma-development-common.md) for UI and frontend API work.

## Scope
- Web UI, frontend state, Web REST v3 client behavior, frontend build, lint and unit tests.
- Inspect actual software/web manifests and implementation; do not assume a framework, WebSocket or undocumented Gateway endpoint.
- Preserve one-based Site identity, independent Site execution and explicit Erase/Program/Verify/Read semantics.
- Changes to backend REST schema or API also load [Manager](plasma-manager.md) and validate affected client/server compatibility.
- Use affected frontend tests and build checks. UI simulation does not prove real PPU or DUT operation.

## Web environment

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

- Web stack includes React/TypeScript plus Next.js/Vinext and Vite tooling; inspect `package.json` before stack assumptions.
- Web REST v3 and Protocol v3.3 are canonical-only development contracts; there is no legacy compatibility requirement.

## Managed Programming (EMode / PMode) — normative

On a Managed Control Station (`apiMode === "managed"`) Programming has one
data path, shared by EMode Single PPU and PMode Factory Console
(`software/web/app/programming/managed-programming.ts`):

Console → same-origin BFF → Manager Registry / Fleet / Programming Routes →
Manager programming plan + run → PPU Runtime.

- Topology: commissioned Manager Registry entries joined with the Manager
  Fleet. The **Manager Alias** is the only routing key; the device **PPU ID**
  is display identity. The Engineering PPU provider
  (`/api/engineering/targets`), direct `/api/jobs` and the Batch runtime are
  the Standalone Mock development runtime only and are never used here.
- Availability is judged in layers, each with an exact reason: PPU ONLINE
  (Fleet transport + current observation), Platform admission (pairing,
  Runtime active, no recovery) and Programming capability (a committed
  Programming Route declares the IC on the Site, Site enabled and idle).
  The UI only reads; it never enrolls, rotates a credential or recovers.
- Programming Source: `Programming Image` (default; e.g. a `.bin`) or `Bundle`, mutually exclusive. These two labels are used on every page (shared `ProgrammingSourceSelector`); the wire values stay `image` / `bundle`.
  Switching clears the file, plan, run view and validation state and issues
  no request.
- One **Start Programming**: lock inputs + SHA256 → Manager plan → exactly
  one run start → observe. There is no manual Prepare step; the Manager plan
  is never skipped. `attempts = 1`, `auto_retry = DISABLED`; Repeat / Retry /
  Stop Policy and ABORT are disabled. A lost start response or
  `OUTCOME_UNKNOWN` is never followed by another write.
- PASS in the UI requires the Manager receipt: single submission, verified
  SAFE_OFF, confirmed Job Binding and Resource Set, matching readback.
- Browser (Playwright) and Mock results are Host-only evidence and never
  physical PPU / FPGA / DUT acceptance.

## Web validation commands

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```
