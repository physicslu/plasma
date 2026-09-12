# H011 — Local Control Station Managed Endpoint Wiring Fix

**Date:** 2026-09-12

## Incident

The co-resident SWPC Local Control Station was configured with PPU endpoint `http://127.0.0.1:18081`.

Observed behavior:

- direct PPU Gateway `127.0.0.1:18080` accepted Site CAS headers and returned `invalid_site_precondition` for an intentionally invalid `If-Match` probe;
- restricted ingress `127.0.0.1:18081` returned `404` for `/api/settings/sites/1` by design;
- Manager and Console/BFF therefore propagated that `404` and Site Desired writes could not reach the PPU Gateway;
- the browser surfaced misleading downstream write failures while health/status remained available.

## Root cause

This was a deployment wiring defect, not an `If-Match` forwarding defect and not a PPU reconciliation defect.

The SWPC Z2-like restricted ingress is intentionally diagnostics/status-only. The Local Control Station requires the full managed-control Plasma Gateway endpoint.

Correct co-resident wiring:

```text
Control Station Console/BFF 127.0.0.1:18190
  -> Manager 127.0.0.1:18280
  -> PPU Gateway 127.0.0.1:18080
```

`127.0.0.1:18081` remains restricted and must continue to return `404` for Site settings routes.

## Fix

- Change Local Control Station SWPC examples from `18081` to `18080`.
- Keep the restricted ingress narrow; do not expose Site write/activation routes there.
- Add `validate_target_control_surface` to `plasmactl-local-control-station`.
- If `/api/health/live` is reachable but `/api/settings/sites` is not HTTP 200, verification fails closed as a deployment configuration error.
- Preserve temporary PPU unavailability as non-fatal for Control Station deployment qualification.
- Add CI contract coverage for the full-vs-restricted endpoint distinction.

## Qualification boundary

This fix validates software deployment/control-plane routing only. It does not qualify Z2/ARMv7, PL/FPGA, electrical Sites, real IC programming, or 8-Site hardware concurrency.
