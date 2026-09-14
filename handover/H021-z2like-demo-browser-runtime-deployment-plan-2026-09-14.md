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
- Device pairing remains bound to Bootstrap `device_id`.
- Public registry mutation is fixed-target: only `disabled` / `commissioned`
  lifecycle transitions are admitted for canonical alias `z2like-qemu`.
- Add/remove/endpoint mutation and unrelated PATCH fields fail closed at the BFF.
- Bootstrap mutation still uses Manager lifecycle admission and trusted idle
  observation requirements.
- SWPC exposes no generic Bootstrap API and no direct public `:18081` listener;
  only the fixed `__plasma/bootstrap` allowlist is projected through `:18082`.
- SWPC host `127.0.0.1:18081` diagnostics retirement boundary is unchanged.

## Acceptance still required

Do not call Browser Runtime Deployment qualified merely because CI passes.
After merge/deploy, live acceptance must prove:

```text
GET Browser Bootstrap status           -> PASS
commissioned Bootstrap mutation        -> BLOCKED
commissioned -> disabled               -> PASS
stale/non-idle maintenance proof        -> BLOCKED
pairing through Manager                -> PASS
bounded upload through Manager         -> PASS
Runtime deployment through Bootstrap   -> PASS
Runtime returns runtime_active          -> PASS
disabled -> commissioned               -> PASS
8-Site Programming regression          -> PASS
unknown Bootstrap route                -> BLOCKED
wrong Bootstrap method                 -> BLOCKED
```

## Qualification boundary

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

This implementation makes no claim for PL/FPGA behavior, target power, real IC
programming, or physical multi-Site concurrency.
