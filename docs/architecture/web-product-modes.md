# Plasma Web Product Modes

This document defines the product-level Web mode model for Plasma.

## 1. Canonical product model

The product-facing model has one primary discriminator:

```text
ProductMode
  ├─ production
  └─ engineering
```

Canonical terms:

- **Production Mode / 量產模式**: factory-operator workflow optimized for fast recognition, low interaction cost, and obvious abnormal-state handling.
- **Engineering Mode / 工程模式**: extensible engineering workspace for development, diagnostics, programming algorithms, low-level inspection, and maintenance.

`Fleet`, `Single PPU`, `Manager`, and multi-PPU aggregation are **not ProductMode values**. They describe implementation topology, aggregation services, or engineering targets.

The Web product model must therefore not expose Fleet as a peer mode beside Production Mode. Production Mode may operate one or many PPUs without changing its ProductMode value.

The current implementation route for the multi-PPU Production Console remains `/fleet` for compatibility, while the canonical product state is `ProductMode = production`. Internal Manager/BFF names such as `fleet` may remain where they specifically describe multi-PPU aggregation contracts; they are infrastructure vocabulary, not user-facing product taxonomy.

Both product modes share the same Plasma backend/domain model. Plasma must not fork into separate Production and Engineering backends.

## 2. Production Mode principles

Production Mode is intended for factory operators and line leaders. The operator first defines the equipment scope for the current production activity and then operates only that committed scope.

The canonical interaction is:

```text
Facility selector
    -> PPU multi-select within that Facility
        -> SET
            -> active Production Set
                -> selected PPU / Site status
                -> batch operations
```

A Production Set belongs to one Facility. The current prototype does not create a cross-Facility Production Set. This is an intentional control boundary, not a network limitation.

After `SET`, the main execution area shows only PPUs committed to that Production Set. Each PPU retains its dynamic Site topology; Plasma therefore does not assume eight Sites per PPU. Two-, four-, six-, eight-, and future N-Site PPUs use the same presentation model.

All enabled Sites on a selected PPU are selected by default when the Production Set is created. Per-PPU Select All / Clear Sites and individual Site checkboxes remain available before execution.

### 2.1 Multi-PPU execution semantics

For the current Mock Production prototype, all selected Site sequences are launched concurrently across all selected PPUs. A Site executes its selected operations sequentially in canonical order:

```text
across PPUs / Sites: concurrent
within one Site:      E -> P -> V -> R in selected canonical order
```

For example:

```text
Production Set
├── PPU-01
│   ├── SITE 1  E -> P -> V
│   └── SITE 2  E -> P -> V
├── PPU-02
│   ├── SITE 1  E -> P -> V
│   └── SITE 2  E -> P -> V
└── PPU-03
    └── ...
```

The PPU branches do not wait for each other. One PPU failure or cancellation must not serialize, stop, or implicitly cancel independent PPUs.

Per-PPU cancellation affects that PPU only. Batch cancellation affects all currently active Jobs in the Production Set. Cancellation before a Job is submitted remains cancellation rather than a programming failure.

The current implementation is a **Mock-only execution prototype**. It reuses the Python-owned Mock PPU Provider so selected targets still execute through real in-process `PlasmaServer`, `SiteManager` / `SiteWorker`, Plasma Protocol v3.3 / `PLASMA33`, and `MockInterface`. It is not a browser animation and it is not evidence of real PPU, Socket, or IC behavior.

### 2.2 Status-light semantics

Status colors are operational semantics, not decoration:

```text
READY      cyan / blue
RUNNING    amber / yellow
PASS       green
FAIL       red
ERROR      red, but explicitly labeled ERROR rather than programming FAIL
DISABLED   gray
OFFLINE    dark gray
CANCELLED  neutral gray
```

Green is reserved for an actual successful programming Job. A reachable/online PPU must not make an untested Site appear green.

PPU connectivity state, Site operational error, cancellation, and programming-job result are different domains. A PPU transport failure or Site runtime error must not be presented as an IC programming FAIL.

### 2.3 Source of truth and result presentation

Production operators must be able to see a completed PASS or FAIL after active execution has returned to idle. The Web UI therefore treats Site execution state and programming result separately.

The PPU STATUS contract exposes browser-safe Job summaries containing operational fields such as job ID, operation, state, stage, progress and timestamps; Programming Asset bytes, metadata, output files and raw result payloads are not part of the fleet observation contract.

Production presentation derives actual result/operation semantics from Job truth rather than guessing from strings.

The current Production Mock prototype also maintains browser execution state while it drives the selected virtual PPUs. This prototype state is not a durable factory production ledger. Server restart durability, audit retention and production traceability remain separate requirements.

## 3. Canonical operation display codes

Plasma UI uses the following stable display codes:

| Code | Canonical operation | zh-TW | en-US |
| --- | --- | --- | --- |
| E | ERASE | 擦除 | Erase |
| P | PROGRAM | 燒錄 | Program |
| V | VERIFY | 驗證 | Verify |
| R | READ | 讀取 | Read |

The backend/domain enum remains the full canonical name (`ERASE`, `PROGRAM`, `VERIFY`, `READ`). E/P/V/R are presentation codes, not replacement protocol values.

`PROGRAM` means write only. It must not silently imply Erase or Verify. A complete sequence is composed explicitly, for example `E -> P -> V`.

## 4. Engineering Mode extension boundary

Engineering Mode remains an extensible engineering workspace rather than a second copy of the Production Console.

Extension areas are:

```text
Overview
PPU / Sites
Programming
Diagnostics
Logs
Tools
Settings
```

`Programming` is the first implemented engineering work area. It provides a single-target programming workbench based on canonical:

```text
Facility -> PPU -> Site
```

The browser does not own the available Facility/PPU topology. It consumes the Python-side `EngineeringPPUProvider` contract, which owns target discovery/status and E/P/V/R execution. The current implementation supplies a server-side Mock provider; a future real-PPU provider is intended to preserve the same Facility/PPU/Site and Job contracts.

```text
Engineering UI
    -> Engineering PPU Control API
    -> EngineeringPPUProvider
         -> MockEngineeringPPUProvider  (current)
         -> RealPPUProvider             (future)
```

The current server-side Mock provider creates three Mock Facilities with four PPUs per Facility. Their Site counts are 2 / 4 / 6 / 8, for 12 PPUs and 60 Sites total. These are Python-owned targets, not React fixtures. Each Mock PPU is backed by a real in-process `PlasmaServer`, `SiteManager` / `SiteWorker`, Protocol v3.3 path and `MockInterface`.

Engineering Programming supports per-Site and batch E/P/V/R, Programming Image selection, Read ranges, Job progress/status, cancellation, Read download and engineering logs. Target switching is blocked while a selected PPU has an active/submitting Job so a running target cannot be silently orphaned by the UI.

The current Production Mock prototype deliberately reuses this same Python Mock execution provider as a simulation source. That reuse does not make `EngineeringPPUProvider` the final Production orchestration architecture; it is a temporary verification boundary for multi-PPU behavior. A future authenticated Production control provider/orchestrator must preserve standalone PPU autonomy and must not turn Manager into a mandatory PPU execution dependency.

Future engineering capability can include IC/device configuration, programming algorithms, timing/voltage controls, memory maps, protocol traces, FPGA/PL diagnostics, register inspection, performance profiling, Read/Compare/Dump tools, and failure analysis.

Low-level engineering controls must not leak into Production Mode merely because they exist in the shared backend.

A single-PPU programming workbench is an engineering/maintenance capability, not a third product mode.

## 5. Internationalization

The first localization foundation supports:

```text
zh-TW
en-US
```

UI components use localized copy instead of accumulating a second independent user-facing vocabulary. Locale choice is a browser preference.

Language switching is required to update React UI state immediately. Browser storage is persistence only; the UI must not wait for storage-event propagation before changing language. Storage events are used only to synchronize the preference across tabs/windows.

Canonical engineering vocabulary remains stable where translation would reduce cross-team clarity, including Facility, PPU, SITE, E/P/V/R, PASS, FAIL, READY, Job ID, SPI, I2C, SWD, and CRC.

## 6. Factory Log contract and current boundary

Factory logging is a first-class Production requirement.

The Manager read-only aggregation path can expose safe latest-Job summaries, so a production console can truthfully show observed job identity, operation, state, stage and progress transitions together with Manager/PPU observation transitions. It must not invent events that the PPU did not report.

The Production Mock prototype additionally shows a bounded browser log for the Mock Jobs it actually submits and observes. This is execution diagnostics for the prototype, not the complete factory programming ledger.

The authoritative detailed event source already exists locally on each PPU: `JobEventLogger` writes structured JSONL under the Plasma Server `log_root`, including job, Site, stage/progress, completion, failure, cancellation, timeout and related events.

The intended production logging transport remains:

```text
PPU JobEventLogger JSONL
    -> read-only PPU Gateway event API (bounded, cursor-based)
    -> authenticated/sanitized management aggregation path
    -> Factory Log Console
    -> retention/search/export layer
```

Required properties:

- no arbitrary filesystem path supplied by a browser;
- no raw PPU endpoint exposed to an untrusted browser contract;
- stable event/cursor identity and bounded page size;
- canonical `ppu_id`, `site_id`, `job_id`, operation, event, severity and timestamp fields;
- localized display text derived from structured event data rather than parsing translated strings;
- explicit retention/rotation policy;
- PPU-local logging continues even if Manager or the management host is unavailable.

Because factory logs are operational evidence, the dedicated log-transport/persistence work should precede treating Production Mode as a complete production traceability system.

## 7. Current security and deployment boundary

### 7.1 Manager remains optional and read-only

Plasma Manager remains outside the PPU-local execution path. Its current contract is discovery-by-explicit-registry plus read-only observation.

```text
Local execution:
Browser / local PPU Console
    -> PPU Gateway
    -> Plasma Server
    -> Site

Production observation:
Production Mode / management UI
    -> Management BFF
    -> read-only Manager
    -> PPU Gateways
```

The Production Mock prototype is a separate simulation path:

```text
Production Mock UI
    -> Plasma Web REST Gateway
    -> Python Mock PPU Provider
    -> selected virtual PlasmaServers
    -> MockInterface
```

This path exists only to prove Facility/PPU selection, cross-PPU concurrency, Site sequencing, status aggregation, and cancellation semantics. It does not grant Manager write authority and it does not authorize remote write access to real PPUs.

### 7.2 Initial factory-network assumption

The first real multi-PPU deployment may assume a controlled factory LAN and an explicit PPU registry. Automatic subnet discovery is not required for this prototype.

A Manager registry entry identifies the root of one autonomous PPU Gateway. The current development/runtime convention remains an operator-local config outside the Git worktree, such as:

```text
$XDG_CONFIG_HOME/plasma/manager.yaml
```

For the future productized system-service deployment, the target canonical locations are:

```text
/etc/plasma/manager.yaml                 # configuration
/var/lib/plasma/manager/                 # runtime state
/var/lib/plasma/manager/observations.sqlite3
```

The `/etc/plasma/manager.yaml` path is a product deployment decision for future service packaging; current code still accepts an explicit `--config` path and does not require this filesystem location yet.

Example explicit registry:

```yaml
ppus:
  - alias: ppu-01
    endpoint: http://192.168.10.101:18080
  - alias: ppu-02
    endpoint: http://192.168.10.102:18080
  - alias: ppu-03
    endpoint: http://192.168.10.103:18080
```

Manager or management aggregation failure must never make a standalone PPU unable to continue local programming.
