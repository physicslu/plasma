# PMode Factory Console v2

## Decision

Production Mode owns one Factory Console at `/fleet`. The console uses the same Plasma operator-panel visual language as Engineering Programming while preserving Production-specific topology and execution semantics.

The browser remains a client of the server-owned Batch runtime. This redesign does not move Batch scheduling, retry, cancellation, or terminal truth into React.

## Three distinct selection scopes

Production must not use one checkbox state for three different meanings.

```text
Draft Selection
    -> editable Facility / PPU / Site tree
    -> SET PRODUCTION SITES

Production Set
    -> committed equipment scope for the production activity
    -> all Sites remain visible in LIVE SITE STATUS

Batch Selection
    -> operator selects a subset of the Production Set
    -> START snapshots this membership once
    -> immutable for the active Batch
```

The durable Site identity remains `(facility_id, ppu_id, site_id)`.

The Batch Selection is always constrained to the committed Production Set. A Site outside the Production Set cannot be inserted into a Batch by browser state.

## Production Site Selection

The Production Site Selection surface keeps the hierarchical tree:

```text
Facility
  -> PPU
      -> Site
```

Facility and PPU checkboxes support all/none/indeterminate semantics. The tree can be collapsed or hidden after the Production Set is committed; hiding the tree changes presentation only and must not delete the committed Production Set.

## LIVE SITE STATUS

LIVE SITE STATUS remains LED-first rather than table-first because Production operators need to scan many Sites at once.

Every Site in the Production Set remains visible even when excluded from the next Batch. PPU and Site checkboxes in this surface control the **next Batch membership**, not the Production Set.

A PPU checkbox is the master for the currently committed Sites of that PPU:

```text
checked       all eligible Sites selected
indeterminate some eligible Sites selected
unchecked     no Sites selected
```

The LED continues to represent Site runtime/result state even when that Site is excluded from the next Batch. Selection and runtime result are separate domains.

Canonical LED semantics:

```text
READY       cyan / blue
RUNNING     amber / yellow
PASS        green
FAIL        red
ERROR       dark red, explicitly ERROR
STOPPED     orange
CANCELLED   neutral gray
DISABLED    gray
```

READY must not be presented as PASS green.

## Immutable Batch membership and cancellation

Before START, the operator may change PPU and Site Batch Selection freely within the Production Set.

`START PROGRAMMING` snapshots the selected membership exactly once and submits that immutable target set to the server Batch runtime.

While Batch state is `QUEUED`, `RUNNING`, or `STOPPING`:

- PPU and Site Batch Selection checkboxes are locked;
- Production Mode exposes no per-PPU cancel;
- Production Mode exposes no per-Site cancel;
- the only operator stop action is whole-Batch `ABORT`.

The Factory Console uses the canonical whole-Batch cancellation endpoint. Existing lower-level or compatibility APIs are not evidence that partial cancellation is a supported Production operator workflow.

An ABORT never rewrites already established execution facts. Completed successful or failed rounds remain recorded by server Batch truth; unfinished work may become `CANCELLED` according to the runtime state machine.

`CANCELLED`, `ERROR`, and `STOPPED` are not manufacturing FAIL results and must not enter Yield accounting.

## Manufacturing KPI contract

The top KPI strip separates equipment scope from Batch intent:

```text
PRODUCTION SITES  committed Production Set Site count
SELECTED          next/current Batch membership count
RUNNING           currently running Site count
PASS              sum(Site.completed_rounds)
FAIL              sum(Site.final_failures)
YIELD             PASS / (PASS + FAIL)
CYCLE TIME        observed Batch elapsed time
```

For Yield, only credible completed manufacturing outcomes are counted:

```text
Total IC = PASS + FAIL
Yield    = PASS / Total IC
```

`ERROR`, `STOPPED`, and `CANCELLED` are excluded.

## Programming Job

The Production Programming Job panel contains:

- Target IC, resolved through the shared Device Catalog selector;
- one Programming Image (`.bin`, current Production limit 4 MiB);
- explicit E/P/V/R operation selection;
- Repeat, Retry, and Stop Policy;
- `START PROGRAMMING | BATCH STATUS | ABORT`.

Target IC is required for a Production Batch. The browser sends the compact canonical identity `{vendor, identifier}`; the server remains responsible for canonical catalog resolution and provenance.

Program continues to mean write only. Verify remains an explicit operation.

## Shared UI boundary

Shared presentation primitives belong to a neutral operator UI layer, not to Production or Engineering ownership:

```text
Production Factory Console
            |
            v
      Shared Operator UI
      - Panel shell
      - KPI strip
      - section header
            ^
            |
Engineering Programming
```

Mode-specific execution models remain separate:

```text
Production -> server-owned Batch runtime, multi-PPU
Engineering -> direct Engineering PPU Jobs, single PPU
```

Visual consistency must not collapse these two execution domains into one scheduler.
