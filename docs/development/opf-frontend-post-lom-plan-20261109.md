# OPF Frontend — Programming UX / Custom Bundle Roadmap (after LOM)

> **Status: Plan only; docs-only Draft PR; NOT IMPLEMENTED.**
> **Owner order, 2026-11-09:** Finish and physically accept **Local Owner Mode (LOM)** → implement and accept **OPF Frontend** → immediately perform **two-Site hardware acceptance using PYNQ-Z2 PMOD A and PMOD B**. Eight-Site physical HIL is deferred until hardware exists; it is **not** an acceptance gate for this next phase.
> Base: `main@c689549e7c67887fa4f26d5ccb83d53be7c30528`. Always re-audit current main and `AGENTS.md` before a future Gate 1.
> This PR authorizes **recording requirements only**. It does NOT authorize implementation, Gate 2 merge, deployment, restart, SWPC/Z2/FPGA/DUT access or a physical Flash job.

## 1. Scope and user requirements

OPF Frontend is the **Console/Manager-facing user workflow**, not a dependency added to standalone portable OPF Core. Both normal and expert flows must converge on the existing single PPU Bundle/Active-Asset/Job execution pipeline.

| ID | User scenario | Required behavior |
| --- | --- | --- |
| **OFE-1** | Same programming resources, **different Firmware** | Allow a different firmware file per Job (eventually per Site), while reusing the same compatible Provider, Profile, Driver and FPGA Image. Firmware replacement alone must not reinstall/reload the programming environment. |
| **OFE-2** | PPU **already supports** an IC | Ordinary user selects IC, uploads firmware, selects PPU/Site and presses Start. Console/Manager automatically composes a canonical Bundle v3 if needed and sends it to PPU. No manual Bundle authoring. |
| **OFE-3** | PPU does **not** support an IC, or experimental Provider/FPGA | Advanced user uploads their own Bundle v3 ZIP through Console for controlled programming tests. Production Catalog membership is not a PPU execution whitelist; actual security, resource, platform, protocol and electrical checks still gate hardware. |
| **OFE-4** | User wants to **create** a Bundle | Provide a Console **Bundle Builder** to assemble Packages and dependencies, validate them, build canonical Bundle v3, export/download it and optionally deploy through an explicitly authorized action. Reuse the existing `plasma_opf.bundle_v3` writer; do not add a parallel writer. |

Product principle: **normal user = IC + Firmware + Start; engineering user = import or build a full Bundle**, with one authoritative backend and one result/receipt model.

## 2. Hard prerequisite: LOM must finish first

**DO NOT start OPF Frontend code work until LOM implementation and acceptance are complete**. No progress in this planning PR counts as LOM completion.

LOM acceptance evidence must cover:

- PPU-owned Enrollment/Takeover with **Controller Generation**, atomic revocation, credential persistence, correct migration of existing P2A-1 HMAC, and real Manager credential handling; P2A-0's test-only reference model is not implementation.
- **G13 Gateway :18080**: all mutating routes require current Controller authentication, Generation, Mode and race-safe handover fencing; old controllers cannot retain write access through an existing session.
- PYNQ-Z2 prototype PS-side **MIO12 / Arduino J7 AR_RST button** profile, subject to pinmux and shared reset-net electrical verification. Long-press, debounce, physical pairing to a specific requesting Controller, and safety negatives. Engineering Mode permits an appropriately privileged **SSH arm**; production mode must not allow a LAN arm shortcut. The earlier SD-ticket spec requires an explicit contractual amendment when its trigger priority changes.
- **Recovery-Gated Takeover**: active Job/Bundle/FPGA operation defers takeover; unresolved seal/UNKNOWN/recovery-required gives at most RECOVERY_ONLY. Never clear durable uncertainty or replay an ambiguous Job.
- Console discovery, pairing/re-pairing, automatic reconnect, user-facing READY/RECOVERY and explicit safety admission. Gate 2, controlled SWPC/Z2 deployment and physical acceptance must be backed by exact source/version/receipts. Keep TLS NOT_QUALIFIED transparent if not fixed.

Then initiate OPF Frontend under **separate Gate 1 implementation approvals**; this docs-only Draft PR is not a blanket implementation authorization.

## 3. Existing implementation — do not reimplement

Current `main` already includes merged Console Bundle workflow (#1369), canonical `plasma_opf.bundle_v3` writer and one committed first-party Programming Route. Physical evidence (#1370) establishes: one real Z2 **Site 2 / STM32F103C8T6** Console-managed Job, correct Readback SHA256, attempts=1 and SAFE_OFF; the **human-UI already-active path** passed, and BFF-driven (not human UI) cache-miss B1/B2/B3 passed. These do NOT prove the human-UI cache-miss path, 2-/8-Site concurrency, external non-OpenOCD Provider, FPGA-bearing custom Bundle, external user Bundle GUI or full negative hardware tests.

Current firmware is included in Bundle identity; if only firmware changes, full Bundle SHA changes and the workflow treats it as a new Active Set. **Do not claim Resource reuse is already solved.** Existing immutable Bundle v3 and single Active Asset Set remain authoritative until an explicitly approved migration.

## 4. Target architecture

### 4.1 Separate Resource identity and Firmware Job identity (OFE-1)

Define an immutable **Programming Resource Set**: Provider, Profile, Driver, optional FPGA Image, Packages/dependencies and relevant ABI/platform/hardware constraints. Define a distinct, immutable **per-Job Firmware Asset**: payload SHA256/size/format/address/segment declarations and applicability. A future approved contract can stage/cache firmware independently and bind it to Job/PPU/Site/Resource identity; an alternative content-addressed reuse scheme is acceptable only if it proves equivalent atomicity and safety.

- One effective Active Resource/Asset Set per PPU at any moment; **never mix untrusted packages from multiple Bundles** or bypass B3 identity checks.
- Firmware-only change => **zero Provider/Driver/FPGA install/reload**, as long as the selected resource is already qualified for the Job. A real resource/target mismatch still requires fresh authorization/admission or denial.
- PPU must verify every Job's exact firmware bytes/hash/format/target geometry; cache identity and durable receipts must be crash safe, with no cross-Job or cross-Site substitution.
- Different Sites may use different Firmware while sharing compatible resources; FPGA reload remains a **PPU-wide exclusive** activity, not a per-Site operation.

### 4.2 Normal Console Programming (OFE-2)

- Console: IC + local Firmware + PPU/Site → Prepare/confirm → Start → authoritative result/Readback/SafeOff and recovery view.
- Manager selects one applicable Programming Route (0 or ambiguous match ⇒ clear refusal), builds canonical Bundle v3 when needed, compares actual qualified Resource Set identity, uses existing Bootstrap B1/B2/B3 only when needed, and submits **exactly one** Job.
- PPU remains authoritative for ABI/Image/Root/voltage/geometry, per-Site lease and session, SAFE_OFF/SEAL and UNKNOWN. Catalog L2/L3 is neither an automatic hardware PASS nor an absolute execution whitelist.
- Preserve the existing `ManagerBootstrapCoordinator`, PPU execution router, canonical writer, receipts and Source/Asset SHA boundaries. No extra deployment coordinator or flash engine.

### 4.3 User Bundle Import/Deployment (OFE-3)

- Advanced Console accepts an **externally built** canonical `plasma.ppu.bundle.v3` ZIP; preview Package list, dependencies, Target Platform, declared capabilities and potential executable/FPGA risk; explicit separate Install/Activate/Flash confirmations.
- Manager validates size, ZIP paths, duplicate records, SHA256, versioned DAG, schema, target and execution privileges; PPU independently re-verifies during B2/B3 and gates actual hardware at Job admission.
- Source repository, publisher and Catalog membership must not be arbitrary mandatory allowlists. A user-provided executable Provider/FPGA requires explicit controlled owner authorization, software isolation and actual hardware compatibility/safety evidence.
- **Upload accepted ≠ B2 admitted ≠ B3 activated ≠ Job executable ≠ physical Flash PASS**. Experimental Flash results never silently promote L2/L3 qualification.

### 4.4 Visual Bundle Builder (OFE-4)

- GUI to add/import Package Files, Provider/Profile/Driver/FPGA/Firmware, configure dependencies and Target, check hashes/sizes and show a reviewable package graph.
- Explicit **Validate → Build → Export/Download → (authorized) Deploy**; Build/Import must not silently activate FPGA or dispatch a Job.
- Delegate canonical binary/Manifest generation and validation to existing `plasma_opf.bundle_v3` and existing PPU verifier. No duplicate Bundle format, second ZIP writer or privileged bypass.
- Test deterministic output and fail-closed invalid target, malicious ZIP, cycles, mismatched SHA, unsupported ABI, unsafe voltage, missing privileges and unknown outcome.

### Ownership

| Layer | Responsibility |
| --- | --- |
| Console (OPF Frontend) | ordinary Programming UI, Firmware chooser, Custom Bundle upload, visual Builder, warnings, receipts |
| Manager | route/resource resolution, canonical Bundle composition, per-Job Firmware identity, credentialed orchestration, durable run journal |
| PPU Bootstrap | authenticated B1/B2/B3, Active Asset Set and protected FPGA deployment/recovery |
| PPU Gateway/Runtime | **G13**, authorized Job admission, Provider execution, physical guards, per-Site isolation, outcome evidence |
| Portable OPF Core | provider/capability/operation/result contract; **no mandatory** Console/Manager/Bundle/PPU coupling |

## 5. Execution sequence and deliverables (all after LOM)

| Stage | Order | Deliverable and approval |
| --- | --- | --- |
| **OFE-0** | 1 | Read-only latest-main gap/contract audit, firmware-vs-resource model, risk/LOC-deletion plan; **new Gate 1** required |
| **OFE-1** | 2 | Normal user IC + Firmware + Start, qualified resource reuse, versioned Job Firmware Asset (or equivalent), Host-only and controlled single-Site HIL |
| **OFE-2** | 3 | Custom Bundle import, preview, verification and authorized B1/B2/B3/Job; controlled experimental path and negatives |
| **OFE-3** | 4 | Visual Bundle Builder, canonical validate/build/export/deploy with hosted CI and packaged Console tests |
| **OFE-4** | 5 | **OPF Frontend feature-complete integration acceptance**, including ordinary/advanced workflows, receipts and security/recovery. Only when this passes, proceed directly to two-Site HIL |
| **HIL-2** | **Immediately after OFE-4** | **Two physical Sites through the two currently available PYNQ-Z2 PMOD A / PMOD B connectors.** Separate Gate 1/2 authorization for any writes, FPGA/Root changes or DUT operations. |
| **HIL-8** | Later | Eight-Site electrical/parallel HIL only when the actual 8-Site hardware exists; **not a blocker** for the current LOM → Frontend → HIL-2 sequence |

### HIL-2 — mandatory acceptance, not simply two sequential flashes

**Hardware bounds:** User currently has **PMOD A and PMOD B only**. Before assigning Site numbers, independently inventory the Z2 XDC/RTL/HWH/FPGA image and physical breakout mapping, required SWD pins, power/ground, buffer levels, reset routing, Site ownership and available safe DUT fixtures. **Do not assume** each PMOD automatically represents a qualified Site or that the existing Site 2 implementation already supports both. Do not hotplug/reassign FPGA signals without hardware permission.

**Minimum evidence:**

1. **Each PMOD path separately**: discover/probe the DUT; one controlled `erase → program → verify → full readback` with exact image SHA/bytes, **SAFE_OFF**, correct Site/FPGA/ABI and durable Job IDs.
2. **True two-Site concurrency:** show **overlapping execution intervals** on A/B (not merely two sequential PASS results), distinct Job/Site/session/owner IDs, no shared SWD cross-talk, no resource/port conflict; FPGA reconfiguration correctly fenced globally.
3. **Same resources, different Firmware:** where compatible, hold Resource Set/FPGA constant and write distinct Firmware A/B at the two Sites, prove no redundant B3/FPGA load and prove each Site reads back **its own** expected hash.
4. **Safety negatives:** one Site idle/busy/fault/timeout/UNKNOWN/SEALED/cancel does not corrupt or falsely PASS the other; shared FPGA reload denied during active Jobs; retry policy never replays uncertain writes.
5. **Electrical safety:** verify PMOD pin-voltage compatibility, power/current control, common GND, target supply and reset sequencing, and independent per-Site safe-off. If independent power/voltage safety cannot be qualified, mark hardware acceptance **BLOCKED**, do not infer it from software tests.
6. **Host and hardware versions:** exact `main`/PR HEAD, FPGA Image/Manifest/HWH, PPU Runtime, Provider/Driver, Bundle/Resource and two Firmware SHA values, controller identity/generation, physical mapping, logs, readback and receipts. Report PASS/FAIL/NOT_RUN without extrapolating to 8 Sites.

**HIL-2 PASS is a scoped two-Site milestone**, not proof of production eight-channel operation or all L3 exact ICPNs.

## 6. Cross-cutting invariants and future PR acceptance

- Use **Replace-by-Default / Deletion-First**. Report production/test/docs Added/Deleted/Net LOC and a retired-code ledger; no second Bundle writer, router, provider registry, security authority or hidden runtime.
- Maintain durable transaction semantics and exact identity all the way from browser to PPU. No automatic replay after ambiguous B3 or Job delivery; preserve `SEALED`, `OUTCOME_UNKNOWN`, recovery and physical Root/FPGA locks.
- Positive and negative CI on exact HEAD, PPU Python 3.10 where appropriate, Windows/macOS/SWPC packaged Console compatibility where in-scope, and distinct owner-approved hardware HIL.
- Firmware/Resource identity and Cache invalidation should be explicit versioned contracts, not UI-only assumptions.
- This plan does not change ADR-0008, Bundle v3, active credentials or hardware privileges by itself. All executable changes require independent **Gate 1 approval**; merges require **Gate 2 approval**.

**Approval boundary:** docs-only Draft PR; **NO merge, deployment, FPGA reload, physical flash, SWPC/Z2/DUT operation or firmware/Runtime changes** as part of this recording.
