# PLASMA Core Convergence and Deletion-First Roadmap

> **Status (updated 2026-11-08):** Approved roadmap (#1343/#1348); S1-B standalone Host-only merged #1349; S1-C single PPU route merged #1347, S2 fail-closed fix merged #1350, real new-path Site 2 Bundle A/B Flash/Readback/SAFE_OFF PASS. These are two independent one-Site hardware Jobs, not S2/S3 multi-Site or non-OpenOCD qualification. Original inventory baseline: `main@5b61e28f34f02ab924daf3e1f70be87f6d346ed0`; S1-C implementation baseline: `main@47a8c6abc674f3975047834a06f9496d4b8245df` (2026-11-08).
> **Purpose:** A single, long-lived reference for subsequent implementation PRs; it is **not** implementation approval, evidence of hardware readiness, or a new approval gate.
> **Authority:** [AGENTS.md](../../AGENTS.md), the [shared development contract](../development/plasma-development-common.md), [OPF architecture](opf-architecture.md), [Unified Bundle-driven Programming Decision](unified-bundle-driven-programming-decision-2026-11-04.md), and [Bundle v3](ppu-canonical-bundle-packages.md). Where a proposal here conflicts with approved contracts or actual executable safeguards, resolve the conflict explicitly through the existing Gate 1 process; do not silently weaken a guard.

## 1. Decision: reduce the executable core, not merely relocate code

PLASMA is a universal multi-Site IC programmer, not a collection of per-IC or per-board routing branches. The primary success metric is a **smaller, more understandable trusted execution core** with fewer independent programming paths and less duplicated authority, while third parties can add supported programming behavior through bounded, verified extensions.

The total repository line count can grow legitimately as new Providers, platforms, tests, and qualification evidence are added. Raw LOC reduction alone is **not** a safety or acceptance criterion. Deletion-first means replacing old mechanisms, removing dead paths, and reducing responsibilities and reachable complexity whenever a successor is delivered.

**Mandatory engineering direction for future PR plans referencing this roadmap:**

1. **One canonical programming execution pipeline.** Do not maintain OPF and legacy exact-ICPN CompilerRegistry routing as two permanently executable product paths.
2. **The IC Catalog, L0/L1/L2 qualifications and exact-ICPN inventory are advisory upstream information**, not a mandatory PPU execution allowlist. A selected authorized Bundle/Profile/Provider must still pass real device, memory, capability, privilege and hardware-safety checks.
3. **PPU-managed Jobs use a verified Active Asset Set.** For the existing PLASMA PPU product route, select Provider, Profile, Driver and applicable FPGA Image from its single authorized Bundle; no unverified source-tree fallback or cross-Bundle mixing. **Do not promote this PPU deployment policy into a mandatory dependency of standalone OPF.**
4. **Separate two meanings of Core.** Portable **OPF Core** owns a minimal Provider/capability/operation/result contract; **PLASMA PPU Runtime Core** owns its Job, Asset/Bundle identity, Resource/Site Sessions, authorization, evidence handling and failure/recovery. Protocol algorithms, geometry, adapter register layouts and platform-specific recovery are not PPU-independent Core concerns.
5. **Replace-by-Default:** delete retired branches, compatibility shims, duplicated validators, stale tests and conflicting documentation in the *same migration PR* once their actual callers have been migrated, absent explicit owner approval.
6. **Extension without generic Core edits:** adding a qualified IC Profile, Provider or Host/transport integration must not require changing a built-in brand/exact-ICPN list, per-operation Compiler Registry, or Z2-only hard-coded branch in OPF Core. Existing tool transport backends are reused rather than reimplemented.
7. **No PPU safety regression:** retained PPU Host checks include ZIP/file hashes and bounded paths, executable restrictions, owner authorization, effective hardware identity/capabilities, Site fencing, PPU-wide shared resource/FPGA reload lock, Job deadline, cancellation, SAFE_OFF, persistent SEALED/Recovery and fail-closed uncertainty. Trust is not synonymous with GitHub origin or Publisher signature.
8. **Deployment is not programming.** Bundle v3 B1/B2/B3 installation and selection do not prove or authorize a DUT Flash Job. Deployment lifecycle actions such as install/verify/activate/rollback are not programming-operation plugins and must not be conflated.
9. **Host-independent OPF is mandatory for the target design.** A standalone Linux/macOS Host-only Python fake Provider must execute through the same abstract OPF contract without PPU, Bundle v3, C-3, FPGA, OpenOCD, Owner HMAC or PPU Lease. Linux Host-only execution has passed in merged #1349; macOS and physical hardware qualification are not established by that proof.
10. **Adapter is optional, not a new mandatory layer.** OpenOCD already owns its ST-LINK USB backend and vendor CLIs may manage their own transport. A PPU FPGA SWD route may need bounded existing C-3/WordPort/PL integration. No second Provider Registry, Router, Executor, Engine or generic lock merely to satisfy a diagram.

This document introduces **no** new API/schema or implementation requirement on its own. It consolidates and makes measurable the already approved direction and requests Gate 1 authorization for each bounded implementation slice.

## 2. Observed baseline and design debt (2026-11-07, read-only)

These are source-inspection findings, **not** claims that the deployed SWPC/Z2 runtime behaves identically or that HIL succeeded.

| Area | Existing source at baseline | Convergence gap |
| --- | --- | --- |
| Bundle-driven Flash C-3 | `software/python/plasma_server/execution_router.py`, `software/python/plasma_interfaces/openocd.py` | C-3 routes `flash_cycle` by Active Bundle; other operations still enter legacy exact-ICPN/CompilerRegistry checks. |
| Static compilation/IC admission | `software/python/plasma_interfaces/compiler_registry.py`, `software/python/plasma_interfaces/openocd_plan.py`, `software/python/plasma_core/ic_support.py` | Legacy binding and static profile sets remain; audit every reachable caller before removal. |
| Verified Bundle v3 | `scripts/ppu_unified_deployment.py`, `scripts/ppu_asset_set.py` | SHA, paths, dependency DAG and target checks exist. Do not replace with publisher/GitHub origin gates. Distinguish canonical v3 from legacy v1/v2 code. |
| One-click CLI | `scripts/plasma_program.py` | `flash/run` currently require `--runtime-sha`; external `--image` must exactly match the image embedded in the Bundle. Separate runtime compatibility/version fencing from Git repository pinning, and define any truly external-image policy explicitly. |
| Provider/Adapter | `scripts/ppu_provider_contract.py`, `scripts/ppu_site_adapter_abi5.py`, `scripts/ppu_site_worker_service.py` | Provider/route resolution is still coupled to the PPU Active Set and Z2 capabilities. Current package execution does not prove a standalone OPF Provider without PPU/Bundle, nor general hardware Adapter plugin support. |
| Platform/recovery | `scripts/ppu_fpga_qualification.py`, `pl/hil/fpga_image_guard.py` | Z2 ABI details and protected Golden recovery are still platform-specific code. Move decisions behind a bounded platform contract only after equivalently safe Z2 behavior is proven. |
| Deployment lifecycle / historical formats | `scripts/ppu_asset_set.py`, `scripts/ppu_unified_deployment.py`, `docs/architecture/ppu-canonical-bundle-packages.md` | Fixed deployment action vocabulary and surviving legacy format descriptions require reachability and contract reconciliation. Do not indiscriminately delete supported active call paths. |

Relevant historical PPU migration contract: [OPF-1 through OPF-5](opf-architecture.md#original-opf-1-through-opf-5-migration-plan--historical-ppu-integration-scope). That sequence has delivered important PPU capabilities but is **not equivalent to host-independent OPF**. **Do not establish a parallel "universal core v2" product pipeline**; refactor/reuse existing OPF, Provider, Package Executor and PPU safety primitives instead of wrapping them with another engine.

### Current verified status at revision baseline (2026-11-08)

| Item | Evidence / disposition |
| --- | --- |
| OPF foundation, Provider schema and PPU Reference Provider | Merged PRs #1301/#1302/#1303/#1306/#1307/#1311/#1316 and subsequent integration fixes; evidence is PPU-focused, not standalone OPF acceptance |
| Z2 Site 2 real STM32F103C8T6 Flash | **New S1-C/S2 route PASS:** [Bundle B Run 42463696052](https://github.com/physicslu/plasma/actions/runs/42463696052), 62,800 bytes; [Bundle A Run 42464939052](https://github.com/physicslu/plasma/actions/runs/42464939052), 18,768 bytes; each one actual Job, full Readback SHA match and SAFE_OFF. Earlier #1338 is historical only; no eight-Site/ST-LINK/independent Python physical claim. |
| Canonical convergence roadmap | PR #1343 **merged**; update this canonical document through a new Draft PR, never rewrite the merged PR history |
| S1-C Job-selected Package Provider cutover | **Merged #1347** (Runtime compiler registry and old product route deleted); **merged #1350** S2 fail-closed Worker; physical OpenOCD C-3 Bundle A/B PASS on Site 2. C-2/non-OpenOCD physical Provider remains unqualified; Host-only fake exit 0 is not Flash PASS. |
| PR #1347 historical code budget | Pre-merge baseline `main@47a8c6a`: production **+403/-361 = net +42 LOC**; tests **+401/-685 = net -284 LOC**, historical full diff net **-242 LOC**. Not a current outstanding Draft or current branch diff. |
| S5 Runtime ICPN admission retirement | `CompilerRegistry`, `CompilerBinding`, `CompilerSelection`, `PlanCompiler` Protocol and the packaged STM32 compiler admission projection deleted (production **-291** Python LOC, -111 JSON). IC Catalog / L0–L2 / admission packages are offline upstream governance and never a direct or indirect PPU Runtime execution dependency. Catalog-side Runtime source pins decoupled by #1357/#1358/#1359. |
| S5 PR-B2 Runtime compiler retirement | `openocd_plan.py`, `openocd_executor.py`, `kl25_openocd_plan.py` and the `OpenOCDInterface` software-validation branch deleted (production **-1,049** Python LOC). The only Runtime OpenOCD path is the Bundle-driven C-3 Site Worker. Historical STM32 admission evidence is reproduced by the add-only replay. Host-only proof (`test_ppu_runtime_catalog_free.py`): PPU Runtime execution modules import with every Catalog module blocked and no Catalog data; a verified Bundle for a non-Catalog ICPN flashes (fake OpenOCD, not physical PASS) while every Catalog query is a tripwire; Catalog presence never changes the decision. Web Gateway Catalog imports remain (PR-C). |
| S5 PR-C1 PPU Catalog-free Gateway / Packaging / Installer (Gate 1 Draft) | Runtime packaging no longer copies Device Catalog / IC Support, drops the build-time IC Support resolver probe, and omits Catalog-only modules from `ppu.pyz`; the Z2 installer no longer requires a Catalog manifest or `ic-support/profiles` and sets no Catalog environment; the Gateway imports no Catalog / Qualification module at startup (Selector moved verbatim to the optional `legacy_device_selector` adapter, absent ⇒ `503 DEVICE_SELECTOR_UNAVAILABLE`, never empty). Host-only proof: `test_ppu_gateway_catalog_free.py`. Device Selector is owned by Manager; Console consumers (`software/web/app/device-catalog-api.ts` `searchDevices` via `ic-selector.tsx` / `ic-picker-field.tsx`, Manager proxy allow-list, managed-ingress `location = /api/devices/search`, Render smoke) are **not** migrated — PR-C2 Consumer Migration. HIL: NOT_RUN. |
| Portable OPF without PPU/Bundle/C-3 | **Linux Host-only PASS** via merged #1349; no physical Flash, macOS or ST-LINK qualification implied. |
| Non-OpenOCD physical Provider; PC ST-LINK; full eight-Site HIL | **NOT_QUALIFIED** by these PRs |

This is a source/PR-evidence status, **not a fresh deployed Z2 state inspection**.

## 3. Target boundaries — separate portable OPF from PPU product Host

```text
Application / CLI or PLASMA Programming Job
                |
                v
       OPF Core contract
 (Provider capabilities, operations, options, evidence/result)
                |
                v
    selected Provider implementation
   (OpenOCD / vendor CLI / Python / Native C / fake)
                |
                +--> built-in Provider transport (e.g. OpenOCD ST-LINK USB)
                |
                +--> optional Host transport capability (only where needed)
                        PC: local devices / process access
                        PPU: Z2 PS-local C-3/WordPort -> optional PL
                v
        target IC / Host-only fake

Independent deployment plane:
Bundle v3 -> B1/B2/B3 -> Active Set -> authorized PPU Host
(bundle is NOT a required OPF Core import or schema)
```

**Portable OPF boundary:** no PPU ID, Site Lease, C-3 socket, Bundle v3, FPGA ABI, Owner HMAC or OpenOCD is mandatory to execute an independent Provider. OPF reports capability and evidence, not authority to open arbitrary devices. A Python/Native Provider's program exit code is not hardware Flash PASS.

**PLASMA PPU product boundary (existing binding contract):** SWPC Web/Controller/BFF issues authorized high-level Jobs; Z2 PS performs live OpenOCD/WordPort; Z2 PL performs SWD/SPI. For a PPU-managed Job, the verified single Active Asset Set, actual device/FPGA identity, PPU Site Session/Lease/Owner/Deadline and Root/SAFE_OFF/SEALED/Recovery restrictions remain mandatory **at the Host integration boundary**. Do not send bit-level SWD traffic across Ethernet or let Provider code bypass C-3 by direct MMIO/device access.

**No forced transport abstraction:** ST-LINK is already supported by OpenOCD's own USB backend; no extra ST-LINK USB driver/adapter is implied. A native vendor CLI may use its own device stack. The PPU FPGA SWD integration reuses its existing C-3/PS-local transport and FPGA ABI rather than defining a parallel hardware-control layer. Host-specific adapters exist only when an actual interoperability gap is demonstrated.

**Dependency direction:** PPU integration and optional Bundle delivery may depend on OPF public contracts; portable OPF must not depend on either. This is a **proposed target**. Current code and the PPU-only portions of [PR #1298](unified-bundle-driven-programming-decision-2026-11-04.md) are not silently replaced by a docs commit. Resolve executable contract changes through separately approved Gate 1 while preserving all current safety checks.

## 4. Revised work breakdown: bounded, deletion-accountable slices

| Slice | Next work and status | Replace/delete responsibility | Observable acceptance |
| --- | --- | --- | --- |
| **S0 — Inventory & boundary audit** | Scoped Runtime caller and dependency audit performed for #1347; broader multi-layer inventory remains **partial**. | Identify import direction, duplicated Router/Executor/Lease and exact reachable callers before changing code. | File/function-level ledger distinguishing portable OPF / PPU Host / Bundle Deployment / existing Provider transport; reproducible baseline. |
| **S1-A — Architecture decision (merged #1348)** | Record standalone OPF Core/Provider vs Host integration/optional Adapter vs independent Bundle v3; **merged**. | Do not create a new Framework merely to describe layers. Preserve the merged #1347 route without adding a parallel engine. | Updated [OPF architecture](opf-architecture.md) and roadmap; explicit platform-dependency and no-fake-PASS invariants. |
| **S1-B — Portable OPF execution** | Linux Host-only standalone Python fake Provider runs without PPU Runtime, Bundle v3, C-3, FPGA, OpenOCD, PPU Lease or PPU Owner HMAC; **merged #1349** (other Hosts not yet qualified). | Split portable operation/result logic away from PPU-bound `PackageProviderInterface`/package action; avoid second Engine/Router/Executor. | Host-only positive and negative tests: no PPU imports, Provider/options validation, child execution, timeout/cancel, explicit unqualified result; exit 0 is not Flash PASS. |
| **S1-C — One PLASMA programming route** | **Merged #1347, #1350; Site 2 C-3 Bundle A/B HIL PASS**. Still no physical C-2 Provider or multi-Site qualification. | Migrate all actual old consumers, then remove obsolete `CompilerRegistry`, static `_resolved_support`/`_resolve_openocd` and duplicate route/guard code where proven unused. | Two Providers including non-OpenOCD fake; one reachable product route, negative routing tests, existing OpenOCD Host-only regression, production LOC change ledger. |
| **S2 — PPU-only Site safety rationalization** | **Source-level fail-closed fix merged #1350 and positive Site 2 HIL PASS.** PPU-wide Job Lease, per-Site C-3 Session/lock and native FPGA Owner fence are different authority scopes, not proven duplicates; multi-Site/negative recovery qualification still pending. | Delete redundant PPU locks/leases only after ensuring the single authoritative scope, stale-worker fencing and safe recovery. | Concurrent Site, stale worker, shared FPGA reload, cancel, deadline, Root/UID, SAFE_OFF, SEALED and recovery fail-closed tests. |
| **S3 — Bundle v3 deployment boundary** | **Two real canonical Bundle v3 activation/Flash PASS (A/B)** on Site 2; standalone Python Provider Host-only runs without Bundle. The legacy direct Site 2 REST Flash utility is being retired in the bounded deletion PR; overall S3 broader provider/host policy remains partial. | Delete retired v1/v2 and duplicated pinning only with observed caller migration; do not relocate B1/B2/B3 into OPF. | PPU Active Set integrity/authorization and no cross-Bundle fallback; standalone OPF runs without Bundle; no deployment-as-Flash PASS. |
| **S4 — Host/transport compositions** | Validate PC Host ST-LINK via existing OpenOCD driver concept, PS-only Z2 and PS+PL Z2 integration through qualified existing hardware boundary. **Pending**. | Only add a Host Adapter on a demonstrated missing capability; eliminate Z2-specific assumptions from generic OPF, not Z2 recovery rules from PPU. | Host-only two-Host matrix and Adapter-negative cases; ST-LINK or Z2 real HIL requires separate approval and authentic evidence. |
| **S5 — Deletion, invariants and final report** | **In progress:** S1-C removed Runtime registry; the bounded S2/S3 deletion proposal removes the obsolete fixed-image Site2 direct Flash CLI and dedicated tests while preserving generic `plasma_program.py` and all Site/FPGA guards. Wider sweep remains pending. | Delete rather than keep a second product path or permanent compatibility layer. | Before/after reachable route/registries/dependencies and production LOC; CI and negative tests; Host-only vs HIL status explicitly separated. |

**Work order:** S0 dependency audit -> S1-A documentation -> S1-B portable Fake Provider -> S1-C existing PPU bridge + old route deletion -> S2/S3/S4 independent bounded integration -> S5 final closure. This order is dependency-driven, not license to bypass a PPU safety gate. No implementation scope is pre-approved by this document.

**Disposition of PR #1347:** **Merged**, no longer a Draft blocker. The sole PPU Job-selected route retains existing C-2/C-3, offline Plan Compiler/ICPN qualification and Site/FPGA safety. New-path Site 2 OpenOCD Bundle A/B Flash qualification is recorded in [the 2026-11-08 evidence](../evidence/opf-site2-ab-newpath-2026-11-08.md). It does not validate untested Providers, multiple Sites, cancellation or recovery failure cases.

### 2026-11-08 S2/S3/S5 follow-up: Gen7-only operator helper retirement (Gate 1 source candidate)

After merged #1353 removed the fixed-image direct Site 2 REST Flash writer and merged #1354 renamed PPU Doctor, a second independently approved deletion scope isolates the former Gen7-only Bootstrap B3/Joint acceptance scripts. The remaining Site 2 Active Set **read-only** observer previously imported the Gen7 joint tool; it must retain its paired-host, source SHA, verified installed Asset Set, preflight, Engine identity and error-denial behavior without importing a retired writer. The PPU Doctor source inventory must not require deleted helpers.

Retire only `scripts/opf_site2_joint_acceptance.py`, `scripts/opf_site2_path2_bundle_deploy.py` and their obsolete dedicated tests after migrating essential observation negatives. Preserve independent `scripts/opf_platform_bundle_v3_build.py`, canonical `scripts/plasma_program.py`, PPU-wide Lease/Quiesce, C-3 Session/Worker, native FPGA reload fence, SAFE_OFF, SEALED and Recovery. The historical Gen7 dispatch records on [Issue #981](https://github.com/physicslu/plasma/issues/981) remain evidence, not current executable interfaces. Do not assume no pending *off-repository* work solely from issue comments.

Acceptance is exact-head Host-only tests/CI plus positive/negative failure guards; these changes do not run any Z2/FPGA/DUT HIL, change the installed Runtime or qualify another Provider. See [the separate retirement ledger](../development/opf-s2-s3-s5-gen7-retirement-gate1-20261108.md). The larger S0/S2/S3/S5 backlog remains **partial**.

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
Third-party extension test: what new Provider/Profile/Platform can be added without portable OPF edits?
Portable OPF import/dependency audit: evidence of no PPU/Bundle/C-3/OpenOCD requirement:
Host transport reuse vs newly justified Adapter: OpenOCD built-in ST-LINK, PPU C-3/FPGA or other:
Process exit/evidence/result separation: why a fake or process success is NOT Flash PASS:
Safety invariants and negative tests retained:
Host-only test/CI evidence (PASS/FAIL/NOT_RUN):
Z2/FPGA/DUT/HIL evidence (PASS/FAIL/NOT_RUN, never inferred from mocks):
Rollback/recovery and remaining risk:
Required Gate 1 scope and Gate 2 merge decision:
```

**Review rule:** A replacement PR which adds a new layer but leaves its obsolete predecessor running is **not convergence-complete**. Mark it as a short-lived, owner-approved transition with the exact removal PR/blocker, or reject the scope as architectural growth. Do not use a follow-up PR promise to evade migration/deletion that can safely occur within the same scope. A genuine feature addition may be net-positive in LOC; justify added authority and prove it is not a duplicate path.

## 6. Acceptance of the overall convergence

- **Behavior:** one authoritative **PLASMA PPU product** programming execution path; one verified Bundle/Asset identity and one authorized Site/Resource owner at each PPU physical action; no silent Catalog/official-GitHub/Publisher execution admission. Independent OPF clients need neither PPU Job nor PPU Bundle.
- **Extensibility:** a standalone Host-only Python fake Provider runs without PPU, Bundle v3, C-3 or OpenOCD; OPF Provider options/capabilities/results remain meaningful. Existing OpenOCD+ST-LINK is reused, not reimplemented. PPU Host-only reference and non-OpenOCD/PS-only mock verify the same abstract contract without Core brand/IC-specific edits; alternative Host testing is independent of qualified Z2 hardware.
- **Complexity:** measured reduction in reachable duplicate routers/registries/validators/adapters and actual removal of retired files/callers/docs, plus demonstrated portable-OPF import independence. Publish before/after LOC, reachable routes and dependencies; **do not invent a percentage target before S0 measurement**.
- **Safety:** PPU content/integrity, privilege, target geometry, hardware identity, Site fencing, FPGA reload, SAFE_OFF and recovery negative coverage does not decrease. Standalone Host tests enforce their own resource/OS access policies. Tests distinguish process success, programming evidence, verified Flash PASS, failure and unverifiable outcome.
- **Evidence:** host-only/CI approval is not a physical Flash PASS. Real Site 2 HIL, any Z2 deployment/service restart, FPGA load, power or DUT operation requires separately bounded authorization and recorded real evidence.
- **Governance:** each implementation slice receives the repository's ordinary Gate 1; each merge requires its own Gate 2. This docs revision changes no executable runtime, deployment or Z2/DUT. It is not a merge or implementation approval; the original roadmap PR #1343 is already merged.

## 7. Explicit non-goals

- Building a second Plugin Framework, mandatory generic Host Adapter, redundant ST-LINK USB driver, additional Engine/Router/Executor or compatibility layers solely for old tests.
- Requiring standalone OPF clients to create Bundle v3, PPU Device ID/Lease, C-3 Session, FPGA Image or PPU Owner HMAC.
- Removing Root/Owner security, Site lock/fence, recovery, operator authorization or all validation in the name of openness.
- Treating SHA256 integrity as proof of Publisher authenticity, or treating GitHub provenance as a required permission to author a Bundle.
- Conflating packaging action names with actual Flash operation plugins.
- Claiming universal IC coverage, 8-Site readiness, production qualification or verified hardware behavior based only on this plan.

**Standing instruction for future discussions and PRs:** use this document as the convergence checklist, cite the roadmap PR, and prefer an evidenced deletion/migration over a new wrapper whenever both meet the same requirement.
