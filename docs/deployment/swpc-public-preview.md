# SWPC Public Preview / Mock Environment

## Purpose

`https://plasma.open4th.com` is the canonical public ingress for the Plasma SWPC Preview / Mock environment.

Its purpose is fast software feedback before a local Control Station or Z2 deployment is available. It is suitable for checking the latest Web UI, PMode / EMode flows, same-origin routing, Engineering Mock behavior, Programming Job presentation, Batch behavior, and other software-only integration paths supported by the SWPC runtime.

It is **not** a production PPU Gateway endpoint and it is **not** evidence of Z2, PS↔PL, FPGA, target-power, electrical, or real-IC acceptance.

## Routing contract

The public hostname and the operator's private SWPC engineering ingress terminate at the same SWPC Web runtime:

```text
public Browser
    |
    v
plasma.open4th.com
    |
    +------------------------------+
                                   v
                          SWPC Vite / Vinext Web
                                   |
                          same-origin API routing
                                   |
                    +--------------+--------------+
                    |                             |
                    v                             v
             local Gateway                  Manager / BFF
                    |
                    v
          Engineering Mock Provider
```

The private overlay-network hostname remains an engineering / operations / fallback ingress. It is intentionally not documented here as a product hostname.

## Ownership boundary

Allowed:

- `plasma.open4th.com` as a Vite `allowedHosts` frontend ingress alias;
- Browser requests using the current origin;
- SWPC-local Vite proxying to the local Gateway;
- Engineering Mock Provider behind the same-origin Web path;
- Manager/BFF routing when the integration host is configured for it.

Retired and forbidden:

- `plasma.open4th.com` as a hard-coded Browser API Base;
- `PLASMA_PUBLIC_API_URL=https://plasma.open4th.com...` as current topology ownership;
- Browser code learning or selecting a PPU Gateway URL through this hostname;
- treating Preview / Mock PASS as Real-Host or Real-PPU acceptance.

The architectural invariant remains:

```text
standalone SWPC Preview / Mock:
Browser -> same origin -> local Vite proxy -> local Gateway -> Mock / local execution

formal Control Station:
Browser -> same-origin Console/BFF -> Manager -> selected PPU
```

## Expected routes

The public Preview should expose the same current product Web routes as the SWPC Web runtime:

```text
/             -> Control Station product entry
/fleet        -> PMode
/engineering  -> EMode
/ppu          -> compatibility redirect to /engineering
```

The public hostname changes ingress only. It must not introduce a second frontend implementation or a second API contract.

## Validation boundary

A useful Preview acceptance proves that the deployed SWPC revision can be reached through the public hostname and that supported same-origin Web / Mock paths operate. It does not prove:

- Windows or macOS installer behavior on a physical operator machine;
- network reachability to a real PPU;
- Z2 embedded-Linux runtime;
- PS↔PL integration;
- FPGA timing or logic;
- target power sequencing;
- physical programming interfaces;
- real IC erase / program / verify / read behavior.

Those remain separate acceptance layers.
