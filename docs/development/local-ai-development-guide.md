# Plasma Local AI Development Guide

> Project: `physicslu/plasma`
> Scope: local AI + VS Code + Continue/Cline + Ollama + Remote-SSH

## 1. Purpose

This guide describes a reusable local-AI development pattern without publishing a developer's personal machine name, account name, private hostname, or home-directory layout.

The intended topology is:

```text
Apple Silicon engineering client
├── Ollama
├── VS Code
│   ├── Continue
│   └── Cline
└── Remote-SSH
     └── Integration Host
          └── $PLASMA_REPO
```

`AGENTS.md` remains the authoritative repository contract for AI-assisted code changes.

## 2. Recommended AI role separation

Use Continue for interactive work such as code completion, code explanation, codebase search, selected-code review, and small edits.

Use Cline for bounded engineering workflows such as:

```text
read AGENTS.md
  -> inspect repository/tests
  -> modify code
  -> run relevant validation
  -> inspect failures
  -> repair
  -> review git diff
  -> report result
```

Protected actions remain governed by `AGENTS.md`, including merge-to-main, deployment/restart, hardware-affecting operations, and destructive Git-history changes.

## 3. Local Ollama models

A practical Plasma setup may use:

| Role | Example model | Purpose |
|---|---|---|
| Chat / Edit / Apply / Agent | `qwen3.8:27b-mlx` | Main reasoning and coding model |
| Autocomplete | `qwen2.5-coder:1.5b` | Low-latency inline completion |
| Embeddings | `qwen3-embedding:0.6b` | Semantic codebase indexing |

Example installation:

```bash
ollama pull qwen3.8:27b-mlx
ollama pull qwen2.5-coder:1.5b
ollama pull qwen3-embedding:0.6b
```

For Apple Silicon systems with sufficient unified memory, a reasonable starting policy is 64K context for normal Continue work and 128K for bounded agent tasks. Treat these as tuning values, not product requirements.

## 4. Continue configuration principles

Continue configuration is machine-local and normally belongs under the user's home configuration directory, not in this repository.

A reusable example should avoid personal labels and credentials:

```yaml
name: Plasma Development
version: 1.0.0
schema: v1

models:
  - name: Plasma Main Model
    provider: ollama
    model: qwen3.8:27b-mlx
    apiBase: http://127.0.0.1:11434
    roles: [chat, edit, apply]
    defaultCompletionOptions:
      contextLength: 65536
      maxTokens: 4096
      temperature: 0.1
      topP: 0.9

  - name: Plasma Autocomplete
    provider: ollama
    model: qwen2.5-coder:1.5b
    apiBase: http://127.0.0.1:11434
    roles: [autocomplete]

  - name: Plasma Embeddings
    provider: ollama
    model: qwen3-embedding:0.6b
    apiBase: http://127.0.0.1:11434
    roles: [embed]
```

Do not commit local API keys, user-specific configuration, SSH configuration, or machine inventory merely to reproduce an AI setup.

## 5. Cline configuration principles

Recommended baseline:

```text
API Provider:        Ollama
Base URL:            http://127.0.0.1:11434
Model:               qwen3.8:27b-mlx
Use Compact Prompt:  ON
Target context:      131072 tokens
```

A bounded permission profile is preferred:

```text
Read project files     ON
Edit project files     ON
Execute safe commands  ON

Read all files         OFF
Edit all files         OFF
Execute all commands   OFF
```

Cline permissions are a technical capability boundary; `AGENTS.md` remains the repository policy boundary.

## 6. Remote-SSH and local Ollama

A VS Code extension running on a Remote-SSH extension host may interpret `127.0.0.1` as the remote integration host rather than the local engineering client.

A reverse SSH tunnel is preferable to exposing Ollama directly to a LAN or the Internet.

Use an operator-local SSH alias:

```bash
ssh -N -R 11434:127.0.0.1:11434 <integration-host-alias>
```

Example local SSH configuration:

```sshconfig
Host plasma-integration
    HostName <integration-host>
    User <developer>
    RemoteForward 11434 127.0.0.1:11434
    ExitOnForwardFailure yes
```

The actual username, hostname, private IP, VPN/Tailscale hostname, SSH key path, and ACL configuration must remain outside the public repository.

Verify the tunnel from the remote integration host with:

```bash
curl http://127.0.0.1:11434/api/tags
```

If remote port 11434 is occupied, choose another remote port and update the remote-side provider URL accordingly.

## 7. Opening the Plasma workspace

Connect to the integration host using the operator-local SSH alias and open the configured repository root:

```text
$PLASMA_REPO
```

Before code-changing work:

```bash
cd "$PLASMA_REPO"
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
```

Do not overwrite unrelated user changes.

## 8. Plasma-specific AI invariants

AI-generated changes must preserve the same engineering constraints as human-generated changes:

- inspect the current repository before making Plasma-specific claims;
- preserve independent channel execution unless a real shared resource requires synchronization;
- scope cancellation to the intended job/channel;
- do not invent hardware register addresses, timing, pin mappings, protocols, or API behavior;
- add or update regression tests when behavior changes;
- report what was actually validated;
- never claim SWPC/Z2/hardware validation unless it was actually performed under the approval policy.

## 9. Information classification

Keep machine-specific operational data out of public documentation:

```text
Public repository
  -> generic AI architecture
  -> model roles and reproducible examples
  -> repository policy and validation workflow

Operator-local / protected documentation
  -> real SSH username and hostname
  -> private overlay-network identifiers
  -> workstation inventory
  -> local absolute paths
  -> credentials, tokens, keys
```

The objective is reproducibility without turning a public source repository into an infrastructure inventory.
