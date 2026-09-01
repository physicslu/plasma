# Render Free public Mock demo

This deployment publishes the Plasma Control Station product pages, Web REST Gateway,
Protocol v3.3 Server, and MockInterface as **one Render Free Web Service**. It
does not introduce a second programming backend, a second Gateway, a persistent
Node.js server, or physical hardware access.

## Architecture and execution boundary

```text
Browser
  -> https://<service>.onrender.com
  -> existing Plasma Web REST Gateway on 0.0.0.0:$PORT
       |-> Control Station product entry / PMode / EMode static assets
       |-> canonical Web REST v3 endpoints and REST polling
       |-> local Plasma Server on 127.0.0.1:9900 -> 8 Mock Sites
       `-> Engineering mock provider -> 3 Facilities / 12 PPUs / 60 Sites
```

`software/web/render/` only supplies a static build entry and small navigation
adapters. Product pages, batch execution, session state, Programming Asset
handling, translations, themes, and API calls are imported directly from the
existing `software/web/app/` implementation.

The former Single PPU Programming Console is retired. Engineering single-PPU
programming is owned by `Engineering Mode -> Programming`; the local PPU REST
API remains available as backend/runtime capability.

The current Plasma application uses HTTP REST polling. **It does not implement
WebSocket.** Render supports WebSocket connections, but deploying Plasma does
not create a nonexistent WebSocket endpoint or claim a transport the existing
application does not provide.

## Create the Render Web Service

Connect the `physicslu/plasma` GitHub repository and choose:

| Render field | Value |
| --- | --- |
| Service type | Web Service |
| Runtime / Language | Python 3 |
| Branch | `main` after the deployment PR is merged |
| Root Directory | Leave empty: repository root |
| Build Command | `bash scripts/render-build.sh` |
| Start Command | `bash scripts/render-start.sh` |
| Instance Type | Free |
| Health Check Path | `/api/health/ready` |

Set the following environment variables:

| Variable | Value | Purpose |
| --- | --- | --- |
| `PYTHON_VERSION` | `3.12.13` | Pin the Python runtime to an allowed, tested version. |
| `NODE_VERSION` | `22.22.0` | Pin the Node.js version used only to build React assets. |
| `PYTHONUNBUFFERED` | `1` | Emit Python service logs immediately. |
| `PLASMA_RENDER_ENGINEERING_MOCK` | `1` | Enable the existing 3-Facility, 12-PPU Engineering provider. |
| `PLASMA_RENDER_FLASH_BYTES` | `1048576` | Allocate 1 MiB of mock Flash for each Engineering Site. |

Do **not** create `PORT`: Render supplies it automatically. Do not set
`NEXT_PUBLIC_PLASMA_API_URL`: the Render browser bundle resolves the API from
`window.location.origin`, so static HTML, REST requests, and asset downloads
always share the visitor's origin.

The repository-root `render.yaml` defines the same service and variables for a
Render Blueprint. A manually created Web Service must still use the values
shown above.

## Build and startup behavior

`scripts/render-build.sh` installs the existing Python package, installs locked
Web dependencies through the project's existing bounded `npm run install:ci`
workflow, and builds `software/web/dist-render/` from the existing React page
components.

`scripts/render-start.sh` starts the existing Protocol v3.3 Plasma Server on
loopback, waits until it is accepting connections, then starts the existing
Gateway on `0.0.0.0:$PORT`. The Gateway serves the SPA shell and static assets
from the same listener as `/api/*`. Both child processes are supervised and
stopped together.

Public paths:

- `/` and `/demo`: Control Station product-mode entry.
- `/fleet`: Production Mode with mock Facilities, PPUs, and Sites.
- `/engineering`: Engineering Mode and canonical single-PPU Programming workspace.
- `/ppu`: compatibility route to Engineering Mode; it no longer exposes `SITE MATRIX / PPU CONTROL`.
- `/api/health/ready`: Server-backed readiness check.
- `/api/status`: canonical local PPU and Site status API.
- `/api/engineering/targets`: existing mock Facility / PPU inventory.

After building the static assets, run the local end-to-end startup and Mock
programming check from the repository root:

```bash
software/python/.venv/bin/python scripts/tests/test-render-runtime.py
```

## 512 MB constraints and public-demo limits

Render Free provides 512 MB RAM. The default Engineering mock allocates
`60 × 4 MiB = 240 MiB` before Python objects, uploads, logs, and HTTP buffers.
This deployment sets `PLASMA_RENDER_FLASH_BYTES=1048576`, reducing its baseline
mock memory to `60 × 1 MiB = 60 MiB`. The separate eight-Site local PPU adds
`8 × 1 MiB = 8 MiB`. Node.js is used during the build only and does not run in
the deployed service.

Each demo Site therefore accepts target Images up to its 1 MiB mock Flash
capacity. Avoid uploading real customer Programming Images, credentials, keys, or other
confidential production data: the service is public, unauthenticated, and uses
only simulated targets. All uploaded data, generated readback files, in-memory
Job state, and logs are ephemeral and disappear when Render restarts,
redeploys, or spins down the instance.

Render Free can spin down after 15 minutes without inbound traffic. The next
visit incurs a cold start. This service is a public software demonstration; it
does not validate a Z2, FPGA I/O, OpenOCD, target voltage, or real IC
programming.
