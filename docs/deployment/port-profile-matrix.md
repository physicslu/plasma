# Plasma Deployment Port / Profile Matrix

## Status

**Current deployment contract.**

Port numbers are profile defaults, not one global topology. A port is meaningful only together with its deployment role and bind boundary. Do not treat an intentional profile override as configuration drift.

## Canonical service ports

| Port | Owner / role | Default exposure | Contract |
|---:|---|---|---|
| `9900` | Plasma Server | PPU-local/private | Plasma Protocol v3.3 / `PLASMA33` |
| `18080` | Full Plasma Gateway | profile-specific PPU interface | Web REST v3; full managed-control surface |
| `18081` | real/simulated `z2-ps` Bootstrap | trusted/private recovery boundary | factory/recovery Bootstrap v1; legacy SWPC host diagnostics ingress retired |
| `18082` | SWPC host `z2like-demo` managed ingress | loopback behind Cloudflare Access | bounded managed routes to private QEMU Gateway; public hostname is `ppu-managed-lab.open4th.com` |
| `18180` | Plasma Manager general/package/Render default | loopback | Manager contract v1 |
| `18190` | Linux `local-control-station` Console/BFF | loopback | same-origin Control Station UI/BFF |
| `18280` | Linux `local-control-station` Manager override | loopback | Manager contract v1 |
| `18380` | SWPC `z2like-demo` internal maintenance Manager | loopback | Bootstrap lifecycle/deployment fixture; not public Control Station ownership |
| `18390` | SWPC `z2like-demo` internal acceptance Console/BFF | loopback | local acceptance fixture only; not a public hostname origin |
| `5173` | integration/development Vite runtime | development profile only | development/demo Web runtime; not a production PPU service |

`18180` and `18280` are therefore **not competing canonical Manager ports**. `18180` is the Manager default used by generic/package and Render-oriented paths; `local-control-station` deliberately overrides its Manager to `18280` so its Console/BFF can own `18190` without colliding with an integration-host Manager.

`18380/18390` are not another public Control Station. They are SWPC-local maintenance/acceptance fixtures used to exercise the QEMU Bootstrap path. The public `z2like-demo.open4th.com` Control Station stays on Render.

`18081` is now a Bootstrap/recovery identity only for explicit real/simulated Z2 profiles. The former SWPC host `127.0.0.1:18081` restricted diagnostics/status ingress was retired by Issue #549 and must remain unused. Inside the private QEMU ARMv7 simulated-Z2 network namespace and on a real `z2-ps` appliance, `:18081` remains the independent Bootstrap/recovery service. Manager derives a Bootstrap endpoint from the registered Gateway host only for the explicitly selected Z2 deployment/simulation path; an arbitrary host `:18081` must not be treated as Bootstrap.

## Profile matrix

| Profile / lane | Console/BFF | Manager | Plasma Gateway | Additional ingress | Notes |
|---|---|---|---|---|---|
| `integration` | development runtime, normally `5173` | optional `127.0.0.1:18180` | `:18080` | none by default | SWPC development/integration ownership |
| Render `plasma-demo` | public Render `$PORT` | `127.0.0.1:18180` | `127.0.0.1:18080` | none | single-service public Mock composition |
| Render `z2like-demo` | public Render `$PORT` | Render loopback `:18180` | QEMU `172.30.77.2:18080` through protected SWPC bridge | public `ppu-managed-lab.open4th.com` -> SWPC `127.0.0.1:18082`; private QEMU `:18081` Bootstrap | QEMU ARMv7 is sole z2like PPU backend; Render owns public Control Station |
| packaged macOS / Windows Control Station | package Console default `:18000` | `127.0.0.1:18180` | configured remote PPU | none | platform packaging default; product contract remains shared |
| `local-control-station` | `127.0.0.1:18190` | `127.0.0.1:18280` | configured PPU endpoint | none | Linux user-systemd reference; loopback-only local services |
| `swpc-z2like` PPU | separate Control Station | separate Control Station | `127.0.0.1:18080` full local Gateway | none | x86_64 engineering surrogate only; host `18081` retired; not `z2like-demo` backend |
| SWPC `z2like-demo` maintenance fixture | `127.0.0.1:18390` internal only | `127.0.0.1:18380` internal only | `<private-QEMU-IP>:18080` | `<private-QEMU-IP>:18081` Bootstrap | deployment/acceptance fixture only; no public hostname terminates here |
| `z2-ps` | separate Control Station | separate Control Station | `<Z2-LAN-IP>:18080` | `<Z2-LAN-IP>:18081` Bootstrap/recovery | real ARMv7 PS profile; Bootstrap stays independently reachable when Product Runtime is absent/broken |

## Routing invariants

Control Station product traffic follows:

```text
Browser
  -> same-origin Console/BFF
  -> loopback Plasma Manager
  -> configured PPU Plasma Gateway / managed PPU route
```

The Browser must not receive Manager service credentials, Bootstrap pairing credentials, or Cloudflare Access service-token credentials.

For the SWPC x86 engineering lane:

```text
host 18080 = full local Plasma Gateway
host 18081 = retired; no diagnostics/public listener may be recreated
```

Managed operator access must use the maintained Control Station path. The public z2like-demo path uses host `18082`; host `18081` must not be repurposed as Programming or Bootstrap for the x86 surrogate.

For public `z2like-demo`:

```text
z2like-demo.open4th.com
  -> Render Console/BFF
  -> Render Manager
  -> ppu-managed-lab.open4th.com
  -> Cloudflare Access/Tunnel
  -> SWPC host 127.0.0.1:18082 bounded managed ingress
  -> private QEMU 172.30.77.2:18080 Product Runtime Gateway

private QEMU 172.30.77.2:18081 = simulated independent Bootstrap
private QEMU 172.30.77.2:9900  = simulated Plasma Server
```

The private QEMU ports are not Docker host-published ports. `z2like-demo.open4th.com` must remain Render-hosted; it must not terminate on host `18390`, QEMU `18080`, or QEMU `18081`.

The SWPC-local maintenance path is separate:

```text
host 18380 = internal Bootstrap-capable Manager
host 18390 = internal acceptance Console/BFF
```

For real `z2-ps`:

```text
18080 = Product Runtime Plasma Gateway
18081 = independent factory/recovery Bootstrap
```

The Bootstrap path is separate from Gateway routing because first installation and recovery must work when Plasma Runtime/Gateway is absent or unhealthy. Normal operator flow is `Browser -> Console/BFF -> Manager -> Bootstrap`; direct Bootstrap access is a factory/recovery operation only. The current Bootstrap transport is qualified only for the controlled private commissioning link; Internet exposure, transport confidentiality and publisher authenticity are not qualified.

For real `z2-ps`, `18080` and `18081` bind to the explicitly selected trusted Z2 LAN address. The SWPC loopback/QEMU topology must not be copied mechanically onto the real appliance.

## Operator rule

When diagnosing a port mismatch, first identify the active profile or scenario. The expected value is the profile/scenario contract above, not whichever port appears most often in the repository.

Executable scripts remain authoritative for actual defaults; this document is the canonical human-readable cross-profile map and must be updated when those defaults intentionally change.
