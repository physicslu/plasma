# Engineering Programming Workspace

## Purpose

`Engineering Mode -> Programming` is the canonical single-PPU engineering programming workspace.

It restores the existing PPU-local Erase / Program / Verify / Read console under Engineering Mode without creating a third ProductMode and without turning Plasma Manager into a write proxy.

## Target sources

The workspace separates target selection from execution authority.

### Connected Local PPU

```text
Browser / Engineering Programming
    -> PPU-local Plasma Web REST Gateway
    -> Plasma Server
    -> SiteManager / SiteWorker
    -> Programming Site
```

This path reuses the existing single-PPU Console and therefore retains its current firmware selection, Read range, per-Site E/P/V/R, batch operation, cancellation, progress, download and live-log behavior.

The PPU identity and Site topology come from canonical PPU STATUS. The Web UI must not hard-code an eight-Site PPU.

### Simulation Catalog

The initial engineering topology fixture contains three Facilities. Each Facility contains four simulated PPUs with heterogeneous Site counts:

```text
Facility 01 / 02 / 03
├── PPU 01 -> 2 Sites
├── PPU 02 -> 4 Sites
├── PPU 03 -> 6 Sites
└── PPU 04 -> 8 Sites
```

This produces 12 simulated PPUs and 60 simulated Sites in total.

Canonical identity remains one-based and local to a PPU:

```text
(facility_id, ppu_id, site_id)
SITE 1 .. SITE N
```

There is no `SITE 0` and Sites are not flattened into a global integer namespace.

The Simulation Catalog is UI/topology validation only. Its E/P/V/R controls are deliberately disabled and it must not dispatch jobs to the connected Local PPU.

## Manager boundary

The current Plasma Manager remains read-only. Selecting a simulated Facility/PPU must never cause a job to be silently routed to the currently connected local Gateway.

Future authenticated remote programming can replace the target adapter behind this workspace, but it requires a separately approved management write/control architecture. The Engineering UI target model must not be treated as proof that remote execution authority already exists.

## Validation expectations

Browser tests cover at least:

- Engineering -> Programming navigation;
- three Facility choices;
- four PPU choices per Facility;
- dynamic 2 / 4 / 6 / 8 Site rendering;
- no SITE 0 or Site N+1;
- simulated E/P/V/R controls cannot execute hardware jobs;
- Connected Local PPU renders the existing single-PPU E/P/V/R console from canonical STATUS.

Existing single-PPU Mock CD Browser Runtime Acceptance remains authoritative for actual browser -> Gateway -> Server -> MockInterface job execution behavior. Simulation Catalog tests do not replace that acceptance layer.
