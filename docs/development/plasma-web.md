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

### PMode Factory Console on the Manager backend

PMode keeps its Facility → PPU → Site UI. On a Managed Control Station the
catalog is the Manager Registry + Fleet (PPU key = Manager Alias) and a
production batch is a **sequence of independent Manager programming runs**
(`software/web/app/fleet/managed-factory-backend.ts`): per-PPU admission on a
fresh observation, one plan / Site lease / Resource check / Job Binding per
Site, `attempts = 1`, no retry. An `OUTCOME_UNKNOWN` run stops the later
Sites of that PPU only; Stop Policy and ABORT only stop queuing.

The page states this mode to the operator
(`Sequential / Session-based / Non-durable · NOT PRODUCTION QUALIFIED`), its
ready label is `SEQUENTIAL BATCH READY`, and each receipt names the Site
interface so a Mock result is never read as hardware evidence.

Not implemented, and not to be claimed:

- **Durable Manager-owned production batch.** The batch lives in the Console
  session; a reload stops queuing (an in-flight run finishes in the Manager).
- **Concurrency.** One run at a time. Parallel Sites on one PPU and parallel
  PPUs are not physically qualified.
- **Production qualification.** Only PYNQ-Z2 Site 2 has physical evidence.
  `site_count` is topology, never capability: a Site is programmable only
  when a committed Programming Route declares the IC on it.

## Web validation commands

```bash
cd software/web
npm run lint
npm test
npm run validate:artifact
```

## EMode Single PPU Programming — Operations, Read Memory, Programming Source (2026-11-11)

- **Operations** are exactly three checkboxes, `E Erase`, `P Program`, `V Verify`, all checked by default and freely combined. The whole selection is sent as one ordered `operations` list and runs as ONE programming Job (never `flash_cycle`). An Operation no Programming Route declares is unchecked and disabled. No selection, or Erase + Verify without Program, disables Start with an explicit reason.
- **Erase only** needs no Programming Image; it erases the Flash range of the Programming Profile.
- **Read Memory** is its own block and button (Start Address, Length, status, Bytes Read, SHA256, binary download). It is an independent Job: not a checkbox, not part of the Batch, not counted in PASS / FAIL / Yield and not subject to Repeat / Retry / Stop Policy. Only the Profile Flash range can be read. The binary comes from the Manager through the same-origin BFF and is re-hashed against the receipt before it is offered; the Browser never contacts a PPU.
- **Programming Source** stays `[ Programming Image ] [ Bundle ]` (wire `image` / `bundle`). The picker shows the real file name (clipped, full name as tooltip), size and format, and `Change...` to re-select; no local path is shown. Switching the Source clears the file, the run and the plan state and submits nothing.
- There is **no standing PROGRAMMING PLAN panel**. Start still locks the inputs and runs the Backend plan; Plan ID, Route, Source, Operations, Range, Resource SHA256 and Job Binding SHA256 are written to the Log and shown under Receipts & Diagnostics of the run.
- **Repeat** is fixed at 1 and disabled.
- **Retry** (0–5) and **Stop Policy** (`Never` / `1 failed Site`) are sent with one Batch request; the Manager alone decides whether another attempt is submitted ([contract](../architecture/emode-batch-retry-stop-policy-v1.md)). The Browser has no retry loop. The stop button is **STOP QUEUING**: it never cancels a running Job. Batch Summary and the Site result count the Batch once, by its final verdict; attempts are listed under BATCH ATTEMPTS.
