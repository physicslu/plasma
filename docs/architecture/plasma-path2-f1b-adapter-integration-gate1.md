# PLASMA Path 2 — F1-B Adapter Integration Gate 1 (Host-only)

**Status:** Draft PR only. No new trusted Dispatcher capability, Registry task, Workflow, Runner activation, hardware operation or deployment. Main basis: Merge SHA \`80f13e1c68d7172000cb78cd787a43272fca48c4\`.

## Reused components / binding points

- \`scripts/plasma_path2_stage_orchestrator.py\`: already-merged 3-stage \`run(request, adapters=...)\`. Three individually triggerable stages and 2 independent transition flags (each defaults false). Unchanged.
- \`scripts/plasma_vivado_host_build.py:run\`: existing fixed Vivado **Build Code** engine. \`existing_host_build\` forwards reviewed task/workspace/approval/evidence directory to this real function, **but is never invoked in CI**. The returned status is \`HOST_BUILD_EVIDENCE_READY_REVIEW_REQUIRED\`, **not Build PASS**. Separate injected build qualification must inspect BIT/HWH/report hashes before issuing a stage PASS receipt. No new builder.
- \`pl/hil/swd04/development.py:HardwareProfile\` / \`pl/hil/f1b.py:PROFILE\`: use existing fixed 64-KiB F1-B identity profile and three expected values. No new ABI or RTL.
- \`pl/hil/swd04/one_shot.py\`: reusable Supervisor preflight, FPGA Manager, protected lifecycle, bounded child, ownership and restoration primitives. **Do not call \`run_live\` as the standalone Download stage**: \`run_live\` automatically restores \`base.bin\` and does not leave the candidate image loaded. The historical 2026-10-20 one-shot success is evidence for sequencing, not a persistent Download operation.
- \`pl/hil/f1b.py:identity_callback\`: \`f1b_identity_adapter\` wraps the existing native three-read callback, requiring an observed exact JSON output and callback PASS. Target execution would require a distinct reviewed, owner-authorized backend; CI injects a fake callback and never opens MMIO.

## Stage boundaries (strictly independent)

| Trigger | Required input and runtime proof | Result boundary |
|---|---|---|
| Build Code | Authorized pinned source, F1-B Profile, existing Vivado Host Build Receipt, separately approved Build Qualification | Immutable image SHA256 and qualification evidence; stop unless \`auto_download_after_build_success=true\` |
| Download FPGA | Previously qualified Build Receipt and image SHA256, authorized target/lease/boot, durable restore intent and **currently loaded-and-held image** from independently reviewed Download backend | Load receipt (source, profile, target, lease, image hash, evidence); stop unless \`auto_test_after_download_success=true\` |
| Testing | Previously observed Load Receipt with same image, target and lease; authorized F1-B Identity callback returning native readonly u32 values at 0x40000000, 0x40000004, 0x40004000 | Three exact Identity reads, read32=3/write32=0, matching evidence; stop |

**Both auto-transition flags default false**, are independent, and are evaluated by the already merged stage Orchestrator. Build can proceed to Testing only when **both** individual flags are true. Failure blocks the next stage. Standalone Download never silently rebuilds; standalone Testing never fabricates a Build PASS.

## Risk / currently missing work

This Gate adds thin callback **binding contracts**, not actual site I/O. Real \`held_download\` and \`identity_test\` providers are **not registered**: the factory \`bind_f1b_adapters()\` with no ports fails closed. The trusted dispatcher still does not expose this feature to operators. The adapter receipts are checked schemas/claims, not independently authenticated, signed hardware attestations.

Before an actual adapter can be authorized: ensure current-boot firmware provenance, exclusive ownership / persistent lease across separate triggers, real AXI quiescence or explicit reviewed risk policy, atomic durable restore intent, bounded MMIO access, guarded recovery after failure and proof of loaded firmware on the target. Do not automatically transfer the dated owner-accepted \`uio1\` risk exception or private sudo route from Path 3 to production Path 2. **Restoration is cleanup authority**, not an automatic fourth stage nor an unconditional reload when AXI is unknown.

The existing [F1-B Path 3 Codex As-run ledger](../development/plasma-f1b-path3-39395142726-codex-steps.md) documents the prior physical Load → Identity → Restore. This Gate reuses interfaces and observed engineering constraints; no second hardware experiment is done.

## Gate 1 Host-only qualification

\`pl/tests/test_path2_f1b_adapters.py\` runs pure pytest with fake Build, Qualification, Download and Test providers. Covers independent triggers, default false options, opt-in chains, malformed/incorrect source, BIT/HWH, load held state, expired/wrong lease, no-op Identity callback, native-read count, writes denied, failure stopping the chain, and no physical side effects. The existing GitHub-hosted workflows run automatically when the Draft PR changes. No SWPC, Vivado, Z2, DUT, LA, deployment or merge is authorized by this PR.

**Next separately authorized Gate:** build trust-aware real Download hold/recovery and current-lease Test providers, then wire them into a pinned Dispatcher/UI command without violating the existing safety boundaries.
