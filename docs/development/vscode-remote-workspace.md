# Plasma VS Code Remote Workspace Standard

## 1. Purpose

Plasma uses one primary Linux engineering workspace on SWPC and multiple VS Code client machines.
The goal is to keep the deterministic toolchain in one place instead of maintaining different
Python, Verilator, cocotb, Node, and Vivado installations on every client computer.

GitHub remains the source of truth for published repository history. SWPC is the primary active
integration/development workspace used by VS Code Remote - SSH.

## 2. Machine roles

| Machine | Role | Normal Plasma access | Local special capability |
|---|---|---|---|
| SWPC (Linux) | Primary development and integration host | Local repository `/storage/projects/plasma` | Verilator, cocotb, pytest, Python environments, Node/Web tools, Vivado |
| Mac | Primary engineering client | VS Code Remote - SSH to SWPC | Ollama and optional local-AI coding tools |
| SHNB (Dell) | Portable engineering client | VS Code Remote - SSH to SWPC | Optional standalone Windows/Vivado experiments only |
| DESKTOP-1 | Company thin client | VS Code Remote - SSH to SWPC | Keep local Plasma footprint minimal |

The normal development path is therefore:

```text
Mac / SHNB / DESKTOP-1
        |
        | VS Code Remote - SSH
        v
       SWPC
/storage/projects/plasma
        |
        +-- Git / GitHub
        +-- Python environments
        +-- Verilator / cocotb
        +-- Web toolchain
        +-- Vivado
```

Client machines do not need a second normal Plasma clone or duplicate FPGA/Python toolchain merely
to edit and verify code. A local clone is allowed for a specific isolated experiment, but it is not
the standard daily workflow.

## 3. VS Code repository configuration

The repository owns these shared files:

```text
.vscode/
├── tasks.json       # executable project actions
├── extensions.json  # recommended extensions
└── settings.json    # project-level engineering settings
```

Personal preferences such as theme, font, window layout, and machine-specific AI configuration do
not belong in repository workspace settings.

### 3.1 Recommended extensions

The repository recommends:

- `ms-vscode-remote.remote-ssh` — Remote - SSH client connection.
- `eirikpre.systemverilog` — SystemVerilog editing/navigation support.
- `surfer-project.surfer` — VCD/FST/GHW waveform viewing.
- `ms-python.python` — Python support.
- `ms-python.vscode-pylance` — Python language services.
- `dbaeumer.vscode-eslint` — Web/TypeScript lint integration.
- `esbenp.prettier-vscode` — Web/TypeScript formatting support.

Continue, Cline, Ollama integrations, themes, and other personal extensions are intentionally not
workspace recommendations. In particular, local-AI extensions on the Mac are machine-specific and
must not become a dependency for SHNB or DESKTOP-1.

## 4. FPGA workflow from VS Code

The SystemVerilog extension is configured not to compile a single file automatically on save/open.
Plasma FPGA compilation and verification must go through the repository target workflow so that
source dependencies and the correct top module are respected.

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

Do not re-enable `systemverilog.compileOnSave` as a substitute for this workflow. Single-file
compilation is not a correct build model once a target contains multiple RTL sources.

## 5. First use on a client machine

### Mac

1. Install VS Code and Remote - SSH locally.
2. Ensure SSH/Tailscale access to SWPC works.
3. Connect to SWPC with VS Code Remote - SSH.
4. Open `/storage/projects/plasma`.
5. Accept the workspace recommended extensions.
6. Open an RTL file and use `Cmd+Shift+B` for the default FPGA Verify task.

Ollama and local-AI extensions remain on the Mac. The source workspace and deterministic build tools
remain on SWPC.

### SHNB / DESKTOP-1

1. Install VS Code and Remote - SSH locally.
2. Connect to SWPC.
3. Open `/storage/projects/plasma`.
4. Accept the workspace recommended extensions.
5. Use `Ctrl+Shift+B` for the default FPGA Verify task.

DESKTOP-1 should remain a thin client where practical. Do not copy credentials, firmware artifacts,
or a complete local FPGA toolchain onto a company-managed computer without a specific need and
appropriate policy approval.

## 6. Python environment boundary

Plasma intentionally has separate Python environments:

```text
pl/.venv/                 FPGA verification (cocotb/pytest)
software/python/.venv/    Plasma software/server tests
```

The workspace does not pin one global Python interpreter because doing so would incorrectly make one
of these environments authoritative for the entire repository.

Use the FPGA VS Code tasks for FPGA verification. Use the software Python environment when working
under `software/python/`.

## 7. What is centralized and what is not

Centralized on SWPC:

- repository working tree used for normal interactive development
- FPGA simulation toolchain
- Python project environments
- Web build/test environment
- Vivado integration environment

Shared through GitHub:

- source code
- `.vscode` project configuration
- documentation
- target manifests and tests
- reviewed branch/PR history

Kept per client machine:

- SSH private keys
- Tailscale client state
- VS Code theme/font/layout
- Mac Ollama models and local-AI configuration
- company-device-specific security settings

This separation minimizes configuration drift while keeping client-specific credentials and personal
tooling out of the repository.
