# Plasma Fleet Demo Deployment

The Fleet demo is a **Management Host** feature. It is not a required Z2/PPU runtime component.

## Public demo routes

On the public demo host `plasma.open4th.com`:

```text
/       -> redirect to /demo
/demo   -> choose Single PPU or Manager/Fleet demo
/ppu    -> existing single-PPU Plasma Console
/fleet  -> read-only Fleet UI
```

The root redirect is host-scoped to `plasma.open4th.com`; localhost and other development hosts keep the existing root PPU Console behavior so current development/E2E flows do not silently change. `/ppu` is the stable explicit route for the single-PPU demo and remains independent of Manager availability.

## Fleet BFF boundary

The browser calls the same-origin Web route:

```text
GET /api/fleet
```

The Web route calls Manager only through a loopback URL. The default expected Management Host endpoint is:

```text
http://127.0.0.1:18180
```

The BFF rejects non-loopback Manager URLs, strips registry endpoints and raw Manager errors, and exposes no write methods.

## Opt-in runtime variables

Fleet BFF is disabled by default. A Management Host enables it explicitly in the Web host-process environment:

```text
PLASMA_FLEET_UI_ENABLED=1
PLASMA_MANAGER_API_URL=http://127.0.0.1:18180
```

`PLASMA_MANAGER_API_URL` must remain loopback-only in this phase. Do not point it at a remote unauthenticated Manager. A future separate Management Server requires authenticated service-to-service design rather than relaxing this guard.

The Vinext server routes execute in a Cloudflare Worker runtime. Therefore host process variables are not treated as Worker bindings implicitly. `software/web/vite.config.ts` explicitly bridges the two approved Fleet settings into Worker text bindings and enables `nodejs_compat_populate_process_env` so `/api/fleet` can read the same values through `process.env` inside the Worker runtime:

```text
systemd / shell environment
    -> Vite host process
    -> Cloudflare Vite plugin vars
    -> Worker bindings
    -> Worker process.env
    -> /api/fleet
```

This boundary is covered by browser E2E: CI enables the Fleet setting on the Vite host process but intentionally starts no Manager. The expected result is a Manager-unavailable response, not `fleet_ui_disabled`; that distinguishes a working host-to-Worker binding bridge from the deployment defect fixed after PR #47.

The current `plasmactl` deployment schema does not yet own these Web-only Fleet variables. Integration-host activation therefore remains an explicit runtime configuration step and must not be performed as part of merge or CI validation. First-class deployment-schema wiring can be added separately once the demo behavior is accepted.

## Z2 production boundary

Do not infer from the integration-host demo that Z2 must run the Fleet stack. Intended product separation is:

```text
Z2 / PPU role
- Embedded Linux
- Plasma Server
- Plasma Web REST Gateway
- PYNQ / FPGA runtime
- production PPU Console Web artifact

Management Host role
- Fleet Web UI
- Fleet BFF
- Plasma Manager
- optional SQLite observation store
```

The integration workstation may co-locate both roles for development and demonstration only.
