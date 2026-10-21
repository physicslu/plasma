# Path 2 Build / Download / Testing — Gate 1 host-only adapter contract

**Status:** Draft PR, software/Host-only contract. No runner activation, SWPC usage, Vivado build, FPGA reconfiguration, DUT/LA operation, or production qualification.

## Existing components to reuse

- Owner-authorized `scripts/plasma_development_dispatch.py` provides strict Issue #981 / PR / SHA approval, one-shot Work Order and capability routing.
- `scripts/plasma_vivado_host_build.py` and `scripts/plasma_fpga_build_diagnostics.py` are the fixed, reviewed Vivado HOST **Build Code** engine; not reimplemented.
- `pl/hil/swd04/one_shot.py`, `pl/hil/swd04/development.py`, and `pl/hil/f1b.py` provide reusable **FPGA Manager lifecycle**, Hardware Profile, and Test Callback. These are used by future independently approved trusted Download and Testing adapters. No direct hardware adapter is enabled in this Gate 1 change.
- Historical [Run #39395142726 evidence](../development/plasma-f1b-path3-39395142726-evidence.md) / [Codex exact operation ledger](../development/plasma-f1b-path3-39395142726-codex-steps.md) provide the prior real Z2 F1-B one-shot and actual command/exception recovery sequence. Historical DEV PASS does **not** prove PS–PL AXI isolation or production readiness.

## New minimal coordinator

`scripts/plasma_path2_stage_orchestrator.py` is a pure Python stage coordinator with **injected** adapter callbacks. It is not exposed as an issue-command task and does not import SSH/sudo, Vivado, FPGA Manager or MMIO. It performs strict request/receipt schema and provenance checks, derives the next stage from the **explicit per-run options** and stops after the selected stage(s). Only the trusted Path 2 execution boundary may later create verified adapters and authorize a real operation.

| Explicit initial trigger | Input prerequisite | Default effect | Independent option |
|---|---|---|---|
| `build` (Build Code) | source SHA, Hardware Profile, target identity and reviewed Build capability | Run Build only; stop | `auto_download_after_build_success=true` adds Download after accepted Build receipt |
| `download` (Download FPGA) | approved Build receipt bound to source SHA, profile and immutable image hash | Run Download only; stop | `auto_test_after_download_success=true` adds Testing after accepted Download receipt |
| `test` (Testing) | approved loaded-image receipt bound to source SHA, image, profile, target and lease | Run Testing only; stop | no implicit next stage |

Options are independent booleans **both default false**; `auto_test_after_download_success=true` by itself does **not** cause a Download after Build. Starting at Build can reach all three only if **both** options were explicitly enabled. An explicitly selected Download or Test never silently calls Build. Failed or malformed evidence stops the current sequence, without blind retry.

A standalone Download or Testing request **must pin the expected artifact SHA256** before any callback is invoked; the supplied prior Build/Load receipt must match that hash. Receipt validation includes exact stage/status/schema, immutable source and artifact SHA256, Profile and Target identity, Download lease, Load evidence and Test evidence. A successful **fake adapter** proves only contract correctness; it does not authenticate the producer of a receipt or establish actual FPGA state. Any real backend integration must independently enforce owner approval, capability, hardware locks, current boot/firmware and AXI ownership, trusted provenance, timeout, recoverability and durable evidence.

**Restore is safety cleanup**, not a fourth automatically triggered stage. Whether a test image remains loaded after Download, when recovery is required, and how the configuration owner preserves the lease across separated triggers must be decided by the reviewed hardware backend; do not blindly reuse the dated Path 3 owner UIO bypass.

## Gate 1 qualification and limit

GitHub-hosted test `pl/tests/test_path2_three_stage_orchestrator.py` uses inert Python callbacks for: three independent triggers, both opt-in transitions independently and together, default OFF, provenance mismatch rejection, missing prior receipts, fail/NO_GO, missing handler preflight, and no retry. Existing CI should run this under `Python and PL source tests`. No changes to trusted Dispatcher Registry or shared Workflow are permitted by this PR.

**Next authorization boundary:** after review, a distinct owner-approved integration Gate must connect the coordinator to existing, appropriately authorized Build/Download/Test adapters. Do not infer real Trigger availability from this software-only contract.
