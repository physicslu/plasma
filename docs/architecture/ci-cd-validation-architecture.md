# CI/CD Validation Architecture

Status: **Current repository validation and delivery contract**

## 1. Purpose

Plasma CI/CD is organized by **risk boundary**, not by the number of YAML files.

The governing question is:

> For this change, which executable contracts can realistically regress, and what is the cheapest gate that proves them?

A workflow should run because it owns a dependency or risk surface. It should not run merely because a broad directory glob happens to contain the changed file.

The priority order is:

```text
correctness
  -> dependency ownership
  -> isolation of failure domains
  -> recoverability / traceability
  -> feedback latency
  -> runner efficiency
```

Runner savings are useful, but they must never be purchased by hiding a real dependency.

## 2. Validation topology

The current repository topology is:

```text
                         repository change
                                |
        +-----------------------+-----------------------+
        |                       |                       |
        v                       v                       v
 Documentation             Web / Console          Python / PL source
 integrity gate                 |                       |
                                +--> Web Fast           +--> Python / PL tests
                                |    lint/build/source
                                |
                                +--> Web E2E + visual
                                |
                                +--> runtime-affecting gates only
                                      when their source dependencies change

                         cross-stack / delivery layers
                                |
          +---------------------+-----------------------+
          |                     |                       |
          v                     v                       v
       Mock CD            Mock CD Browser      Control Station runtime
    software stack        real browser +       Linux/macOS/Windows
                          persistent stack      packaging acceptance

          |                     |                       |
          +---------------------+-----------------------+
                                |
                                v
                        installer / release gates
                 Windows MSI / macOS PKG / Product / PPU

                    Device support validation domain
                                |
                +---------------+---------------+
                |                               |
                v                               v
     Device Catalog historical       Device Catalog current
          regression gate                  regression gate
                |                               |
                +---------------+---------------+
                                |
                                v
                  production Device Catalog inputs
                                |
                                v
                      IC Support coverage
                                |
                     resolver / OpenOCD plan /
                     software executor /
                     execution-admission checks
```

A PASS in one layer does not imply PASS in a higher layer. In particular:

```text
GitHub software CI PASS
    != SWPC deployment acceptance
    != Z2 / FPGA acceptance
    != real-IC programming validation
```

## 3. Fast source gates

### 3.1 Documentation integrity

Workflow:

```text
.github/workflows/documentation-integrity.yml
```

Primary responsibility:

- Markdown structure and local-link integrity;
- documentation index coverage;
- public-document sanitization;
- selected executable documentation contracts;
- canonical documentation facts that must track source values.

Markdown-only changes should normally terminate at this layer unless a specific higher-level workflow actually consumes the Markdown as build/runtime input.

### 3.2 Web Fast

Workflow:

```text
.github/workflows/web-tests.yml
```

Primary responsibility:

- Web dependency installation;
- lint;
- build and source/SSR tests.

This is the fast Web source gate. It is intentionally separate from Playwright/browser installation.

### 3.3 Web E2E and visual regression

Workflow:

```text
.github/workflows/web-e2e.yml
```

Primary responsibility:

- Playwright browser acceptance;
- Chromium/browser runtime;
- visual regression diagnostics and artifacts.

Browser tests are validation assets, not deployable runtime. A test-only E2E change must not automatically be treated as a Control Station or Mock CD runtime-source change unless that downstream workflow directly executes the changed test/helper/config.

### 3.4 Python and PL source tests

Workflow:

```text
.github/workflows/python-tests.yml
```

Primary responsibility:

- repository safety/configuration checks owned by the workflow;
- Python package installation;
- Python regression suite;
- PL source tests.

Python documentation is handled by the documentation layer. Runtime workflows should distinguish Python runtime source from `software/python/tests/**` and `software/python/docs/**` when they do not execute those trees.

## 4. Cross-stack runtime acceptance

### 4.1 Mock CD

Workflow:

```text
.github/workflows/mock-cd.yml
```

Mock CD validates an ephemeral Plasma software stack on a clean runner. It is broader than unit/source CI and narrower than real deployment/hardware acceptance.

Its trigger boundary follows runtime source, not unrelated test/documentation trees.

### 4.2 Mock CD Browser Runtime Acceptance

Workflow:

```text
.github/workflows/mock-cd-browser.yml
```

This gate starts the real Mock CD software stack and executes the explicitly selected real-stack Playwright specifications.

The trigger set is intentionally narrower than all of `software/web/e2e/**`: only the real-stack specs, their shared helper/config/package inputs, and runtime source they actually consume belong to this gate.

### 4.3 Control Station runtime packaging acceptance

Workflow:

```text
.github/workflows/control-station-runtime.yml
```

Primary responsibility:

- build the Control Station runtime;
- validate clean extraction;
- smoke Console/BFF/Manager behavior;
- run on Linux, macOS and Windows.

Web/Python test implementation is not itself a deployable Control Station artifact and should not trigger this gate unless it changes a directly consumed runtime/build contract.

## 5. Installer and release gates

Installer and release validation is not the same as application compatibility validation.

Current delivery gates include:

```text
.github/workflows/windows-control-station-installer.yml
.github/workflows/macos-control-station-installer.yml
.github/workflows/product-release.yml
.github/workflows/ppu-release.yml
```

Their responsibility is packaging/release behavior such as:

- immutable release payloads;
- clean extraction;
- service/install lifecycle;
- platform-specific installer behavior;
- SHA-256/integrity verification;
- PPU ARMv7/QEMU acceptance and network acceptance where owned by the PPU release workflow.

Ordinary React/UI or Markdown changes must not pay the cost of MSI/PKG/QEMU validation unless they modify a contract that those packaging pipelines consume.

Release CI remains software evidence. A PPU release/QEMU PASS is not PYNQ-Z2 native hardware acceptance.

## 6. Device Catalog validation domains

Device Catalog validation is deliberately split into two complementary gates.

### 6.1 Historical/full regression

Workflow:

```text
.github/workflows/device-catalog-validation.yml
```

This gate protects retained historical acquisition, evidence, policy and admission contracts. At the current repository state it covers the historical chain through STM32F4 Phase 4.1 batch3 plus the production manifest/runtime-view checks owned by that workflow.

The historical gate exists because a new admission must not silently invalidate earlier fail-closed policy or retained evidence.

### 6.2 Current regression

Workflow:

```text
.github/workflows/device-catalog-current-validation.yml
```

This gate owns the current continuation surface:

```text
Phase 4.1 R/T batch4
Phase 4.2A
Phase 4.2B
Phase 4.2D
Phase 4.2E0
Phase 4.2F
Phase 4.2H
Phase 4.2I
Phase 4.2J
```

The current gate shares one runner/setup boundary and executes each unique deterministic regression contract once.

Historical and Current are **not duplicates**. They cover different lifecycle ranges. Do not delete one merely because both react to Device Catalog work.

Future trigger partitioning between these two gates requires an explicit dependency map for shared validators/helpers. Do not use filename-only negative globs to hide a shared dependency.

## 7. Device Catalog -> IC Support cross-domain dependency

Workflow:

```text
.github/workflows/ic-support-validation.yml
```

IC Support coverage is derived from production Device Catalog inputs. Therefore IC Support validation must run when its direct production inputs change:

```text
data/device-catalog/production/icpn-v1-manifest.json
data/device-catalog/research/stm32f1-commercial-icpn.csv
data/device-catalog/research/stm32f4-commercial-icpn.csv
```

This dependency prevents the production catalog from expanding while IC Support coverage snapshots remain stale.

The current enforced production coverage is:

```text
Exact ICPNs:                           286
STM32F1 exact ICPNs:                    75
STM32F4 exact ICPNs:                   211
Base Devices:                           91
Deterministic OpenOCD-mapped ICPNs:    286
Direct IC Support-bound ICPNs:           2
Unresolved Programming Profile ICPNs:  284
Evidence-backed Programming Profiles:    1
Native PPU runtime-ready ICPNs:           0
```

These metrics are not interchangeable. `286 deterministic OpenOCD-mapped ICPNs` is routing/catalog evidence; it is not a claim of 286 Programming Profiles or 286 hardware-supported targets.

## 8. Concurrency and superseded runs

PR-oriented workflows that can be superseded by a newer commit should use workflow-level concurrency such as:

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```

The invariant is:

> Once a newer commit supersedes an older PR commit, the obsolete run should not continue consuming runners unless the workflow has an explicit evidence reason to complete every run.

Manual/live evidence workflows may intentionally use different concurrency semantics.

## 9. Trigger ownership rules

Use these rules when changing workflow `paths`:

1. **Executable dependency beats directory convention.** Read the job and identify what it actually imports, executes, packages or validates.
2. **Documentation is not runtime by default.** Markdown belongs to Documentation integrity unless another workflow truly consumes it.
3. **Tests are not deployable runtime by default.** A runtime workflow should follow only the tests it executes directly.
4. **Shared helpers require explicit treatment.** Do not exclude a directory if a retained test imports a helper from it.
5. **Production data is a runtime dependency when code reads it.** Device Catalog manifest/source changes legitimately cross into IC Support and release/runtime validation where consumed.
6. **Do not use workflow count as the optimization metric.** One workflow with ten expensive matrix jobs can cost more than ten small workflows.
7. **Do not weaken coverage during topology cleanup.** First change when/where validation runs; only deduplicate commands after proving identical invocations add no distinct fixture, state or failure domain.

## 10. Required validation for CI/CD changes

A CI/CD topology PR should prove its own boundary before merge:

- modified workflows self-trigger when practical;
- every retained validation command still executes at least once in the intended gate;
- no application/runtime test is removed merely to obtain a green result;
- stale/failing assertions are investigated against the current executable contract rather than skipped;
- documentation integrity is green when Current documentation changes;
- historical evidence documents are not rewritten to present-day numbers.

For changes that intentionally prevent a workflow from triggering on an unrelated path, the strongest proof is a later PR containing only that unrelated path and showing the heavy workflow no longer fans out.

## 11. Historical evidence boundary

`data/device-catalog/research/**` contains admission plans, baselines, retained evidence and audit records whose counts represent the repository state at those historical checkpoints.

Do **not** rewrite those old numbers to match the current 286-ICPN catalog. They are evidence, not Current coverage documentation.

Current architecture/coverage documents must instead report present executable facts and clearly distinguish them from historical snapshots.

## 12. Related documents

- [Documentation Maintenance](../development/documentation-maintenance.md)
- [Operator Acceptance Test Matrix](../development/operator-acceptance-test-matrix.md)
- [Mock Continuous Delivery](../development/mock-cd.md)
- [Runtime Acceptance](../testing/runtime-acceptance.md)
- [IC Support Coverage Normalization](ic-support-coverage-normalization.md)
- [IC Support Runtime Resolver Foundation](ic-support-runtime-resolver.md)
- [Product Deployment Foundation](../deployment/product-deployment-foundation.md)
- [Product Release Format v1](../deployment/product-release-format.md)
