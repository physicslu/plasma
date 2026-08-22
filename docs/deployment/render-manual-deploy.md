# Render manual deployment with plasmactl

Plasma normally relies on Render Auto-Deploy from the repository's linked `main` branch. `plasmactl render-deploy` is the operator-controlled fallback for explicitly redeploying the latest commit on that linked branch.

It does **not** replace Auto-Deploy and it intentionally does not select a Git SHA.

## Why latest linked branch only

Render Deploy Hooks accept an optional `ref` query parameter for deploying a specific commit. Render documents that using a Deploy Hook with a specific `ref` disables automatic deploys for the service.

Plasma therefore rejects a hook URL containing `ref=`. The deployment source of truth remains the branch linked in Render, normally `main`.

## One-time setup

In the Render Dashboard for `plasma-public-demo`:

1. Open **Settings**.
2. Locate the service's **Deploy Hook**.
3. Copy the secret hook URL.
4. Keep the hook secret. Do not put it in Git, `render.yaml`, documentation, screenshots, issues, or PR comments.

On the trusted operator host, add it to the local `plasmactl` environment/config:

```bash
mkdir -p ~/.config/plasma
chmod 700 ~/.config/plasma

cat >> ~/.config/plasma/plasmactl.env <<'EOF'
PLASMA_RENDER_DEPLOY_HOOK_URL='https://api.render.com/deploy/srv-REDACTED?key=REDACTED'
EOF

chmod 600 ~/.config/plasma/plasmactl.env
```

Replace the redacted example with the actual Render Deploy Hook URL. The local config file is sourced by `plasmactl` and is not part of the repository.

## Trigger a deployment

```bash
plasmactl render-deploy
```

The command:

- requires `curl`;
- requires `PLASMA_RENDER_DEPLOY_HOOK_URL`;
- accepts only an HTTPS Render Deploy Hook under `api.render.com/deploy/`;
- rejects a hook containing `ref=` so it cannot silently disable the service's normal auto-deploy behavior;
- sends a `POST` request to the hook;
- never prints the hook URL or its secret key;
- returns success when Render accepts the request.

A successful command means the deploy was **triggered**, not that the new runtime is already healthy. Render may still be building or waiting behind another deployment.

## Runtime verification

After Render reports the service as live, verify at minimum:

```text
https://plasma-6zz7.onrender.com/api/health/ready
```

For release acceptance, also verify the intended Production / Engineering routes and Mock Runtime behavior. A Render Mock deployment is software acceptance only and is not Z2, FPGA, electrical, socket, or physical IC validation.

## Security

Treat the Deploy Hook URL as a credential. Anyone with the URL can trigger deployments. If the URL is exposed, regenerate the hook in Render and update the local operator config.
