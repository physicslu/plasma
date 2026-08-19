# Plasma Multi-Machine Development Guide

> Project: `physicslu/plasma`
> Standard: one primary Linux integration workspace + multiple VS Code Remote-SSH clients

## 1. Development model

Plasma uses GitHub as the publication/integration source of truth and one primary Linux integration host as the deterministic development workspace.

```text
                    GitHub
                      ^
                      |
                 branch / PR
                      |
             Integration Host
                $PLASMA_REPO
               /      |      \
              /       |       \
       Client A   Client B   Thin Client
          \          |          /
           +---- Remote SSH ----+

                      |
                      | approved target validation
                      v
                     Z2
```

The purpose is to avoid maintaining divergent Python, Verilator, cocotb, Node, and Vivado environments on every client computer.

## 2. Domain baseline

All new software/documentation uses:

```text
Facility -> PPU -> Site
SITE 1 .. SITE N
```

The canonical TCP wire contract is Plasma Protocol v3.2 (`PLASMA32`, one-based `site_id`). Protocol v3.1 zero-based `channel_id` exists only in explicit compatibility code/tests.

## 3. Role boundaries

| Role | Normal access | Responsibility |
|---|---|---|
| Integration Host | Local repository | Deterministic build/test, Vivado integration, shared runtime validation |
| Engineering Client | VS Code Remote-SSH | Interactive editing, review, optional local AI tooling |
| Portable Client | VS Code Remote-SSH | Remote engineering work; isolated local experiments only when necessary |
| Managed Thin Client | VS Code Remote-SSH | Minimal local footprint; avoid storing source artifacts or credentials unnecessarily |
| Z2 Target | Approved target access | Embedded runtime, PS/PL integration, electrical and real-device validation |

Machine names, usernames, private DNS names, VPN identifiers, and physical-device inventory belong in operator-local configuration or protected infrastructure records.

## 4. Repository location

The absolute repository path is deployment-specific. Public examples use:

```bash
export PLASMA_REPO=/path/to/plasma
cd "$PLASMA_REPO"
```

Repository layout:

```text
$PLASMA_REPO/
├── .vscode/
├── pl/
├── software/python/
├── software/web/
├── scripts/
└── docs/
```

Python environment boundary:

```text
pl/.venv/                 FPGA verification
software/python/.venv/    Plasma software/server
```

Do not merge these environments merely to make one editor setting convenient.

## 5. Client setup

A normal client needs only:

- Visual Studio Code
- OpenSSH client
- VS Code Remote-SSH
- an approved network path to the integration host

The client does not need a second normal installation of Verilator, cocotb, Plasma Python environments, Node/Web dependencies, or Vivado.

Connect using an operator-local SSH alias:

```text
Cmd/Ctrl + Shift + P
-> Remote-SSH: Connect to Host...
-> <integration-host-alias>
```

Then open `$PLASMA_REPO`.

## 6. VS Code workspace standard

The repository provides shared project configuration:

```text
.vscode/tasks.json
.vscode/extensions.json
.vscode/settings.json
```

Project configuration may define deterministic engineering behavior. Personal themes, fonts, local AI credentials, machine names, and SSH connection details remain per-client settings.

### FPGA workflow

```text
Open RTL
   |
   | Cmd/Ctrl + Shift + B
   v
FPGA: Verify Current Target
   |
   v
pl/env.sh
   |
   v
pl/tools/fpga.py
   |
   +-- target resolution
   +-- Verilator lint
   +-- cocotb / pytest
```

The build unit is a target manifest, not an arbitrary single `.sv` file.

## 7. Git workflow

Before code-changing work:

```bash
cd "$PLASMA_REPO"
git status -sb
git branch --show-current
git fetch origin main
```

Update a clean local `main` with:

```bash
git switch main
git pull --ff-only origin main
```

Create feature work on a separate branch:

```bash
git switch -c agent/<feature-name>
```

Routine engineering may continue through implementation, tests, commits, push, PR creation, and CI repair. Merge to `main`, deployment/restart, hardware-affecting operations, destructive history changes, and unresolved material architecture/security decisions remain approval gates defined by `AGENTS.md`.

Do not use `git reset --hard`, `git clean -fd`, or force push as ordinary synchronization tools.

## 8. Python development

Software tests:

```bash
cd "$PLASMA_REPO/software/python"
.venv/bin/python -m pytest -q
```

The Python domain is canonical PPU/Site. New code must not introduce `SITE 0` or treat v3.1 `channel_id` as numerically identical to v3.2 `site_id`.

## 9. Web development

```bash
cd "$PLASMA_REPO/software/web"
npm run lint
npm test
npm run validate:artifact
```

Use `package.json` and `AGENTS.md` as the source of truth for the current Web toolchain and validation contract.

The current UI is the **Plasma PPU Console**. It discovers PPU/Site topology dynamically from canonical status and sends one-based `site_id` requests.

## 10. Runtime services and ports

| Service | Default port | Role |
|---|---:|---|
| Plasma PPU Programming Server | 9900 | Plasma Protocol v3.2 TCP Server |
| Plasma Web REST Gateway | 18080 | HTTP REST boundary for the Web Console |
| Plasma PPU Console development/demo service | 5173 | Vite/Vinext Web runtime |

The current Gateway uses Python standard-library HTTP (`ThreadingHTTPServer`) and REST polling. It is not FastAPI and does not currently use WebSocket.

A port number is not a credential. The security boundary is whether that port is exposed to an untrusted network and what authentication/authorization protects it.

## 11. When a local clone is appropriate

A client-local clone is an exception for a defined use case such as an isolated experiment, offline work, or a platform-specific tool test.

When using one:

1. use a separate branch;
2. avoid concurrent edits to the same branch from multiple workspaces;
3. commit/push before transferring work between machines;
4. return final integration validation to the integration host;
5. never treat local build artifacts as repository source of truth.

## 12. Security boundary

Keep these out of the public repository:

- SSH private keys and credentials
- personal usernames and email addresses in public documentation
- private DNS/VPN hostnames
- workstation-specific absolute home paths
- customer firmware and customer credentials
- production certificates/tokens

Generic architecture, service contracts, port assignments, target manifests, tests, and public API behavior may remain documented when intentionally part of the project interface.
