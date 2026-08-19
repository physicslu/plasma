# Plasma Fleet Demo Deployment

The Fleet demo is a **Management Host** feature. It is not a required Z2/PPU runtime component.

## Public demo routes

```text
/       -> redirect to /demo
/demo   -> choose Single PPU or Manager/Fleet demo
/ppu    -> existing single-PPU Plasma Console
/fleet  -> read-only Fleet UI
```

The `/ppu` path remains independent of Manager availability.

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

Fleet BFF is disabled by default. A Management Host enables it explicitly in the Web runtime environment:

```text
PLASMA_FLEET_UI_ENABLED=1
PLASMA_MANAGER_API_URL=http://127.0.0.1:18180
```

`PLASMA_MANAGER_API_URL` must remain loopback-only in this phase. Do not point it at a remote unauthenticated Manager. A future separate Management Server requires authenticated service-to-service design rather than relaxing this guard.

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
