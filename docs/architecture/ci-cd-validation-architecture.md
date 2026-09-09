# CI/CD Validation Architecture

Status: **Current repository validation and delivery contract**

## 1. Purpose

Plasma CI/CD is organized by **risk boundary and authority**, not by directory size or workflow count.

The governing question is:

> For this change, which executable contract can realistically regress, and what is the cheapest gate that proves it?

A workflow must run because it owns a real dependency. It must not run merely because a broad path glob happens to include an unrelated data file.

Priority:

```text
correctness
  -> authority / dependency ownership
  -> isolation of failure domains
  -> reproducibility / auditability
  -> feedback latency
  -> runner efficiency
```

## 2. Top-level validation domains

The repository has several independent validation domains:

```text
Repository / docs
    -> repository-contracts

Web / Control Station software
    -> web source / browser / runtime / installer gates

Python / PL software
    -> Python + PL source tests
    -> software runtime acceptance

Device Catalog
    -> historical catalog regression
    -> current catalog regression
    -> family-specific bounded discovery/policy/admission

AI IC Support research
    -> manufacturer evidence processing
    -> Evidence Pack / applicability
    -> AI extraction benchmarks
    -> candidate programming-method research

PPU / Z2 release
    -> packaging
    -> ARMv7 / QEMU acceptance
    -> installer / network / release qualification
```

These domains can reference one another's facts without sharing the same CI gate.

A PASS in one domain does not imply a PASS in another:

```text
Device Catalog admission
    != OpenOCD programming support
    != PPU implementation
    != Socket support
    != physical IC qualification

AI IC Support research PASS
    != software runtime support
    != PPU implementation
    != real-IC programming validation

GitHub software CI PASS
    != SWPC deployment acceptance
    != Z2 / FPGA hardware acceptance
```

## 3. Device Catalog authority

`data/device-catalog/` owns commercial IC identity and user-selectable catalog admission.

A Production ICPN means the exact commercial part is admitted to the selectable catalog with its canonical identity/metadata evidence. It does **not** mean every programming backend supports it.

Primary workflows:

```text
.github/workflows/device-catalog-validation.yml
.github/workflows/device-catalog-current-validation.yml
.github/workflows/device-catalog-stm32f2-bounded-validation.yml
.github/workflows/device-catalog-stm32f3-foundation-validation.yml
```

Catalog changes may run targeted catalog-facing adapter tests when those tests are part of the catalog contract. They must not fan out into the complete Python/PL suite, PPU release, or Z2 release merely because the Production manifest gained rows.

The governing invariant is:

> ICPN count is inventory/selectability. Backend capability is status.

Examples of orthogonal capability status include:

```text
OpenOCD mapping / execution support
Plasma native programming support
PPU qualification
Socket availability
Electrical qualification
HIL / physical programming verification
```

## 4. AI IC Support research authority

`data/ic-support/` is an AI-assisted **research/pilot** domain for deriving evidence-backed programming knowledge and candidate programming methods from manufacturer documentation.

Primary deterministic workflow:

```text
.github/workflows/ic-support-validation.yml
```

Networked manufacturer-source validation remains separately bounded, for example:

```text
.github/workflows/ic-evidence-live-validation.yml
```

AI IC Support research does not own:

- commercial ICPN admission;
- Plasma software runtime behavior;
- OpenOCD execution implementation;
- PPU implementation;
- Socket support;
- physical programming qualification.

Therefore ordinary AI IC Support research changes must not trigger Python/PL runtime tests or release qualification.

The research workflow may depend on a **precise retained reference input** when the benchmark itself binds that input. For example, the STM32F103C research pilot pins the STM32F1 commercial catalog. That precise data-to-data dependency is valid; it is not permission to trigger the workflow for every new ICPN in every family.

Research output is not automatically promoted into runtime support. Promotion requires a separate capability/runtime contract.

## 5. Python and PL source tests

Workflow:

```text
.github/workflows/python-tests.yml
```

Primary responsibility:

- Python source regressions;
- PL source regressions;
- software-owned repository/configuration checks executed by this workflow.

Device Catalog data-only changes do not trigger this workflow. Catalog-specific Python adapter behavior is validated by the Device Catalog domain where required.

AI IC Support research data does not trigger this workflow merely because research artifacts exist in the same repository.

## 6. Runtime, installer and release gates

Software/release workflows validate executable or deployable artifacts, not catalog inventory counts.

Examples:

```text
.github/workflows/control-station-runtime.yml
.github/workflows/ppu-release.yml
.github/workflows/z2-ps-release.yml
.github/workflows/product-release.yml
.github/workflows/windows-control-station-installer.yml
.github/workflows/macos-control-station-installer.yml
```

PPU and Z2 gates own risks such as:

- immutable release payload construction;
- ARMv7 userspace execution;
- QEMU qualification;
- installer behavior;
- PPU networking acceptance;
- release artifact integrity.

A Device Catalog row addition does not alter those artifacts by itself and therefore does not trigger those release gates.

Conversely, changes to PPU/Z2 software, packaging scripts, deployment contracts, or explicitly executed release tests must still trigger the appropriate heavy release validation.

## 7. Capability status is separate from catalog admission

The product model is:

```text
Manufacturer identity evidence
        |
        v
Device Catalog
        |
        +--> ICPN selectable = yes
        |
        v
Capability / qualification state
        +-- OpenOCD
        +-- Plasma native / PPU
        +-- Socket
        +-- electrical
        `-- physical/HIL
```

A catalog ICPN can therefore be valid and selectable while a capability is `unsupported`, `unqualified`, `unknown`, or `not tested`.

CI must preserve that separation. Missing backend support is not a reason to hide a valid commercial ICPN from the catalog.

## 8. Runtime capability promotion boundary

The former code-level bridge from SW/PPU runtime directly into `data/ic-support/` is closed.

Current executable rules are:

```text
AI IC Support research (`data/ic-support/`)
        X  no implicit runtime read
        |
        v only through future explicit promotion
SW/PPU-owned runtime capability source
        -> explicit resolver injection
        -> route/plan/runtime gates
```

`software/python/plasma_core/ic_support.py` has no repository-relative AI-research default and no environment fallback to `data/ic-support/`. `SiteManager` does not automatically construct a research-backed resolver for non-Mock Sites.

Because no Production-promoted runtime capability package exists today, the default non-Mock runtime state is intentionally fail-closed. A Job requiring target capability cannot enter the registry, acquire the PPU execution lease, reach a SiteWorker queue or access hardware unless an explicit SW/PPU-owned resolver is supplied and later runtime gates also pass.

Software plan/router/executor tests use a SW-owned synthetic capability fixture. Passing those tests validates software mechanics only; it does not promote AI research output or create a hardware-support claim.

A future research-to-runtime promotion mechanism must be an explicit reviewed transaction with its own SW/PPU validation and, where appropriate, PPU/HIL qualification.

## 9. Trigger ownership rules

1. **Authority first.** Decide which domain owns the changed fact before choosing a workflow.
2. **Executable dependency beats directory convention.** A path glob is evidence of dependency only when the workflow actually owns the risk.
3. **ICPN inventory is not a release artifact.** Device Catalog additions do not trigger Python/PL, PPU, or Z2 release qualification by default.
4. **AI research is not runtime.** `data/ic-support/**` research changes do not automatically trigger software runtime validation.
5. **Capability is orthogonal to identity.** OpenOCD/PPU/Socket/HIL status does not gate catalog selectability unless a separate product policy explicitly says so.
6. **Use precise cross-data dependencies.** A benchmark may trigger on one pinned catalog source it actually binds; do not replace that with a whole-family or whole-production glob.
7. **Tests are not deployable runtime by default.** Release workflows follow only tests/helpers they execute directly.
8. **Documentation is not runtime by default.** Markdown belongs to documentation integrity unless a release process consumes it.
9. **Do not weaken a real dependency to save runners.** If a true code-level dependency exists, fix the architecture rather than hiding it with a path exclusion.
10. **Historical evidence stays historical.** Current catalog growth must not rewrite old phase boundaries.

## 10. Concurrency and superseded runs

PR-oriented workflows that can be superseded by a newer commit should use workflow-level concurrency such as:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

The invariant is:

> Once a newer commit supersedes an older PR commit, the obsolete run should not continue consuming runners unless the workflow has an explicit evidence reason to complete every run.

Manual/live evidence workflows may intentionally use different concurrency semantics.

## 11. Required validation for CI topology changes

A CI topology PR should prove its own boundary:

- modified workflows self-trigger when practical;
- retained validation commands remain owned somewhere appropriate;
- no software/runtime test is deleted merely to obtain a green result;
- no historical evidence is rewritten to present-day numbers;
- documentation integrity remains green;
- data-only catalog work must not fan out into Python/PL, PPU and Z2;
- AI IC Support research-only work must not fan out into software/runtime qualification.

## 12. Historical evidence boundary

`data/device-catalog/research/**` contains admission plans, baselines, retained evidence and audit records whose counts represent the repository state at those historical checkpoints.

Do **not** rewrite old numbers to match the current Production catalog. They are transaction evidence, not current coverage documentation.

The authoritative current catalog count belongs to:

```text
data/device-catalog/production/icpn-v1-manifest.json
```

## 13. Related documents

- [Plasma Engineering Workstreams](../../WORKSTREAMS.md)
- [Documentation Maintenance](../development/documentation-maintenance.md)
- [Operator Acceptance Test Matrix](../development/operator-acceptance-test-matrix.md)
- [Mock Continuous Delivery](../development/mock-cd.md)
- [Runtime Acceptance](../testing/runtime-acceptance.md)
- [IC Support Coverage Normalization](ic-support-coverage-normalization.md)
- [Runtime Capability Resolver and Execution Binding](ic-support-runtime-resolver.md)
- [Product Deployment Foundation](../deployment/product-deployment-foundation.md)
- [Product Release Format v1](../deployment/product-release-format.md)
