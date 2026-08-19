# Plasma Web Product Modes

This document defines the product-level Web mode model introduced with the Factory Production Console work.

## 1. Mode and Scope are independent dimensions

Plasma must not equate a work mode with a hardware scope.

```text
                    Scope
              Single PPU     Fleet
Mode
Production         yes         yes
Engineering        yes         yes
```

Canonical terms:

- **Production Mode / 量產模式**: factory-operator workflow optimized for fast recognition, low interaction cost, and obvious abnormal-state handling.
- **Engineering Mode / 工程模式**: extensible engineering workspace for development, diagnostics, programming algorithms, low-level inspection, and maintenance.
- **Single PPU** and **Fleet** describe the equipment scope, not the user mode.

The two modes share the same Plasma backend/domain model. Plasma must not fork into a Production backend and an Engineering backend.

## 2. Production Mode principles

Production Mode is intended for factory operators and line leaders. The primary screen must keep all relevant PPUs and Sites visible together instead of forcing the operator to drill into one PPU at a time.

The current Fleet Production Console groups dynamic Site topology by PPU and therefore does not assume eight Sites per PPU. Two-, four-, eight-, and future N-Site PPUs use the same presentation model.

Per-PPU selection provides:

- Select All / 全選: selects only enabled Sites on a currently reachable/current PPU;
- Deselect All / 全部取消: clears selection for that PPU;
- individual Site checkboxes remain available.

The top selection count is global across the visible Fleet.

### 2.1 Status-light semantics

Status colors are operational semantics, not decoration:

```text
READY      cyan / blue
RUNNING    amber / yellow
PASS       green
FAIL       red
ERROR      red, but explicitly labeled ERROR rather than programming FAIL
DISABLED   gray
OFFLINE    dark gray
```

Green is reserved for an actual successful programming job. A reachable/online PPU must not make an untested Site appear green.

PPU connectivity state, Site operational error, and programming-job result are different domains. A PPU transport failure or Site runtime error must not be presented as an IC programming FAIL.

### 2.2 Source of truth and latched result presentation

Production operators must be able to see a completed PASS or FAIL after active execution has returned to idle. The Web UI therefore treats Site execution state and latest programming result separately.

The PPU v3.2 STATUS contract now exposes a browser-safe `latest_job` summary for each Site. It carries only operational fields such as job ID, operation, state, stage, progress and timestamps; firmware bytes, metadata, output files and raw result payloads are not included.

Production presentation derives:

```text
latest_job.state = queued/running       -> RUNNING
latest_job.state = success              -> PASS
latest_job.state = failed/timeout/aborted -> FAIL
no latest job + idle Site               -> READY
```

E/P/V/R comes from `latest_job.operation`; it must never be guessed by substring matching `site.state`.

A terminal `latest_job` remains visible after the Site returns to idle, which supplies the initial latch semantics. The operator's **Clear Result** action only suppresses that exact terminal job result in the local browser view; it does not mutate the PPU or erase the job. A new job has a different signature and becomes visible normally.

The current latest-job registry is runtime memory, not a durable factory production ledger. Server restart durability, audit retention and production traceability remain separate requirements.

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

Engineering Mode starts as an extensible information-architecture shell rather than a second copy of the Production Console.

Initial extension slots are:

```text
Overview
PPU / Sites
Programming
Diagnostics
Logs
Tools
Settings
```

Future engineering capability can include IC/device configuration, programming algorithms, timing/voltage controls, memory maps, protocol traces, FPGA/PL diagnostics, register inspection, performance profiling, Read/Compare/Dump tools, and failure analysis.

Low-level engineering controls must not leak into Production Mode merely because they exist in the shared backend.

## 5. Internationalization

The first localization foundation supports:

```text
zh-TW
en-US
```

UI components use translation keys instead of accumulating mixed hard-coded Chinese and English labels. Locale choice is a browser preference.

Canonical engineering vocabulary remains stable where translation would reduce cross-team clarity, including PPU, SITE, E/P/V/R, PASS, FAIL, READY, Job ID, SPI, I2C, SWD, and CRC.

## 6. Factory Log contract and current boundary

Factory logging is a first-class Production requirement. The Production Console keeps a persistent Factory Log Console visible and provides filters, auto-scroll, and a full-screen log view.

The current read-only Fleet path can now expose safe `latest_job` summaries, so the console can truthfully show observed job identity, operation, state, stage and progress transitions together with Manager/PPU observation transitions. It must not invent events that the PPU did not report.

This is still **not** the complete factory programming log. The authoritative detailed event source already exists locally on each PPU: `JobEventLogger` writes structured JSONL under the Plasma Server `log_root`, including job, Site, stage/progress, completion, failure, cancellation, timeout and related events.

The intended next logging transport is:

```text
PPU JobEventLogger JSONL
    -> read-only PPU Gateway event API (bounded, cursor-based)
    -> authenticated/sanitized management aggregation path
    -> Factory Log Console
    -> retention/search/export layer
```

Required properties:

- no arbitrary filesystem path supplied by a browser;
- no raw PPU endpoint exposed to the browser;
- stable event/cursor identity and bounded page size;
- canonical `ppu_id`, `site_id`, `job_id`, operation, event, severity and timestamp fields;
- localized display text derived from structured event data rather than parsing translated strings;
- explicit retention/rotation policy;
- PPU-local logging continues even if Manager or the management host is unavailable.

Because factory logs are operational evidence, the dedicated log-transport/persistence work should precede treating the Fleet UI as a complete production traceability system.

## 7. Current security boundary

The Factory Production Console may select Sites and operations in the UI, but cross-PPU write execution remains disabled until an authenticated/authorized management control path is separately designed and approved.

The current Manager remains read-only and outside the PPU-local execution path.

```text
Local execution:
Browser / local PPU Console
    -> PPU Gateway
    -> Plasma Server
    -> Site

Fleet observation:
Fleet UI
    -> same-origin Management BFF
    -> read-only Manager
    -> PPU Gateways
```

Manager or Fleet failure must never make a standalone PPU unable to continue local programming.
