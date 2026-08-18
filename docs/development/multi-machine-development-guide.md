# Plasma Multi-Machine Development Guide

> Project: `physicslu/plasma`
> Standard: one primary Linux integration workspace + multiple VS Code Remote-SSH clients

## 1. Development model

Plasma uses GitHub as the publication/integration source of truth and one primary Linux host as the deterministic development and integration workspace.

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

## 2. Role boundaries

| Role | Normal access | Responsibility |
|---|---|---|
| Integration Host | Local repository | Deterministic build/test, Vivado integration, shared runtime validation |
| Engineering Client | VS Code Remote-SSH | Interactive editing, review, optional local AI tooling |
| Portable Client | VS Code Remote-SSH | Remote engineering work; isolated local experiments only when necessary |
| Managed Thin Client | VS Code Remote-SSH | Minimal local footprint; avoid storing source artifacts or credentials unnecessarily |
| Z2 Target | Approved target access | Embedded runtime, PS/PL integration, electrical and real-device validation |

Machine names, usernames, private DNS names, VPN/Tailscale identifiers, and physical-device inventory belong in operator-local configuration or protected infrastructure records. They are not part of the public Plasma architecture contract.

## 3. Repository location

The absolute repository path is site-specific. Public examples use:

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

Important Python environment boundary:

```text
pl/.venv/                 FPGA verification
software/python/.venv/    Plasma software/server
```

Do not merge these environments merely to make one editor setting convenient.

## 4. Client setup

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

The real SSH username, hostname, private IP, overlay-network hostname, and key path must remain outside public repository documentation.

## 5. VS Code workspace standard

The repository provides shared project configuration:

```text
.vscode/tasks.json
.vscode/extensions.json
.vscode/settings.json
```

Project configuration may define deterministic engineering behavior. Personal themes, fonts, local AI credentials, machine names, and SSH connection details must remain per-client settings.

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

## 6. Git workflow

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

Routine engineering may continue through implementation, tests, commits, push, PR creation, and CI repair. Merge to `main`, deployment/restart, hardware-affecting operations, and destructive history changes remain explicit approval gates defined by `AGENTS.md`.

Do not use `git reset --hard`, `git clean -fd`, or force push as ordinary synchronization tools.

## 7. FPGA development

Preferred entry point:

```bash
cd "$PLASMA_REPO"
source pl/env.sh
python pl/tools/fpga.py list
python pl/tools/fpga.py verify <target>
```

Target manifests live under `pl/targets/`; generated build artifacts live under `pl/build/` and are not repository source of truth.

Verilator/cocotb PASS does not prove Vivado timing closure or real hardware behavior.

## 8. Python development

FPGA verification uses:

```text
pl/.venv/
```

Plasma software uses:

```text
software/python/.venv/
```

Software tests:

```bash
cd "$PLASMA_REPO/software/python"
.venv/bin/python -m pytest -q
```

## 9. Web development

```bash
cd "$PLASMA_REPO/software/web"
npm run lint
npm test
npm run validate:artifact
```

Use `package.json` and `AGENTS.md` as the source of truth for the current Web toolchain and validation contract.

## 10. Runtime ports

The current development/runtime service contract is public and may remain documented:

| Service | Default port |
|---|---:|
| Plasma Server | 9900 |
| Python HTTP REST Gateway | 18080 |
| Web Console development/demo service | 5173 |

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
- personal usernames and email addresses in documentation
- private DNS/VPN/Tailscale hostnames
- workstation-specific absolute home paths
- customer firmware and customer credentials
- production certificates/tokens

Generic architecture, service contracts, port assignments, target manifests, tests, and public API behavior may remain documented when they are intentionally part of the project interface.
