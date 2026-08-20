# Plasma Integration Host Deployment Guide

This guide documents the deployment contract for the Plasma integration host without publishing account names, private DNS names, or workstation-specific absolute paths.

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

`plasmactl` is the operational entry point. It is intentionally separate from the PPU programming CLI named `plasma`.

## 2. Repository location

The repository location is deployment configuration, not a public product contract. In examples below, use:

```bash
export PLASMA_REPO=/path/to/plasma
cd "$PLASMA_REPO"
```

Do not publish a developer username, home-directory name, private hostname, or private overlay-network address in shared documentation.

## 3. First install

```bash
cd "$PLASMA_REPO"
git status
git pull --ff-only origin main
chmod +x scripts/plasmactl
./scripts/plasmactl install
```

The installer creates or uses the Python environment, installs dependencies, runs `npm ci`, creates persistent deployment configuration, generates user-level systemd units, and creates the `plasmactl` command link. Services are enabled according to deployment configuration but are not started automatically during initial install.

## 4. Runtime services

| systemd unit | Default port | Operator name / role |
|---|---:|---|
| `plasma-server.service` | 9900 | **Plasma PPU Programming Server** — Protocol v3.3 / `PLASMA33` TCP Server |
| `plasma-web.service` | 18080 | **Plasma Web REST Gateway** — Web REST API Contract v3; optional Engineering Mock Provider host |
| `plasma-vite.service` | 5173 | Plasma PPU Console development/demo Web runtime |
| `plasma-manager.service` | 18180 | **Plasma Manager** — optional read-only fleet control plane |

The first three services are the PPU/integration baseline. `plasma-manager.service` is opt-in and is not required for standalone PPU execution. The Engineering Mock Provider is also opt-in but hosted inside `plasma-web.service`; it is not a separate systemd service.

The Plasma Server canonical wire protocol is v3.3 (`PLASMA33`, one-based `site_id = 1..N`). Current development runtime does not maintain retired v3.1/v3.2 Programmer/Channel compatibility adapters.

The Plasma Web REST Gateway uses Python standard-library `ThreadingHTTPServer` and REST polling. It is not FastAPI and does not use WebSocket.

## 5. Normal deployment

```bash
plasmactl deploy
```

The deployment contract is:

- refuse update when the working tree contains uncommitted changes;
- refuse update when the integration host contains local unpublished commits;
- use fast-forward only;
- synchronize dependencies only when definitions change;
- re-exec the updated `plasmactl` after fast-forward;
- run validation before restart;
- regenerate systemd units before start/restart;
- perform health checks after restart;
- start/restart Manager only when `PLASMA_MANAGER_ENABLED=1`;
- validate Manager YAML before activating an enabled Manager service;
- add Engineering Mock Provider Gateway arguments only when `PLASMA_ENGINEERING_MOCK_ENABLED=1`;
- probe `/api/engineering/targets` after restart when Engineering Mock Provider is enabled.

A failed validation must not replace a healthy running service with an unvalidated revision.

## 6. Remote operations

Remote access details are operator-local configuration. Shared documentation uses an SSH alias:

```bash
ssh <integration-host-alias> 'plasmactl status'
ssh <integration-host-alias> 'plasmactl update'
ssh <integration-host-alias> 'plasmactl deploy'
ssh -t <integration-host-alias> 'plasmactl logs'
```

## 7. Persistent deployment configuration

The persistent deployment file is:

```text
$HOME/.config/plasma/plasmactl.env
```

The current schema is v4. Generic example:

```bash
PLASMA_CONFIG_VERSION=4
PLASMA_REPO=/path/to/plasma
PLASMA_BRANCH=main
PLASMA_NPM=/path/to/npm
PLASMA_UV=/path/to/uv
PLASMA_GATEWAY_HOST=0.0.0.0
PLASMA_GATEWAY_PORT=18080
PLASMA_CORS_ORIGIN='*'
PLASMA_VITE_HOST=127.0.0.1
PLASMA_VITE_PORT=5173
PLASMA_PUBLIC_API_URL=https://example.invalid
PLASMA_MANAGER_ENABLED=0
PLASMA_MANAGER_CONFIG=/absolute/operator/local/path/manager.yaml
PLASMA_ENGINEERING_MOCK_ENABLED=0
PLASMA_ENGINEERING_MOCK_ROOT=/absolute/operator/local/state/engineering-mock
```

The Web Console appends API paths to the configured API Base; do not append `/api` to the base value itself.

`PLASMA_MANAGER_ENABLED=0` is the default so upgrading a standalone PPU/integration host cannot accidentally create a fleet-control dependency. `PLASMA_ENGINEERING_MOCK_ENABLED=0` is also the default; simulation must be explicit.

Runtime output/log state and Manager registry/config belong outside the Git worktree.

## 8. Migration and reconciliation

Persistent deployment configuration survives source upgrades. Deployment therefore distinguishes generated defaults from explicit operator overrides.

Policy:

- known obsolete generated defaults may migrate only at a defined configuration-schema transition;
- unknown/custom values are preserved as explicit operator overrides;
- current schema completeness checks append only missing assignments and preserve existing operator values;
- reconciliation is idempotent;
- a configuration schema newer than the running `plasmactl` supports is rejected rather than mutated;
- generated systemd units are derived state and regenerated from validated configuration;
- disabling optional Manager/Engineering Mock features removes them from the relevant managed runtime behavior.

## 9. Contract and validation boundary

Deployment health proves that the selected software revision starts and its configured service/API health checks pass on the integration host. It does **not** prove Z2 FPGA behavior, electrical safety, real IC programming, socket lifetime, or production validation.

Current software contracts to keep aligned during deployment are:

```text
Web REST API Contract v3   # Browser/external-facing input API
Plasma Protocol v3.3       # internal execution wire contract
Fleet Contract v1          # optional Manager-facing PPU observation contract
```
