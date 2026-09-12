# SWPC Z2-like Secure Managed Programming Ingress

Status: integration qualification path for Render Control Station -> SWPC Z2-like **mock Programming**. This does not qualify PYNQ-Z2, ARMv7, PL/FPGA, Site electrical behavior, target power, OpenOCD, or real IC programming.

## Purpose

The historical public SWPC ingress remains diagnostics-only:

```text
127.0.0.1:18081
  health / ready / node / status / PS loopback only
```

Do not widen that listener and do not expose the full Plasma Gateway on `127.0.0.1:18080` directly to the Internet.

The managed Programming path adds a separate least-privilege listener:

```text
Render Z2Like Console/BFF
  -> Render Plasma Manager
  -> Cloudflare Access service-token protected HTTPS hostname
  -> Cloudflare Tunnel
  -> SWPC 127.0.0.1:18082 managed Programming ingress
  -> SWPC 127.0.0.1:18080 Plasma Gateway
  -> Plasma Server
  -> SITE1..SITE8 mock execution
```

The listener is loopback-only. Public exposure is permitted only through a Cloudflare Access policy that requires a service token owned by the Render deployment.

## Security model

The design intentionally keeps three different boundaries:

```text
18080  full Plasma Gateway                 loopback only
18081  diagnostics/status ingress          loopback only, existing public lab path
18082  managed Programming ingress         loopback only, Cloudflare Access required
```

`18082` is not a generic reverse proxy. Its Nginx allowlist is limited to the managed software surfaces needed for mock Programming:

- health/readiness/node/status;
- principal introspection and target discovery;
- read-only Gateway communication-policy visibility;
- read-only PPU network visibility;
- Site Desired read/write and bounded Runtime Activation;
- Mock runtime settings;
- Engineering session and PS loopback;
- Programming Asset check/upload;
- Job submit/cancel/readback;
- Batch submit/status/cancel.

The ingress deliberately excludes Gateway settings mutation, PPU network mutation/activation, and arbitrary `/api/*` paths. Read-only settings visibility is retained because the managed UI consumes those JSON surfaces for communication policy and PPU/Site presentation; removing them produces a degraded/non-JSON control-station experience without adding meaningful protection against destructive operations.

Cloudflare Access is transport service identity only. Plasma Gateway remains the final application authorization, Site scope, idempotency, and execution authority. The Render Manager service token must not be stored in Manager registry state or exposed to the Browser.

## SWPC install

Prerequisite: the normal `swpc-z2like` profile must already pass:

```bash
cd "$PLASMA_REPO"
sudo bash scripts/plasmactl-swpc-z2like verify
```

Install the separate managed ingress:

```bash
sudo bash scripts/plasmactl-swpc-z2like-managed-ingress install
```

Read-only verification:

```bash
sudo bash scripts/plasmactl-swpc-z2like-managed-ingress verify
```

Expected result includes:

```text
PASS: loopback-only managed Programming ingress is bounded and operational
edge-auth boundary: public exposure requires Cloudflare Access service-token enforcement
qualification boundary: mock/software path only; no Z2/ARMv7/PL/FPGA/Site/IC claim
```

The verifier also proves:

- the listener is bound only to `127.0.0.1`;
- `/api/settings/sites` is reachable through the managed ingress;
- GET `/api/settings/gateway` and GET `/api/settings/ppu-network` remain available for managed read-only UI state;
- POST mutation of Gateway and PPU network settings is rejected;
- PPU network activation remains hidden;
- unknown API paths remain blocked;
- invalid methods such as `GET /api/jobs` are rejected.

Once both configured Mock Programming and this managed ingress have been explicitly enabled, future SWPC release upgrades use only:

```bash
sudo ./scripts/plasmactl deploy swpc-z2like
```

The top-level profile orchestrator preserves the declared add-on state, regenerates the Programming activation, rewrites managed-ingress evidence against the newly deployed base release, and re-runs both verifiers. A fresh base install does not implicitly enable this ingress. An incomplete state, such as managed-ingress evidence without its Plasma-owned Nginx configuration, fails closed before base deployment begins.

## Cloudflare configuration

Use a **new hostname** for managed control, for example:

```text
ppu-managed-lab.example.com
```

Cloudflare Tunnel origin:

```text
http://127.0.0.1:18082
```

Do not repoint the existing diagnostics hostname if it is still used as PS-loopback evidence, and never point a public hostname directly at `127.0.0.1:18080`.

Before enabling the hostname for Render:

1. create a Cloudflare Access application for the managed hostname;
2. create a service token dedicated to the Render Z2Like service;
3. allow that service token;
4. deny unauthenticated/public requests;
5. verify a request without the service token is denied at the Cloudflare edge.

The Access policy is an external deployment dependency. Repository tests cannot prove that the Cloudflare policy is configured correctly.

## Render configuration

Set the Render Z2Like service environment to the managed hostname:

```text
PLASMA_RENDER_PPU_ENDPOINT=https://ppu-managed-lab.example.com
PLASMA_RENDER_PPU_ACCESS_CLIENT_ID=<Cloudflare Access service-token client ID>
PLASMA_RENDER_PPU_ACCESS_CLIENT_SECRET=<Cloudflare Access service-token secret>
```

Both Access variables must be supplied together. The startup script maps them into Manager-only environment variables scoped to the exact configured PPU origin. They are not written to `manager.yaml`.

The Manager transport adds these Cloudflare headers only when the request target exactly matches `PLASMA_MANAGER_CF_ACCESS_ORIGIN`:

```text
CF-Access-Client-Id
CF-Access-Client-Secret
```

This prevents the service credential from being sent to an unrelated PPU endpoint.

## Functional acceptance

After SWPC, Cloudflare, and Render configuration are active:

1. Render Z2Like Fleet shows the configured Z2-like PPU as Online/Healthy with 8 Sites.
2. PPU/Site Configuration can read Site Desired and read-only network/Gateway state without `managed_upstream_non_json`.
3. SITE1 remains enabled with `interface=mock` and the intended target.
4. Engineering Programming can upload/check a binary Programming Asset.
5. Submit `Erase -> Program -> Verify` to SITE1.
6. Observe Job progress and terminal PASS.
7. Verify Cancel and a controlled Mock failure case.
8. Verify readback if selected.
9. Confirm SITE2..SITE8 routing remains independently addressable according to Desired state.
10. Re-run both ingress verifiers and confirm `18081` diagnostics restrictions did not regress.

A PASS supports only this claim:

```text
Render managed control -> protected SWPC ingress -> Plasma Gateway/Server -> mock Programming
```

It does not support any real-hardware programming claim.