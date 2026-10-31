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
