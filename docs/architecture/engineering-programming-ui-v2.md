# Engineering Programming UI v2

## Decision

`Engineering Mode -> Programming` is the primary and only dedicated single-PPU programming workbench.

The former Production `/fleet/programming` workspace is retired. That route redirects to `/fleet`, and Production Mode exposes only the Factory Console as its primary operator surface. This keeps single-PPU engineering/maintenance controls out of PMode while preserving the canonical two-mode product model.

The Engineering v2 UI is status-first. The approved desktop layout is now a strict vertical hierarchy so the Programming controls do not compete for horizontal space and `LIVE SITE STATUS` remains the primary runtime surface.

```text
EMode sidebar | SINGLE PPU PROGRAMMING
              |
              | KPI
              | PPU Sites | Selected | Running | Pass | Fail | Yield | Cycle Time
              |
              | 1. SYSTEM SETUP
              | Facility | PPU
              | topology summary
              |
              | 2. PROGRAMMING JOB
              | Target IC          | Programming Image
              | Operations E/P/V/R | Repeat / Retry / Stop Policy
              | Batch Ready        | START / ABORT
              |
              | 3. LIVE SITE STATUS — all Sites on selected PPU
              | Batch ✓ | Site | Target IC | State | Progress | Result | E/P/V/R
```

There is no separate `TARGET SITES` panel and no separate `LIVE PROGRESS MONITOR`. Both duplicate information already represented by the primary Site table.

`RECENT EVENTS` is also removed from the Programming workspace because it duplicates detailed Engineering log evidence while consuming the viewport needed by Site runtime status. The detailed Engineering log capability remains available as Engineering evidence and is not replaced by a five-line summary.

## Engineering navigation

Engineering uses a persistent dark EMode sidebar for workspace navigation:

- EMode / Plasma / Engineering Mode identity at the top;
- Overview, PPU / Sites, Programming, Mock, Diagnostics, Logs, Tools and Settings as one vertical menu;
- the active section uses the blue operator-selection treatment;
- the desktop sidebar may collapse to a narrow icon rail without changing the active Engineering section;
- narrow/mobile layouts may switch to a horizontal scrollable navigation bar.

This is navigation presentation only. It does not create a new Product Mode. ProductMode remains only `production` and `engineering`.

## Site visibility versus Batch membership

These are separate concepts and must not be conflated:

- **PPU Sites**: every Site reported by the currently selected PPU. Every one remains visible in `LIVE SITE STATUS`, including unselected and disabled Sites.
- **Batch Selected Sites**: the operator intent for the next Engineering Batch. The first table column owns this checkbox state.

The table header may select or clear all currently selectable Sites. A disabled or otherwise non-selectable Site remains visible but cannot be added to the Batch.

When `START PROGRAMMING` is pressed, the browser snapshots the checked Site IDs once. That immutable snapshot is the membership of the active Batch. Selection controls are not allowed to mutate an active Batch; later checkbox changes apply only to a future Batch.

Selection state continues to be keyed by the canonical Engineering target `(facility_id, ppu_id)` and Site IDs. A PPU switch therefore changes both the displayed Site topology and the relevant Batch-selection scope.

An explicit empty selection is valid operator state and must survive polling/reconnect; it is not equivalent to an uninitialized selection.

## KPI semantics

The Engineering KPI row distinguishes topology from operator intent:

- `PPU SITES`: number of Sites exposed by the selected PPU;
- `SELECTED`: number of Sites checked for the next/current Batch;
- `RUNNING`, `PASS`, `FAIL`, `YIELD`, `CYCLE TIME`: Engineering execution projection for the current Batch context.

Do not label the number of checked Sites as `TOTAL IC`; Site membership and completed-IC accounting are different domains.

## Execution ownership

Engineering v2 must continue to use direct PPU Jobs:

```text
Engineering Programming UI
        |
        | Web REST v3
        v
selected Engineering PPU
        |
        +--> E / P / V / R Job per Site
```

It must **not** silently reuse Production server-side Batch ownership.

The browser may coordinate a selected-Site Engineering batch, but every actual operation remains a canonical PPU Job. Sites are concurrent; operations within one Site remain ordered.

## Engineering-only controls

Engineering deliberately keeps controls that Production may hide:

- explicit Site Retry Limit, default 3;
- direct per-Site E/P/V/R;
- Gateway reconnect control;
- detailed Engineering log evidence suitable for development and diagnosis.

Canonical `R` reads the complete Main Programmable Flash. Special memory regions remain separate explicit engineering features rather than operator-entered generic READ ranges.

## Target IC contract

The shared IC Selector is used as the Target IC picker.

Engineering differs from Production in one important way:

- selected Target IC: the browser sends `{vendor, identifier}` with the direct Engineering Job;
- Gateway resolves that pair against the canonical Device Catalog;
- resolution is fail-closed if the pair does not identify one canonical record;
- the resolved ICPN/identifier becomes `JobRequest.target`;
- the canonical target-device snapshot is also preserved in Job metadata;
- no selected Target IC: the existing PPU/Site configured target remains authoritative so raw Engineering diagnostics stay usable.

A catalog mapping is provenance, **not** proof of PPU, socket, voltage or physical-device validation.

## Programming Image boundary

The current executable normalizer is still only:

```text
Image Asset + binary (.bin) -> Normalized Image
```

The UI must not advertise Intel HEX, S-Record or ELF until their parsers/normalizers are implemented and verified.

Engineering retains the current 16 MiB source-Asset limit. Program/Verify continue to use the Engineering session/PPU Programming Asset cache and normalized-Image lease.

## Status semantics

The UI keeps execution domains distinct:

```text
IDLE / READY     available Site
RUNNING          active Job
PASS             successful operation/batch result
FAIL             credible DUT/Site failure after retry exhaustion
ERROR            infrastructure/control failure
CANCELLED        operator cancellation
STOPPED          policy stop
DISABLED         unavailable Site
```

`ERROR` must not be counted as manufacturing `FAIL` when calculating yield.

## Production boundary

Production has one canonical operator surface:

```text
Production / Factory Console (/fleet)
    -> server Batch runtime

/fleet/programming
    -> redirect to /fleet

Engineering / Programming
    -> direct Engineering PPU Jobs
```

There is no Production-local workspace navigation switch and no dedicated Production Single PPU Programming page. Selecting one PPU inside the Factory Console remains a topology choice inside Production, not a second programming workbench.

Production and Engineering may share visual primitives, the Device Catalog and server contracts where appropriate, but they must not be coupled by execution ownership or hidden cross-mode state.
