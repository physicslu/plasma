# OPF S5-A — bounded source convergence and import-boundary regression

**Approval:** 2026-11-08 Gate 1, ChatGPT Direct / source-only.
**Baseline:** `main@3d102beaece1c55ede986645809b4bbaecc56797`.
**Scope:** A small, bounded first S5 cleanup; **not** S5 Final Closure.
**Reference:** [S0–S5 roadmap](../architecture/plasma-core-convergence-and-deletion-first-roadmap.md) and [OPF architecture](../architecture/opf-architecture.md).

## Responsibility and deletion ledger

- **Portable OPF:** `plasma_opf/__init__.py` imports `.contract` and `.python_provider`; `python_provider` imports `.contract`. All three files use Python standard-library modules and internal OPF references, with no direct PPU, Bundle, C-3, OpenOCD, FPGA or Catalog imports. An isolated `python -I -S` test copies **only** `plasma_opf`, parses a selection and proves that a fake successful process cannot be reported as qualified Flash.
- **PPU Host:** `SiteManager` owns `SiteExecutionRouter` and its existing `SiteWorker`/PPUExecutionLease; the single router admits `mock_workflow`, C-3 `openocd` or authorized C-2 `opf_package`. Those are three modes of one route authority, **not** three independent executable routers. No route/safety behavior is modified here.
- **Catalog:** #1356/#1360 removed Runtime CompilerRegistry/PlanCompiler/Executor; #1361 removed Catalog modules/data from PPU packaging and its Gateway startup. Historical ICPN evidence remains upstream governance.
- **Source fix:** `execution_router.py` described a retired Plan Compiler as current. Correct the module comment to describe Bundle-driven C-3. Reconcile the corresponding stale S5 roadmap/disposition text.
- **Tests:** add a source AST import-boundary guard, true isolated OPF-only subprocess import, injected cross-boundary import negative control, and retired compiler source-absence checks.
- **Production LOC:** no executable statements, functions or routes added/deleted. Only a module docstring changes. Record exact GitHub diff separately from executable LOC.

## Non-goals / preserved safety

No changes to OPF selection/Provider behavior, Bundle v3/Active Set, `SiteManager`, Router/Handler control flow, PPUExecutionLease, RuntimeQuiesceGate, C-3 Site Worker, FPGA Owner/Reload, Root Guard, SAFE_OFF, SEALED, Recovery, unknown-outcome no-resend, or device access. No alternative Router, Registry, Executor or Adapter.

PR-C2 owns Manager/Console Device Selector consumer migration; the legacy PPU Gateway Selector compatibility endpoint is intentionally **not** touched until that migration is complete. OPF is still distributed in the shared `plasma-multichannel` wheel: independent Python distribution packaging is a product decision, not an S5-A dependency.

## Evidence and remaining closure

- Required CI: Python PS tests (including existing S1-B standalone Provider, S1-C routing and S5-A negative tests), repository contracts and applicable Host-only safety checks.
- Host-only / exact-HEAD CI: report observed outcomes in the PR; tests are not presumed passed by this document.
- Z2 / SWPC services / FPGA / DUT / physical Flash: **NOT_RUN**; previous Site 2 A/B HIL receipts remain historical evidence, not S5-A results.
- S5 Final Closure remains pending PR-C2 migration, broader import/reachability ledger, and S2/S4 multi-Site/non-OpenOCD physical qualification. Do not remove existing safety owners on file-name similarity alone.
