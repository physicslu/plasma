# Engineering Programming UI v2

## Decision

`Engineering Mode -> Programming` is the primary single-PPU engineering workbench.

Production `/fleet/programming` remains available, but it is a separate Production workspace and is not the implementation authority for Engineering execution.

The Engineering v2 UI adopts the approved operator layout:

```text
SINGLE PPU PROGRAMMING

KPI
Sites | Total IC | Running | Pass | Fail | Yield | Cycle Time

+----------------------------+--------------------------------+
| SYSTEM SETUP & TARGETING   | PROGRAMMING JOB                |
| Facility                   | Target IC                      |
| PPU                        | Programming Image              |
| Target Sites               | E / P / V / R                  |
|                            | Repeat / Retry / Stop Policy   |
|                            | START / ABORT                  |
+----------------------------+--------------------------------+
                              | LIVE PROGRESS MONITOR          |
                              +--------------------------------+

LIVE SITE STATUS
Recent Events
```

The outer Engineering Mode navigation remains unchanged.

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
- READ offset and length;
- direct per-Site E/P/V/R;
- Gateway reconnect control;
- detailed Recent Events suitable for development and diagnosis.

This is not a third Product Mode. ProductMode remains only `production` and `engineering`.

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

Production Single PPU Programming remains intact:

```text
Production / Single PPU Programming
    -> server Batch runtime

Engineering / Programming
    -> direct Engineering PPU Jobs
```

The two workspaces may share visual primitives and the IC Selector, but they must not be coupled by execution ownership or hidden cross-mode state.
