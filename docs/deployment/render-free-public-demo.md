# Render Free public Mock demo

This deployment publishes the Plasma **Control Station product runtime** on Render Free while keeping the simulated PPU behind the same product control path used by deployed Control Stations.

It is a public software demo only. It does not provide physical hardware access and does not validate Z2, FPGA I/O, OpenOCD, target voltage, or real IC programming.

## Architecture and execution boundary

```text
Browser
  -> https://<service>.onrender.com
  -> Control Station Console/BFF on 0.0.0.0:$PORT
       -> Plasma Manager on 127.0.0.1:18180
            -> render-demo-ppu Plasma Gateway on 127.0.0.1:18080
                 -> Plasma Protocol v3.3 Server on 127.0.0.1:9900
                      -> 8 Mock Sites
```

The public listener is the Console/BFF only. The Manager, Plasma Gateway, and Protocol server remain loopback-only inside the Render service.

This removes the former demo-only architecture in which the browser connected directly to a public Plasma Gateway serving static assets. The demo now exercises the same managed browser route as the product:

```text
/api/manager/ppu/<PPU API path>
```

The Manager relay remains allowlisted. This convergence does **not** turn Manager into an unrestricted HTTP proxy.

Engineering Mode continues to use the existing Mock provider for multi-PPU UI scenarios. The local `render-demo-ppu` remains an independent eight-Site Mock PPU used for managed PPU operations and programming acceptance.

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
| Health Check Path | `/` |

Set the following environment variables:

| Variable | Value | Purpose |
| --- | --- | --- |
| `PYTHON_VERSION` | `3.12.13` | Pin the Python runtime to an allowed, tested version. |
| `NODE_VERSION` | `22.22.0` | Build and run the standalone Console/BFF. |
| `PYTHONUNBUFFERED` | `1` | Emit Python service logs immediately. |
| `PLASMA_RENDER_PPU_ALIAS` | `render-demo-ppu` | Fixed Manager registry alias for the local Mock PPU. |
| `PLASMA_RENDER_ENGINEERING_MOCK` | `1` | Enable the existing Engineering Mock provider. |
| `PLASMA_RENDER_FLASH_BYTES` | `1048576` | Allocate 1 MiB of Mock Flash per Engineering Site. |

Do **not** create `PORT`: Render supplies it automatically.

The repository-root `render.yaml` defines the same service and variables for a Render Blueprint.

## Build and startup behavior

`scripts/render-build.sh` installs the existing Python package, installs locked Web dependencies through `npm run install:ci`, and builds only the source-tree-independent product runtime with:

```text
npm run build:product
software/web/dist/standalone/server.js
```

The legacy `dist-render` static SPA build is no longer part of the deployed public-demo path.

`scripts/render-start.sh` performs the following sequence:

1. validates the production Device Catalog before opening the public listener;
2. starts the Protocol v3.3 Server on loopback;
3. starts the Mock PPU Plasma Gateway on loopback and waits for execution readiness;
4. generates an immutable one-PPU Manager registry for `render-demo-ppu`;
5. starts Plasma Manager on loopback;
6. starts the Control Station Console/BFF on Render `$PORT` with Managed Mode enabled.

The Console/BFF receives:

```text
PLASMA_CONTROL_STATION_MODE=managed
PLASMA_MANAGER_API_URL=http://127.0.0.1:18180
PLASMA_MANAGER_PPU_ALIAS=render-demo-ppu
```

`/deployment.json` is exposed only because the Render demo explicitly enables deployment identity. It contains Render-provided non-secret Git commit/branch metadata for post-deployment acceptance. Other Control Station deployments receive HTTP 404 unless they explicitly opt in.

## Validation

After building the standalone product runtime, run the local end-to-end startup and managed Mock programming check from the repository root:

```bash
software/python/.venv/bin/python scripts/tests/test-render-runtime.py
```

The acceptance requires:

- Console/BFF product pages are served from the public origin;
- Manager registry contains exactly the configured demo PPU;
- `/api/manager/ppu/api/status` reports `render-demo-ppu` with eight Sites;
- Engineering Mock inventory remains available through the managed PPU route;
- a SITE 1 Mock programming Job can be submitted and reaches `success` through Console/BFF -> Manager -> Gateway;
- direct child-process RSS remains below the Render Free 512 MiB budget on Linux CI.

For the deployed public service, use the cold-start-aware smoke test with the exact deployed commit:

```bash
python scripts/tests/test-render-public-smoke.py \
  --origin https://plasma-6zz7.onrender.com \
  --expected-commit <40-character-git-sha>
```

Pinned smoke acceptance requires the managed `/api/manager/ppu/...` path and performs a Mock programming Job. An unpinned pull-request smoke only observes the currently deployed main revision and therefore remains backward-compatible until the PR itself is deployed.

## 512 MiB constraints and public-demo limits

Render Free provides 512 MiB RAM. `PLASMA_RENDER_FLASH_BYTES=1048576` keeps the Engineering Mock memory footprint bounded; the separate eight-Site local PPU also uses 1 MiB Mock Flash per Site.

The product-path convergence adds the standalone Node Console/BFF and Manager process, so the runtime acceptance measures the direct child-process RSS of the Render supervisor. This is a deployment budget check, not a claim about production sizing.

Avoid uploading real customer Programming Images, credentials, keys, or other confidential production data. The service is public, unauthenticated, and uses simulated targets. Uploaded data, readback files, in-memory Job state, and logs are ephemeral and disappear when Render restarts, redeploys, or spins down the instance.

Render Free may spin down after inactivity; the next visit can incur a cold start.
