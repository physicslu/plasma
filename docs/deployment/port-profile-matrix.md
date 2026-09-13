# Plasma Deployment Port / Profile Matrix

## Status

**Current deployment contract.**

Port numbers are profile defaults, not one global topology. A port is meaningful only together with its deployment role and bind boundary. Do not treat an intentional profile override as configuration drift.

## Canonical service ports

| Port | Owner / role | Default exposure | Contract |
|---:|---|---|---|
| `9900` | Plasma Server | PPU-local/private | Plasma Protocol v3.3 / `PLASMA33` |
| `18080` | Full Plasma Gateway | profile-specific PPU interface | Web REST v3; full managed-control surface |
| `18081` | SWPC Z2-like restricted ingress | loopback behind controlled external routing | diagnostics/status only; **not** a full Gateway endpoint |
| `18082` | SWPC Z2-like managed Programming ingress | loopback behind Cloudflare Access | allowlisted managed Programming routes; separate from `18081` |
| `18180` | Plasma Manager general/package default | loopback | Manager contract v1 |
| `18190` | Linux `local-control-station` Console/BFF | loopback | same-origin Control Station UI/BFF |
| `18280` | Linux `local-control-station` Manager override | loopback | Manager contract v1 |
| `5173` | integration/development Vite runtime | development profile only | development/demo Web runtime; not a production PPU service |

`18180` and `18280` are therefore **not competing canonical Manager ports**. `18180` is the Manager default used by the generic/package and Render-oriented paths; `local-control-station` deliberately overrides its Manager to `18280` so its Console/BFF can own `18190` without colliding with an integration-host Manager.

## Profile matrix

| Profile / lane | Console/BFF | Manager | Plasma Gateway | Additional ingress | Notes |
|---|---|---|---|---|---|
| `integration` | development runtime, normally `5173` | optional `127.0.0.1:18180` | `:18080` | none by default | SWPC development/integration ownership |
| Render `plasma-demo` | public Render `$PORT` | `127.0.0.1:18180` | `127.0.0.1:18080` | none | single-service public Mock composition |
| packaged macOS / Windows Control Station | package Console default `:18000` | `127.0.0.1:18180` | configured remote PPU | none | platform packaging default; product contract remains shared |
| `local-control-station` | `127.0.0.1:18190` | `127.0.0.1:18280` | configured PPU endpoint | none | Linux user-systemd reference; loopback-only local services |
| `swpc-z2like` PPU | separate Control Station | separate Control Station | `127.0.0.1:18080` full local Gateway | `127.0.0.1:18081` restricted; `127.0.0.1:18082` managed Programming | surrogate PPU; `18081` and `18082` are intentionally separate security surfaces |
| `z2-ps` | separate Control Station | separate Control Station | `<Z2-LAN-IP>:18080` | none implied by `z2-ps` | real ARMv7 PS-only qualification; Gateway host must be an explicit non-loopback Z2 IPv4 address |

## Routing invariants

Control Station product traffic follows:

```text
Browser
  -> same-origin Console/BFF
  -> loopback Plasma Manager
  -> configured PPU Plasma Gateway / managed PPU route
```

The Browser must not receive Manager service credentials or Cloudflare Access service-token credentials.

For the SWPC Z2-like laboratory lane:

```text
18080 = full local Plasma Gateway
18081 = restricted diagnostics/status ingress
18082 = managed Programming ingress
```

Do not repurpose `18081` as the managed Programming surface and do not collapse `18081` and `18082` into one listener without a separate security/architecture decision.

For real `z2-ps`, `18080` is the PPU Gateway listener on the explicitly selected trusted Z2 LAN address. The SWPC loopback topology must not be copied mechanically onto the real appliance.

## Operator rule

When diagnosing a port mismatch, first identify the active profile. The expected value is the profile contract above, not whichever port appears most often in the repository.

Executable scripts remain authoritative for a profile's actual defaults; this document is the canonical human-readable cross-profile map and must be updated when those defaults intentionally change.
