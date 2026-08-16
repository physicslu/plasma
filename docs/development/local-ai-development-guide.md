# Plasma Local AI Development Guide

> Project: `physicslu/plasma`  
> Scope: macOS local AI + VS Code + Continue + Cline + Ollama + SWPC Remote-SSH  
> Updated: 2026-08-16

###### tags: `Plasma` `AI` `Continue` `Cline` `Ollama` `VS Code` `SWPC`

---

## 1. Purpose

This document defines the recommended local AI development setup for Plasma.
The goal is to use the Mac as the local inference machine while the Plasma repository remains on SWPC.

The intended division of work is:

```text
MacBook Pro
├── Ollama
│   ├── qwen3.8:27b-mlx              Chat / Edit / Apply / Agent
│   ├── qwen2.5-coder:1.5b           fast inline autocomplete
│   └── qwen3-embedding:0.6b         codebase embeddings
│
├── VS Code
│   ├── Continue                     daily coding assistant
│   └── Cline                        autonomous coding agent
│
└── Remote-SSH
     └── SWPC
          └── /storage/projects/plasma
```

Continue and Cline must follow the repository `AGENTS.md`.
`AGENTS.md` is the authoritative cross-tool AI development contract; do not create a second conflicting copy of the same Plasma rules for each AI tool.

---

## 2. AI role separation

### 2.1 Continue

Use Continue for interactive daily work:

- inline code completion
- code explanation
- codebase search
- local chat
- small edits
- reviewing selected code
- quick design discussion

Recommended model roles:

| Continue role | Model | Purpose |
|---|---|---|
| Chat | `qwen3.8:27b-mlx` | reasoning and coding discussion |
| Edit | `qwen3.8:27b-mlx` | code generation/editing |
| Apply | `qwen3.8:27b-mlx` | applying generated changes |
| Autocomplete | `qwen2.5-coder:1.5b` | low-latency inline completion |
| Embed | `qwen3-embedding:0.6b` | semantic codebase search |
| Rerank | none | not required initially |

### 2.2 Cline

Use Cline when the task should be executed as an engineering workflow rather than answered as a chat message.
Typical Cline tasks include:

```text
read AGENTS.md
    -> inspect repository
    -> inspect tests
    -> modify code
    -> run tests
    -> inspect failures
    -> fix again
    -> review git diff
    -> report result
```

Good Cline tasks include:

- fixing a bug across several files
- adding a feature with tests
- running pytest and repairing failures
- modifying both Python and Web code for one API change
- examining a concurrency problem
- producing a merge-ready feature branch when authorized by `AGENTS.md`

Protected operations remain governed by `AGENTS.md`, especially merge-to-main, deployment/restart, hardware-affecting actions, and destructive Git operations.

---

## 3. Ollama models

Install the selected models on the Mac:

```bash
ollama pull qwen3.8:27b-mlx
ollama pull qwen2.5-coder:1.5b
ollama pull qwen3-embedding:0.6b
```

Check installed models:

```bash
ollama list
```

Check models currently loaded in memory:

```bash
ollama ps
```

The main model is intentionally the MLX build because the local inference machine is Apple Silicon.

### 3.1 Current memory/context policy

Recommended starting point:

| Workload | Context |
|---|---:|
| Continue Chat / Edit / Apply | 65,536 tokens |
| Cline Agent | 131,072 tokens |
| Continue Autocomplete prompt | 2,048 tokens |
| Embedding chunk | 1,024 tokens |

Do not automatically set every role to the maximum model context.
Large context windows consume additional KV-cache memory and increase prompt-processing latency.

For a 48 GB unified-memory Mac, use 64K for normal Continue work and 128K for Cline agent tasks first.
Increase beyond 128K only after verifying memory pressure and real task benefit.

The model may support a larger maximum context than the values above; that does not mean maximum context is optimal for every request.

---

## 4. Continue configuration

Continue v2 uses local YAML configuration.
The local configuration is normally stored at:

```text
~/.continue/config.yaml
```

Recommended Plasma configuration:

```yaml
name: Gordon Plasma Development
version: 1.3.0
schema: v1

models:
  # ============================================================
  # Main Plasma model: Chat / Edit / Apply
  # ============================================================
  - name: Qwen3.8 27B MLX
    provider: ollama
    model: qwen3.8:27b-mlx
    apiBase: http://127.0.0.1:11434

    roles:
      - chat
      - edit
      - apply

    capabilities:
      - tool_use
      - image_input

    defaultCompletionOptions:
      contextLength: 65536
      maxTokens: 4096
      temperature: 0.1
      topP: 0.9

    chatOptions:
      baseSystemMessage: |
        You are a senior software, firmware, FPGA, and system-integration engineer
        working on the Plasma multi-channel IC Programmer repository.

        Primary Plasma areas include:
        - Python / asyncio / pytest
        - Plasma Server and protocol implementation
        - Web Gateway / HTTP API
        - React / TypeScript Web Console
        - multi-channel job scheduling and cancellation
        - PYNQ-Z2 / FPGA / AXI integration
        - SWD / SPI / I2C programmer interfaces
        - Linux / systemd / SWPC integration
        - Git / GitHub / pull-request workflow

        Before making Plasma-specific claims, inspect the current workspace.
        Read AGENTS.md first when it is available and treat it as the primary AI-agent contract.
        Prefer executable code, checked-in configuration, tests, and current documentation over assumptions.

        Do not invent Plasma APIs, ports, channel counts, job states, hardware register
        addresses, pin assignments, timing, or electrical behavior.

        Preserve multi-channel independence. Do not serialize unrelated channels merely
        to avoid a concurrency bug. Scope cancellation to the intended job/channel and
        explicitly identify any genuinely shared resource that requires synchronization.

        For code changes, consider relevant tests and report what was actually validated.
        Do not claim SWPC deployment, Z2 validation, or real-target programming unless
        those operations were actually performed under the approval rules in AGENTS.md.

    requestOptions:
      timeout: 300000

  # ============================================================
  # Fast inline completion
  # ============================================================
  - name: Qwen2.5-Coder 1.5B Autocomplete
    provider: ollama
    model: qwen2.5-coder:1.5b
    apiBase: http://127.0.0.1:11434

    roles:
      - autocomplete

    autocompleteOptions:
      maxPromptTokens: 2048
      debounceDelay: 150
      modelTimeout: 500
      onlyMyCode: true
      useCache: true
      useImports: true
      useRecentlyEdited: true
      useRecentlyOpened: true

    requestOptions:
      timeout: 30000

  # ============================================================
  # Codebase embeddings
  # ============================================================
  - name: Qwen3 Embedding 0.6B
    provider: ollama
    model: qwen3-embedding:0.6b
    apiBase: http://127.0.0.1:11434

    roles:
      - embed

    embedOptions:
      maxChunkSize: 1024
      maxBatchSize: 8

    requestOptions:
      timeout: 60000

context:
  - provider: file
  - provider: code
  - provider: diff
  - provider: terminal
  - provider: problems
  - provider: folder

rules:
  - |
    This workspace may contain the Plasma repository.

    When AGENTS.md is present:
    - read it before Plasma code-changing work
    - follow its source-of-truth order, Git policy, validation rules, and approval gates
    - do not duplicate or override it with stale generic embedded/RTOS rules

    If the workspace is clearly not the Plasma repository, confirm that once and stop
    repeatedly searching for missing Plasma files. State that repository context is not
    available and answer only as a generic architecture discussion.
```

### 4.1 Continue UI role selection

In Continue Settings -> Models, verify:

```text
Chat          -> Qwen3.8 27B MLX
Edit          -> Qwen3.8 27B MLX
Apply         -> Qwen3.8 27B MLX
Autocomplete  -> Qwen2.5-Coder 1.5B Autocomplete
Embed         -> Qwen3 Embedding 0.6B
Rerank        -> none
```

### 4.2 Autocomplete settings

Recommended starting settings:

```text
Autocomplete timeout: 500 ms
Debounce delay:        150 ms
Prompt tokens:         2048
```

Do not give the autocomplete model the 64K/128K agent context window.
Autocomplete is latency-sensitive and should remain small and fast.

### 4.3 Embedding migration

The previous local embedding model may be `nomic-embed-text`.
Keep it installed until `qwen3-embedding:0.6b` has successfully rebuilt and queried the Plasma index.

After changing the embedding model, rebuild the Continue codebase index.
During indexing, use:

```bash
ollama ps
```

and verify that the Qwen3 embedding model is actually being used.

If Qwen3 Embedding causes compatibility or quality problems in Continue, `nomic-embed-text` remains the conservative fallback.

### 4.4 Remove obsolete generic RTOS rules

Do not keep old global CMSIS-RTOS rules always enabled when the current work is Plasma-specific.
Global rules consume context and can steer the model toward unrelated assumptions.

Continue should primarily receive Plasma project rules plus the current repository context.

---

## 5. Cline configuration

### 5.1 Provider settings

Open Cline Settings and configure:

```text
API Provider:        Ollama
Base URL:            http://127.0.0.1:11434
Model:               qwen3.8:27b-mlx
Use Compact Prompt:  ON
Target context:      131072 tokens
```

No API key is required for local Ollama.

Cline local-model documentation recommends compact prompts for local inference.
Keep Compact Prompt enabled unless a specific compatibility problem is found.

### 5.2 Context window

For Plasma Cline tasks, start with:

```text
131072 tokens (128K)
```

If the Cline/Ollama settings page exposes a model-context or maximum-context field, set it to 131072.
After starting a task, verify the effective runtime context rather than assuming the UI value was applied.

Use:

```bash
ollama ps
```

and inspect the reported context information when available.

If 128K causes excessive memory pressure or prompt latency, reduce to 64K.
If 128K is stable and a real long-horizon task needs more context, test a larger value incrementally.

### 5.3 Recommended Cline permissions

Start with a useful but bounded agent profile:

```text
Read project files     ON
Edit project files     ON
Execute safe commands  ON

Read all files         OFF
Edit all files         OFF
Execute all commands   OFF
```

This allows normal repository work while retaining approval for broader/destructive actions.
Do not use YOLO/fully unrestricted execution merely to avoid approval prompts.

`AGENTS.md` remains the policy authority even when Cline UI permissions technically allow an action.

### 5.4 Cline rules and AGENTS.md

Cline natively recognizes `AGENTS.md` as a supported rule source.
Therefore the normal Plasma configuration should be:

```text
AGENTS.md                       authoritative shared repository contract
.clinerules/ or .cline/rules/   only for genuinely Cline-specific behavior, if needed
```

Do not copy the complete contents of `AGENTS.md` into `.clinerules`.
Duplicated rule files drift over time, consume context, and can contradict each other.

In the Cline Rules panel, keep the repository `AGENTS.md` rule enabled.

---

## 6. Mac Ollama + SWPC Remote-SSH topology

### 6.1 Important localhost rule

When VS Code is opened locally on the Mac:

```text
http://127.0.0.1:11434
```

is the Mac Ollama service.

When an extension executes on a Remote-SSH extension host, `127.0.0.1` may instead refer to SWPC.
Do not assume the execution location.

The preferred solution is an SSH reverse port forward so that SWPC loopback port 11434 also reaches the Mac Ollama service.
This avoids exposing Ollama directly to the LAN or Internet.

### 6.2 One-time reverse tunnel test

On the Mac:

```bash
ssh -N -R 11434:127.0.0.1:11434 gordon@swpc
```

Keep that SSH session running.

Then, from a SWPC terminal:

```bash
curl http://127.0.0.1:11434/api/tags
```

If model data is returned, SWPC can reach the Mac Ollama service through the SSH tunnel.

### 6.3 Persistent SSH configuration

A convenient Mac `~/.ssh/config` entry is:

```sshconfig
Host swpc
    HostName swpc
    User gordon
    RemoteForward 11434 127.0.0.1:11434
    ExitOnForwardFailure yes
```

After changing SSH configuration, reconnect the VS Code Remote-SSH session.

Before relying on the tunnel, verify from the SWPC terminal:

```bash
curl http://127.0.0.1:11434/api/tags
```

If SWPC already uses TCP port 11434 for another service, choose a different remote port, for example:

```sshconfig
RemoteForward 11435 127.0.0.1:11434
```

and change the remote-side AI provider Base URL to:

```text
http://127.0.0.1:11435
```

### 6.4 Do not expose Ollama unnecessarily

Do not set Ollama to listen on all interfaces merely to make Remote-SSH work unless there is a deliberate network-security decision.
An SSH tunnel is preferred for the normal Plasma development setup.

---

## 7. Opening Plasma on SWPC

Connect with VS Code Remote-SSH:

```text
gordon@swpc
```

Open:

```text
/storage/projects/plasma
```

Before code-changing work, follow `AGENTS.md` and inspect the repository state.
Typical initial checks are:

```bash
cd /storage/projects/plasma
git status -sb
git branch --show-current
git log -1 --oneline
git fetch origin main
```

Do not overwrite unrelated user changes.

---

## 8. Recommended development workflow

### 8.1 Interactive development with Continue

Use Continue while personally editing code:

```text
write code
  -> inline autocomplete
  -> ask about selected code
  -> search the codebase
  -> make small edits
  -> review diff
```

Example Continue question after the real Plasma workspace is open:

```text
Find the implementation of channel cancellation in this repository.
Read AGENTS.md and the relevant tests first.
Explain the actual control flow and identify any cross-channel coupling.
Do not guess from generic architecture.
```

### 8.2 Task execution with Cline

Use Cline for a bounded implementation goal.
Example:

```text
Analyze the Plasma batch-operation behavior.

Requirements:
- Read AGENTS.md first.
- Inspect the current implementation and relevant tests before editing.
- Different channels must remain independent unless a real shared resource requires synchronization.
- Do not serialize unrelated channels as a shortcut.
- Implement only changes required by this task.
- Add or update regression tests.
- Run the relevant validation.
- Review git status and git diff at the end.
- Follow all approval gates in AGENTS.md.
```

A good Cline task should have one clear engineering objective.
Do not combine unrelated frontend, backend, FPGA, deployment, and hardware experiments into one long task unless they are genuinely one feature.

---

## 9. Plasma-specific AI invariants

These principles are important enough to check during every AI-generated multi-channel change:

1. Channels are independent execution units unless the actual implementation documents a shared resource.
2. An operation on one channel must not wait for an unrelated operation on another channel.
3. Cancellation must be scoped to the intended job/channel.
4. A global lock is not an acceptable generic fix for a multi-channel race condition.
5. Shared resources must be explicitly identified before adding serialization.
6. Tests passing does not by itself prove architectural correctness.
7. Mock success does not prove Z2 or real-target hardware success.
8. Deployment and hardware validation remain separate approval/validation stages.

If these principles conflict with executable code or a newer repository-defined requirement, report the inconsistency and follow the source-of-truth order in `AGENTS.md`.

---

## 10. Performance and troubleshooting

### 10.1 First chat is slow

A first Qwen3.8 request can be noticeably slower because the model must be loaded into memory.
If subsequent requests are faster and `ollama ps` shows the model loaded, this is expected behavior.

### 10.2 Agent is slow with a large context

Check:

```bash
ollama ps
```

Then monitor macOS memory pressure.
If the system starts swapping heavily, reduce Cline from 128K to 64K before changing the model.

More context is not always better.
Relevant context is more valuable than loading the entire repository into every prompt.

### 10.3 Continue cannot reach Ollama after Remote-SSH

From the current VS Code terminal, run:

```bash
curl http://127.0.0.1:11434/api/tags
```

If it fails only on SWPC, check the SSH reverse tunnel.
If it succeeds, verify Continue/Cline are configured with the same Base URL.

### 10.4 Autocomplete works but Chat is slow

This is expected to a degree because autocomplete uses a 1.5B model while Chat uses a 27B model.
Do not replace autocomplete with the 27B model unless there is a measured quality reason that justifies the latency cost.

### 10.5 Codebase search quality is poor

After changing embedding models:

1. rebuild the Continue codebase index
2. confirm the embedding model is loaded during indexing
3. test repository-specific queries
4. fall back to `nomic-embed-text` if necessary

---

## 11. Validation checklist

### Continue

- [ ] `qwen2.5-coder:1.5b` produces inline autocomplete
- [ ] `qwen3.8:27b-mlx` answers Chat requests
- [ ] Edit/Apply use Qwen3.8
- [ ] Qwen3 Embedding rebuilds the codebase index
- [ ] obsolete CMSIS/RTOS global rules are disabled or removed
- [ ] Plasma `AGENTS.md` is visible when the Plasma workspace is open

### Cline

- [ ] Provider is Ollama
- [ ] model is `qwen3.8:27b-mlx`
- [ ] Compact Prompt is enabled
- [ ] target context is 128K
- [ ] project-file read/edit permissions are enabled
- [ ] unrestricted outside-workspace/destructive permissions remain disabled
- [ ] `AGENTS.md` appears in the Rules panel and is enabled

### SWPC Remote-SSH

- [ ] VS Code opens `/storage/projects/plasma`
- [ ] `curl http://127.0.0.1:11434/api/tags` works from the relevant execution environment
- [ ] Git worktree state is checked before edits
- [ ] AI changes stay on the task scope/feature branch required by `AGENTS.md`
- [ ] tests are run before declaring the task complete
- [ ] protected merge/deploy/hardware gates are respected

---

## 12. Official references

- Continue Ollama provider: <https://docs.continue.dev/customize/model-providers/ollama/>
- Continue YAML reference: <https://docs.continue.dev/reference>
- Continue model roles: <https://docs.continue.dev/customize/model-roles/intro>
- Cline local models: <https://docs.cline.bot/running-models-locally/overview>
- Cline rules / AGENTS.md support: <https://docs.cline.bot/customization/cline-rules>
- Cline task/context management: <https://docs.cline.bot/core-workflows/task-management>
- Cline Auto Approve: <https://docs.cline.bot/features/auto-approve>

---

## 13. Summary

Recommended Plasma local AI stack:

```text
Continue
├── Chat/Edit/Apply -> Qwen3.8 27B MLX, 64K context
├── Autocomplete    -> Qwen2.5-Coder 1.5B, 2K prompt
└── Embeddings      -> Qwen3 Embedding 0.6B

Cline
└── Agent            -> Qwen3.8 27B MLX, 128K target context

Policy
└── AGENTS.md         -> shared authoritative AI development contract

Inference
└── Mac Ollama        -> accessed locally or through an SSH reverse tunnel from SWPC
```

Use Continue as the always-on coding assistant and Cline as the task-oriented implementation agent.
Keep `AGENTS.md` tool-agnostic so Continue, Cline, Codex, and future agents share one source of truth.
