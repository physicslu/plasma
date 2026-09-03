# Render public browser acceptance

This acceptance layer uses Chromium from a GitHub-hosted runner against the already-deployed public Render Plasma demo. It complements the HTTP-only `Render Public Smoke Acceptance` by validating real browser layout and UI readiness behavior.

Public target:

```text
https://plasma-6zz7.onrender.com
```

## Deployment identity

The browser workflow requires an exact deployed commit before running UI assertions.

- On a pull request that changes the browser-acceptance infrastructure itself, the expected commit is the PR base SHA. This proves the public Render service is serving the currently accepted `main`, not the PR branch.
- On `workflow_dispatch`, the expected commit defaults to the selected ref SHA unless an explicit full commit is supplied.
- The Playwright preflight polls `/deployment.json` for up to 150 seconds and only proceeds when `git_commit` exactly matches the expected SHA.

## Current browser contracts

The acceptance intentionally exercises only non-destructive UI behavior.

### Production iPad landscape layout

At a 1194 x 834 CSS viewport, the current PMode V2 `Production Programming Job` must remain contained inside the Factory Console:

- the Programming Job field grid remains inside the panel;
- E/P/V/R remain on one line and do not wrap;
- START / status / ABORT remain inside the panel bounds;
- the Programming Job does not horizontally overflow;
- collapsing the `PRODUCTION SITE SELECTION` body must not cause the Programming Job to overflow or lose those constraints.

This public check intentionally follows the same Programming Job contract used by deterministic local tablet-layout acceptance instead of maintaining a separate legacy batch-toolbar DOM contract.

### Mock Synthetic Image selection

Against the live Mock provider:

1. commit `mock-facility-01 / mock-facility-01-ppu-01 / SITE-01` into the Production Set using the current `SET PRODUCTION SITES` flow;
2. select Program without choosing a user Programming Image;
3. require `Mock Synthetic Image` and `data-image-source=mock_synthetic` from the current `Production Programming Job` Image field;
4. require that Programming Job readiness is **not** `IMAGE REQUIRED`.

The public Render demo is shared state. A fixed Site can legitimately be `SITE BUSY` because another browser/session or prior acceptance work is using it. Site availability therefore must not determine whether the Synthetic Image contract passes:

- `BATCH READY` -> START must be enabled;
- `SITE BUSY` -> START must remain disabled;
- either state is acceptable for this public Image-selection acceptance, but `IMAGE REQUIRED` is not.

Deterministic local Playwright and Mock CD tests separately prove that an idle Mock Site with Program selected and no user Image becomes `BATCH READY`.

The public test deliberately does **not** click START. It therefore creates no Batch or Job, uploads no Programming Image, and changes no Mock Runtime settings. The page may create its normal short-lived Engineering session.

## Boundary

This is deployment/browser acceptance only. It does not replace deterministic local Playwright tests, Mock CD browser runtime acceptance, SWPC capacity acceptance, Z2 validation, FPGA validation, or physical IC programming validation.
