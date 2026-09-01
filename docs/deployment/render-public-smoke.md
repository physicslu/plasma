# Render public smoke acceptance

This check validates the already-deployed public Plasma demo from a GitHub-hosted runner. It is a deployment/runtime acceptance layer, not a replacement for source CI, Mock CD, SWPC acceptance, Z2 validation, or physical IC programming validation.

Public target:

```text
https://plasma-6zz7.onrender.com
```

## Why this is separate from source CI

The Render service is configured to deploy **After CI Checks Pass**. A smoke test that waits for the new Render deployment must therefore not be a required push check for the same commit, or the deployment and the smoke check can wait on each other.

The workflow `.github/workflows/render-public-smoke.yml` is intentionally available through:

- `pull_request` only when the smoke-test/deployment files themselves change; this validates GitHub-runner connectivity and the currently deployed public contract without claiming that the PR branch is deployed.
- `workflow_dispatch` for post-deploy acceptance. A manual run on `main` defaults the expected deployed commit to the selected `main` SHA. An explicit commit SHA may also be supplied.

It does **not** run on every `main` push.

## Cold-start behavior

Render Free may spin the service down after inactivity. The smoke test therefore:

1. sends an initial request to wake the service;
2. polls for up to 150 seconds;
3. requires `/api/health/ready` to report Gateway alive and execution ready;
4. when an expected commit is supplied, waits until `/deployment.json` reports that exact `RENDER_GIT_COMMIT` before accepting readiness.

A DNS failure, TLS failure, or continued lack of readiness after the wake window is a smoke-test failure. A response from an older commit is not accepted when commit pinning is enabled.

## Deployment identity

At startup, `scripts/render-start.sh` writes a public `deployment.json` file into the built static root using only Render-provided non-secret metadata:

```json
{
  "schema_version": 1,
  "service": "plasma-public-demo",
  "platform": "render",
  "git_commit": "<RENDER_GIT_COMMIT>",
  "git_branch": "<RENDER_GIT_BRANCH>"
}
```

No Render API key, deploy hook, service ID, credential, or customer data is exposed.

## Smoke contract

After readiness, the smoke test performs read-only checks only:

- `/api/status` -> `render-demo-ppu` and 8 local Mock Sites;
- `/api/engineering/targets` -> Web REST v3, Mock provider, 3 Facilities / 12 PPUs / 60 Sites;
- `/api/mock/runtime` -> Web REST v3 and canonical Erase / Program / Verify / Read settings structure;
- `/` and `/demo` -> Control Station product entry;
- `/fleet` -> Production Mode;
- `/engineering` -> Engineering Mode;
- `/ppu` -> compatibility route to Engineering Mode;
- all browser product routes use the `Plasma Control Station` shell and must not expose the retired `SITE MATRIX / PPU CONTROL` UI.

The public smoke test deliberately does not POST Jobs, mutate Mock Settings, upload a Programming Image, cancel a Batch, or change any runtime state. Those behaviors are covered by deterministic Mock CD and browser acceptance rather than by a shared public demo.

## Run manually

In GitHub Actions, choose **Render Public Smoke Acceptance** -> **Run workflow** on `main`.

Leave `expected_commit` blank to require the selected `main` SHA, or provide a specific full Git commit SHA when validating a known deployment.

The workflow uploads `render-public-smoke-report` for 14 days. The JSON report records the expected and observed commit, cold-start duration, each completed check, and failure details when applicable.
