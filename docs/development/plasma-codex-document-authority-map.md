# PLASMA Codex documentation authority map

**Status:** Gate 1 documentation-only inventory; no runtime or permission changes.  
**Baseline:** main `833a0f577c3697d891629c405d91267c05c2b476` (PR #1226 merged).

## Read only what applies

| Situation | Primary source | Additional source only when relevant |
| --- | --- | --- |
| Any Codex work (Desktop or SWPC) | Root [AGENTS.md](../../AGENTS.md) | [Detailed autonomous development contract](plasma-autonomous-development-contract-full.md), matching safety/architecture clauses |
| Deterministic SWPC Path 2 | [Path 2 execution rules](plasma-codex-path2-execution.md) | [Three-path execution model](plasma-three-path-execution-model.md), actual reviewed script/build contracts |
| Autonomous SWPC Path 3 | [Path 3 execution rules](plasma-codex-path3-execution.md) | [Native hardware tools](plasma-path3-direct-hardware-tools.md), only for approved hardware work |
| Offline Desktop/Direct token analysis | [Codex benchmark usage](codex-benchmark-usage.md) | Explicitly selected local JSONL and [extractor](../../scripts/plasma_codex_benchmark_usage.py); do not upload raw session |
| Path 3 runtime/usage investigation | [Path 3 token optimization RCA](plasma-path3-token-optimization-rca-closure-2026-10-23.md) | Actual Dispatcher receipts and pinned run evidence |
| Historical cross-job resume | [Cross-job resume historical report](plasma-path3-cross-job-resume-gate1.md) and [offline PoC](plasma-path3-session-resume-host-only-poc.md) | Historical only: no execution authority |
| Historical Issue #981 trigger removal | [Legacy trigger retirement](plasma-legacy-codex-issue981-trigger-retirement.md) | Historical only: not a current dispatch path |

## Cleanup decisions

1. **Retain** root AGENTS and detailed contract as mandatory authorities. Do not reduce guard clauses solely to hit a character target.
2. **Retain** separate Path 2/3 instructions. Load only the selected path's detailed rules; Desktop local Codex is not automatically SWPC Path 3.
3. **Retain with historical label** the retired resume/Issue #981 documents. They provide provenance, but cannot authorize runtime behavior.
4. **Do not create** an additional Supervisor, JSON Relay, fixed adapter, stage/profile or session-resume middleware as a documentation cleanup.
5. **Do not delete or archive** files solely by filename or age. First inspect inbound references, current ADRs, CI/tests, and actual implementation.
6. **No claimed token reduction** without comparable model, effort, fresh context, acceptance criteria and measured telemetry. Cached input is a subset of input.

## Deferred follow-up

- Review repeated normative paragraphs between root AGENTS, the full contract, and the Path-specific documents with line-level semantics and inbound references.
- Evaluate whether historical references can be grouped under an archive index without moving files or breaking links.
- Benchmark Desktop and Path 3 independently; preserve safety and task success rates.

## Revised Gate 1 — Path 3 Codex documentation governance

**Owner-approved scope:** Shared documentation governance across Desktop Codex CLI, Path 2 and Path 3. Path 3 is the selected execution route for an actual SWPC Codex run; a GitHub documentation edit alone is **not** proof that the Owner Work Order, SWPC Runner or Codex executed.

### Authority and duplication inventory

| Topic | Canonical authority | Potential overlap / treatment |
| --- | --- | --- |
| Global work authorization, two Owner gates, source precedence | Root [AGENTS.md](../../AGENTS.md) | Detailed [full contract](plasma-autonomous-development-contract-full.md) elaborates; preserve non-conflicting safeguards and cross-reference rather than copy into every Path |
| Architecture decisions and accepted/proposed status | [ADR index](../adr/README.md) and each relevant ADR | AGENTS/full contract may summarize decisions; ADR is authoritative for the decision, implementation/tests for actual behavior |
| Path selection and common constraints | Root [AGENTS.md](../../AGENTS.md) | [Three-path model](plasma-three-path-execution-model.md) is supporting design/flow reference |
| Path 2 CPU-only, operator-cli, Vivado | [Path 2 execution rules](plasma-codex-path2-execution.md) | Root AGENTS should link rather than restate path-specific operational detail |
| Path 3 sandbox, approved SWPC Codex, native tools | [Path 3 execution rules](plasma-codex-path3-execution.md) | [Direct hardware tools](plasma-path3-direct-hardware-tools.md) gives device-specific evidence and must not be interpreted as a new permission grant |
| Path 3 Owner Work Order, trusted Dispatcher/Runner, receipt and GitHub evidence | Root AGENTS + [Path 3 execution rules](plasma-codex-path3-execution.md) + actual `scripts/plasma_development_dispatch.py` and trusted workflow | The runtime implementation, authorization, and verified receipt prevail over descriptive duplication; do not add a second Runner, Token Receipt or evidence pipeline |
| Token metrics | [Benchmark usage](codex-benchmark-usage.md) and actual receipts | Avoid comparing mismatched Desktop turn and Path 3 full run; never add cached input to total input |
| Retired cross-job resume and Issue #981 triggers | Historical reports listed above | Retain historical warnings, remove from current operational navigation; never restore retired middleware |

### Path 3 execution and evidence acceptance

1. **Owner Work Order:** bind the exact objective, approved scope, immutable source SHA/digest, task identity and permitted Host-only boundaries. Do not treat this document as a Work Order.
2. **Runner:** use only the existing trusted-main Dispatcher and non-root SWPC Codex Runner. No new adapter, supervisor, relay, permission escalation or hardware access.
3. **Token Receipt:** capture existing bounded numeric usage fields and accounting status from a real run; missing telemetry is `NOT_AVAILABLE`, never zero. Do not publish prompts, raw rollout JSONL, credentials or private tool output.
4. **GitHub Evidence:** preserve Work Order/Run/Job identifiers, pinned SHA, CI results, PR diff and sanitized receipts. A created PR or queued job does not prove Codex execution.
5. **Acceptance:** inventory inbound references and overlapping clauses; identify a single authority for each rule; retain safety and two-gate invariants; validate documentation links and CI. Actual Path 3 execution is a separate measurable action and must be explicitly evidenced.

**This PR is a documentation-only Gate 1 deliverable.** No claim of Path 3 Runner invocation, Codex Token Receipt or GitHub Run ID is made. No deployment, Z2/DUT/FPGA operation, CI/workflow modification or merge is authorized here.
