# H021 — z2like-demo Browser Runtime Deployment Management Path

**Date:** 2026-09-14  
**Project:** Plasma  
**Scope:** Render Control Station -> controlled QEMU Bootstrap management path  
**Status:** Implementation candidate; requires CI and live SWPC/Render acceptance before qualification

## What changed

The existing browser Runtime Deployment UI and Manager Bootstrap API already
existed. The missing production path was transport/lifecycle composition for the
Render-hosted `z2like-demo` profile.

This change adds:

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
  credential state. This negative challenge is contract-tested; a dedicated
  read-only authentication probe remains a future protocol cleanup, not a reason
  to weaken admission now.
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

## Acceptance still required

Do not call Browser Runtime Deployment qualified merely because CI passes.
After merge/deploy, live acceptance must prove:

```text
GET Browser Bootstrap status                       -> PASS
wrong Bootstrap pairing token                      -> BLOCKED, no credential state
correct Bootstrap pairing while commissioned       -> PASS
verified pairing returns maintenance capability    -> PASS
lifecycle PATCH without capability                 -> BLOCKED
cross-origin lifecycle/Bootstrap mutation          -> BLOCKED
commissioned Bootstrap upload/deploy mutation      -> BLOCKED
commissioned -> disabled with active Site Job      -> BLOCKED
commissioned -> disabled when idle                 -> PASS
stale/non-idle maintenance proof                   -> BLOCKED
bounded upload through Manager                     -> PASS
Runtime deployment through Bootstrap               -> PASS
Runtime returns runtime_active                      -> PASS
disabled -> commissioned                           -> PASS
expired/tampered capability                        -> BLOCKED
8-Site Programming regression                      -> PASS
unknown Bootstrap route                            -> BLOCKED
wrong Bootstrap method                             -> BLOCKED
```

## Qualification boundary

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

This implementation makes no claim for PL/FPGA behavior, target power, real IC
programming, or physical multi-Site concurrency.
