# Render public smoke acceptance

This check validates the already-deployed public Plasma demo from a GitHub-hosted runner. It is deployment/runtime acceptance, not a replacement for source CI, Mock CD, SWPC acceptance, Z2 validation, or physical IC programming validation.

Public target:

```text
https://plasma-6zz7.onrender.com
```

## Why this is separate from source CI

The Render service deploys only after repository CI succeeds. A smoke test that waits for that new deployment must therefore not be a required push check for the same commit, otherwise deployment and acceptance can deadlock.

The workflow `.github/workflows/render-public-smoke.yml` is intentionally available through:

- `pull_request` only when the smoke/deployment files themselves change; this observes the currently deployed public service and does not claim the PR branch is already deployed;
- `workflow_dispatch` for post-deploy acceptance. A manual run on `main` defaults the expected deployed commit to the selected `main` SHA; an explicit full SHA may also be supplied.

It does **not** run on every `main` push.

## Cold-start and routing behavior

Render Free may spin the service down after inactivity. The smoke test therefore:

1. sends an initial request to wake the service;
2. polls for up to 150 seconds;
3. when an expected commit is supplied, waits until `/deployment.json` reports that exact `RENDER_GIT_COMMIT`;
4. for a pinned post-deployment run, requires readiness through the product managed path:

```text
/api/manager/ppu/api/health/ready
```

5. for an unpinned pull-request observation only, it remains compatible with the previously deployed direct-Gateway readiness path until the PR itself is deployed.

A DNS failure, TLS failure, continued lack of readiness, wrong deployed commit, or inability to reach the managed PPU path is a failure.

## Deployment identity

The product Console/BFF contains an opt-in `/deployment.json` route. The public Render demo enables it with:

```text
PLASMA_DEPLOYMENT_IDENTITY_ENABLED=1
PLASMA_DEPLOYMENT_IDENTITY_SERVICE=plasma-public-demo
```

It exposes only Render-provided non-secret deployment metadata:

```json
{
  "schema_version": 1,
  "service": "plasma-public-demo",
  "platform": "render",
  "git_commit": "<RENDER_GIT_COMMIT>",
  "git_branch": "<RENDER_GIT_BRANCH>"
}
```

Other Control Station deployments receive HTTP 404 unless they explicitly opt in. No Render API key, deploy hook, service ID, credential, or customer data is exposed.

## Pinned post-deployment smoke contract

After readiness, a pinned run checks the public Console/BFF and accesses PPU capabilities through:

```text
Browser-style request
  -> Console/BFF
  -> Manager allowlisted relay
  -> render-demo-ppu Plasma Gateway
```

Required checks include:

- `/api/manager/ppu/api/status` -> `render-demo-ppu` and eight local Mock Sites;
- `/api/manager/ppu/api/engineering/targets` -> Web REST v3 Mock provider;
- `/api/manager/ppu/api/devices/search` -> production Device Catalog is reachable through the managed path;
- `/api/manager/ppu/api/mock/runtime` -> canonical Erase / Program / Verify / Read settings structure;
- a small SITE 1 Mock `program` Job submitted through `/api/manager/ppu/api/jobs` reaches `success`;
- `/`, `/demo`, `/fleet`, `/engineering`, `/devices`, and `/ppu` use the `Plasma Control Station` shell and do not expose the retired `SITE MATRIX / PPU CONTROL` UI.

The Job is deliberately small and targets only simulated memory in the public Mock demo. This acceptance does not touch Z2 hardware, DUT power, OpenOCD, or a real IC.

## Run manually

In GitHub Actions, choose **Render Public Smoke Acceptance** -> **Run workflow** on `main`.

Leave `expected_commit` blank to require the selected `main` SHA, or provide a specific full Git commit SHA when validating a known deployment.

The workflow uploads `render-public-smoke-report` for 14 days. The JSON report records the expected and observed commit, cold-start duration, routing mode, completed checks, and failure details when applicable.
