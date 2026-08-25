# PMode Factory Console v2

## Decision

Production Mode owns one Factory Console at `/fleet`. The console uses the same Plasma operator-panel visual language as Engineering Programming while preserving Production-specific topology and execution semantics.

The browser remains a client of the server-owned Batch runtime. This redesign does not move Batch scheduling, retry, cancellation, or terminal truth into React.

## Responsibility model

Production uses three authoritative responsibility domains:

```text
Equipment Scope         -> Production Set
Operator's Batch Intent -> Batch Selection
Execution Truth         -> Server Batch Runtime
```

`Draft Selection` is only transient browser edit state used to prepare a
Production Set. It is not an authoritative production or execution domain.

The browser must not use one checkbox state for different meanings:

```text
Draft Selection
    -> editable Facility / PPU / Site tree
    -> SET PRODUCTION SITES

Production Set
    -> committed equipment scope for the production activity
    -> all Sites remain visible in LIVE SITE STATUS

Batch Selection
    -> operator selects a subset of the Production Set

Server Batch Runtime
    -> START submits a Batch Selection snapshot
    -> accepted Server Batch snapshot owns active membership and state
    -> immutable execution truth for the active Batch
```

The durable Site identity remains `(facility_id, ppu_id, site_id)`.

The Batch Selection is always constrained to the committed Production Set. A Site outside the Production Set cannot be inserted into a Batch by browser state. Server Batch snapshots may reconstruct missing browser context after reconnection, but normal runtime updates must not rewrite the operator's Batch Selection or the committed Production Set.

While a Batch is active, LIVE SITE STATUS displays the membership returned by Server Batch Runtime. After the Batch reaches a terminal state, its selection controls return to the retained operator Batch Selection for preparation of the next Batch. The section header exposes the selected-versus-production Site count without conflating Site membership with manufacturing IC quantities.

## Production Site Selection

The Production Site Selection surface keeps the hierarchical tree:

```text
Facility
  -> PPU
      -> Site
```

Facility and PPU checkboxes support all/none/indeterminate semantics. The tree can be collapsed or hidden after the Production Set is committed; hiding the tree changes presentation only and must not delete the committed Production Set.

LIVE SITE STATUS repeats the same Facility / PPU / Site selection hierarchy for
the next Batch. Facility and PPU master checkboxes select or clear all
Production Set Sites below them, expose an indeterminate state for partial
membership, and become immutable after START.

## LIVE SITE STATUS

LIVE SITE STATUS remains LED-first rather than table-first because Production operators need to scan many Sites at once.

Every Site in the Production Set remains visible even when excluded from the next Batch. PPU and Site checkboxes in this surface control the **next Batch membership**, not the Production Set.

Each Facility contains compact, intrinsically sized PPU cards laid out in topology order and wrapped responsively. A two-Site PPU therefore does not reserve an entire Facility-width row. Site card and LED dimensions are chosen once from the complete Production Set density and remain identical across every PPU.

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

An active `RUNNING` LED pulses at 1 Hz. Its Site card exposes `IC current/total` so an operator can distinguish an in-progress IC from a completed or failed manufacturing result.

## Immutable Batch membership and cancellation

Before START, the operator may change PPU and Site Batch Selection freely within the Production Set.

`START PROGRAMMING` snapshots the selected membership exactly once and submits that target set to the server. After acceptance, membership, lifecycle state, counters, cancellation state, and terminal result come only from the Server Batch Runtime snapshot.

While Batch state is `QUEUED`, `RUNNING`, or `STOPPING`:

- PPU and Site Batch Selection checkboxes are locked;
- Production Mode exposes no per-PPU cancel;
- Production Mode exposes no per-Site cancel;
- the only operator stop action is whole-Batch `ABORT`.

The Factory Console uses the canonical whole-Batch cancellation endpoint. Existing lower-level or compatibility APIs are not evidence that partial cancellation is a supported Production operator workflow.

An ABORT never rewrites already established execution facts. Completed successful or failed rounds remain recorded by server Batch truth; unfinished work may become `CANCELLED` according to the runtime state machine.

`CANCELLED`, `ERROR`, and `STOPPED` are not manufacturing FAIL results and must not enter Yield accounting.

## Manufacturing KPI contract

The top KPI strip is named **BATCH SUMMARY** and separates equipment scope, planned IC quantity, and adjudicated IC results:

```text
SITES       accepted current Batch Site count, or current checked Batch Selection before START
TOTAL IC    current Mock Batch planned quantity = accepted Batch Sites * repeat_count
PROCESSED IC  PASS + FAIL, the IC count with an adjudicated manufacturing result
PASS        sum(Site.completed_rounds), counted as successful ICs
FAIL        sum(Site.final_failures), counted as retry-exhausted ICs
YIELD       PASS / (PASS + FAIL)
BATCH TIME  observed Batch elapsed time, formatted HH:MM:SS
```

`TOTAL IC` is the planned quantity for the displayed Batch. Before START, its preview uses the current Batch Selection and valid Mock repeat count. After START, its value is derived from the authoritative accepted server snapshot and does not change when the operator later prepares another selection.

For Yield, only credible completed manufacturing outcomes are counted:

```text
Completed IC = PASS + FAIL
Yield        = PASS / Completed IC
```

`ERROR`, `STOPPED`, and `CANCELLED` are excluded. Retry attempts are not additional ICs. On an uninterrupted completed Batch, `PASS + FAIL` equals `TOTAL IC`; cancellation, infrastructure error, or early stop may leave planned ICs unfinished.

Before the first PASS or FAIL, Yield is mathematically undefined and the KPI
displays `—`; neither `0%` nor `100%` is a credible manufacturing result.

The current repeated-round quantity mechanism is Mock-only. Future real production must use an explicit operator/MES Planned IC Quantity and physical next-device handoff rather than assume that rerunning operations on one loaded IC produces another IC.

Batch Time uses server `started_at` and `finished_at`, updates once per second during execution, starts at `00:00:00`, and freezes at the authoritative terminal duration.

## Programming Job

The Production Programming Job panel contains:

- Target IC, resolved through the shared Device Catalog selector;
- one Programming Image (`.bin`, current Production limit 4 MiB);
- explicit E/P/V/R operation selection;
- Repeat, Retry, and Stop Policy;
- `START PROGRAMMING | BATCH STATUS | ABORT`.

Target IC is optional when the active Provider is Mock and required for real/non-Mock Production execution. When supplied, the browser sends the compact canonical identity `{vendor, identifier}`; the server remains responsible for canonical catalog resolution and provenance.

## Batch observation and global mode lock

The Production mode-switch guard is fail-closed while a non-terminal Batch lease remains in browser session storage. Temporary REST polling failures transition the operator status to `RECONNECTING` and retry observation with bounded backoff instead of abandoning the server-owned Batch.

Every path that receives a terminal Batch snapshot, including ordinary polling, reconnect/restore, immediately terminal creation, and ABORT against an already-finished Batch, performs the same terminal cleanup: clear the stored Batch lease, release execution activity, notify the global navigation store, and stop the old observation generation. `SUCCESS`, `PARTIAL`, `ERROR`, and `CANCELLED` must all restore Production/Engineering mode switching.

The communication policy is configured under `EMode -> Settings -> Gateway`,
persisted by the Gateway, and frozen into each server Batch snapshot as
`gateway_settings`. Defaults are a 10-second PPU request timeout and three
retries with 1/2/4-second backoff. A retrying Site exposes `RECONNECTING` and
its current retry number without being counted as an IC failure.

Infrastructure faults are isolated to the affected PPU. Its current Batch Jobs
receive scoped cancellation and unfinished sibling Sites stop, while healthy
PPUs continue independently. A mixed successful/error outcome terminates as
`PARTIAL`; if no unaffected PPU completes, the Batch terminates as `ERROR`.
Only an explicit operator ABORT cancels the complete Batch. Failure to observe
the Gateway itself remains a reconnecting observation state and cannot be used
to infer Site failure or Job termination.

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

The PMode Programming Job panel is independently collapsible. Its collapsed
form hides Target IC, Programming Image, Operations, and Batch Policy while
keeping the complete START PROGRAMMING / BATCH STATUS / ABORT action row
visible. Collapsing a panel changes presentation only and never mutates Batch
selection, policy, execution, or server-owned runtime state.
