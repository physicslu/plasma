# Plasma Fleet Demo Deployment

The Fleet demo is a **Management Host** feature. It is not a required Z2/PPU runtime component.

## Public demo routes

The browser product routes are:

```text
/            -> redirect to /demo
/demo        -> Control Station product entry
/fleet       -> Production Mode
/engineering -> Engineering Mode
/ppu         -> compatibility redirect to /engineering
```

The former Single PPU Programming Console is retired. Root behavior is no longer host-specific: localhost, packaged Control Stations, integration hosts, and public demos all enter the Control Station product surface instead of `SITE MATRIX / PPU CONTROL`. Engineering single-PPU programming is owned by `Engineering Mode -> Programming`.

`/ppu` remains only as a compatibility redirect for old bookmarks; it does not render or own a second Programming UI.

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

## Post-deploy acceptance

After an approved deployment, run:

```bash
plasmactl verify fleet
```

This command is read-only. It does not restart services, modify configuration, write the Manager database, or touch Z2/FPGA hardware. It checks the deployed Git state, Vite/Manager systemd state, Fleet opt-in values in both the service and actual Vite process, loopback Manager scope, Manager liveness/fleet API, the same-origin Fleet BFF, sanitized browser contract, stale/current capacity semantics, and the Control Station product routes.

Route acceptance requires `/` and `/demo` to resolve to the product entry, `/fleet` to resolve to Production Mode, `/engineering` to resolve to Engineering Mode, and `/ppu` to resolve to Engineering Mode without exposing `SITE MATRIX / PPU CONTROL`.

The command ends with either:

```text
RESULT: PASS
```

or a non-zero exit with explicit `[FAIL]` checks. Its full output is intended to be pasted into an engineering review or AI-assisted acceptance session.

`plasmactl verify fleet` does **not** claim visual correctness, browser layout correctness, responsive behavior, or human usability. Those remain explicit manual UI acceptance steps. It also validates the application through the local Vite listener with the public Host header; it does not by itself prove external DNS/TLS/tunnel availability.

## Z2 production boundary

Do not infer from the integration-host demo that Z2 must run the Control Station stack. Intended product separation is:

```text
Z2 / PPU role
- Embedded Linux
- Plasma Server
- Plasma Web REST Gateway
- PYNQ / FPGA runtime
- PPU execution and diagnostics APIs

Control Station / Management Host role
- Product entry
- Production Mode
- Engineering Mode / Programming
- Fleet BFF
- Plasma Manager
- optional SQLite observation store
```

The integration workstation may co-locate both roles for development and demonstration only. A separate PPU Programming frontend is not part of the canonical product surface.
