# PLASMA Repository Documentation Reorganization — P1 Gate 1 Inventory

**Scope:** Repository-wide documentation governance, de-duplication, canonical authority and historical cleanup (Host-only source audit). Codex/Path 3 are only examples, not the project boundary. **Pinned main:** `833a0f577c3697d891629c405d91267c05c2b476`. PR #1227 was closed without merge; this is a separate, minimal audit, not a revival of that PR.

## P1-A: AGENTS.override.md decision

- Root `AGENTS.md` is 22,818 characters at the pinned main; it explicitly delegates relevant full-contract sections on demand.
- No root `AGENTS.override.md` exists in the checked root listing.
- **Decision: do not add a shared root override.** An override could supersede repository safety/authorization instructions and cause divergence across Desktop and Path 3. Its actual load precedence and behavior must be verified against the pinned Codex CLI version before any local experiment.
- Use task-specific, scoped prompts and the existing AGENTS on-demand rule. Never instruct Codex to skip required privileges, hardware, deployment, electrical safety, Root Guard, or architecture clauses.

## P1-B: Historical documents, ADR, and duplication

- Canonical shared entrypoint: `AGENTS.md`; full detailed contract: `docs/development/plasma-autonomous-development-contract-full.md`; Path-specific clauses: `plasma-codex-path2-execution.md` and `plasma-codex-path3-execution.md`.
- The existing ADR index is `docs/adr/README.md`; the observed directory has ADR-0001, ADR-0002 and ADR-0003. Do not infer that other ADR numbers do not exist elsewhere; inspect references before declaring authority.
- `plasma-path3-cross-job-resume-gate1.md` and `plasma-path3-session-resume-host-only-poc.md` explicitly label retired/historical mechanisms. `plasma-legacy-codex-issue981-trigger-retirement.md` is a historical trigger-retirement record.
- **Decision: no file deletion, relocation, or replacement authority map in this Gate 1.** Audit inbound references and paragraph-level overlap first; the canceled PR #1227 is not a basis for new edits.
- Existing `docs/README.md` still describes merged PR #1226 entries as “Gate 1 Draft”; correct those labels only after reference review in a separate focused change.

## P1-C: Device Catalog CI consolidation feasibility — DEFERRED BY OWNER

**Owner scope update:** The 245 Device Catalog workflows are explicitly **out of scope** for this PR and current P1 work. Retain the following counts as historical inventory only; do not inspect workflow internals, propose Matrix conversion, change CI or create a separate workflow task without new Owner approval.


At the pinned `main`, GitHub `.github/workflows/` directory listing shows:
- **321** YAML workflow files in total.
- **245** filenames beginning with `device-catalog-`.
- **21** filenames containing `phase` (not a count of active jobs or triggers).

These are **filename counts only**, not execution frequency, redundancy, cost, or safe matrix-compatibility evidence. The uploaded guide's “~141 workflows” estimate is not current repository inventory.

**No bulk matrix rewrite is authorized from filename counts.** Before proposing a Matrix Workflow:
1. Classify `on` triggers, required-check names, permissions, secrets, concurrency, runner and path filters.
2. Group only semantically identical workflows; retain PR-required status-check compatibility.
3. Compare baseline and proposed positive/negative fixtures, duration, and GitHub Actions minutes.
4. Preserve vendor/ICPN evidence isolation, source locks, non-production qualification and Gate 2 controls.
5. Deliver a separate source-only PR with an explicit migration/rollback plan; no CI edits in this audit.

## Repository-wide document reorganization: authority and information architecture

- **Shared governance:** AGENTS.md and the detailed development contract; identify normative clauses, their canonical owner and safe cross-references.
- **Architecture:** ADRs, architecture specifications, and current implementation documents; distinguish accepted decisions from proposals and historical experiments.
- **Execution paths:** Path 1, Path 2, Path 3 and Desktop tooling; route-specific detail stays on demand, without making Path 3 the primary organizing axis.
- **Product and IC support:** catalog/provider/qualification and raw evidence documents; distinguish runtime authority, qualification evidence, research notes and retired snapshots.
- **Operational documentation:** deployment, FPGA/PS, programming, CI and HIL runbooks; avoid duplicated procedures and stale links while retaining safety invariants.
- **Archive:** mark retired/obsolete documents as historical before any move; verify inbound links, GitHub references and CI/tests. Do not delete based on age alone.

**Deliverables:** document inventory and classification, source-of-truth ownership matrix, overlap/conflict and inbound-link report, prioritized move/merge/deprecate plan, link validation and regression evidence. This Gate 1 does not itself authorize wholesale deletion or migration.

## Document-only next actions

1. Inventory inbound links to current AGENTS, full contract, Path 2/3 rules, ADRs and retired documents; classify authoritative vs historical references.
2. Build a paragraph-level duplicate/contradiction list, separating shared safety requirements from Path-specific or device-specific implementation detail.
3. Correct stale PR #1226 Draft labels and broken references only after verifying their targets; retain the two Owner gates and actual runtime safeguards.
4. Do not add a shared AGENTS.override.md or make any runtime/CI changes without evidence and separate authorization.

## Acceptance and exclusions

This inventory records evidence and defers unsafe transformations. No Codex run, new Runner, override file, Workflow modification, merge, deployment, SWPC/Z2/DUT/FPGA operation, or measured Token reduction is claimed. Actual changes require their own Gate 1 scope and Gate 2 approval.

## Gate 1 repository document inventory — first verified pass

This section records direct GitHub directory-listing counts at pinned `main`; these are **not** recursively aggregated totals and do not establish whether a document is active, obsolete, or duplicative.

| Directory | Immediate entries | Immediate Markdown files | Subdirectories |
| --- | ---: | ---: | --- |
| `docs/architecture/` | 95 | 94 | none |
| `docs/development/` | 90 | 89 | `evidence/` |
| `docs/deployment/` | 25 | 25 | none |
| `docs/adr/` | 4 | 4 | none |
| `handover/` | 34 | 34 | none |
| `docs/operator/` | 1 | 1 | none |
| `docs/testing/` | 1 | 1 | none |
| `docs/evidence/` | 13 | 0 | 13 evidence subdirectories |
| `docs/archive/` | 1 | 0 | `ci-workflows/` |
| `docs/engineering/` | 1 | 0 | `ci/` |

**Verified minimum:** 248 immediate Markdown files across the seven flat/direct document locations listed above (94+89+25+4+34+1+1); not the repository-wide total. Nested evidence, engineering and archive contents require separate classification. Do not treat YAML/JSON evidence as obsolete documentation.

### First-pass authority candidates and ambiguity

- `docs/adr/README.md` indexes three immediate ADR decision files (0001–0003). Audit cross-references to other ADR-like identifiers before declaring the index complete.
- `docs/architecture/` contains `openocd-software-qualification-v1.md` through `v7.md`. **Seven versioned files are a review candidate, not proof of seven redundant contracts**: determine supersession, inbound references and whether each contains immutable qualification evidence.
- `docs/architecture/device-catalog-ci-coverage-map.md` is a likely large reference, but workflow consolidation is explicitly out of scope.
- `docs/evidence/` is a structured collection of device-specific evidence folders; preserve raw evidence and receipts, even if a current guide links to them.
- `docs/archive/ci-workflows/` contains archived workflow subtrees. Do not re-enable, delete, or migrate them in this PR.

### Required next evidence before any move or deletion

1. Recursive tracked-file inventory, including `docs/evidence/`, `docs/engineering/`, `docs/archive/`, root Markdown, and `specs/`.
2. For each candidate: current authority classification, duplicate/supersession proof, backlinks, ADR/CI/test references, and proposed replacement URL.
3. Resolve conflicts by explicit owner approval and source precedence; retain immutable evidence and signed/hash-locked material.
4. Perform link-integrity and documentation CI after each bounded change. No bulk archival move based on title/version alone.

## Gate 1 complete tracked-tree Markdown inventory (verified)

A recursive GitHub Git Tree read of pinned `main` `833a0f577c3697d891629c405d91267c05c2b476` returned **5,207 tracked tree entries**, `truncated=false`, and **662 tracked `.md` blobs**. This is the repository-wide Markdown count at that commit, unlike the earlier nonrecursive 248 minimum. It does not include untracked local files, other document formats, or content beyond the pinned commit.

| Scope | Tracked Markdown count |
| --- | ---: |
| `data/device-catalog/**` | 342 |
| `docs/architecture/**` | 94 |
| `docs/development/**` | 89 |
| `handover/**` | 34 |
| `data/ic-support/**` | 31 |
| `docs/deployment/**` | 25 |
| `docs/evidence/**` | 15 |
| `pl/projects/**` | 8 |
| Other locations, including root, ADR, engineering, operator and testing | 24 |
| **Total** | **662** |

The counts are classified by path prefix, **not** by whether the content is normative. In particular, the 342 Device Catalog Markdown files are research/evidence candidates for classification, **not authorization to edit 245 Device Catalog GitHub Actions workflows**.

### Highest-size document review candidates

| Tracked path | Git blob size (bytes) | Review question |
| --- | ---: | --- |
| `docs/development/plasma-autonomous-development-contract-full.md` | 69,292 | Normative clauses vs AGENTS and path-specific docs |
| `docs/README.md` | 64,814 | Can navigation be split into topical indexes without losing links? |
| `docs/adr/0002-openocd-software-qualified-catalog-visibility.md` | 55,838 | Separate accepted ADR decisions from historical amendments/evidence |
| `docs/development/todo.md` | 44,667 | Distinguish active backlog from historical completion log |
| `data/device-catalog/research/MICROCHIP_BULK_ACQUISITION_V1.md` | 37,140 | Preserve immutable research evidence and provenance |
| `docs/architecture/ppu-unified-deployment-gate1.md` | 34,584 | Current architecture vs Gate 1 proposal and superseded decisions |

**Do not delete or shorten solely due to size.** Size is a triage signal, not evidence of duplication, invalid authority, or token cost in a real Codex session.

### Work packages for document-only reorganization

1. **Authority classification:** map each Markdown file to Normative, Reference, Evidence, Historical or Mixed; mark Mixed for section-level analysis rather than arbitrarily labeling the entire file.
2. **Cross-reference graph:** extract tracked Markdown links and reference paths, identify broken/ambiguous backlinks and link dependencies; distinguish GitHub issue/PR links from file links.
3. **Conflict analysis:** begin with AGENTS/full contract/ADR-0002 and current Path 1/2/3 docs; document exact overlapping clause and controlling decision.
4. **Incremental migration:** propose small, reversible, reviewable documentation-only PRs by domain; keep this PR as audit. Preserve immutable source locks, receipts and historical records.

### Integrity boundary

No 662-file content review, cross-reference graph, exact duplicate proof, or per-file migration classification has been completed merely by reading the Git tree. This verified inventory is a starting point for those tasks, not a claim that the repository has already been reorganized.

## Content-level authority findings — verified against pinned main

1. `docs/README.md` begins by declaring itself the canonical **documentation index**, and defines Current / Reference / Plan / Historical labels. This makes it a navigation entrypoint, **not** a substitute for the actual code/schema/tests or an ADR.
2. The full development contract's new introductory paragraph explicitly calls root `AGENTS.md` the concise mandatory entrypoint and the full contract the **on-demand detailed normative source**. However, the retained historical body still says “This file is the primary operating contract ... Read it before making code, configuration, deployment, hardware, or documentation changes.” These two statements create an **actual document-loading precedence ambiguity** for agents and should be resolved by a narrow explanatory edit, without changing the safety clauses.
3. `docs/adr/README.md` explicitly distinguishes Accepted, Proposed, Superseded and Deprecated. Its immediate records are ADR-0001 Accepted, ADR-0002 Accepted, and ADR-0003 **Proposed**. Never describe ADR-0003 as an implemented/approved driver.
4. ADR maintenance currently requires `docs/README.md` to track all `docs/**/*.md`; a future index split must preserve the documentation integrity guard rather than assuming a shorter index is harmless.
5. Seven `openocd-software-qualification-v*.md` files are present, but no contents/backlinks have yet been compared; **no supersession claim** is justified.

**Owner decision implemented:** Root `AGENTS.md` is the mandatory entrypoint. The old conflicting full-contract introduction was replaced with on-demand normative reference wording in commit `aa37f7eee2e992a91d5e8bdca1fb0295da006a52`. Applicable safety and hardware clauses remain mandatory.

## Qualification v1–v7 content review (not filename-only)

Read all seven `docs/architecture/openocd-software-qualification-v*.md` documents at pinned `main`.

- **v1–v4:** progressively record the reference cohort, ordering-equivalent TR variants, R/V medium-density additions and T7 additions. Each describes bounded, exact ICPN applicability. The files self-label as current phase-specific qualification references; **do not erase their evidence** simply because a newer umbrella manifest exists.
- **v5:** explicitly self-labels Historical, superseded by v6; records the transition to a content-addressed umbrella and a 31-exact-ICPN cohort.
- **v6:** explicitly self-labels Historical, superseded by v7; records the R/V high-density expansion and a 41-exact-ICPN cohort.
- **v7:** explicitly self-labels Current ADR-0002 Programming Qualification authority for Catalog Level 2 derivation; documents a 49-exact-ICPN combined registry and references v4 medium-density authority.

**Decision:** retain all seven as provenance-bearing versioned qualification records. Treat v7 as the current **umbrella reference for this bounded STM32F103 cohort**, v4 as its referenced medium-density authority, v5/v6 as historical. Do not infer that the v7 cohort is the entire current PLASMA catalog or supersedes unrelated provider manifests. Do not modify qualification counts or L2 entitlements during documentation cleanup.

**Document cleanup candidate:** create a short navigation table linking v1–v7 with explicit scope/status, and add verified backlinks to the main documentation index. Do not rewrite immutable evidence or move these files without checking inbound links.

## Owner scope revision — software development documentation first (WEB / PS / PL)

**Current priority:** Reorganize the documentation used to implement and maintain the PLASMA programming system: **WEB**, embedded-Linux **PS**, FPGA **PL**, and their shared contracts. This is a bounded documentation-governance phase, not an IC Catalog migration.

**Explicitly deferred:** IC Catalog, ICPN discovery, L0–L3 promotion, Provider/Programming Qualification, vendor acquisition/research, and Device Catalog CI workflow consolidation. Existing qualification-version navigation already added to the docs index is preserved, but no additional catalog edits should be made under this phase. Historical/evidence files remain untouched.

### Domain entrypoints (verified tracked paths, not a full semantic audit)

| Domain | Initial entrypoints | Audit focus |
| --- | --- | --- |
| WEB | `software/web/README.md`, `docs/architecture/web-rest-api-contract.md`, `docs/architecture/web-product-modes.md`, `docs/deployment/web-runtime-hygiene.md` | Frontend/runtime, REST contract, UI modes, deployment boundaries |
| PS | `docs/development/linux-mmio-backend-v1.md`, `docs/deployment/z2-ps-installer.md`, `docs/development/mmio-lt02-ps-pl-loopback.md`, `docs/architecture/runtime-data-root-contract-v1.md` | Embedded Linux ownership, services, driver/MMIO, PS–PL bridge, installation and recovery |
| PL | `docs/architecture/fixed-fpga-hardware-abi-v1-gate1.md`, `docs/architecture/fixed-fpga-swd-site1-rtl-gate1.md`, `docs/architecture/plasma-unified-fpga-build-diagnostics-v1.md`, `docs/development/swd06-rtl-python-differential.md` | FPGA RTL/IP, ABI, timing/build evidence, HIL and safety |
| Shared | Root `AGENTS.md`, full development contract, `docs/adr/README.md`, `docs/README.md` | Single entrypoint, authoritative cross-domain contracts, references and status |

**Rule:** A filename or historical Gate 1 title is not proof of current implementation. Verify code, test and accepted ADR before marking a document Current. Keep PS/PL interface and WEB/API boundaries consistent across domain indexes. Do not create new normative rules in a navigation document.

### Next document-only deliverables

1. WEB/PS/PL authority and cross-reference map, identifying canonical source for each implementation contract.
2. Exact overlapping and conflicting clauses, with line-level evidence and proposed minimal edits.
3. Smaller topical indexes with stable existing links; preserve documentation CI.
4. Regression checks and a scoped Gate 2 report before any merge.

No runtime code, device operations, workflow refactoring, qualification promotions or broad file deletions are in scope.

## WEB / PS / PL content audit — first verified sample

Read the following documents from pinned `main`: `software/web/README.md`, `docs/architecture/web-rest-api-contract.md`, `docs/architecture/web-product-modes.md`, `docs/deployment/web-runtime-hygiene.md`, `docs/development/linux-mmio-backend-v1.md`, `docs/deployment/z2-ps-installer.md`, `docs/architecture/runtime-data-root-contract-v1.md`, `docs/architecture/fixed-fpga-hardware-abi-v1-gate1.md`, `docs/architecture/fixed-fpga-swd-site1-rtl-gate1.md`, `docs/architecture/plasma-unified-fpga-build-diagnostics-v1.md`, and `docs/adr/0003-runtime-fpga-driver-reconfiguration-boundary.md`.

| Domain | Document and actual declared role | Proposed documentation treatment |
| --- | --- | --- |
| WEB | `software/web/README.md`: React/TypeScript PPU Console, REST v3, Site jobs and backend-owned progress | Keep as developer onboarding; link API authority rather than copy endpoints |
| WEB | `docs/architecture/web-rest-api-contract.md`: browser-facing REST contract, independent of PLASMA33 wire protocol | Treat as REST contract reference; validate against executable routes/tests before calling implementation current |
| WEB | `docs/architecture/web-product-modes.md`: Production/Engineering product mode model | Keep product UX semantics separate from API wire/versioning |
| WEB | `docs/deployment/web-runtime-hygiene.md`: SWPC development runtime restart and deploy guidance | Keep as operational runbook, not frontend architecture |
| PS | `docs/development/linux-mmio-backend-v1.md`: explicitly HISTORICAL / INTERNAL-FIXTURE ONLY for retired SWD-03 synthetic responder | Mark historical in navigation; never use as current Blue Pill Path 3 instructions |
| PS | `docs/deployment/z2-ps-installer.md`: PS release kit and managed acceptance with live Z2 qualification still required | Keep release/install evidence boundary; verify against current deployment engine before changing authority |
| PS | `docs/architecture/runtime-data-root-contract-v1.md`: installed Python package data-root CI contract | Narrowly scoped Python/runtime data ownership; not a generic PS/PL or hardware admission rule |
| PL | `docs/architecture/fixed-fpga-hardware-abi-v1-gate1.md`: proposed ABI, REVIEW CANDIDATE, M1 NO-GO | Do not present as accepted/current hardware ABI |
| PL | `docs/architecture/fixed-fpga-swd-site1-rtl-gate1.md`: simulation-only Site 1 vertical slice, M1 NO-GO | Preserve feasibility/evidence status; later semantic candidate supersedes earlier gap table |
| PL | `docs/architecture/plasma-unified-fpga-build-diagnostics-v1.md`: Gate 1 draft offline validation | Do not claim physical build/HIL or new execution pipeline |
| Shared PL/PS | `docs/adr/0003-runtime-fpga-driver-reconfiguration-boundary.md`: Proposed, not Accepted, original dynamic switching deferred | Keep proposal and amendment history; do not elevate to normative accepted ADR |

**Boundary note:** This is an 11-document sample, not a comprehensive code-vs-document reconciliation. Future work must check actual API route implementation, PS deployment engine, PL register definitions, RTL, and tests before assigning a single authoritative contract.

**Owner scope:** IC Catalog and all device-catalog workflows remain deferred. Do not migrate evidence or change catalog/provider qualifications under this PR.

## Implementation-to-document spot checks — WEB / PS / PL

Reviewed tracked source on pinned `main`, not just Markdown filenames.

| Contract or concern | Actual source inspected | Grounded conclusion |
| --- | --- | --- |
| WEB REST remote-write boundary | `software/python/plasma_web/secure_gateway.py` | `SecurePlasmaWebHandler` exists and inherits the canonical gateway handler; the REST contract names this actual class. Authentication/authorization implementation needs endpoint-by-endpoint test reconciliation before any claim of full coverage. |
| WEB Manager BFF | `software/web/app/api/manager/ppu/route.ts` | GET and POST route handlers exist; managed-routing errors can return 503 and unmanaged mode can report `managed:false`. This is a distinct browser-side manager route, not proof that the PPU REST contract itself defines these BFF endpoints. |
| PS secure gateway wiring | `software/python/plasma_web/secure_gateway_app.py` | Imports `SecurePlasmaWebHandler`, gateway phase mixins and security/runtime activation components. Do not treat PS installer documentation as the sole runtime API source. |
| PL proposed fixed-image ABI | `pl/verification/fixed_image_abi_v1_gate1.json` | Explicit machine-readable `status=review_candidate_not_implemented`, `sites_physically_verified=0`, `site_count_ceiling=8`; ceiling is **not** eight verified physical channels. |
| PL AXI identity RTL | `pl/rtl/bus/fixed_fpga_ppu_global_identity_axi_lite.sv` | Explicitly host-simulation-only and not connected to physical decoder, UIO, FPGA Manager or pins; build parameter examples are not identity evidence. |
| PL integrated fixture RTL | `pl/projects/z2-fixed-unified-site1/rtl/fixed_ppu_z2_internal_fixture_axi.sv` | Explicitly internal synthetic SWD responder with no external PMOD/SWD/JTAG/DUT. Never use its simulated response as external DUT proof. |

### Cross-domain authority map (initial, subject to tests)

- **Agent workflow:** root `AGENTS.md` entrypoint; detailed contract on demand.
- **WEB browser UX:** `software/web/` implementation and tests; `web-product-modes.md` defines product semantics; `web-rest-api-contract.md` describes PPU-facing REST, distinct from Manager BFF routes.
- **PS gateway:** `software/python/plasma_web/` runtime implementation and tests; PS install/release docs govern packaging/operations, not arbitrary browser endpoints.
- **PL fixed-image candidate:** `pl/verification/fixed_image_abi_v1_gate1.json` is the machine-readable **proposal**; relevant `pl/rtl/` is simulation evidence, not physical admission.
- **Cross-domain boundary:** WEB/PS REST is distinct from PS/PL register-level ABI; neither grants hardware operation or eight-site physical qualification.

**Next verification needed:** route-by-route API-to-tests map; PS deployment-engine executable entrypoint and rollback tests; JSON ABI-to-RTL register/offset tests and physical admission receipts. No code edits, claims of physical acceptance, or catalog work in this PR.

## Owner-approved Batch 1 Baseline v1 — FROZEN (16 documents)

Owner explicitly approved **WEB 4 + PS 4 + PL 4 + Shared 4 = 16** as the first batch of PR #1228 Gate 1 documentation governance. This table is the frozen acceptance population. **Do not add, substitute or remove entries without a separate Owner baseline revision.** Audit/report documents and referenced implementation/test files may be consulted as evidence but do not count as additional batch documents.

| ID | Area | Frozen document path | Starting blob SHA |
| --- | --- | --- | --- |
| W01 | WEB | `software/web/README.md` | `093d5244a5243b637e579cae1aa0bc5c0260f493` |
| W02 | WEB | `docs/architecture/web-rest-api-contract.md` | `276036b571c0f43b7cce131b2c8e2b500561dc04` |
| W03 | WEB | `docs/architecture/web-product-modes.md` | `aa77db3d60c956089c5ff1480946ff9fed44fd7b` |
| W04 | WEB | `docs/deployment/web-runtime-hygiene.md` | `717f22539ee08484578ceedbbbed86f2f2c3203e` |
| S01 | PS | `docs/deployment/z2-ps-installer.md` | `a4c7ff0bbece26b1f27e9d2d954add59d20fe67e` |
| S02 | PS | `docs/architecture/runtime-data-root-contract-v1.md` | `3f1bf077afff287819a50c4abff107f430602b19` |
| S03 | PS | `docs/development/linux-mmio-backend-v1.md` | `43b6f776ba17e39ac130c6ea5a6ba6a4e035f0fc` |
| S04 | PS | `docs/development/swd-legacy-path-retirement.md` | `569ee37517bbd67fc9d5a9452a17d51739621727` |
| P01 | PL | `docs/architecture/fixed-fpga-hardware-abi-v1-gate1.md` | `68f3336aaf708923bc6bd631489e9fe153e0bb2d` |
| P02 | PL | `docs/architecture/fixed-fpga-swd-site1-rtl-gate1.md` | `613111849474a39d02da43e86215f1081afa3dc9` |
| P03 | PL | `docs/architecture/plasma-unified-fpga-build-diagnostics-v1.md` | `0d666709cfc8d97fc7f475c95249fc5016cb7086` |
| P04 | PL | `docs/adr/0003-runtime-fpga-driver-reconfiguration-boundary.md` | `92dab7ad202115896ca1c57b94b6c7cdfaa38432` |
| C01 | Shared | `AGENTS.md` | `52485d65c715858addcfa3fe2b3a6d750dbf81cd` |
| C02 | Shared | `docs/development/plasma-autonomous-development-contract-full.md` | `8117f704a3f99ba9e101e077c2986f88c1b66c5f` |
| C03 | Shared | `docs/README.md` | `5b8c0c904a42c3d343456876b46c6ceb3d6ebed4` |
| C04 | Shared | `docs/adr/README.md` | `9d65aa9c1617a75324deaec64c43a8cd1409d13b` |

### Acceptance rules — all 16 entries

For each document record: (1) authority/status classification, (2) exact duplicate/contradictory clauses or evidence-backed no-change decision, (3) implementation and test alignment where applicable, (4) valid navigation/inbound link impact, and (5) relevant documentation/contract CI outcome. Count **reviewed**, **modified**, and **accepted** separately. A file is accepted only with a recorded disposition and evidence; unchanged files may be accepted if no change is justified.

**Explicit exclusions:** IC Catalog/ICPN/Provider Qualification and the 245 Device Catalog workflows; no hardware operations, deployment, runtime code changes or merge. Existing out-of-batch historical navigation in `docs/README.md` is preserved, not expanded. Root `AGENTS.md` remains mandatory entrypoint, full contract on demand.

**Initial evidence:** All 16 paths were fetched successfully from the PR branch; the starting blob SHAs above identify their exact baseline. This is an inventory milestone, **not** a claim that 16/16 content acceptance is complete.

## Batch 1 Gate 1 dispositions — WEB first pass

Evidence: the four frozen WEB documents W01–W04 were read from their pinned baseline blobs; source spot checks inspected `software/web/app/api/fleet/route.ts`, `software/web/app/api/manager/ppu/route.ts`, `software/python/plasma_web/secure_gateway.py` and `software/python/plasma_web/gateway.py` on `main`.

| ID | Authority/status | Finding and disposition | Acceptance |
| --- | --- | --- | --- |
| W01 | Developer entrypoint, not normative API | Added links to W02/W03/W04 and root AGENTS; clarified Manager BFF versus PPU REST. Commit `df64fb9557063ae0481ff7f831d6f684c96c8719`. | Pending link and CI regression |
| W02 | PPU-facing REST v3 contract | Contract declares `rest_contract_version="3"` and names `SecurePlasmaWebHandler`; actual `secure_gateway.py` defines that class and `gateway.py` emits version fields. Endpoint-by-endpoint route/test comparison still pending. | Pending |
| W03 | Product UX semantics | Distinguishes Production/Engineering from Fleet topology; explicitly describes Mock-only execution prototype and future Manager packaging paths. Do not silently elevate future packaging to deployed behavior. | Pending |
| W04 | SWPC Web operational runbook | Distinguishes `plasmactl update`, `web-restart`, and `deploy`. Actual command implementation and rollback/restart tests not yet verified. | Pending |

**Counts:** Batch 1 baseline 16/16 exists; 4/16 WEB documents have initial content disposition; 2/16 baseline documents have been directly modified to date (C03 index, W01 README); **0/16 fully accepted** until evidence and CI are complete. Audit report itself is not a baseline document. No modifications to W02–W04 or runtime code in this step.

## Owner execution directive — batch CI only

Owner instructed: **finish organizing all 16 frozen Batch 1 documents before performing a consolidated CI verification.** Do not run, poll, or report per-file CI as an acceptance step. Continue document/content/source reconciliation without requesting separate approval for each document. After all 16 have recorded dispositions and the final edits are complete, perform one consolidated relevant CI review and report Gate 2 readiness.

GitHub may independently trigger push-based Actions; this instruction does not authorize modifying shared workflows or claiming those automatic runs are suppressed. Do not manually dispatch workflows during the document-edit phase. Keep PR Draft, do not merge, deploy, operate hardware, or expand into IC Catalog.

## Batch 1 remaining document review — PS / PL / shared (CI deferred)

All frozen PS S01–S04, PL P01–P04 and shared C01–C04 documents were read from the PR branch. These are **content review dispositions**, not final acceptance or CI claims.

| ID | Authority / reviewed finding | Disposition |
| --- | --- | --- |
| S01 | Z2 PS release-kit and managed acceptance; distinct from deployment-engine transport and Factory Recovery | Edited: explicit PS-only / no implied SSH production transport / no hardware admission; verify live engine later |
| S02 | Installed Python runtime data-root CI contract; scoped to Python package assets, not generic PS/PL memory map | No text change justified at present; verify relevant CI after batch |
| S03 | Explicit historical synthetic SWD-03 MMIO backend; not current Blue Pill external SWD | Preserve historical evidence; no change |
| S04 | Explicit current external Blue Pill path vs retired SWD-03/EMIO and guarded legacy HIL | Preserve boundary; no change |
| P01 | Fixed-image ABI v1 candidate, M1 NO-GO | Edited: manifest status, zero physically verified sites, simulated AXI and internal synthetic fixture |
| P02 | Site-1 RTL simulation-only candidate; newer semantic convergence document supersedes older gap table | Preserve historical feasibility result; no change |
| P03 | Proposed unified FPGA build diagnostics, offline/host evidence only | Edited: no implicit physical image/timing/DUT qualification |
| P04 | ADR-0003 Proposed, not Accepted, M1 NO-GO | Preserve status and owner-review requirement; no change |
| C01 | Root AGENTS mandatory concise entrypoint | Preserve normative rules; no change |
| C02 | Full development contract detailed normative reference, read on demand | Prior introductory clarification retained; no additional change |
| C03 | Docs navigation index, already changed in PR | Preserve first-batch navigation; verify links at batch end |
| C04 | ADR status index; ADR-0003 Proposed | No change |

**Batch review coverage:** 16/16 initial content classification (W01–W04 in preceding section; S01–S04, P01–P04, C01–C04 above). **Final accepted: 0/16 pending implementation/test/link reconciliation and consolidated CI.** Directly edited frozen baseline paths so far: W01, S01, P01, P03, C02, C03 (6/16); C02/C03 edits predate frozen baseline, and the baseline SHA captures their then-current state. No changes outside the frozen documents except this audit report. The owner-directed CI-only-after-batch rule remains in force.

## Additional cross-domain source/document reconciliation (CI not run)

- **W02:** PPU REST v3 contract explicitly distinguished from Next.js Manager BFF and frontend fleet aggregation. Verified actual `software/web/app/api/manager/ppu/route.ts` GET/POST, `software/web/app/api/fleet/route.ts` GET, `software/python/plasma_web/secure_gateway.py` secure handler and `software/python/plasma_web/gateway.py` REST version emission. **Not** claiming complete route/test coverage.
- **S01:** The release-kit document itself uses `scripts/plasmactl install z2-ps` and `deploy z2-ps`. Added an explicit verification checkpoint against the executable deployment engine and rollback tests; do not promote release-kit examples to canonical current transport without reconciliation.
- **P02:** Site-1 RTL feasibility is simulation-only; linked the superseding SWD semantic convergence candidate and preserved physical pairing/real DUT proof boundary.
- **Changes:** W02, S01, P02 updated in this pass; frozen set unchanged. Continue evidence and navigation reconciliation across all 16 before one consolidated CI review.

## PS deployment source-level discrepancy resolved in S01

Read `scripts/plasmactl` (profile dispatch and help), `scripts/plasmactl-z2-ps` (install/deploy/verify/status command dispatch), and `docs/architecture/ppu-unified-deployment-gate1.md` (current proposed convergence). Confirmed the **local Z2 PS release-kit CLI** is implemented, while the newer **single network PPU Deployment Engine** remains a partial Host-only convergence with an outstanding trusted on-device installer; legacy SSH engineering paths are still explicitly described as existing. These are not the same deployed capability. S01 now states this distinction and links the evidence. This is documentation-only; no SSH connection, API submission, deployment, CI dispatch or hardware operation.

Batch 1 16-file scope remains unchanged. Continue link/implementation review before consolidated CI.

## SWPC Web runtime and ADR navigation source reconciliation (CI deferred)

Verified `scripts/plasmactl` routes integration-only `update`, `deploy`, `web-restart` to `scripts/plasmactl-integration`. The integration backend runs Vite via `plasma-vite.service`, checks `software/web/package-lock.json` before `npm ci`, and restarts only Vite for `web-restart`. Updated W04 to explicitly limit the runbook to SWPC integration; it does not prove product PPU network deployment. Corrected C03 ADR-0003 navigation label from the older dynamic-reconfiguration framing to fixed-image candidate framing, without changing ADR-0003's Proposed status.

No per-file CI or hardware action performed. Remaining batch work: complete relative-link and evidence reconciliation, then the owner-directed consolidated CI review.

## Frozen Batch 1 repository-relative Markdown link audit — 16/16

At PR HEAD `924fe90910a34ea0c982c676eafbf2810a4e4746`, fetched the complete recursive Git tree (5,208 entries, `truncated=false`) and all 16 frozen documents. For Markdown inline links of form `[label](relative/path)`, resolved relative paths against each source directory and checked exact target paths in the HEAD Git tree. **Result: 16/16 checked; 0 missing target paths.** Counts by frozen ID: W01=4, W02=4, W03=0, W04=0, S01=3, S02=0, S03=3, S04=0, P01=6, P02=2, P03=1, P04=14, C01=8, C02=4, C03=264, C04=3. Total inline Markdown links inspected: **316** (includes anchors/external links, which are not checked for target existence). This check does not verify heading anchors, external HTTP URLs, reference-style links, or semantic accuracy.

This is a **documentation-only static source audit**, not a CI execution. Preserve the owner instruction to defer consolidated CI until all 16 dispositions are complete. Final acceptance remains pending the other criteria.
