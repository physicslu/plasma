# PMode Programming UI v2

Status: implementation contract for the approved single-PPU Production programming workspace.

## Purpose

PMode Programming UI v2 is a Production Mode operator workflow for one selected PPU. It does not create a third Product Mode and it does not replace the existing multi-PPU Production Console in this phase.

The route is:

```text
/fleet/programming
```

The existing `/fleet` server-Batch Production Console remains available while this workflow is integrated and validated.

## Operator workflow

The approved workflow is:

```text
Facility
  -> PPU
    -> Site selection
      -> Target IC
        -> Programming Image
          -> E/P/V/R operation set
            -> Batch Policy
              -> Start Programming
                -> Live Site Status / Result
```

The screen hierarchy is intentionally split into:

```text
SYSTEM SETUP & TARGETING     PROGRAMMING JOB
Facility / PPU               Target IC
Target Sites                 Programming Image
                             Operations E/P/V/R
                             Batch Policy
                             Start / Abort

LIVE SITE STATUS
Recent Events
```

## Target IC

Target IC uses the shared Device Catalog search service introduced by IC Selector.

The compact picker consumes:

```text
GET /api/devices/search?q=<identifier>&limit=<N>
```

The browser does not parse the catalog CSV and does not implement a second search/ranking engine.

The selected value is a `DeviceSearchResult`. Operator display uses exact `icpn` when authoritative; otherwise it uses the catalog `identifier` without pretending that a broader identifier is an exact manufacturer part number.

## Programming Job draft domain

Before execution, the browser owns one immutable-intent draft:

```text
ProductionProgrammingJobDraft
├── facilityId
├── ppuId
├── siteIds[]
├── targetDevice
├── programmingImage
├── operations[]
├── repeatCount
└── stopPolicy
```

This draft is an operator-input model. Runtime execution remains server-owned Batch orchestration.

The adapter to the Web REST Batch contract is implemented by `buildServerBatchOptions()`.

## Programming Image support boundary

The current implemented Normalized Image path supports binary Image input. Therefore PMode v2 exposes `.bin` only:

```text
Programming Image: *.bin
```

The UI must not advertise `.hex` until an Intel HEX parser/normalizer is actually implemented and tested. File-name support and parser capability must remain truthful rather than being inferred from a mockup placeholder.

## Batch policy presentation

PMode deliberately does not expose all engineering-level policy knobs in the primary operator surface.

Visible controls are:

```text
Repeat:      [ 1 ]
Stop Policy: [ Never v ]
```

`Site Retry Limit` remains an internal Production policy default of `3` in this phase. Engineering Mode may continue to expose the detailed retry field.

Stop Policy maps to the canonical server field:

```text
Never          -> failed_site_stop_threshold = null
N Fail         -> failed_site_stop_threshold = N
```

The UI width is content-driven rather than stretched:

```text
Repeat input        ~72 px
Stop Policy select  ~118 px
```

The Stop Policy control must not grow with the available row width.

## Site operation controls

Each Site row exposes E/P/V/R directly:

```text
SITE-01  ...  [E] [P] [V] [R]
SITE-02  ...  [E] [P] [V] [R]
```

There is no gear/more-menu indirection for these four operations.

A direct Site operation still uses the canonical server Batch path with a one-Site target set. The browser must not create a second Job scheduler or retry loop.

## Status and color semantics

PMode remains low-color by default:

```text
IDLE / DISABLED   neutral gray
RUNNING           blue
PASS              green
FAIL / ERROR      red
ABORT              red action
Primary Start      blue action
```

Green is not used merely because a Site is reachable or idle.

## Manufacturing KPI projection

While a server Batch exists, PASS/FAIL/Yield continue to follow server Batch truth:

```text
PASS     = sum(Site.completed_rounds)
FAIL     = sum(Site.final_failures)
Total IC = PASS + FAIL
Yield    = PASS / Total IC
```

Before the first Batch snapshot exists, the v2 mockup keeps the selected Site count visible as the initial Total IC planning context. This is presentation fallback only; once execution begins, the server snapshot is authoritative.

## Target IC REST / Batch provenance contract

The Batch create request may carry a compact Device Catalog identity:

```json
{
  "target_device": {
    "vendor": "...",
    "identifier": "..."
  }
}
```

The Gateway does **not** trust browser-supplied family, ICPN, validation state, or backend evidence. It resolves `vendor + identifier` against the server-owned canonical Device Catalog. If the identity cannot resolve unambiguously, Batch creation fails closed.

The immutable server Batch snapshot then carries canonical provenance:

```text
target_device
├── vendor
├── family
├── identifier
├── identifier_kind
└── icpn | null
```

This snapshot is bound to the Batch together with targets, operations, execution policy, and Programming Asset provenance. The same canonical Target IC snapshot is also inserted into underlying Job metadata so PPU-local execution evidence can retain the selected device identity.

Existing Batch clients remain compatible because `target_device` is optional at the REST boundary. PMode Programming v2 requires a Target IC before execution and therefore always supplies it.

This is device **identity provenance**, not proof that the selected PPU/Socket/Programming Configuration has been physically verified for that IC. Physical support evidence remains a separate contract.

## Non-goals of this phase

- no replacement of the existing multi-PPU `/fleet` workflow;
- no new browser-owned scheduler;
- no durable factory ledger;
- no Target IC physical verification claim;
- no PPU/Socket support inference from OpenOCD mapping;
- no real hardware programming validation;
- no change to Protocol v3.3.
