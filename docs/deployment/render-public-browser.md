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

At a 1194 x 834 CSS viewport:

- the expanded FPS selector leaves the Production batch toolbar in the accepted two-row tablet layout;
- Programming Image and E/P/V/R remain on the first row;
- E/P/V/R do not wrap;
- Batch readiness/actions remain on the second row;
- the toolbar does not horizontally overflow;
- collapsing the FPS selector restores the desktop single-row toolbar.

### Mock Synthetic Image selection

Against the live Mock provider:

1. select `mock-facility-01 / mock-facility-01-ppu-01 / SITE-01`;
2. confirm the selection;
3. select Program without choosing a user Programming Image;
4. require `Mock Synthetic Image` and `data-image-source=mock_synthetic`;
5. require that readiness is **not** `IMAGE REQUIRED`.

The public Render demo is shared state. A fixed Site can legitimately be `SITE BUSY` because another browser/session or prior acceptance work is using it. Site availability therefore must not determine whether the Synthetic Image contract passes:

- `BATCH READY` -> Execute must be enabled;
- `SITE BUSY` -> Execute must remain disabled;
- either state is acceptable for this public Image-selection acceptance, but `IMAGE REQUIRED` is not.

Deterministic local Playwright and Mock CD tests separately prove that an idle Mock Site with Program selected and no user Image becomes `BATCH READY`.

The public test deliberately does **not** click Execute. It therefore creates no Batch or Job, uploads no Programming Image, and changes no Mock Runtime settings. The page may create its normal short-lived Engineering session.

## Boundary

This is deployment/browser acceptance only. It does not replace deterministic local Playwright tests, Mock CD browser runtime acceptance, SWPC capacity acceptance, Z2 validation, FPGA validation, or physical IC programming validation.
