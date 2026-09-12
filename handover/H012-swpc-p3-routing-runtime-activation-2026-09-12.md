# H012 — SWPC P3 Routing and Runtime Activation Handover

**Repository:** `physicslu/plasma`  
**Date:** 2026-09-12  
**Branch:** `agent/local-control-station-direct-gateway`  
**Open PR:** #502 — Fix Local Control Station managed PPU endpoint contract  
**Status:** SWPC P3 software path operational; routing corrected; SITE1 Save Desired + Runtime Activation accepted.

## 1. Current state

The SWPC surrogate PPU and Local Control Station are now using the intended managed-control path.

Validated operator flow:

```text
SITE1 Desired Enabled = true
  -> Save Desired
  -> restart_required
  -> Activate Desired Configuration
  -> controlled plasma-server.service restart
  -> SITE1 Runtime = Enabled / mock / STM32F103C8T6
  -> SITE1 reconciliation = in_sync
```

SITE2..SITE8 remain disabled. Their dormant interface/target bindings are intentionally not observable under Protocol v3.3, so aggregate reconciliation remains `Partially Observable`. This is expected, not a failure.

## 2. Root cause of the Save Desired incident

Two independent deployment-routing defects were present.

### A. Local Control Station pointed to the wrong PPU ingress

The co-resident Local Control Station was initially configured with:

```text
http://127.0.0.1:18081
```

But `18081` is the restricted diagnostics/status ingress. `/api/settings/sites/*` correctly returns 404 there.

The managed Control Station must use the full local PPU Gateway:

```text
http://127.0.0.1:18080
```

CAS probes proved that `If-Match` forwarding itself was correct:

```text
Direct Gateway 18080               -> invalid_site_precondition for bad If-Match
Manager 18280 -> Gateway           -> same
Console/BFF 18190 -> Manager       -> same
Valid revision through full chain  -> HTTP 200
```

Therefore the failure was routing/wiring, not CAS/header forwarding.

### B. Public Control Station hostname still targeted the old development UI

After the Local Control Station endpoint was fixed, `plasma.open4th.com` was still routed by Cloudflare Tunnel to:

```text
127.0.0.1:5173
```

That old UI/runtime exposed a different Manager registry:

```text
alias=ppu-a
storage=file
mutable=true
```

The deployed Local Control Station exposed:

```text
alias=swpc-ppu
endpoint=http://127.0.0.1:18080
storage=config
mutable=false
```

Cloudflare was corrected so `plasma.open4th.com` now targets `127.0.0.1:18190`.

## 3. Canonical SWPC routing

### Public Control Station path

```text
Browser
  -> https://plasma.open4th.com
  -> Cloudflare Access + Tunnel
  -> 127.0.0.1:18190  Control Station Console/BFF
  -> 127.0.0.1:18280  Plasma Manager
  -> 127.0.0.1:18080  Full PPU Plasma Gateway
  -> Plasma Server / Site Desired / Runtime Activation
```

### Restricted PPU path

```text
https://ppu-lab.open4th.com
  -> Cloudflare Access + Tunnel
  -> 127.0.0.1:18081
  -> restricted diagnostics/status-only PPU ingress
```

### Port ownership

```text
18190 = Local Control Station Console/BFF
18280 = Plasma Manager
18080 = Full local PPU Gateway / managed control
18081 = Restricted PPU diagnostics/status ingress
5173  = legacy/development UI; do not use for plasma.open4th.com
```

Do not point `plasma.open4th.com` directly to `18080` or `18081`.

## 4. Current deployment evidence

PPU software release currently validated on SWPC:

```text
0.1.1-0f1123a23a5b
source SHA: 0f1123a23a5b6cdc0e97a21014cb40bc535aa38c
```

Local Control Station is configured as:

```text
PPU alias:    swpc-ppu
PPU endpoint: http://127.0.0.1:18080
Console:      http://127.0.0.1:18190
Manager:      http://127.0.0.1:18280
```

Public `/api/manager/registry` after the Cloudflare route fix reports:

```text
alias=swpc-ppu
endpoint=http://127.0.0.1:18080
storage=config
mutable=false
```

## 5. PR #502

PR #502 is the permanent deployment-contract fix for this incident.

It:

- changes Local Control Station SWPC examples from `18081` to `18080`;
- preserves `18081` as restricted diagnostics/status ingress;
- adds a managed-control capability probe so a health-only endpoint cannot be accepted as a writable PPU endpoint;
- adds regression coverage for full-vs-restricted endpoint semantics;
- documents the routing incident and corrected topology.

Current PR head:

```text
83fac67ffa9891ce4245020cbf96c4d2d1c8232c
```

CI on the PR head is green:

```text
Repository contracts      PASS
Python and PL source tests PASS
Z2 PS release candidate   PASS
```

PR #502 is still open and requires Gate 2 merge approval.

After merge:

```bash
git pull
./scripts/plasmactl deploy local-control-station
./scripts/plasmactl verify local-control-station
./scripts/plasmactl status local-control-station
```

This deploy is needed to install the new Local Control Station endpoint-validation guard. The PPU itself does not need redeployment solely for PR #502.

## 6. Next phase: demo convergence

After PR #502 is merged and deployed, continue the previously planned demo cleanup as a separate transaction.

### `plasma-demo`

Converge toward the same product architecture:

```text
Control Station Console/BFF
  -> Manager
  -> Mock PPU Gateway
```

The demo should not maintain a second control-plane architecture that diverges from the product path.

### `z2like-demo`

Do not solve managed control by widening the existing `18081` restricted ingress.

The current restricted boundary is intentional. Site writes and Runtime Activation need a separately designed authenticated managed-control path/security transaction if they are to be exposed remotely.

Preserve the rule:

```text
18081 != general PPU control surface
```

## 7. Qualification boundary

Validated here:

```text
SWPC x86_64 surrogate
+ Local Control Station
+ Manager
+ full local PPU Gateway
+ Site Desired CAS Save
+ controlled P3 Runtime Activation
+ SITE1 mock runtime reconciliation
```

Not validated here:

```text
Real PYNQ-Z2 / ARMv7 hardware
PS <-> PL
FPGA behavior
Site electrical behavior
DUT power
physical OpenOCD/JTAG/SWD
real IC erase/program/verify
8-Site hardware concurrency
production hardware readiness
```

## 8. Recommended next-session entry

```text
Read AGENTS.md and handover/H012-swpc-p3-routing-runtime-activation-2026-09-12.md.
First close PR #502 through Gate 2 and deploy the merged Local Control Station guard on SWPC. Then continue the demo-convergence phase: plasma-demo first, z2like-demo as a separate security/architecture transaction.
```
