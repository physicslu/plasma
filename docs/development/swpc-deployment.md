# Plasma Integration Host Deployment Guide

This guide documents the deployment contract for the Plasma integration host without publishing site-specific account names, private DNS names, or workstation-specific absolute paths.

## 1. Deployment model

```text
GitHub main
  -> integration host fast-forward update
  -> re-exec updated plasmactl
  -> validation
  -> configuration migration / systemd reconciliation
  -> restart
  -> health check
```

`plasmactl` is the operational entry point. It is intentionally separate from the programmer CLI named `plasma`.

## 2. Repository location

The repository location is site configuration, not a public contract. In examples below, use:

```bash
export PLASMA_REPO=/path/to/plasma
cd "$PLASMA_REPO"
```

Do not publish a developer username, home-directory name, private hostname, or private overlay-network address in shared documentation.

## 3. First install

Update the repository:

```bash
cd "$PLASMA_REPO"
git status
git pull --ff-only origin main
```

Then install the user services:

```bash
chmod +x scripts/plasmactl
./scripts/plasmactl install
```

The installer creates or uses the Python environment, installs dependencies, runs `npm ci`, creates the persistent deployment configuration, generates user-level systemd units, and creates the `plasmactl` command link. Services are enabled but are not started automatically during the initial install.

## 4. Runtime services

The current service contract is intentionally public because clients and tests depend on it:

| systemd unit | Default port | Role |
|---|---:|---|
| `plasma-server.service` | 9900 | Plasma v3.1 TCP server |
| `plasma-web.service` | 18080 | Python HTTP REST Gateway |
| `plasma-vite.service` | 5173 | Web Console development/demo service |

These ports are architectural defaults, not credentials. Network exposure must still be controlled by firewall, private-network policy, or reverse proxy.

## 5. Normal deployment

```bash
plasmactl deploy
```

The deployment contract is:

- refuse update when the working tree contains uncommitted changes;
- refuse update when the integration host contains local unpublished commits;
- use fast-forward only;
- synchronize dependencies only when their definitions change;
- re-exec the updated `plasmactl` after the fast-forward;
- run validation before restart;
- regenerate systemd units before start/restart;
- perform health checks after restart.

A failed validation must not replace a healthy running service with an unvalidated revision.

## 6. Remote operations

Remote access details are operator-local configuration. Shared documentation uses an SSH alias instead of publishing a real account or hostname:

```bash
ssh <integration-host-alias> 'plasmactl status'
ssh <integration-host-alias> 'plasmactl update'
ssh <integration-host-alias> 'plasmactl deploy'
ssh -t <integration-host-alias> 'plasmactl logs'
```

The actual SSH `HostName`, `User`, private-network address, keys, and ACL policy belong in the operator's local SSH configuration or protected infrastructure documentation, not in this public repository.

For non-interactive SSH, ensure `$HOME/.local/bin` is available before the shell's early return:

```bash
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
```

The expected command location is expressed generically as:

```text
$HOME/.local/bin/plasmactl
```

## 7. Persistent deployment configuration

The persistent deployment file is:

```text
$HOME/.config/plasma/plasmactl.env
```

The current schema is v2. A public example should use placeholders for machine-specific paths:

```bash
PLASMA_CONFIG_VERSION=2
PLASMA_REPO=/path/to/plasma
PLASMA_BRANCH=main
PLASMA_NPM=/path/to/npm
PLASMA_UV=/path/to/uv
PLASMA_GATEWAY_HOST=0.0.0.0
PLASMA_GATEWAY_PORT=18080
PLASMA_CORS_ORIGIN='*'
PLASMA_VITE_HOST=127.0.0.1
PLASMA_VITE_PORT=5173
PLASMA_PUBLIC_API_URL=https://plasma.open4th.com
```

The Web Console appends API paths to the configured API Base; do not append `/api` to the base value itself.

## 8. Migration and reconciliation

Persistent configuration survives source-code upgrades. Therefore deployment must distinguish an old generated value from an intentional operator override.

The migration policy is:

- known obsolete historical defaults may migrate to the current default;
- unknown/custom values are preserved as explicit operator overrides;
- already-versioned configuration is not guessed or silently rewritten;
- generated systemd units are derived state and are regenerated from validated configuration.

The specific private addresses used by an individual development site are intentionally not documented here. Compatibility logic in executable source remains the source of truth for any historical migration values that must still be recognized.

## 9. Public routing boundary

The public Web Console endpoint may be documented when it is intentionally public. Internal maintenance routes, private overlay-network hostnames, and administrative gateway addresses must not be copied into public documentation.

A reverse proxy may route the public Web Console to the local Vite service, with `/api/*` forwarded to the REST Gateway. The Gateway should not be exposed directly to the public Internet without an explicit security design.

## 10. Troubleshooting

```bash
plasmactl status
plasmactl ports
plasmactl logs server
plasmactl logs web
plasmactl logs vite
systemctl --user status plasma-server plasma-web plasma-vite --no-pager
```

If a port is already in use, identify the owning process before stopping anything. Do not use broad process-kill commands as a substitute for diagnosis.
