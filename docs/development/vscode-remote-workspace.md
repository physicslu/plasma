# Plasma VS Code Remote Workspace Standard

## 1. Purpose

Plasma uses one primary Linux integration workspace and multiple VS Code client machines. The goal is to keep the deterministic toolchain in one place instead of maintaining divergent Python, Verilator, cocotb, Node, and Vivado installations on every client.

GitHub remains the source of truth for published repository history. The integration host is the primary active engineering workspace used through VS Code Remote-SSH.

## 2. Machine roles

| Role | Normal Plasma access | Responsibility |
|---|---|---|
| Integration Host | Local `$PLASMA_REPO` | Verilator, cocotb, pytest, Python environments, Node/Web tools, Vivado |
| Engineering Client | VS Code Remote-SSH | Interactive editing, review, optional local AI tooling |
| Portable Client | VS Code Remote-SSH | Remote development and bounded platform-specific experiments |
| Managed Thin Client | VS Code Remote-SSH | Minimal local footprint and minimal local data retention |

Normal development path:

```text
Engineering clients
        |
        | VS Code Remote-SSH
        v
Integration Host
    $PLASMA_REPO
        |
        +-- Git / GitHub
        +-- Python environments
        +-- Verilator / cocotb
        +-- Web toolchain
        +-- Vivado
```

Private machine names, real SSH usernames, private DNS/VPN identifiers, and site-specific absolute paths are intentionally not part of the public workspace standard.

## 3. Shared VS Code repository configuration

The repository owns:

```text
.vscode/
├── tasks.json
├── extensions.json
└── settings.json
```

Personal preferences such as theme, font, window layout, SSH targets, credentials, and machine-specific AI configuration do not belong in shared workspace settings.

Recommended extension categories include Remote-SSH, SystemVerilog support, waveform viewing, Python/Pylance, ESLint, and Prettier.

## 4. FPGA workflow

The SystemVerilog extension must not substitute single-file compile-on-save for Plasma's target-based build model.

```text
Open an RTL file
      |
      | Cmd+Shift+B on macOS
      | Ctrl+Shift+B on Windows/Linux
      v
.vscode/tasks.json
      |
      v
source pl/env.sh
      |
      v
python pl/tools/fpga.py verify --file <current-file>
      |
      +-- resolve pl/targets/*.toml
      +-- Verilator lint
      +-- cocotb / pytest regression
```

A target may contain multiple RTL sources, constraints, and tests. Verification must therefore resolve the target rather than treating the current source file as an isolated build unit.

## 5. First use on a client

1. Install VS Code and Remote-SSH locally.
2. Establish an approved SSH/private-network path to the integration host.
3. Connect using an operator-local SSH alias such as `<integration-host-alias>`.
4. Open `$PLASMA_REPO`.
5. Accept the workspace recommended extensions.
6. Use the default FPGA Verify task for RTL validation.

The actual hostname, username, private IP, VPN/Tailscale hostname, and SSH key path belong in the operator's local SSH configuration, not the public repository.

## 6. Python environment boundary

Plasma intentionally has separate Python environments:

```text
pl/.venv/                 FPGA verification
software/python/.venv/    Plasma software/server tests
```

Do not pin one global Python interpreter as authoritative for the entire repository. Use the FPGA tasks for FPGA verification and the software environment for `software/python/` work.

## 7. Centralized versus per-client state

Centralized on the integration host:

- normal repository working tree
- FPGA simulation toolchain
- Python environments
- Web build/test environment
- Vivado integration environment

Shared through GitHub:

- source code
- project `.vscode` configuration
- architecture/development documentation
- target manifests and tests
- reviewed branch/PR history

Kept per client/operator:

- SSH private keys
- private-network client state
- SSH host aliases and usernames
- personal editor/UI settings
- local AI models and machine-specific AI configuration
- managed-device security settings

This separation minimizes configuration drift while keeping private infrastructure and credentials out of the repository.
