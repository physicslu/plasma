# H007 — Plasma Vendor-Neutral IC Admission / NXP KL25 Handover

**Date:** 2026-09-10 21:51 +08:00  
**Status:** Architecture / Engineering Handover  
**Primary workstream:** AI IC Support / Vendor-Neutral Admission  
**Repository:** `physicslu/plasma`  
**Current GitHub `main` at handover creation:** `205122c067e68ef6cdc4120e9c185e4cf7c47337`

---

## 1. Executive Summary

Plasma 的 NXP KL25 MCU Software Executor milestone 已完成；後續工作已從「把 KL25 做完」轉向「把已驗證的 NXP/ST 流程抽象成 vendor-neutral trust/admission framework」。

目前最重要的已完成里程碑是 **PR-A / PR #474 — vendor-neutral IC admission governance**。PR #474 已合併，merge commit 為：

`39cbe4b6bbb11687ff7117dfac0b06cb856428fc`

PR-A 建立了通用的 trust ABI，包括 artifact identity/digest、review binding、exact reviewed-subject coverage、post-review disposition、candidate review、canonical admission envelope、operation admission、backend binding 與 compiler binding。Generic validator 只驗證 governance structure / lineage / digest / structural binding，不解讀 vendor silicon semantics。

下一步為 **PR-B — NXP KL25 compatibility adapter**。PR-B 的 Gate 1 已在本次工作對話中批准，但在本 handover 建立前重新檢查 GitHub 時，**尚未找到可驗證的 PR-B PR、branch、commit 或 adapter 檔案**。因此不能宣稱 PR-B 已完成。最可能的狀況是 Work mode / SWPC local work 已完成但尚未 push，或 branch/PR 名稱與預期不同。

下一個接手者的第一個動作不是重新實作 PR-B，而是：

1. 先搜尋 GitHub 與 SWPC/local repo 是否已有 PR-B branch / commit / PR。
2. 若已存在，直接做 Gate 2 audit。
3. 若只存在 local implementation，完成 push、PR、CI，然後停在 Gate 2。
4. 若完全不存在，再依本文件的 frozen PR-B scope 實作。

---

## 2. System Goal and Architectural Boundary

Plasma 目標是建立可擴充的通用 IC 燒錄器：

- Embedded Linux PS 作為主控制器。
- FPGA PL 作為客製化、時序敏感的週邊。
- 每台 programmer 最終支援最多 8 個 programming sites/channels。
- Control Station / upper PC 透過 Ethernet 與 programmer 溝通。
- Browser/UI 不得直接驅動 FPGA programming signals。

目前 MCU 軟體里程碑的 stop line 明確定義為：

```text
Manufacturer Evidence
→ Semantic Extraction / Review
→ Canonical IC Support Specification
→ Programming Profile + Memory Geometry
→ Backend Plan Compiler
→ Software Executor
→ STOP
```

目前明確不在本階段宣稱完成的項目：

- Real MCU HIL
- Physical SWD programming
- PPU hardware runtime enable
- FPGA/PL native programming engine
- Production admission / production routing expansion
- Destructive security operation enable
- 8-site physical concurrency qualification

必須持續維持下列判斷邊界：

```text
Specification correctness
≠ Software correctness
≠ Hardware correctness
≠ Production readiness
```

---

## 3. Trust Model

Plasma IC Support 的 authority order：

```text
Manufacturer Evidence
> Validated Canonical Specification
> Generated / Compiled Implementation
> AI opinion
```

AI 只允許作為 semantic extraction / review assistant，不可自行擁有：

- commercial identity authority
- exact target applicability authority
- manufacturer truth authority
- canonical admission authority
- operation admission authority
- destructive security admission authority

Generic governance layer 與 vendor semantics 必須分離：

```text
Generic layer = why an artifact is trusted, admitted, bound, and executable
Vendor layer  = how the silicon actually works
```

禁止建立假的 cross-vendor silicon abstraction，例如：

```text
GenericFlashController.unlock()
GenericFlashController.erase()
GenericFlashController.program()
```

這會錯誤地把 STM32 FLASH/Option Byte、NXP FTFA/FCCOB/FSEC、其他 vendor controller 的不同 silicon semantics 強行視為同一模型。

---

## 4. NXP KL25 Completed Milestone

### 4.1 Exact target

- Vendor: NXP
- Family: Kinetis KL25
- Exact target: `MKL25Z128VLK4`

### 4.2 Manufacturer source lock

Source lock: `nxp-kl25-source-lock-v0`

Datasheet:

- Document: `KL25P80M48SF0`
- Revision: 5
- SHA-256: `e42271b7f612ac1b0812001e62bef10d217be4a61dbee5bb0a1e5c4076209a3b`

Reference manual:

- Document: `KL25P80M48SF0RM`
- Revision: 3
- SHA-256: `7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241`

NXP native ontology includes FTFA, FSTAT, FCCOB/FCCOBn, Program Longword, Erase Flash Sector, Erase All Blocks, FSEC, SWD, MDM-AP。不得投射 STM32 unlock-key / FLASH_CR 等概念到 NXP。

### 4.3 Gate 5.7A retained semantic run

Successful retained primary run:

`/storage/projects/plasma-benchmark/nxp-kl25/bounded-primary-runs/20260909T080946Z`

Result:

- 8/8 evidence units `INTEGRITY_PASS`
- `READY_FOR_REVIEW`
- PRIMARY evidence can generate facts
- DEPENDENCY evidence is context-only
- every fact requires PRIMARY citation
- dependency-only fact generation is forbidden

### 4.4 Gate 5.8 manufacturer review

Gate 5.8 exact retained result is permanently:

`REJECTED_REVIEW`

Review coverage:

- total retained facts: 140
- all-pass facts: 130
- findings: 10

The 10 findings were classified as:

- 3 citation-only
- 2 atomicity-only
- 5 semantic/scope related

Gate 5.8 result must never be rewritten to PASS after downstream repair. Downstream disposition is a new artifact lineage, not mutation of Gate 5.8 history.

### 4.5 Post-review disposition and Software Executor

PR #472 was merged with merge commit:

`519a81bf563b3b024e21b8e31d2bef5288a8e786`

The post-review flow:

- preserved the 130 all-pass facts
- handled the 10 findings through replace / split / narrow / citation supplement
- produced 13 transformed/reviewed candidates
- expected total projected knowledge candidates: 143

Immutable candidate release:

`/storage/projects/plasma-benchmark/nxp-kl25/post-review-disposition/releases/20260910T055202Z-dc256318618f`

Release digest:

`dc256318618f20d3d5bffbee8fe74fd0c9554b7b457d448f1bc13ed86f18f987`

Admitted software operations:

- READ
- VERIFY
- PROGRAM
- exact-sector ERASE

Blocked / excluded:

- Flash Configuration Field programming
- Flash Configuration Field sector erase
- Erase All Blocks
- MDM-AP mass erase
- backdoor key workflows
- security-state modification
- unprotect workflows
- implicit destructive erase/security flows

The Software Executor crosses only an injected fake-process boundary. It does not prove physical SWD programming.

---

## 5. NXP Backend Lock

Existing NXP/OpenOCD backend implementation lock:

- OpenOCD implementation commit: `56b8d93fbe61a78dc903d770820d6d896b6d8134`
- Legacy backend lock digest: `877b3fd9c0b9f8dc3191eb53393e5670efb93b9952ac1747bded155ebcaef4d1`

Important admitted backend constraints include:

- target config: `target/kl25.cfg`
- program start alignment: 4 bytes
- tail padding: `0xFF`
- implicit erase: false
- erase requires exact sector range
- Flash Configuration Field start: `0x00000400`
- Flash Configuration Field size: 16 bytes
- FCF-containing sector size: 1024 bytes

The current `KL25OpenOCDPlanCompiler` maps application `Operation.ERASE` to the NXP-specific `ERASE_SECTOR` contract and requires exactly one aligned 1 KiB sector. It also blocks the sector containing the Flash Configuration Field.

This is a key architecture lesson: the same application operation name cannot imply identical destructive semantics across vendors.

```text
STM32 ERASE may mean full main-flash erase
NXP    ERASE means exact one-sector erase in the current candidate
```

Therefore generic operation admission must bind both the request operation and a vendor-owned operation contract identity/digest.

---

## 6. PR-A — Vendor-Neutral Governance Framework — DONE

### 6.1 PR identity

- PR: `#474`
- Branch: `agent/vendor-neutral-ic-admission`
- Final head: `63963094cc466ddc6b941d4991dc389f5d2b00b2`
- Merge commit: `39cbe4b6bbb11687ff7117dfac0b06cb856428fc`

### 6.2 Generic schema IDs

PR-A introduced these v1 contracts:

- `plasma://ic-support/admission/artifact-ref-v1`
- `plasma://ic-support/admission/manufacturer-evidence-ref-v1`
- `plasma://ic-support/admission/review-binding-v1`
- `plasma://ic-support/admission/post-review-disposition-v1`
- `plasma://ic-support/admission/candidate-review-v1`
- `plasma://ic-support/admission/canonical-admission-envelope-v1`
- `plasma://ic-support/admission/operation-admission-v1`
- `plasma://ic-support/admission/backend-implementation-binding-v1`

### 6.3 Gate 2 hardening that was completed before merge

Three important trust-ABI defects were identified and fixed before merge:

1. **Exact review-subject coverage**
   - `review_binding.review_subjects` is explicit and content-addressed.
   - disposition source facts must equal the exact reviewed-subject set.
   - missing / extra / duplicate / stale / swapped subjects fail closed.

2. **Canonical requirement structural binding**
   - requirements are no longer free-form strings.
   - each requirement binds the exact canonical vendor payload artifact and an absolute JSON Pointer.
   - validator resolves the artifact and confirms the path exists.
   - validator does not interpret the field meaning.

3. **Artifact reference schema consistency**
   - v1 trust references consistently require artifact ID/type/digest and schema identity/version.

Final vendor-neutral test count was 14 tests across three synthetic vendors. CI passed before merge.

### 6.4 Generic architecture invariants

The following distinctions must remain explicit:

```text
reviewed
≠ canonical admitted
≠ operation admitted
≠ production routed
≠ hardware runtime ready
```

And:

```text
Generic governance
≠ Generic silicon semantics
```

---

## 7. Current Repository State at This Handover

At handover creation time, GitHub `main` is:

`205122c067e68ef6cdc4120e9c185e4cf7c47337`

This is later than PR-A because unrelated workstreams continued and merged PRs #476, #477, and #478. These later PRs are not evidence that PR-B has been implemented.

### Critical status: PR-B is NOT yet verifiable on GitHub

A fresh GitHub check before creating this handover found:

- no recent PR matching NXP vendor-neutral admission compatibility work
- no matching branch under expected vendor-neutral naming
- no searchable `vendor_neutral_admission_adapter` file on default branch
- no relevant compatibility-adapter commit found by expected keywords

Therefore the authoritative status is:

```text
PR-A: DONE / merged
PR-B Gate 1: APPROVED
PR-B implementation: UNKNOWN / NOT VERIFIED ON GITHUB
PR-C: NOT STARTED under this framework migration plan
PR-D: NOT STARTED under this framework migration plan
```

Do not infer that PR-B is absent from SWPC/local state. The user believes it may already be complete. The next session must inspect local/Work output before reimplementing anything.

---

## 8. PR-B Frozen Scope — NXP Compatibility Adapter

PR-B is a compatibility proof, not a semantic rerun.

Purpose:

```text
Existing immutable NXP #472 lineage
        ↓ deterministic compatibility projection
Vendor-neutral Admission v1 package
```

Forbidden interpretation:

```text
old artifacts
→ regenerate / rewrite
→ "new equivalent truth"
```

### 8.1 Required behavior

The adapter must:

- preserve all existing Gate 5.7A / Gate 5.8 / #472 artifacts byte-for-byte
- keep the exact Gate 5.8 `REJECTED_REVIEW` result
- wrap legacy facts/candidates/backend information into v1 artifact references
- create exact 140 reviewed-subject bindings
- preserve 130 inherited Gate 5.8 full-PASS facts
- preserve 10 Gate 5.8 findings
- represent 13 transformed explicitly reviewed candidates
- produce expected 143 projected candidates
- project the NXP canonical payload into a vendor-owned opaque payload suitable for generic v1 structural validation
- create a generic canonical admission envelope
- create operation admission with explicit operation contracts
- wrap the legacy OpenOCD backend implementation lock instead of replacing it
- keep `hardware_runtime_ready=false`
- retain legacy validation in parallel with generic validation

### 8.2 Operation semantics to preserve

Generic request operation should not erase vendor-specific semantics.

Required conceptual binding:

```text
request_operation = ERASE
operation_contract_id = NXP KL25 exact-sector erase contract
operation_contract_digest = content-addressed digest
```

The operation contract must preserve:

- exact one-sector erase
- 1 KiB sector geometry
- alignment requirement
- FCF-containing sector prohibition
- no implicit erase

READ / VERIFY / PROGRAM should also bind explicit target/backend operation contracts.

### 8.3 Backend compatibility binding

The generic backend binding should preserve the legacy backend lock digest:

`877b3fd9c0b9f8dc3191eb53393e5670efb93b9952ac1747bded155ebcaef4d1`

A new generic binding may have a different digest. That is expected. The new artifact must explicitly contain lineage to the legacy lock; it must not pretend the generic digest replaces historical identity.

### 8.4 Expected sidecar release

Do not modify the existing #472 release directory.

Create a separate content-addressed lineage such as:

```text
vendor-neutral-admission/releases/<content-addressed-id>/
    generic-admission-package.json
    adapter-validation-report.json
    adapter-manifest.json
```

This sidecar means:

> This artifact is the vendor-neutral compatibility representation of the immutable NXP #472 release.

It does not supersede or rewrite the #472 release.

---

## 9. PR-B Expected Repository Changes

The exact filenames may vary if implementation already exists, but the conceptual change should remain narrow. Expected files include equivalents of:

```text
data/ic-support/benchmarks/nxp-kl25/
    vendor-neutral-admission-adapter-contract-v1.json
    vendor_neutral_admission_adapter.py
    test_vendor_neutral_admission_adapter.py
    vendor-neutral-admission-payload.schema.json
    vendor-neutral-admission-wrapper.schema.json
    VENDOR_NEUTRAL_ADMISSION_ADAPTER.md
```

A minimal NXP CI workflow update is allowed if necessary.

Do not modify PR-A v1 generic schema just to make the NXP adapter easier. If NXP exposes a genuine generic-contract defect, stop and request a revised architecture decision rather than silently weakening the trust ABI.

---

## 10. PR-B Gate 2 Acceptance Criteria

A Gate 2 report should demonstrate at least the following:

| Requirement | Expected result |
|---|---|
| Legacy #472 release digest | unchanged |
| Gate 5.8 final status | `REJECTED_REVIEW`, unchanged |
| Generic review subjects | exactly 140 |
| Gate 5.8 all-pass facts | 130 |
| Gate 5.8 findings | 10 |
| Transformed candidates | 13 |
| Projected candidates | 143 expected |
| Generic canonical envelope | ADMITTED |
| READ | admitted |
| VERIFY | admitted |
| PROGRAM | admitted |
| ERASE | admitted only with exact-sector operation contract |
| Destructive/security workflows | BLOCKED |
| `hardware_runtime_ready` | false |
| Legacy NXP validator | PASS |
| Generic v1 validator | VALID |
| `KL25OpenOCDPlanCompiler` | unchanged |
| Production routing | unchanged |
| Qwen / AI rerun | not performed |
| HIL | not performed |
| PL/PPU | unchanged |

Required fail-closed mutation tests should include:

- change one retained fact digest → FAIL
- drop one reviewed subject → FAIL
- add/swap reviewed subject → FAIL
- swap candidate → FAIL
- forge inherited Gate 5.8 PASS → FAIL
- modify canonical payload/value without correct binding → FAIL
- point requirement at nonexistent/wrong JSON Pointer → FAIL
- replace backend lock/digest → FAIL
- change legacy release digest → FAIL
- promote a blocked destructive operation → FAIL
- set `hardware_runtime_ready=true` → FAIL

---

## 11. PR-C and PR-D — Do Not Start Before PR-B Closes

### PR-C — STM32 migration

Purpose: migrate existing STM32F103C knowledge/profile lineage into the same generic governance model without rewriting historical v0-v9 artifacts.

Expected work:

- freeze current relevant STM32 canonical/profile knowledge as migration facts
- perform a new manufacturer semantic review against locked DS5319 / PM0075
- disposition findings
- create new STM32 vendor canonical payload
- create generic canonical admission envelope
- bind STM32 operation semantics explicitly
- add/update STM32 backend implementation lock if operation admission is to be enabled

Do not rerun Qwen by default. Do not re-review all historical v0-v9 history. Do not call the STM32 review “NXP Gate 5.8”.

### PR-D — compiler/admission registry separation

Purpose: remove the historical coupling between compiler availability and Production routing.

Desired architecture:

```text
Operation Admission
→ backend_id / compiler_id / backend_lock_digest
→ Compiler Registry
→ vendor/backend-specific compiler
→ OpenOCDExecutionPlan
→ OpenOCDPlanExecutor
```

Maintain these distinctions:

```text
compiler available
≠ operation admitted
≠ production routed
≠ hardware runtime ready
```

Do not expand Production target set or hardware readiness as part of PR-D.

---

## 12. Overall Progress Snapshot

Within the vendor-neutral IC Support architecture track:

```text
PR-A Generic trust ABI                  DONE
PR-B NXP real-vendor compatibility      NEXT / Gate 1 approved / GitHub status unverified
PR-C STM32 migration                    pending
PR-D Compiler/admission registry        pending
Architecture Freeze v1                  after B/C/D
```

The NXP KL25 MCU Software Executor milestone itself is complete at software level. The broader Plasma production-grade programmer remains substantially unfinished because real HIL, physical SWD, PL-native programming, 8-site concurrency, fault containment, power/reset isolation, retry/recovery, manufacturing traceability, throughput qualification, and long-duration reliability are still outside the current software milestone.

---

## 13. Repository Governance / Approval Model

Per the approved repository workflow, there are exactly two approval gate types per scope:

```text
Request
→ minimal read-only inspection
→ Gate 1 Plan Approval
→ autonomous implementation / validation / commit / PR / CI repair
→ Gate 2 Merge Approval
→ merge
```

No third routine approval gate should be invented.

Unexpected out-of-scope findings require a revised Gate 1 instead of silently broadening implementation.

For PR-B, Gate 1 is already approved. If implementation exists, proceed directly toward Gate 2 validation; do not request Gate 1 again unless scope must change.

---

## 14. Execution Environment Boundary

Use the normal chat session for:

- architecture decisions
- GitHub read-only inspection
- PR review / Gate 2 reasoning
- trust-boundary analysis

Use Work mode when actual execution requires:

- repository edits
- branch/commit/push/PR implementation workflows
- SWPC command execution
- reading authoritative `/storage/projects/plasma-benchmark/...` artifacts
- generating sidecar release artifacts
- running local regression suites that require the canonical workspace

When touching SWPC:

- canonical repo: `/storage/projects/plasma`
- preserve untracked files
- do not overwrite retained artifacts
- stop on unexpected tracked changes/divergence
- read `AGENTS.md` before implementation

---

## 15. Immediate Continuation Procedure

The next session should execute the following sequence:

```text
1. Read this H007 handover.
2. Check GitHub main and latest PRs again.
3. Search for an existing PR-B branch/PR/commit under any plausible name.
4. If GitHub still has nothing, inspect SWPC/local Work output before reimplementing.
5. If a completed local PR-B exists:
      push branch
      create/update PR
      run CI
      produce Gate 2 report
      STOP before merge
6. If no implementation exists:
      implement frozen PR-B scope only
      run legacy + generic validation
      create sidecar release
      push PR
      run CI
      STOP at Gate 2
7. Do not start PR-C or PR-D until PR-B is closed.
```

---

## 16. Copy/Paste Prompt for the Next Session

```text
[AI IC SUPPORT] NXP-2

Read handover H007 and continue the NXP KL25 vendor-neutral admission compatibility transaction.

PR-A / PR #474 is already merged. PR-B Gate 1 is already approved. First determine whether PR-B implementation already exists in GitHub or SWPC/local Work output; do not reimplement it blindly.

If a PR/branch exists, audit it against H007 Gate 2 acceptance criteria. If implementation exists only locally, push it, create/update the PR, run CI, and stop at Gate 2. If no implementation exists, implement PR-B exactly as frozen in H007.

Do not modify immutable NXP Gate 5.7A / Gate 5.8 / #472 releases, do not rerun AI, do not modify runtime/compiler selection, Production routing, HIL, PL/PPU, or STM32. Preserve Gate 5.8 REJECTED_REVIEW and the #472 release digest. Require both legacy NXP validation and generic v1 validation.

Do not merge without explicit Gate 2 approval.
```

---

## 17. Key References

- PR #472 — Add KL25 post-review Software Executor candidate  
  `https://github.com/physicslu/plasma/pull/472`

- PR #474 — Add vendor-neutral IC admission governance  
  `https://github.com/physicslu/plasma/pull/474`

- PR-A merge commit  
  `39cbe4b6bbb11687ff7117dfac0b06cb856428fc`

- Current main at handover creation  
  `205122c067e68ef6cdc4120e9c185e4cf7c47337`

- Existing repository handovers through H006 were present at handover creation; H007 was not yet present in the repository.

---

**End of H007.**
