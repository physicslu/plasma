# SWPC Public Preview / Mock Environment

## Status

**Historical.** This document records the retired role of `plasma.open4th.com` before the Local Control Station reference deployment was introduced.

The current public Mock / software-demo lane is:

```text
plasma-demo.open4th.com
  -> Render
  -> Integration / Mock runtime
```

The current intended SWPC hostname role, after Local Control Station runtime acceptance and explicit tunnel retargeting, is:

```text
plasma.open4th.com
  -> Cloudflare Tunnel
  -> SWPC Local Control Station Console/BFF
```

The old Preview/Mock route remains historical evidence only. It must not be used as the current deployment contract.

## Historical purpose

`https://plasma.open4th.com` previously served as the canonical public ingress for the Plasma SWPC Preview / Mock environment.

Its purpose was fast software feedback before a local Control Station or Z2 deployment was available. It was suitable for checking Web UI, PMode / EMode flows, same-origin routing, Engineering Mock behavior, Programming Job presentation, Batch behavior, and other software-only integration paths supported by the SWPC runtime.

It was **not** a production Plasma Gateway Endpoint and was never evidence of Z2, PS↔PL, FPGA, target-power, electrical, or real-IC acceptance.

## Historical routing contract

The retired route was:

```text
public Browser
    |
    v
plasma.open4th.com
    |
    v
SWPC Vite / Vinext Web
    |
    +--> local Plasma Gateway
    |       |
    |       v
    |   Engineering Mock Provider
    |
    +--> optional Manager / BFF
```

This topology is no longer the intended role for `plasma.open4th.com`.

## Current replacement

Mock/demo responsibility moved to the independent Render lane:

```text
plasma-demo.open4th.com
    |
    v
Render Integration / Mock
```

SWPC is being repositioned as the Linux reference host for the Local Control Station role:

```text
plasma.open4th.com
    |
    v
SWPC Local Control Station
    |
    +--> Console/BFF
    |
    v
Manager
    |
    v
configured PPU Plasma Gateway endpoint
```

The actual Cloudflare tunnel must not be retargeted until the Local Control Station profile has been merged and its SWPC runtime has passed local acceptance.

## Preserved invariants

The architectural rules from the retired Preview remain useful:

- `plasma.open4th.com` is never a Plasma Gateway Endpoint or Browser API Base;
- Browser traffic uses same-origin Control Station routing;
- PPU endpoint ownership belongs to Manager/deployment configuration, not Browser-selected state;
- Mock PASS is never real PPU, Z2, PL, Site, electrical, or real-IC evidence;
- changing ingress must not create a second frontend implementation or a second Plasma Gateway API contract.

The three concepts remain distinct:

```text
Control Station hostname   browser/operator ingress
Plasma Gateway Endpoint    one PPU's northbound service root
Linux Default Gateway      Layer-3 network next hop
```

## Historical validation boundary

A successful old SWPC Preview acceptance proved only software ingress and supported Mock paths. It did not prove:

- Windows or macOS installer behavior on a physical operator machine;
- network reachability to a real PPU Plasma Gateway Endpoint;
- Z2 embedded-Linux runtime;
- PS↔PL integration;
- FPGA timing or logic;
- target power sequencing;
- physical programming interfaces;
- real IC erase / program / verify / read behavior.

Those remain separate acceptance layers under the current architecture as well.
