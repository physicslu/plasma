# H011 — Local Control Station Managed Endpoint Wiring Fix

**Date:** 2026-09-12

## Incident

Two deployment-wiring defects combined to make Site Desired Save appear broken.

First, the co-resident SWPC Local Control Station was configured with PPU endpoint `http://127.0.0.1:18081`.

Observed behavior:

- direct PPU Gateway `127.0.0.1:18080` accepted Site CAS headers and returned `invalid_site_precondition` for an intentionally invalid `If-Match` probe;
- restricted ingress `127.0.0.1:18081` returned `404` for `/api/settings/sites/1` by design;
- Manager and Console/BFF therefore propagated that `404` and Site Desired writes could not reach the PPU Gateway;
- health/status remained available, which initially made the endpoint look healthy.

Second, after the Local Control Station was corrected to use `18080`, the public hostname `plasma.open4th.com` was still routed by Cloudflare Tunnel to the old development UI on `127.0.0.1:5173` instead of the deployed Local Control Station on `127.0.0.1:18190`.

Evidence of the split runtime:

```text
Local 127.0.0.1:18190 registry:
  alias=swpc-ppu
  endpoint=http://127.0.0.1:18080
  storage=config
  mutable=false

Public plasma.open4th.com registry before Tunnel fix:
  alias=ppu-a
  storage=file
  mutable=true
```

This explained why local API probes passed while the browser still showed the old behavior.

## Root cause

This was a deployment routing/wiring defect, not an `If-Match` forwarding defect and not a PPU reconciliation defect.

The SWPC Z2-like restricted ingress is intentionally diagnostics/status-only. The Local Control Station requires the full managed-control Plasma Gateway endpoint. Separately, the public Control Station hostname must terminate at the deployed Console/BFF rather than the legacy development UI.

## Current canonical routing

```text
Browser
  |
  v
https://plasma.open4th.com
  |
  v
Cloudflare Access + Tunnel
  |
  v
127.0.0.1:18190  Local Control Station Console/BFF
  |
  v
127.0.0.1:18280  Plasma Manager
  |
  v
127.0.0.1:18080  Full PPU Plasma Gateway
  |
  v
Plasma Server / Site Desired / Runtime Activation
```

Separate restricted PPU route:

```text
https://ppu-lab.open4th.com
  -> Cloudflare Access + Tunnel
  -> 127.0.0.1:18081
  -> diagnostics/status-only restricted PPU ingress
```

Port roles:

```text
18190 = Control Station Console/BFF
18280 = Manager
18080 = full local PPU Gateway / managed control
18081 = restricted PPU diagnostics/status ingress
5173  = legacy/development UI; not the production Control Station route
```

Cloudflare published-application routes:

```text
plasma.open4th.com  -> http://127.0.0.1:18190
ppu-lab.open4th.com -> http://127.0.0.1:18081
```

Do not point `plasma.open4th.com` directly at `18080` or `18081`.

## Fix

- Change Local Control Station SWPC examples from `18081` to `18080`.
- Keep the restricted ingress narrow; do not expose Site write/activation routes there.
- Route `plasma.open4th.com` to `127.0.0.1:18190` instead of legacy port `5173`.
- Keep `ppu-lab.open4th.com` on restricted ingress `127.0.0.1:18081`.
- Add `validate_target_control_surface` to `plasmactl-local-control-station`.
- If `/api/health/live` is reachable but `/api/settings/sites` is not HTTP 200, verification fails closed as a deployment configuration error.
- Preserve temporary PPU unavailability as non-fatal for Control Station deployment qualification.
- Add CI contract coverage for the full-vs-restricted endpoint distinction.

## Acceptance evidence

After correcting both routing layers:

- public `/api/manager/registry` reported `swpc-ppu`, `storage=config`, `mutable=false`, endpoint `http://127.0.0.1:18080`;
- valid CAS Save through `18190 -> 18280 -> 18080` returned HTTP 200;
- SITE1 Desired was saved Enabled with `mock / STM32F103C8T6`;
- reconciliation became `restart_required`;
- Runtime Activation executed the bounded P3 path;
- SITE1 Runtime became `Enabled · mock · STM32F103C8T6` and reconciliation became `In sync`;
- SITE2..SITE8 remained disabled with dormant bindings intentionally unobservable;
- aggregate state therefore remained `Partially Observable`, which is expected under Protocol v3.3.

## Qualification boundary

This validates software deployment/control-plane routing and the SWPC-surrogate P3 controlled activation path only. It does not qualify real PYNQ-Z2/ARMv7 hardware, PS↔PL, FPGA behavior, Site electrical behavior, real IC programming, or 8-Site hardware concurrency.
