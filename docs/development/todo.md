# Plasma Development Debt Register

This file tracks known executable gaps that are intentionally deferred from the current implementation scope. A Current architecture document may link here, but it must not describe these items as already implemented.

An item leaves this register only when its backend invariant, recovery semantics, tests and operator documentation are merged together. UI-only masking is not closure.

## High Priority

### IC Electrical Programming Profile / Voltage Capability Database

**Status:** TODO / required before physical multi-IC programming qualification

**Layer:** Device Support / Programming Profile / Electrical Capability / Control Station / PPU hardware execution

**Reason:** The current Production ICPN catalog identifies exact commercial IC identities and programming backend routes, but it does not yet model the electrical conditions required to power and program the selected IC safely. A valid backend route is not sufficient evidence that the programmer may apply power to a physical target. Electrical operating limits and programming conditions must therefore become a first-class, evidence-backed part of the selected IC profile rather than a separate lookup table or operator memory.

Required data model:

- define an evidence-backed **Electrical Programming Profile** linked to the exact ICPN and/or an explicitly authorized equivalent device family/profile;
- model normal supply range separately from programming conditions:
  - `vdd_operating_min/max`;
  - `vdd_programming_min/max`;
  - recommended programming VDD where the manufacturer specifies one;
  - VPP requirement/range, including explicit `not_required` when authoritative;
  - I/O / debug-interface voltage requirements and level-shifter constraints;
  - required power-up / power-down sequencing;
  - reset-state requirements during power sequencing where specified;
  - per-target current limit / expected current envelope where authoritative and useful for protection;
  - any programming-specific voltage or timing exceptions;
- retain source authority, datasheet/programming-manual reference, revision, evidence location and verification status for every electrical profile;
- distinguish manufacturer absolute maximum ratings from valid operating/programming ranges; absolute maximum values must never be treated as programmable setpoints;
- never infer missing electrical values merely from another device sharing an OpenOCD target config.

Selected-IC Profile integration:

- when an operator selects an IC in the Control Station, the **same selected IC / Programming Profile view** must present its electrical requirements together with identity and backend information;
- do not force operators to consult a separate voltage database or separate configuration page;
- the selected IC profile should expose, at minimum:
  - exact ICPN / family / package;
  - Programming Backend and resolved target/profile;
  - operating VDD range;
  - permitted programming VDD range and recommended programming voltage;
  - VPP requirement;
  - debug/programming I/O voltage requirement;
  - power-sequencing requirement;
  - current-limit/protection requirement when defined;
  - evidence / verification status;
- clearly distinguish **IC operating range** from **the voltage Plasma will actually apply** to the selected Site;
- show an explicit unresolved/unsupported state when electrical evidence is incomplete instead of hiding missing values.

Execution and safety boundary:

- physical programming readiness must require both:
  1. a valid Programming Backend/Profile; and
  2. a verified Electrical Programming Profile compatible with the selected PPU/Site hardware capabilities;
- missing or conflicting electrical data must fail closed for automatic DUT power enable and physical programming;
- software-only catalog lookup, route research and control-plane diagnostics may remain available when electrical readiness is unresolved, but must not be reported as hardware-ready;
- the PPU must validate the requested Site voltage/current configuration against the selected IC electrical profile before enabling DUT power;
- future programmable power rails, level shifters and protection circuitry must expose capabilities in machine-readable form so compatibility can be evaluated rather than assumed;
- eight-Site operation must validate electrical compatibility per Site and must not assume all loaded ICs share identical voltage requirements unless the Job/Batch contract explicitly guarantees that condition.

UI / API contract:

- the backend API that resolves a selected IC must return the electrical profile and its evidence state together with the Programming Profile/backend resolution;
- Control Station must render this information in the selected-IC profile surface before execution;
- the UI must distinguish catalog/evidence values from the actual PPU/Site electrical configuration that will be applied;
- unresolved electrical readiness must be visible to the operator and must block physical execution rather than silently falling back to a default voltage.

Pilot evidence / model status (STM32F103C8T6):

- Selected IC Profile v1 now composes the frozen manufacturer baseline into the read-only
  IC Support resolver and `GET /api/devices/search` result without changing execution admission;
- IC Selector presents IC Information, Programming and PLASMA Compatibility as separate
  primary sections, with backend/runtime provenance moved to Advanced Evidence;
- missing operating/programming electrical facts fail profile resolution closed;
- exact ICPN Flash capacity is cross-checked against Catalog identity so the Blue Pill
  128-KiB OpenOCD board override cannot contaminate STM32F103C8T6's 64-KiB Device Profile;
- a manufacturer-only Device + Programming baseline is now frozen before backend inspection;
- operating VDD and memory map are owned by the Device Profile while programming VDD,
  interface behavior and Flash operations are owned by the Programming Profile;
- manufacturer-unknown SWD/JTAG clock limits remain explicitly unknown rather than being
  populated from backend defaults;
- the machine-readable manufacturer Flash sequence is compared only after freeze against
  the pinned OpenOCD implementation;
- the pilot comparison explicitly prevents the OpenOCD Blue Pill 128-KiB convenience
  override from changing the exact STM32F103C8T6 64-KiB Device Profile;
- this pilot proves the information-architecture method only; broad ST enrichment,
  PPU/Site capability matching and physical qualification remain open.

Programming Profile Information Architecture Review:

- before the physical-programming schema is finalized, perform a dedicated review of additional **software and hardware programming information** that should be presented with the selected IC;
- candidate information to evaluate includes, but is not limited to:
  - programming interface/protocol (SWD, JTAG, SWIM, SPI, UART, I2C or vendor-specific);
  - backend/provider and target/algorithm identity;
  - supported erase modes, program granularity and verify/readback behavior;
  - flash geometry, bank/page/sector organization and address ranges;
  - maximum/recommended programming/debug clock;
  - reset/connect-under-reset requirements;
  - option bytes, fuses, security/protection state and irreversible operations;
  - mass-erase restrictions and recovery semantics;
  - required adapter, socket, fixture or pin-routing constraints;
  - PPU/PL feature requirements and minimum hardware/bitstream capability;
  - per-operation timeout/retry constraints;
  - device identification/signature expectations;
  - known silicon/revision-specific programming exceptions;
- decide explicitly which information belongs to:
  1. the exact IC identity record;
  2. the Electrical Programming Profile;
  3. the Programming Profile / algorithm layer;
  4. the Programmer Backend capability;
  5. the PPU/PL/Site hardware capability;
  rather than duplicating the same fact across multiple layers;
- design the selected-IC UI as a composed profile sourced from these layers, not as one oversized flat CSV schema;
- review this information architecture with actual programming use cases before freezing field names or compatibility rules.

Architectural invariant:

> Selecting an IC must resolve one evidence-backed programming view that combines device identity, programming capability and electrical requirements, while keeping each fact owned by the correct data layer. A backend route alone is never sufficient evidence for physical-programming readiness.

Closure evidence must include schema/version contracts, authoritative source evidence, API resolution, Control Station presentation, PPU-side compatibility enforcement, fail-closed negative tests, and physical validation on representative devices before this capability is marked Current.

### Security Rollout and Identity Integration

**Status:** TODO / follow-up after PRs #167-#169

**Layer:** Security/control plane

**Reason:** The core remote-write authentication and authorization boundary is implemented and is no longer technical debt. Remaining work is production rollout and identity lifecycle integration around that boundary.

Required remaining work:

- complete the production threat model before exposing write APIs outside a trusted network;
- decide and document when secure Gateway deployment becomes the canonical production default while preserving standalone PPU operation and rollback;
- map Cloudflare Access / OIDC identities into the existing backend Principal / Permission / Facility-PPU-Site Scope model without bypassing backend authorization;
- add permission-aware disabled/hidden execution controls throughout PMode and EMode as operator guidance, while keeping the backend as the authority;
- add human credential rotation, revocation and session-lifecycle UX;
- define centralized multi-PPU identity management through Plasma Manager without making standalone PPU authorization depend on Manager availability.

### macOS Control Station Static Asset / Font Packaging 404

**Status:** TODO / observed during installed Control Station acceptance after PR #242

**Layer:** Control Station Web runtime / Common Release Format / macOS installer

**Reason:** Real installed-Control-Station browser acceptance observed `.woff2` and related static-asset requests returning HTTP 404 from `127.0.0.1:18000`. Managed routing itself passed: the Browser remained on the Manager-owned route and did not leak direct PPU Gateway traffic. This packaging/serving defect must therefore remain a separate deployment debt item rather than being misclassified as a routing failure.

Required work:

- capture the exact missing font/static-asset URLs and map each reference back to the generated Web build output;
- determine whether the loss occurs during Web build, standalone runtime assembly, Common Release Format packaging, macOS installer staging, or installed static-file serving;
- ensure every asset referenced by installed HTML/CSS/JS is present under the immutable installed runtime with the same hashed path/name expected by the browser;
- verify CJK/local font packaging explicitly, including `.woff2` files, rather than relying only on source-tree or development-server behavior;
- extend packaged-runtime and macOS installer acceptance to request referenced static assets and fail deterministically on unexpected 404 responses;
- add an installed-browser smoke assertion that no required `/assets/...` or font request returns 404 during normal page load;
- preserve the Single Routing Owner invariant while fixing asset serving: static-asset repair must not reintroduce Browser-owned PPU/Gateway routing or direct Gateway fallback.

Closure evidence must include a rebuilt/installed macOS package and real browser Network evidence showing required static/font assets load successfully without the previously observed 404 class.

## Deferred architecture evolution

### Mock Runtime Core Convergence

**Status:** TODO / medium-term architecture cleanup; no immediate runtime merge required

**Layer:** Mock Runtime / deployment profiles / test infrastructure

**Reason:** Plasma currently has two useful Mock deployment shapes with different verification purposes: the Render `render-demo-ppu` fixture models one managed PPU with eight Sites for `Console/BFF -> Manager -> Gateway -> Protocol Server` acceptance, while PMode and EMode use the Python-owned Engineering Mock topology with eight Facilities, 32 PPUs and 160 Sites for multi-PPU workflow and Batch simulation. Keeping both deployment profiles is intentional. The debt is not that two profiles exist; the risk is allowing their E/P/V/R execution semantics, Mock Flash behavior, timing/error injection, Job/Site state transitions, retry or cancellation rules to evolve independently and drift.

Required work:

- preserve a single-PPU managed-path deployment profile for Render/public-demo smoke and programming acceptance;
- preserve the factory-scale Engineering Mock topology profile for PMode/EMode multi-PPU and Batch scenarios;
- inventory duplicated or divergent Mock execution behavior across both profiles, including E/P/V/R, timing, error injection, Mock Flash, Job/Site state, retry, cancellation and readback semantics;
- converge duplicated behavior onto one shared Mock Execution Core where practical instead of forcing both deployment profiles into one runtime shape;
- keep topology construction and deployment adapters separate so single-PPU acceptance does not become coupled to the 32-PPU/160-Site factory topology;
- keep Manager as routing/management infrastructure rather than making it the Mock execution owner;
- add parity tests that prove equivalent operation/state/retry/cancellation semantics for both deployment profiles where they intentionally overlap;
- document any intentionally different behavior explicitly instead of relying on fixture-specific implementation accidents;
- consider renaming `render-demo-ppu` to a clearer managed-smoke/deployment-fixture identity only if that can be done without creating unnecessary deployment churn.

Architectural invariant:

> Plasma may have multiple Mock deployment profiles, but equivalent Mock execution semantics should have one implementation owner. Deployment shape is configuration; E/P/V/R behavior must not fork silently.

Closure evidence must show that the single-PPU managed acceptance profile and the factory-scale 32-PPU/160-Site profile still serve their separate purposes while shared execution semantics are implemented once or guarded by deterministic parity tests.

### Plasma Hardware API / OpenOCD Adapter Productization

**Status:** TODO / post-PoC architecture evolution

**Layer:** Device Support / Programmer Backend / PPU hardware execution

**Reason:** The current PoC should continue using PYNQ + Python because it maximizes learning velocity for `PS -> PL -> Site -> real IC`. After the PoC proves the end-to-end programming path, the product architecture should decouple Python Device Support and replaceable Programmer Backends from board-specific PL access. The approved direction is documented in [Device Support / Hardware Execution / OpenOCD Architecture](../architecture/device-support-hardware-openocd.md) and must remain a Plan until production implementation and hardware evidence exist.

Required work:

- keep Device Support, parsers, Device Profiles, Programming Plans and Image handling in Python so new IC support remains data/rule driven rather than C-code driven;
- define a semantic Plasma Hardware API that exposes operations such as Site power/reset, SWD/JTAG transactions, program start/cancel and status without exposing raw register addresses to Programming Logic;
- evaluate a stable `libplasma_hw.so` boundary after PoC, with Python calling it through an approved binding only where C is justified;
- use UIO as the user-space hardware resource boundary, MMIO for control/status register access, IRQ for events and DMA for Programming Image bulk transfer;
- keep raw `/dev/mem` and per-register implementation details out of the production application contract;
- design a custom OpenOCD Plasma adapter that calls the Plasma Hardware API while preserving OpenOCD as a replaceable Programmer Backend;
- avoid per-bit OpenOCD/Python MMIO bit-banging; send high-level SWD/JTAG transactions to PL protocol engines so deterministic timing and multi-Site parallelism remain in hardware;
- keep OpenOCD target/flash-algorithm knowledge separate from Plasma hardware execution so a future Plasma-native or vendor backend can use the same Hardware API;
- after PYNQ is removed from the production hardware path, make Plasma own its Python runtime version instead of coupling application Python to the PYNQ image;
- evaluate Linux FPGA Manager for production bitstream loading and remove any production dependency on Jupyter;
- add native Z2 acceptance for UIO/MMIO/IRQ/DMA behavior, memory/resource stability, PS-to-PL execution, Site I/O and real IC programming before declaring this architecture Current.

Architectural invariant:

> Device knowledge and programming orchestration remain high-level and replaceable; the Hardware API describes Plasma hardware capabilities rather than raw registers, and PL owns deterministic protocol execution.

### Z2 AXI Control/Data Plane / DMA Architecture Assessment

**Status:** TODO / deferred until Path 2 real F1-B Provider and independent cross-trigger HIL pass; no immediate RTL or driver change

**Layer:** Zynq-7000 PS/PL Hardware API / FPGA PL / firmware transfer performance / eight-Site programming

**Reason:** PYNQ-Z2 can implement AXI4-Lite register control, memory-mapped AXI4 data movement and AXI4-Stream transfers within PL, but availability is not evidence that DMA is necessary for PLASMA. Zynq-7000 PS GP/HP interfaces have AXI3-specific details; any PL AXI4/AXI4-Stream design must select a compatible Interconnect/Protocol Converter and DMA/FIFO data path rather than assuming PS directly exposes an AXI4-Stream port. Eight simultaneous Sites alone does not prove bulk-transfer bottlenecks.

Required follow-up, **after current PR #1082 Gate 1**:

- preserve the existing AXI4-Lite control/status/identity register ABI and shared Linux MMIO Hardware API rather than rebuilding the current F1-B Provider;
- measure actual PS-to-PL transfer time, CPU consumption, buffer usage, throughput and Site fairness under representative firmware/image sizes and 1/2/8 concurrent Sites; distinguish SWD/JTAG protocol wait time and DUT Flash programming bottlenecks from PS/PL data-copy cost;
- compare (A) bounded MMIO register/FIFO writes, (B) an AXI DMA memory-mapped path using Zynq HP/DDR access and (C) AXI4-Stream plus a PL-side FIFO/dispatcher; record coherency, cache maintenance, buffer ownership and IRQ/completion semantics;
- separately assess AXI3 PS-side compatibility, AXI4/AXI4-Lite IP choices, AXI4-Stream's addressless data-flow model and Xilinx AXI Interconnect/Protocol Converter boundaries;
- specify stop/quiesce/restore behavior for every DMA/Stream Master **before** FPGA Manager reconfiguration; a DMA engine and a generic UIO driver do not establish AXI idleness or isolation;
- require an evidence-backed latency/throughput threshold and end-to-end eight-Site HIL before adopting DMA. Defer implementation if simple MMIO/FIFO meets the measured throughput goal;
- reflect the selected design in the common Linux-to-PL Hardware API, Site safety/ownership contract, RTL tests and operator recovery procedure. No Production hardware readiness follows from Host-only benchmarks.

**Current scope exclusion:** This is a backlog design/performance decision. Do not add AXI DMA, modify PL bitstream, or dispatch hardware work as part of PR #1082's current Real Provider Gate 1. Existing F1-B Build and one-shot HIL evidence may be reused if exact hashes and environment bindings still match.

### Split Programming Image Data Plane

**Status:** TODO / future architecture optimization

**Layer:** Control plane / Programming data plane

**Reason:** Managed Mode currently sends Programming Asset/Image traffic through the same `Control Console -> BFF -> Manager -> PPU Gateway` routing ownership as Programming commands. This deliberately favors one trustworthy production route over premature data-plane separation. A direct or otherwise separate Image data channel should be introduced only when measured fleet bandwidth, concurrency, latency, memory pressure or reliability shows that Manager relay is a material bottleneck.

Required work before any split data plane may become canonical:

- measure Manager CPU, RAM, network utilization, Image throughput, concurrent PPU transfers, command latency and failure behavior at intended fleet scale;
- define an explicit Image data-channel contract that does not let the caller choose an arbitrary PPU URL;
- keep Manager authoritative for managed PPU identity/routing policy even if the Image bytes no longer transit Manager;
- preserve PPU identity binding, authorization, auditability, bounded transfer semantics and fail-closed behavior;
- preserve source Asset SHA-256, PPU cache identity and the Job/Batch reference to the exact Asset/Image consumed by execution;
- define retry, resume, cache, timeout and partial-transfer recovery semantics before deployment;
- prove that control commands such as status/cancel retain predictable latency while Image transfers are active.

### Loopback Coverage for a Split Image Data Plane

**Status:** TODO / mandatory companion to any future split Image data plane

**Layer:** Diagnostics / Programming data plane

**Reason:** If Programming later uses separate Control and Image data paths, a Control Path Loopback PASS alone no longer proves that the Programming Image route is healthy. Diagnostics must cover every production path that Programming depends on; otherwise Plasma could again report diagnostic PASS while Programming fails on an untested transport boundary.

Required work:

- add an Image Path diagnostic that uses the real production Programming Asset upload/cache API rather than a diagnostic-only upload route;
- verify `Console -> production Image data channel -> PPU Asset Service/Cache` with byte count, content integrity and SHA-256 evidence;
- verify that the uploaded/cached Asset identity is the same `asset_sha256` referenced by the Job or Batch that consumes it;
- preserve production authentication, PPU identity binding, timeout, retry, cache and error behavior during the diagnostic;
- report Control Path and Image Data Path evidence separately so a shallow PASS cannot be presented as complete Programming readiness;
- define complete Programming-path readiness as requiring all production-path evidence that the selected operation depends on.

Architectural invariant:

> If Programming is split into a Control Path and an Image Data Path, diagnostics must cover both production paths. Plasma must never claim complete Programming Route PASS from a Control Path Loopback alone.

## Deferred product capability

### Control Station Product Version / Build Identity Visibility

**Status:** TODO / product traceability follow-up

**Layer:** Control Station / release identity / operator diagnostics

**Reason:** The global header currently shows the canonical Plasma Product Version (for example `v0.2.1`) but does not identify the exact deployed build. Product Version is intentionally stable across ordinary PR merges, so using it alone makes it difficult to distinguish which commit/release is actually running on `plasma-demo`, `z2like-demo`, `plasma.open4th.com`, or an installed Control Station.

Required work:

- keep `release/product.json` as the canonical Product Version source; do not bump Product Version for every merged PR;
- expose the deployed Build/Release identity separately from Product Version, preferably using the existing `<product_version>-<12-char git sha>` release identity where available;
- show a compact short Git SHA or equivalent build identifier in the global header without overloading the Product Version label;
- make the full Product Version, full Git SHA and/or full release identity available through hover/tooltip or an equivalent low-noise detail surface;
- source build identity from immutable release/build metadata rather than a manually maintained UI constant;
- keep development/demo builds explicit when no immutable product release artifact exists;
- add tests proving that Product Version and Build/Release identity remain distinct and that packaged/installed Control Station builds expose the exact build they contain;
- verify the behavior consistently across Render `plasma-demo`, `z2like-demo`, `plasma.open4th.com`, Windows/macOS/Linux Control Station packages, and future production deployments.

Architectural invariant:

> Product Version expresses the released product line; Build/Release identity expresses the exact deployed revision. A PR merge alone must not imply a Product Version bump.

### UI Configuration Profiles — Save / Load

**Status:** TODO / future product capability

**Layer:** Control Station / Settings / configuration management

**Reason:** Plasma Settings will grow beyond one-off browser controls. Operators and engineers need a deterministic way to save a known-good configuration and later restore it without manually re-entering every field. This must be implemented as configuration management, not as an unversioned localStorage dump.

Required work:

- define which settings are profile-owned versus runtime/session-owned, PPU-owned, Manager-owned or security-sensitive;
- provide Settings UI actions to save a named configuration profile and load/activate an existing profile;
- define a versioned profile schema with validation, defaults and forward migration rules;
- preserve configuration ownership boundaries so loading a UI profile cannot bypass Manager routing, backend authorization or PPU-specific constraints;
- exclude secrets and credentials from portable profile data unless a separate approved secure-secret contract exists;
- define profile scope explicitly, including whether a profile is Control-Station-local, user-specific, Facility-specific, PPU-specific or portable;
- provide deterministic import/export only after schema/version/validation semantics are defined;
- show the active profile, unsaved changes and load/save failures clearly in the UI;
- add backend or durable local persistence based on the final ownership decision rather than treating browser localStorage as the canonical store;
- add tests for save/load round-trip, invalid or stale profile rejection, schema migration, partial failure and Managed/Standalone routing invariants.

### Real Provider and Physical IC Quantity Handoff

**Status:** TODO / deferred from the current 1-4 technical-debt sequence

**Layer:** Production execution

**Reason:** Current `Repeat` produces IC quantity semantics only in Mock. Repeating operations against one physically loaded target is not proof that multiple ICs were processed.

Required work:

- implement an approved authenticated real-PPU execution provider;
- introduce explicit operator/MES planned quantity and next-device handoff/acknowledgement;
- bind PASS/FAIL to one physical IC identity or traceable presentation event;
- preserve `PROCESSED IC = PASS + FAIL` and exclude infrastructure ERROR;
- validate sockets, hardware, Z2/FPGA path and real target separately from Mock.

## Resolved presentation debt

### PMode / EMode Design System Convergence

Resolved by the shared Operator UI convergence work completed through PRs #170-#178 and the final repository audit performed after PR #179.

The current design-system boundary is:

```text
same operational concept
    -> shared component / presentation owner

mode-specific operational responsibility
    -> mode-specific information architecture / diagnostics
```

Shared-equivalent surfaces now have explicit common ownership:

- Programming Job uses the same `ProgrammingJobPanel` component in PMode and EMode, with `operator-ui/programming-job-controls.css` as the shared presentation owner;
- first-level Operator Panel Header / Title / Meta / Collapse presentation is owned by shared `operator-ui/operator-panel.css` primitives;
- Batch Summary and PASS / FAIL / YIELD presentation use shared `operator-ui` ownership and semantic theme tokens;
- Engineering Gateway and Mock Settings use the shared Settings UI primitives rather than independent page-local control systems;
- operator density contracts define shared panel, field, checkbox, action and status sizing for equivalent operator surfaces;
- source, browser parity and visual-regression contracts prevent equivalent PMode / EMode presentation ownership from silently splitting again.

The final audit also confirms that the remaining differences are intentional workflow boundaries rather than unresolved convergence debt:

- PMode keeps LED-first Site cards for production/operator visibility;
- EMode keeps the diagnostic Site table for engineering diagnosis;
- EMode Gateway, Facility/PPU targeting, engineering warnings and Site-selection controls remain Engineering-specific because PMode does not expose equivalent diagnostic controls;
- Engineering navigation and page composition remain mode-specific and are not required to mirror the PMode information architecture.

Therefore the convergence target is complete: Plasma has one shared design system for equivalent concepts without forcing PMode and EMode into one layout. Future presentation duplication should be tracked as a new, concrete ownership defect rather than reopening this broad convergence debt.

Relevant guardrails include:

- `software/web/tests/programming-job-control-design-system-contract.test.mjs`;
- `software/web/tests/engineering-programming-css-ownership-contract.test.mjs`;
- `software/web/tests/settings-ui-design-system-contract.test.mjs`;
- `software/web/e2e/tests/operator-panel-header-parity.spec.ts`;
- `software/web/e2e/tests/programming-job-real-stack-parity.spec.ts`.

## Resolved architecture debt

### OpenOCD Control-Plane Qualification

Resolved on main by the ARMv7 QEMU / Browser Runtime qualification sequence culminating in commit `50816ada8450d7a347be02be7c2333e4ef228a7e` and workflow run `38199283003` (Browser Runtime run #120, successful attempt 2).

Closure evidence now proves:

- the production routing chain reaches the real Plasma-owned ARMv7 OpenOCD runtime through Console / BFF / Manager / PPU Gateway / PS Runtime;
- the qualified OpenOCD `0.12.0` runtime is restored from the portable v2 cache and re-verified before use;
- the canonical ARMv7 Z2 PS kit is built and deployed through the managed runtime path;
- the live OpenOCD control plane reports `result=PASS`, `execution_capability=openocd-control-plane-only`, and `hardware_runtime_ready=false`;
- all eight managed Site diagnostics pass through the Browser / Render / SWPC QEMU route;
- direct ARMv7 eight-worker isolation and failed-Site restart evidence passes;
- the live evidence artifact `z2like-demo-browser-runtime-live-50816ada8450d7a347be02be7c2333e4ef228a7e` was uploaded successfully.

This closes the software OpenOCD control-plane milestone only. It does **not** claim physical SWD/JTAG, FPGA/PL transport, target power/reset, target detection, flash programming, physical PYNQ-Z2, or real-IC readiness.

### Dual Manager Lifecycle Ownership / State Drift

Resolved by the fixed read-only SWPC-local maintenance registry plus the post-merge Browser Runtime live qualification on commit `50816ada8450d7a347be02be7c2333e4ef228a7e`, workflow run `38199283003`.

The live acceptance contract fails unless the local maintenance Manager reports:

- `storage=config`;
- `mutable=false`;
- exactly one canonical `z2like-qemu` connection bound to the expected QEMU endpoint;
- `programming_registration_owner=public-production-control-plane`.

The same live run also proved runtime deployment, return to commissioned state, verified pairing while commissioned, and the managed OpenOCD control-plane path without requiring synchronization of a second mutable Programming Registration lifecycle.

Architectural invariant:

> Programming Registration has one authoritative owner in the public production control plane. The SWPC-local maintenance Manager owns only a fixed read-only connection registry and Platform maintenance access.

### Remote Write Authentication and Authorization

Resolved by the security boundary and integration work merged in PRs #167, #168 and #169.

The current security invariant is:

```text
authenticated Principal
    -> permission authorization
    -> Facility / PPU / Site scope authorization
    -> durable Idempotency-Key command identity
    -> auditable command admission
    -> execution
```

The implementation now provides:

- canonical backend Principal, Permission and Facility / PPU / Site Scope authorization;
- Viewer / Operator / Engineer / Admin / Service role bundles while keeping authorization permission-based rather than role-name based;
- high-entropy Bearer authentication using stored SHA-256 token digests rather than persisted plaintext credentials;
- durable SQLite command/audit state with replay protection and idempotent completed-command replay;
- stable `401/E4101`, `403/E4102`, `409/E4103` and `409/E4104` security contracts;
- secure Gateway deployment wiring with owner-only security state/configuration, restrictive process permissions and reversible systemd enable/disable behavior;
- browser transport for Authorization and Idempotency-Key that remains passive on canonical non-secure deployments;
- authenticated `GET /api/security/me` Principal / permission / scope introspection;
- Viewer / Operator / Engineer / Admin expected-profile entry flow with the backend Principal remaining authoritative;
- standalone PPU authorization that does not depend on Plasma Manager availability.

Cloudflare Access / OIDC identity bridging, permission-aware control disabling, credential lifecycle UX and centralized multi-PPU identity management are follow-up rollout work and are tracked separately above; they do not reopen the completed backend remote-write authorization invariant.

See [Remote Write Security Boundary](../architecture/remote-write-security-boundary.md).

### Backend PPU Execution Ownership / Lease

Resolved by the backend execution-ownership contract merged in PR #164.

The physical PPU now enforces:

```text
one PPU -> at most one active execution owner
```

The invariant lives at the Python/backend PPU execution boundary, supports same-owner multi-Site concurrency, exposes `E4010 PPU_BUSY` / HTTP 409 for conflicting owners, preserves ownership until terminal Job state, and is not bypassed by direct REST access. PMode/EMode navigation guards remain UX protection rather than concurrency authority.

See [PPU Execution Ownership](../architecture/ppu-execution-ownership.md).

### Persistent Batch State and Gateway Restart Recovery

Resolved by the durable Batch persistence/reconciliation contract introduced with PR #165.

The current invariant is:

```text
Gateway restart -> recover Batch identity and reconcile durable Job IDs -> no fabricated terminal result
```

The implementation persists immutable Batch input, frozen communication policy, Programming Asset material when needed, execution checkpoints and Job admission state in versioned SQLite storage. Recovery reconciles `submitting` / `accepted` Job IDs against authoritative independent-PPU state, rebuilds Site cursors from the durable Job ledger, handles restart during ABORT idempotently, retries transient recovery observation according to Gateway policy, and retains terminal Batch history for later REST lookup.

The process-coupled Engineering Mock topology cannot preserve an independent PPU Job registry across Gateway restart; non-terminal Mock work therefore becomes an infrastructure recovery ERROR rather than a fabricated manufacturing result.

See [Batch Persistence and Gateway Restart Recovery](../architecture/batch-persistence-recovery.md).

## Resolved maintenance debt

Resolved items belong in Git history rather than staying as open TODOs. In particular, do not reintroduce static test-count reports, superseded duplicate UI specifications, retired Programming Image filenames, or the misleading `gateway_legacy` module name. CI documentation integrity checks protect these boundaries.
