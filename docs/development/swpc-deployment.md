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

The installer creates or uses the Python environment, installs dependencies, runs `npm ci`, creates persistent deployment configuration, generates user-level systemd units, and creates the `plasmactl` command link. Services are enabled according to the deployment configuration but are not started automatically during the initial install.

## 4. Runtime services

The current service contract is:

| systemd unit | Default port | Operator name / role |
|---|---:|---|
| `plasma-server.service` | 9900 | **Plasma PPU Programming Server** — Protocol v3.2 TCP Server |
| `plasma-web.service` | 18080 | **Plasma Web REST Gateway** — HTTP REST boundary; also hosts the optional Engineering Mock PPU Provider |
| `plasma-vite.service` | 5173 | Plasma PPU Console development/demo Web runtime |
| `plasma-manager.service` | 18180 | **Plasma Manager** — optional read-only fleet control plane |

The first three services are the PPU/integration baseline. `plasma-manager.service` is opt-in and is not required for standalone PPU execution. The Engineering Mock PPU Provider is also opt-in, but it is hosted inside `plasma-web.service`; it is not a separate systemd service.

The Plasma Server canonical protocol is v3.2 (`PLASMA32`, one-based `site_id = 1..N`). Protocol v3.1 remains only as an explicit compatibility adapter.

The Plasma Web REST Gateway currently uses Python standard-library `ThreadingHTTPServer` and REST polling. It is not FastAPI and does not currently use WebSocket.

The Manager also uses the Python standard-library HTTP server. Its default port is 18180, but the actual bind host/port come from the operator-local Manager YAML. Its systemd unit depends on network availability only; it does not require a local PPU Gateway on the same machine.

These ports are architectural/deployment defaults, not credentials. Network exposure still requires firewall, private-network, reverse-proxy, authentication, and authorization decisions appropriate to the environment.

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
- perform health checks after restart;
- start/restart Manager only when `PLASMA_MANAGER_ENABLED=1`;
- validate the Manager YAML before activating an enabled Manager service;
- add Engineering Mock Provider Gateway arguments only when `PLASMA_ENGINEERING_MOCK_ENABLED=1`;
- probe `/api/engineering/targets` after restart when the Engineering Mock Provider is enabled.

A failed validation must not replace a healthy running service with an unvalidated revision.

## 6. Remote operations

Remote access details are operator-local configuration. Shared documentation uses an SSH alias instead of publishing a real account or hostname:

```bash
ssh <integration-host-alias> 'plasmactl status'
ssh <integration-host-alias> 'plasmactl update'
ssh <integration-host-alias> 'plasmactl deploy'
ssh -t <integration-host-alias> 'plasmactl logs'
```

The actual SSH `HostName`, `User`, private-network address, keys, and ACL policy belong in operator-local configuration or protected infrastructure documentation.

For non-interactive SSH, ensure `$HOME/.local/bin` is available before the shell's early return:

```bash
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) export PATH="$HOME/.local/bin:$PATH" ;;
esac
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

`PLASMA_MANAGER_ENABLED=0` is the default so upgrading an existing standalone PPU/integration host cannot accidentally create a new fleet-control dependency. Setting it to `1` is an explicit operational choice.

`PLASMA_ENGINEERING_MOCK_ENABLED=0` is also the default. Enabling simulation must be explicit because the same Engineering UI and REST contract will later be used by real PPU providers.

If `PLASMA_ENGINEERING_MOCK_ROOT` is not explicitly configured, `plasmactl` resolves it under `$XDG_STATE_HOME/plasma/engineering-mock`, or `$HOME/.local/state/plasma/engineering-mock` when `XDG_STATE_HOME` is unset. Runtime output/log state is intentionally kept outside the Git worktree; `plasmactl` rejects an Engineering Mock root located inside the repository because that would contaminate `git status` and break clean-tree deployment gates.

The Manager registry belongs outside the Git worktree. A minimal local-only integration configuration is:

```yaml
manager:
  host: 127.0.0.1
  port: 18180
  request_timeout_s: 2.0

ppus:
  - alias: local-ppu
    endpoint: http://127.0.0.1:18080
```

Do not use repository `manager.example.yaml` as persistent site state. It contains example endpoints and is intended for documentation/tests.

## 8. Migration and reconciliation

Persistent configuration survives source-code upgrades. Therefore deployment must distinguish an old generated value from an intentional operator override.

Policy:

- known obsolete historical defaults may migrate to the current default only at the schema version where that migration is defined;
- unknown/custom values are preserved as explicit operator overrides;
- schema v2 -> v3 adds Manager settings with Manager disabled by default and does not reinterpret an already-versioned API Base;
- schema v3 -> v4 adds Engineering Mock Provider deployment settings with simulation disabled by default and a state root outside the Git worktree;
- a current schema marker does not suppress completeness checks: if a deployment field is missing, `plasmactl` appends only the missing assignment using the already-resolved value and preserves every explicit operator value already present;
- completeness reconciliation is idempotent and must not create duplicate assignments on repeated `restart` / `deploy` runs;
- a configuration schema newer than the running `plasmactl` supports is rejected rather than mutated by an older deployment tool;
- generated systemd units are derived state and are regenerated from validated configuration;
- disabling Manager removes it from the managed start/restart service set and stops any stale Manager process during runtime reconciliation;
- disabling Engineering Mock removes the `--engineering-mock` arguments from the regenerated `plasma-web.service` unit on the next reconciliation/restart.

This distinction matters operationally: a version number is metadata, not proof that every field introduced by that schema is physically present. Runtime defaults may keep a service safe, but persistent configuration still needs deterministic reconciliation so the next operator sees the same state that the runtime is using.

Systemd Description values are also generated state. After terminology changes, `plasmactl restart` / `deploy` reconciles the units so new journal entries use the canonical operator names.

## 9. Manager opt-in activation

Prepare the operator-local Manager YAML first, then edit `plasmactl.env`:

```bash
PLASMA_MANAGER_ENABLED=1
PLASMA_MANAGER_CONFIG=/absolute/operator/local/path/manager.yaml
```

`plasmactl restart` or `plasmactl deploy` then validates that file, regenerates the unit, enables `plasma-manager.service`, restarts the configured service set, and checks Manager liveness.

This activation changes shared runtime state and remains an explicit deployment approval gate. A source-code merge alone must not silently enable Manager.

To return to standalone operation, set:

```bash
PLASMA_MANAGER_ENABLED=0
```

and reconcile/restart. Local PPU programming remains independent of Manager in either mode.

## 10. Engineering Mock Provider opt-in activation

The Engineering Mock Provider is a server-side simulation provider used by `Engineering Mode -> Programming`. It reports the mock Facility/PPU/Site catalog from Python and executes E/P/V/R jobs through real in-process `PlasmaServer` runtimes backed by `MockInterface`.

To enable it on an integration/development host, edit `plasmactl.env`:

```bash
PLASMA_ENGINEERING_MOCK_ENABLED=1
PLASMA_ENGINEERING_MOCK_ROOT=/absolute/operator/local/state/engineering-mock
```

The root must be absolute and must not live inside the Plasma Git worktree. Omitting an explicit root is valid; the safe XDG state default will be persisted during configuration migration.

Then reconcile and restart:

```bash
plasmactl restart
```

The regenerated `plasma-web.service` adds:

```text
--engineering-mock --engineering-mock-root <configured-root>
```

After restart, `plasmactl` verifies:

```text
GET http://127.0.0.1:<gateway-port>/api/engineering/targets
```

The Engineering UI should then receive the Python-owned Mock catalog rather than showing `Engineering PPU provider is not enabled`.

To disable simulation again:

```bash
PLASMA_ENGINEERING_MOCK_ENABLED=0
plasmactl restart
```

This provider is an Engineering execution facility. It does not grant Plasma Manager write authority, does not enter the Production Manager registry, and does not claim Z2/FPGA/electrical/real-IC validation.

## 11. Public routing boundary

A reverse proxy may route the Web Console to the local Vite service, with `/api/*` forwarded to the Plasma Web REST Gateway. The Gateway should not be exposed directly to the public Internet without an explicit security design.

When Engineering Mock is enabled, its `/api/engineering/targets/*` execution routes are exposed through the same Gateway boundary. Treat that as an explicit development/integration-host capability rather than harmless static demo data.

The current Manager is also not intended for direct public-Internet exposure. Before remote command routing or broader access is added, authentication/authorization and transport security require an explicit architecture decision.

A transient browser polling timeout does not by itself prove that the Gateway process crashed. Diagnose browser/network/proxy, local Gateway request handling, and Plasma Server dependencies separately.

## 12. Troubleshooting

```bash
plasmactl status
plasmactl ports
plasmactl logs server
plasmactl logs web
plasmactl logs vite
plasmactl logs manager
systemctl --user status plasma-server plasma-web plasma-vite plasma-manager --no-pager
```

`plasmactl status` reports both Manager and Engineering Mock opt-in state. When Engineering Mock is enabled, the status line also shows its persistent state root.

To validate operator-visible service naming:

```bash
systemctl --user show plasma-server.service -p Description --value
systemctl --user show plasma-web.service -p Description --value
systemctl --user show plasma-manager.service -p Description --value
```

Expected values:

```text
Plasma PPU Programming Server
Plasma Web REST Gateway
Plasma Manager Read-only Fleet Control Plane
```

If a port is already in use, identify the owning process before stopping anything. Do not use broad process-kill commands as a substitute for diagnosis.
