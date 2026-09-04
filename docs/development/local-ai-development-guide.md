# Plasma Local AI Development Guide

> Project: `physicslu/plasma`
> Scope: local AI + VS Code + Continue/Cline + Ollama + Remote-SSH

## 1. Purpose

This guide describes a reusable local-AI development pattern without publishing a developer's personal machine name, account name, private hostname, or home-directory layout.

The intended topology is:

```text
Engineering client
├── Ollama
├── VS Code
│   ├── Continue
│   └── Cline
└── Remote-SSH
     └── Integration Host
          └── $PLASMA_REPO
```

`AGENTS.md` remains the authoritative repository contract for AI-assisted changes.

## 2. Plasma domain baseline

AI tools must use the canonical product/domain vocabulary:

```text
Facility -> PPU -> Site
SITE 1 .. SITE N
```

Protocol v3.3 is canonical (`PLASMA33`, one-based `site_id`). Retired zero-based Channel identity is not accepted by the current runtime. New code and current-guidance documentation must not invent `SITE 0`.

## 3. Recommended AI role separation

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

Protected actions remain governed by `AGENTS.md`, including merge-to-main, deployment/restart, hardware-affecting operations, destructive Git-history changes, and unresolved material architecture/security tradeoffs.

## 4. Local Ollama models

A practical setup may use:

| Role | Example model | Purpose |
|---|---|---|
| Chat / Edit / Apply / Agent | `qwen3.8:27b-mlx` | Main interactive reasoning model; for IC Support ingestion, use as a manufacturer-document-grounded specification candidate generator rather than a production-code authority |
| Autocomplete | `qwen2.5-coder:1.5b` | Low-latency inline completion |
| Embeddings | `qwen3-embedding:0.6b` | Semantic codebase indexing |

Example installation:

```bash
ollama pull qwen3.8:27b-mlx
ollama pull qwen2.5-coder:1.5b
ollama pull qwen3-embedding:0.6b
```

For Apple Silicon systems with sufficient unified memory, context size is a machine-local tuning decision. The current DeepSeek Harness configuration uses a 32,768-token context; preserve that value unless measurement and the installed provider configuration justify a change. These tuning values are not Plasma product requirements.

### 4.1 IC Support model-role experiment

The STM32F103C manufacturer-grounded experiment showed that model roles should be separated by the kind of error they are expected to make.

Observed with `qwen3.8:27b-mlx` and exact ST manufacturer documentation:

- strong technical fact extraction and cross-document reasoning;
- strong profile decomposition after explicit architecture guidance;
- useful evidence/provenance classification;
- materially weaker consistency when converting the same facts into detailed executable-style pseudocode.

The recommended IC Support research pipeline is therefore:

```text
Manufacturer documents
        |
        v
IC Knowledge / Specification Agent
        |
        v
Candidate IC Support
        |
        v
Deterministic schema + semantic validation
        |
        v
Validated canonical specification
        |
        v
Coding-specialized model
        |
        v
Driver / executor / tests candidate
        |
        v
Independent different-family reviewer
        |
        v
Compiler / static checks / simulation / HIL
```

The coding model should consume a validated canonical specification rather than independently rediscovering register/security semantics from the PDFs. A second AI reviewer can improve defect discovery, but agreement between models is not a trust boundary. Manufacturer evidence, deterministic validation, and real-target acceptance remain authoritative.

See [IC Support Local-AI Benchmark Handover](ic-support-ai-benchmark-handover.md) and the STM32F103C benchmark review record for the current experiment scope and known failure classes.

## 5. DeepSeek Harness launcher

The supported local DeepSeek Harness + Ollama workflow uses the repository helper. It keeps process startup reproducible without copying machine-local provider credentials or Harness configuration into Plasma.

The verified machine-local runtime configuration is:

```text
Ollama API:                    http://127.0.0.1:11434
Harness custom-provider API:  http://127.0.0.1:11434/v1
Harness API protocol:         openai-completions
Harness Model ID:             qwen3.8:27b-mlx
```

DeepSeek Harness currently requires a credential entry for this custom provider even though local Ollama does not authenticate requests. Configure a non-secret placeholder credential in Harness's machine-local credentials. Do not store that placeholder, provider configuration, or any real credential in Plasma. Use the exact model ID above; do not substitute retired oMLX model aliases.

Terminal 1:

```bash
scripts/local-ai-harness ollama
```

Terminal 2:

```bash
scripts/local-ai-harness warmup
scripts/local-ai-harness harness
```

Diagnostics:

```bash
scripts/local-ai-harness status
```

The helper keeps Ollama in the foreground so transport and model-runner errors remain visible. `OLLAMA_KEEP_ALIVE=-1` keeps the large model resident during long Harness agent sessions, while `OLLAMA_NUM_PARALLEL=1` prevents two large Qwen contexts from competing for Apple unified memory. Large concurrent Harness missions should therefore be serialized for now.

The Ollama and Harness timeout settings control different layers. `OLLAMA_LOAD_TIMEOUT=30m` allows a model load to make progress for longer; it is not the model inference or Harness request timeout. The Harness request timeout remains machine-local. Verify in the Harness Web UI's active local-provider/model settings that the request timeout is 30 minutes, and inspect the resolved, non-secret profile with:

```bash
dsh --profile web --dump-config
```

The installed developer-preview CLI does not currently expose a stable documented repository-local setting for the already configured 30-minute model request timeout. Do not invent a patch key. Re-check the resolved configuration and current upstream Harness documentation when upgrading Harness.

Defaults can be overridden for one invocation without editing the script:

```bash
PLASMA_LOCAL_AI_MODEL=<model> scripts/local-ai-harness warmup
PLASMA_OLLAMA_URL=http://127.0.0.1:<port> scripts/local-ai-harness status
PLASMA_HARNESS_PORT=<port> scripts/local-ai-harness harness
```

Use the same URL and port overrides with `status` and `stop` that were used to launch the services. If the recorded process does not own the expected listening port, `stop` refuses to signal it and prints a manual inspection command.

The Harness command runs from the detected Plasma repository root, which becomes its default workspace. It prefers an installed `dsh`; an already available official npm launcher may be used without package installation. The helper never pulls a model or installs Harness. Machine-local Harness provider settings, credentials, API keys, and tokens must not be committed.

For Plasma work, select the Plasma repository as the Harness workspace. Do not use its parent projects directory as the session workspace; doing so broadens file visibility beyond the repository boundary defined by `AGENTS.md`.

## 6. Continue configuration principles

Continue configuration is machine-local and normally belongs under the user's home configuration directory, not in this repository.

Reusable example:

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

## 7. Cline configuration principles

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

## 8. Remote-SSH and local Ollama

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

The actual username, hostname, private IP, VPN hostname, SSH key path, and ACL configuration remain outside the public repository.

Verify the tunnel from the integration host with:

```bash
curl http://127.0.0.1:11434/api/tags
```

If remote port 11434 is occupied, choose another remote port and update the remote-side provider URL accordingly.

## 9. Opening the Plasma workspace

Connect using the operator-local SSH alias and open:

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

## 10. Plasma-specific AI invariants

AI-generated changes must preserve the same engineering constraints as human-generated changes:

- inspect the current repository before making Plasma-specific claims;
- use Facility / PPU / Site as canonical domain vocabulary;
- preserve independent **Site** execution unless a real shared resource requires synchronization;
- scope cancellation to the intended job/Site;
- keep canonical Site identity one-based;
- do not reintroduce retired Programmer/Channel identity or zero-based Site compatibility;
- recognize the current Web boundary as **Plasma Gateway**, implemented with standard-library HTTP and REST polling;
- do not invent FastAPI/WebSocket behavior that is not implemented;
- do not invent hardware register addresses, timing, pin mappings, protocols, or API behavior;
- add or update regression tests when behavior changes;
- report what was actually validated;
- never claim integration-host/Z2/hardware validation unless it was actually performed under the approval policy.

## 11. Information classification

```text
Public repository
  -> generic AI architecture
  -> model roles and reproducible examples
  -> repository policy and validation workflow

Operator-local / protected documentation
  -> real SSH username and hostname
  -> private network identifiers
  -> workstation inventory
  -> local absolute paths
  -> credentials, tokens, keys
```

The objective is reproducibility without turning a public source repository into an infrastructure inventory.
