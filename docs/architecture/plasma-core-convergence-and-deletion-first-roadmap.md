# PLASMA Core Convergence and Deletion-First Roadmap

> **Status:** Proposed, documentation-only plan. **Baseline:** `main@5b61e28f34f02ab924daf3e1f70be87f6d346ed0` (2026-11-07).
> **Purpose:** A single, long-lived reference for subsequent implementation PRs; it is **not** implementation approval, evidence of hardware readiness, or a new approval gate.
> **Authority:** [AGENTS.md](../../AGENTS.md), the [shared development contract](../development/plasma-development-common.md), [OPF architecture](opf-architecture.md), [Unified Bundle-driven Programming Decision](unified-bundle-driven-programming-decision-2026-11-04.md), and [Bundle v3](ppu-canonical-bundle-packages.md). Where a proposal here conflicts with approved contracts or actual executable safeguards, resolve the conflict explicitly through the existing Gate 1 process; do not silently weaken a guard.

## 1. Decision: reduce the executable core, not merely relocate code

PLASMA is a universal multi-Site IC programmer, not a collection of per-IC or per-board routing branches. The primary success metric is a **smaller, more understandable trusted execution core** with fewer independent programming paths and less duplicated authority, while third parties can add supported programming behavior through bounded, verified extensions.

The total repository line count can grow legitimately as new Providers, platforms, tests, and qualification evidence are added. Raw LOC reduction alone is **not** a safety or acceptance criterion. Deletion-first means replacing old mechanisms, removing dead paths, and reducing responsibilities and reachable complexity whenever a successor is delivered.

**Mandatory engineering direction for future PR plans referencing this roadmap:**

1. **One canonical programming execution pipeline.** Do not maintain OPF and legacy exact-ICPN CompilerRegistry routing as two permanently executable product paths.
2. **The IC Catalog, L0/L1/L2 qualifications and exact-ICPN inventory are advisory upstream information**, not a mandatory PPU execution allowlist. A selected authorized Bundle/Profile/Provider must still pass real device, memory, capability, privilege and hardware-safety checks.
3. **A verified Active Asset Set supplies runtime programming artifacts.** Select Provider, Profile, Driver and applicable FPGA Image from the same authorized Bundle; no unverified source-tree fallback or cross-Bundle mixing.
4. **Core owns Job, Asset/Bundle identity, Resource/Site Sessions, authority, evidence and failure handling.** Protocol algorithms, geometry, adapter register layouts and platform-specific recovery belong behind narrow interfaces.
5. **Replace-by-Default:** delete retired branches, compatibility shims, duplicated validators, stale tests and conflicting documentation in the *same migration PR* once their actual callers have been migrated, absent explicit owner approval.
6. **Extension without core edits:** adding a qualified IC Profile or independently implemented Provider must not require changing a built-in brand/exact-ICPN list, per-operation Compiler Registry, or Z2-only hard-coded branch in Core.
7. **No safety regression:** retained checks include ZIP/file hashes and bounded paths, executable restrictions, owner authorization, effective hardware identity/capabilities, Site fencing, PPU-wide shared resource/FPGA reload lock, Job deadline, cancellation, SAFE_OFF, persistent SEALED/Recovery and fail-closed uncertainty. Trust is not synonymous with GitHub origin or Publisher signature.
8. **Deployment is not programming.** Bundle v3 B1/B2/B3 installation and selection do not prove or authorize a DUT Flash Job. Deployment lifecycle actions such as install/verify/activate/rollback are not programming-operation plugins and must not be conflated.

This document introduces **no** new API/schema or implementation requirement on its own. It consolidates and makes measurable the already approved direction and requests Gate 1 authorization for each bounded implementation slice.

## 2. Observed baseline and design debt (2026-11-07, read-only)

These are source-inspection findings, **not** claims that the deployed SWPC/Z2 runtime behaves identically or that HIL succeeded.

| Area | Existing source at baseline | Convergence gap |
| --- | --- | --- |
| Bundle-driven Flash C-3 | `software/python/plasma_server/execution_router.py`, `software/python/plasma_interfaces/openocd.py` | C-3 routes `flash_cycle` by Active Bundle; other operations still enter legacy exact-ICPN/CompilerRegistry checks. |
| Static compilation/IC admission | `software/python/plasma_interfaces/compiler_registry.py`, `software/python/plasma_interfaces/openocd_plan.py`, `software/python/plasma_core/ic_support.py` | Legacy binding and static profile sets remain; audit every reachable caller before removal. |
| Verified Bundle v3 | `scripts/ppu_unified_deployment.py`, `scripts/ppu_asset_set.py` | SHA, paths, dependency DAG and target checks exist. Do not replace with publisher/GitHub origin gates. Distinguish canonical v3 from legacy v1/v2 code. |
| One-click CLI | `scripts/plasma_program.py` | `flash/run` currently require `--runtime-sha`; external `--image` must exactly match the image embedded in the Bundle. Separate runtime compatibility/version fencing from Git repository pinning, and define any truly external-image policy explicitly. |
| Provider/Adapter | `scripts/ppu_provider_contract.py`, `scripts/ppu_site_adapter_abi5.py`, `scripts/ppu_site_worker_service.py` | Some Bundle/Capability checks exist, but the production worker directly instantiates the Z2 ABI-v5 adapter with fixed Sites and operations. Package execution does not yet prove general hardware Provider/Adapter plugin support. |
| Platform/recovery | `scripts/ppu_fpga_qualification.py`, `pl/hil/fpga_image_guard.py` | Z2 ABI details and protected Golden recovery are still platform-specific code. Move decisions behind a bounded platform contract only after equivalently safe Z2 behavior is proven. |
| Deployment lifecycle / historical formats | `scripts/ppu_asset_set.py`, `scripts/ppu_unified_deployment.py`, `docs/architecture/ppu-canonical-bundle-packages.md` | Fixed deployment action vocabulary and surviving legacy format descriptions require reachability and contract reconciliation. Do not indiscriminately delete supported active call paths. |

Relevant existing migration contract: [OPF-1 through OPF-5](opf-architecture.md#opf-migration-plan--independent-prs). **Do not establish a parallel "universal core v2" product pipeline**. Work must converge on OPF and Bundle v3, not wrap the old system in an additional abstraction layer.

## 3. Target boundaries

```text
Console / Manager / user-defined client
    | authorized high-level Job (no SWD bit transport)
    v
PPU Gateway + Job/Asset/Resource Core
    | verified, single Active Asset Set + operator authorization
    | one Site Session / stale-worker fence + deadline + SAFE_OFF authority
    v
OPF Provider selection and narrow execution interface
    | Provider-owned algorithm/options/geometry; PPU-owned permissions
    +--> qualified platform Adapter/Driver --> Z2 PS --> PL --> DUT
    +--> qualified PS-only transport ---------------------------> DUT

Bundle v3 B1/B2/B3 admission/install/activate is independent of Flash Job admission.
```

Non-negotiable current placement for the physical Z2 prototype: **SWPC Web/Controller/BFF; Z2 PS runs live OpenOCD/WordPort; Z2 PL performs SWD/SPI I/O.** A platform extension must not move live bit-level traffic across Ethernet. Different physical platforms must establish their own qualified adapter and ownership contract rather than silently bypassing the present boundary.

"Plugin" never implies arbitrary root execution. An authorized package executable may run within the existing controlled process boundary; it receives no inherent right to grant itself Site leases, load FPGA images, override ABI or SAFE_OFF, use arbitrary file paths or issue unmediated power/reset commands.

## 4. Implementation sequence: small, deletion-accountable PRs

| Slice | Planned output | Replacement/deletion obligation | Acceptance proof |
| --- | --- | --- | --- |
| **S0 — Inventory** | Trace production entrypoints, dynamic imports, callers, legacy paths, tests and docs; capture measurable baseline and a keep/replace/remove ledger. | Identify exact owners of each duplicate check. No speculative deletion. | Reproducible inventory, explicit reachable vs dead classification, no production code edits. |
| **S1 — Single route** | Align `execution_router` and OPF selection with the existing [OPF-2/OPF-4](opf-architecture.md) plan. Cover all supported programming operations through one Provider boundary, not just C-3 `flash_cycle`. | Remove old route branches and redundant compilation/allowlist checks once their consumers are migrated. | Two independent host-only Providers including a non-OpenOCD fake; negative routing tests; one product path shown by reachability. |
| **S2 — Unified Site authority** | Coordinate [OPF-3](opf-architecture.md) Session/fence/deadline integration with existing PPU execution ownership. | Retire only superseded lease/lock/timeout implementations, not persistent safety state. | Stale worker, concurrent Site, shared FPGA reload, cancel/timeout, SEALED and SAFE_OFF negative tests. |
| **S3 — Bundle/CLI identity** | Reconcile Bundle v3 admission, Active Set, Job inputs and one-click CLI. Decide whether a separate external image is supported and how it is content-bound to the selected programming Profile. Replace gratuitous Git SHA coupling only where it is not a genuine Runtime or Dispatcher identity guard. | Retire reachable v1/v2/duplicated source-pinning paths only with caller migration; remove obsolete docs/tests. | B1/B2/B3 vs Job separation; integrity, target, operator authorization, mismatch, rollback and failure tests. |
| **S4 — Platform/Adapter split** | Make Z2 ABI-v5 adapter and Golden policy an explicit, replaceable, capability-checked platform implementation; enable alternative qualified platform without editing generic Core. | Remove hard-coded Z2/Site/ABI decisions from Core, while retaining Z2-owned recovery rules. | Host-only simulated two-platform matrix, mismatched ABI/FPGA/driver, site-count tests; Z2 hardware tests separately gated. |
| **S5 — Retirement and invariant CI** | Final sweep for unreachable legacy Router, Compiler, Package, ABI and duplicate tests/config/docs; update authoritative architecture links. | Delete superseded code rather than leave a second "temporary" path. | No remaining dual production routes; negative regression suite; observed LOC/branch/dependency inventory; HIL status reported separately. |

**Slice ordering is dependency-driven.** A PR may combine adjacent slices only when the complete migration and deletion fit a bounded Gate 1 scope. In-flight OPF PRs must be reconciled rather than duplicated.

## 5. Required change ledger for every future implementation PR

Every PR implementing this roadmap must link this roadmap PR and include the following in its description:

```text
Roadmap: <link to this reference PR and the canonical plan file>
Baseline and target main SHA:
Slice(s): S0/S1/S2/S3/S4/S5
Single authoritative owner of the affected responsibility:
Added/replaced/deleted files and functions:
Old entrypoints/callers removed or migrated:
Why any former path remains reachable (explicit approved exception if applicable):
Production LOC added/deleted (excluding tests/docs/generated code):
Executable route/registry/lock counts before -> after:
Third-party extension test: what new Provider/Profile/Platform can be added without Core edits?
Safety invariants and negative tests retained:
Host-only test/CI evidence (PASS/FAIL/NOT_RUN):
Z2/FPGA/DUT/HIL evidence (PASS/FAIL/NOT_RUN, never inferred from mocks):
Rollback/recovery and remaining risk:
Required Gate 1 scope and Gate 2 merge decision:
```

**Review rule:** A replacement PR which adds a new layer but leaves its obsolete predecessor running is **not convergence-complete**. Mark it as a short-lived, owner-approved transition with the exact removal PR/blocker, or reject the scope as architectural growth. Do not use a follow-up PR promise to evade migration/deletion that can safely occur within the same scope. A genuine feature addition may be net-positive in LOC; justify added authority and prove it is not a duplicate path.

## 6. Acceptance of the overall convergence

- **Behavior:** one authoritative product programming execution path; one verified Bundle/Asset identity and one authorized Site/Resource owner at each physical action; no silent Catalog/official-GitHub/Publisher execution admission.
- **Extensibility:** host-only reference Providers and at least one non-OpenOCD or PS-only mock prove that a new Provider/Profile does not require Core brand/IC-specific edits. Alternative platform test is independent of the qualified Z2 reference implementation.
- **Complexity:** measured reduction in reachable duplicate routers/registries/validators/adapters and actual removal of retired files/callers/docs. Publish before/after LOC, reachable routes and dependencies; **do not invent a percentage target before S0 measurement**.
- **Safety:** content/integrity, privilege, target geometry, hardware identity, Site fencing, FPGA reload, SAFE_OFF and recovery negative coverage does not decrease. Tests distinguish failure from unverifiable outcome.
- **Evidence:** host-only/CI approval is not a physical Flash PASS. Real Site 2 HIL, any Z2 deployment/service restart, FPGA load, power or DUT operation requires separately bounded authorization and recorded real evidence.
- **Governance:** each implementation slice receives the repository's ordinary Gate 1; each merge requires its own Gate 2. This roadmap PR must not itself merge, deploy, alter runtime or change the Z2/DUT.

## 7. Explicit non-goals

- Building a second Plugin Framework, adding compatibility layers or retaining obsolete formats solely for old tests.
- Removing Root/Owner security, Site lock/fence, recovery, operator authorization or all validation in the name of openness.
- Treating SHA256 integrity as proof of Publisher authenticity, or treating GitHub provenance as a required permission to author a Bundle.
- Conflating packaging action names with actual Flash operation plugins.
- Claiming universal IC coverage, 8-Site readiness, production qualification or verified hardware behavior based only on this plan.

**Standing instruction for future discussions and PRs:** use this document as the convergence checklist, cite the roadmap PR, and prefer an evidenced deletion/migration over a new wrapper whenever both meet the same requirement.
