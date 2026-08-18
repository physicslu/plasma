# Web runtime deployment hygiene

Plasma's SWPC Web Console is currently served by a long-running Vite/Vinext development process. A Git fast-forward can change source files underneath that process, so HMR state must not be treated as a completed deployment.

## Rules

- `plasmactl update` updates source only. If `software/web/**` changed, restart the Web runtime before browser validation.
- Use `plasmactl web-restart` for a targeted Vite refresh when Server and REST Gateway do not need to be restarted.
- `plasmactl deploy` remains the normal validated deployment path: update, re-exec the latest deployment logic, run tests, then restart services and perform health checks.
- `npm ci` is run during an update only when `software/web/package-lock.json` changes. A metadata-only `package.json` edit must not replace `node_modules` underneath a live Vite process.
- If `package.json` dependency sections disagree with the lockfile while the lockfile is unchanged, deployment stops instead of guessing.
- Do not routinely delete `node_modules/.vite`. Cache removal is a troubleshooting action, not the normal deployment mechanism.

## Recovery from a client hydration/runtime failure

If the initial HTML renders and the browser then reports a React/Vinext runtime error, refresh the Vite process first:

```bash
plasmactl web-restart
```

Then perform a browser hard reload so old ESM modules are not reused.

The current HTTP health check proves that the Vite endpoint responds, but it does not prove browser hydration. Playwright remains the browser-level validation layer in CI; a future production Web deployment should avoid depending on a long-running development/HMR server altogether.
