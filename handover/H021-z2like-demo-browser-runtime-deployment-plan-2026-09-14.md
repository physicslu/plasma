# H021 — z2like-demo Browser Runtime Deployment Management Path

**Date:** 2026-09-14  
**Updated:** 2026-09-15  
**Project:** Plasma  
**Scope:** Render Control Station -> controlled QEMU Bootstrap management path  
**Status:** Browser Runtime live path qualified on SWPC/QEMU; active-Site-Job negative follow-up still pending corrected live evidence

## Implemented path

PR #560 merged the controlled Browser Runtime Deployment path:

```text
Browser
  -> Render Console/BFF
  -> Bootstrap-capable Render Manager
  -> ppu-managed-lab.open4th.com/__plasma/bootstrap/...
  -> Cloudflare Access / Tunnel
  -> SWPC 127.0.0.1:18082
  -> fixed Bootstrap route/method allowlist
  -> QEMU 172.30.77.2:18081
```

The qualified Programming path remains independently mapped to QEMU `:18080`.

## Security model

- Browser never receives the direct QEMU Bootstrap endpoint.
- Browser never receives the persisted device Bootstrap bearer token.
- Cloudflare Access identity remains Manager-owned and scoped to the configured
  `ppu-managed-lab` HTTPS origin.
- Pairing is an authentication operation, not a Runtime mutation. It may be
  performed while the PPU is commissioned, but the supplied token must first be
  proved against the registered Bootstrap device before Manager persists it.
- The current proof is a deliberately invalid zero-sized upload request. The
  Bootstrap authenticates the bearer first and then returns the exact
  side-effect-free validation rejection. Wrong bearer, unavailable control, an
  unexpected success, or any other response fails closed and creates no Manager
  credential state. A dedicated read-only authentication probe remains protocol
  cleanup debt; it is not part of the current merged contract.
- Successful verified pairing issues a short-lived browser maintenance
  capability. The capability is an alias-bound HMAC-SHA256 token carried only in
  an `HttpOnly; Secure; SameSite=Strict` cookie scoped to `/api/manager`.
- The maintenance capability expires after 15 minutes, requires a same-origin
  mutation request, and is signed with a dedicated Render-generated secret
  (`PLASMA_MANAGER_MAINTENANCE_CAPABILITY_SECRET`). It does not reuse the
  Cloudflare Access secret or the device Bootstrap token.
- Public registry mutation is fixed-target: only `disabled` / `commissioned`
  lifecycle transitions are admitted for canonical alias `z2like-qemu`, and
  those transitions require the maintenance capability.
- Bootstrap POST mutation other than `pair` also requires the same capability.
  Public Bootstrap status remains read-only.
- Add/remove/endpoint mutation and unrelated PATCH fields fail closed at the BFF.
- Manager remains authoritative for lifecycle safety: disabling is rejected while
  Site execution is active; commissioning requires a current trusted observation;
  Runtime upload/deploy still requires the normal pending/disabled maintenance and
  trusted-idle gates.
- SWPC exposes no generic Bootstrap API and no direct public `:18081` listener;
  only the fixed `__plasma/bootstrap` allowlist is projected through `:18082`.
- SWPC host `127.0.0.1:18081` diagnostics retirement boundary is unchanged.

## Canonical operator sequence

```text
GET Bootstrap status                         read-only
Verify & Pair Bootstrap token                authenticated, no Runtime mutation
receive short-lived maintenance capability  browser-only opaque cookie
commissioned -> disabled                     capability + Manager busy gate
disabled trusted-idle proof                  Manager authoritative
upload / commit / deploy                     capability + lifecycle admission
Runtime returns runtime_active               observed evidence
disabled -> commissioned                     capability + trusted enable gate
```

## Post-merge Browser Runtime live gate

The live-acceptance transaction uses:

- `scripts/z2like-demo-browser-live-acceptance.py`
- `.github/workflows/z2like-demo-browser-live-acceptance.yml`

The workflow is intentionally split:

- Pull requests run source/contract validation only.
- Live mutation is permitted only for `physicslu/plasma`, `refs/heads/main`, on
  the trusted `[self-hosted, linux, x64, plasma-integration]` SWPC runner.
- The public Render deployment must be the triggering `main` commit or a later
  descendant before Browser acceptance starts.
- The canonical ARMv7 Z2 PS kit is built from the accepted source commit before
  pairing, so the 15-minute Browser maintenance capability is not consumed by
  the build stage.
- Failure cleanup may return a disabled target to `commissioned` only through the
  normal Manager gate. There is no force-commission fallback.
- Device pairing tokens and browser maintenance capability values are never
  written to the acceptance report.

The merge of PR #591 triggered Browser Runtime live run `34942047814`; its
`live-swpc-render-qemu` job completed successfully for commit
`19e6df408da7f01a5ea0ce777a1bf5f8c2db1ebe`.

### Automated live coverage in this gate

```text
GET Browser Bootstrap status                       -> required
wrong Bootstrap pairing token                      -> BLOCKED, no credential state
correct Bootstrap pairing while commissioned       -> required
verified pairing returns maintenance capability    -> required
lifecycle PATCH without capability                 -> BLOCKED
cross-origin lifecycle/Bootstrap mutation          -> BLOCKED
tampered capability                                -> BLOCKED
commissioned Bootstrap upload/deploy mutation      -> BLOCKED
commissioned -> disabled when idle                 -> required
bounded upload through Manager                     -> required
Runtime deployment through Bootstrap               -> required
Runtime returns runtime_active                      -> required
disabled -> commissioned                           -> required
8-Site Programming regression before/after         -> required
unknown Bootstrap route                            -> BLOCKED
wrong Bootstrap method                             -> BLOCKED
SWPC local Bootstrap allowlist projection           -> required
```

### Still not live-qualified by the Browser Runtime gate

These cases remain explicit qualification debt and must not be inferred from a
PASS of the Browser Runtime gate:

```text
commissioned -> disabled with active Site Job      -> corrected live evidence still required
forced stale/non-idle maintenance proof            -> live evidence still required
15-minute capability expiry wall-clock rejection   -> live evidence still required
```

## Active-Site-Job disable rejection follow-up gate

PR #591 added a separate live-negative gate for **active-Site-Job disable rejection**.
It must observe the exact configured-Mock Site Job through Manager before attempting
`commissioned -> disabled`, and PASS requires HTTP 409 `ppu_busy`.

The first post-merge execution (`34942047881`) failed safely before any test Job was
created. The gate attempted to read `/api/mock/runtime` and received HTTP 503
`MOCK_RUNTIME_UNAVAILABLE`. That endpoint belongs to the mutable Shared-Image Mock
Runtime; the canonical QEMU Programming path uses `configured_mock`, whose timing is
owned by the deployed PPU Site configuration. The failed run therefore produced no
active-job disable evidence and closes no qualification debt.

The correction is intentionally structural rather than an SWPC operator workaround:

- the QEMU simulation installer owns a deterministic 10-second configured-Mock erase
  delay, giving the 2-second Render Manager poller multiple observation windows;
- only previously Plasma-managed no-delay QEMU configs are admitted for automatic
  migration; arbitrary operator-edited configs remain untouched;
- the active-job script no longer reads, writes, enables, or restores
  `/api/mock/runtime`;
- the active-job workflow is triggered only after the Browser Runtime live workflow
  completes successfully on `main`;
- the exact triggering Browser workflow `head_sha` is checked out and passed as the
  accepted source commit, preventing the single SWPC runner from testing an older
  runtime merely because the active-job job happened to acquire the runner first;
- the test still uses only the normal maintenance capability, performs bounded Job
  cancellation/idle cleanup, and has no force lifecycle transition.

A PASS of this corrected follow-up closes only the active-Site-Job disable rejection
debt. The following remain explicit live qualification debt:

- forced stale/non-idle maintenance proof rejection
- 15-minute capability expiry wall-clock rejection
- real PYNQ-Z2 deployment/reboot/rollback
- PL/FPGA behavior
- target power/electrical behavior
- real IC programming
- physical multi-Site concurrency

## Qualification boundary

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

This implementation and its SWPC/QEMU live gates make no claim for PL/FPGA behavior,
target power, real IC programming, physical multi-Site concurrency, or physical Z2
reboot/rollback qualification.
