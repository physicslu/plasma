# Plasma Deployment Port / Profile Matrix

## Status

**Current deployment contract.**

Port numbers are profile defaults, not one global topology. A port is meaningful only together with its deployment role and bind boundary. Do not treat an intentional profile override as configuration drift.

## Canonical service ports

| Port | Owner / role | Default exposure | Contract |
|---:|---|---|---|
| `9900` | Plasma Server | PPU-local/private | Plasma Protocol v3.3 / `PLASMA33` |
| `18080` | Full Plasma Gateway | profile-specific PPU interface | Web REST v3; full managed-control surface |
| `18081` | profile-specific: SWPC Z2-like restricted ingress **or** real/simulated `z2-ps` Bootstrap | controlled profile boundary | SWPC x86 diagnostics/status only; real Z2 or private QEMU appliance factory/recovery Bootstrap v1 |
| `18082` | SWPC x86 Z2-like managed Programming ingress | loopback behind Cloudflare Access | allowlisted managed Programming routes; separate from `18081` |
| `18083` | `z2like-demo` QEMU ARMv7 managed Programming ingress | SWPC loopback behind Cloudflare Access | public-demo steady-state allowlist to private QEMU Gateway; Bootstrap not exposed |
| `18180` | Plasma Manager general/package default | loopback | Manager contract v1 |
| `18190` | Linux `local-control-station` Console/BFF | loopback | same-origin Control Station UI/BFF |
| `18280` | Linux `local-control-station` Manager override | loopback | Manager contract v1 |
| `5173` | integration/development Vite runtime | development profile only | development/demo Web runtime; not a production PPU service |

`18180` and `18280` are therefore **not competing canonical Manager ports**. `18180` is the Manager default used by the generic/package and Render-oriented paths; `local-control-station` deliberately overrides its Manager to `18280` so its Console/BFF can own `18190` without colliding with an integration-host Manager.

`18081` is likewise **not one global service identity**. On host-level `swpc-z2like` it remains the restricted diagnostics/status ingress. On a real `z2-ps` appliance it is the independent Bootstrap/recovery service. Inside the private QEMU ARMv7 simulated-Z2 appliance it is also Bootstrap, scoped by the dedicated Docker bridge IP `172.29.33.21`, not the SWPC host listener. Manager derives Bootstrap only for the selected real/simulated Z2 appliance; it must not reinterpret the host-level SWPC `:18081` listener as Bootstrap.

## Profile matrix

| Profile / lane | Console/BFF | Manager | Plasma Gateway | Additional ingress | Notes |
|---|---|---|---|---|---|
| `integration` | development runtime, normally `5173` | optional `127.0.0.1:18180` | `:18080` | none by default | SWPC development/integration ownership |
| Render `plasma-demo` | public Render `$PORT` | `127.0.0.1:18180` | `127.0.0.1:18080` | none | single-service public Mock composition |
| packaged macOS / Windows Control Station | package Console default `:18000` | `127.0.0.1:18180` | configured remote PPU | none | platform packaging default; product contract remains shared |
| `local-control-station` | `127.0.0.1:18190` | `127.0.0.1:18280` | configured PPU endpoint | none | Linux user-systemd reference; loopback-only local services |
| `swpc-z2like` x86 PPU | separate Control Station | separate Control Station | `127.0.0.1:18080` full local Gateway | `127.0.0.1:18081` restricted; `127.0.0.1:18082` managed Programming | engineering surrogate; not canonical `z2like-demo` backend |
| `z2like-demo` QEMU ARMv7 PPU | SWPC local CS for commissioning; Render CS for public steady state | local/Render Manager according to path | `172.29.33.21:18080` private QEMU Gateway | private `172.29.33.21:18081` Bootstrap; host `127.0.0.1:18083` public managed Programming ingress | canonical simulation backend; QEMU is inside the single SWPC Simulation Environment |
| `z2-ps` | separate Control Station | separate Control Station | `<Z2-LAN-IP>:18080` | `<Z2-LAN-IP>:18081` Bootstrap/recovery | real ARMv7 PS profile; Bootstrap stays independently reachable when Product Runtime is absent/broken |

## Routing invariants

Control Station product traffic follows:

```text
Browser
  -> same-origin Console/BFF
  -> loopback Plasma Manager
  -> configured PPU Plasma Gateway / managed PPU route
```

The Browser must not receive Manager service credentials or Cloudflare Access service-token credentials.

For the SWPC x86 Z2-like engineering surrogate:

```text
127.0.0.1:18080 = full local Plasma Gateway
127.0.0.1:18081 = restricted diagnostics/status ingress
127.0.0.1:18082 = managed Programming ingress
```

Do not repurpose host `18081` as the managed Programming or Bootstrap surface and do not collapse `18081` and `18082` into one listener without a separate security/architecture decision.

For the canonical `z2like-demo` QEMU ARMv7 backend:

```text
172.29.33.21:18080 = private simulated-Z2 Product Runtime Gateway
172.29.33.21:18081 = private simulated-Z2 Bootstrap
127.0.0.1:18083    = Cloudflare Access-protected public managed Programming ingress
```

Private commissioning uses the SWPC local Control Station/Manager directly against the QEMU bridge address. Public Render `z2like-demo` uses only the `18083` allowlisted ingress to the QEMU Gateway; it does not proxy or expose Bootstrap. The QEMU public ingress also keeps Site runtime activation closed because the simulation deliberately does not emulate the real privileged systemd activation helper.

For real `z2-ps`:

```text
18080 = Product Runtime Plasma Gateway
18081 = independent factory/recovery Bootstrap
```

The Bootstrap path is separate from Gateway routing because first installation and recovery must work when Plasma Runtime/Gateway is absent or unhealthy. Normal operator flow is `Browser -> Console/BFF -> Manager -> Bootstrap`; direct Bootstrap access is a factory/recovery operation only. The current Bootstrap transport is qualified only for the controlled private commissioning link; Internet exposure, transport confidentiality and publisher authenticity are not qualified.

For real `z2-ps`, `18080` and `18081` bind to the explicitly selected trusted Z2 LAN address. The SWPC loopback topology must not be copied mechanically onto the real appliance.

## Operator rule

When diagnosing a port mismatch, first identify the active profile and IP/bind scope. The expected value is the profile contract above, not whichever port appears most often in the repository.

Executable scripts remain authoritative for a profile's actual defaults; this document is the canonical human-readable cross-profile map and must be updated when those defaults intentionally change.
