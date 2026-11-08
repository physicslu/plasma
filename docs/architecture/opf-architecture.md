# PLASMA OPF — Open Provider Framework architecture

**Status (2026-11-08):** Host-independent OPF boundary approved in merged #1348; Linux standalone Python fake Provider implemented/Host-only tested in merged #1349. PPU S1-C cutover is an unmerged #1347 Draft candidate; no new-path HIL or Gate 2 approval. The historical OPF-1 through OPF-5 plan was PPU-integrated and did not itself establish portability.
**Governance:** [Core convergence / deletion-first roadmap (PR #1343)](plasma-core-convergence-and-deletion-first-roadmap.md). The [2026-11-04 Bundle-driven Programming Decision (PR #1298)](unified-bundle-driven-programming-decision-2026-11-04.md) continues to govern **PLASMA PPU product execution**, not every independent use of OPF.
**Scope:** Define the common programming contract and distinguish it from each Host's packaging, authorization and hardware controls. Engineering and Production still share **one PPU execution pipeline** after Console policy admission. No existing privileged guard is changed by this document.

## Target architecture: portable contract, no mandatory PPU dependency

```text
Standalone application / CLI OR PLASMA Manager / Runtime
        | programming request (target, operation, image, options)
        v
OPF Core contract: Provider capability / operation / result
        | selects a compatible Provider implementation
        v
Provider: OpenOCD / vendor CLI / Python / Native C / fake test Provider
        |
        +--> Provider's existing transport (e.g. OpenOCD ST-LINK USB driver)
        |
        +--> Host-provided capability/transport (when needed)
               PC Host: local USB / SWD / process permissions
               PPU Host: Z2 PS -> bounded C-3 / WordPort -> optional PL -> DUT
        v
Target IC (or fake Host-only target for contract tests)

Separate deployment plane: Bundle v3 -> install/verify/activate -> selected
Provider/Profile/Firmware for a PLASMA PPU Host. This is NOT OPF Core.
```

**OPF Core is a programming library/contract, not a second executable Engine.** It describes operation requests, capability negotiation, Provider-specific validated options, evidence-bearing outcomes and failure/UNKNOWN semantics. It must not import PPU Runtime, PPU Job/Lease/Site, C-3, FPGA ABI, Bundle v3 or OpenOCD as prerequisites for basic Provider execution. A Provider may understand IC protocol/geometry, while platform-specific resource controls are owned by the Host. Avoid a universal new Router, Runner, Executor or lock when an existing component already fulfills the responsibility.

**Provider vs transport:** A Provider implements programming behavior. A Host capability/transport adapter is needed only when the Provider cannot already use its own transport. An OpenOCD+ST-LINK Provider uses OpenOCD's existing ST-LINK USB support; do not add a redundant ST-LINK protocol adapter. A vendor CLI may manage its own device access. A Z2 FPGA SWD Provider may use existing authorized C-3/PS-local WordPort/PL integration. Do not require all Providers to implement one low-level SWD or USB interface.

**OPF independence is functional, not an assertion that every executable is portable.** Each Host must meet toolchain, OS/architecture, USB/device permissions, capabilities and safety policies. The OPF public contract may run on a PC without PPU or Bundle v3, but the present PLASMA product route is still subject to its stronger PPU admission rules.

**Trust and outcome ownership:** OPF must not treat process exit code 0, successful Probe, Bundle SHA256, or Provider self-report alone as qualified Flash PASS. Evidence for actual Erase/Program/Verify/Readback and hardware-safe completion is distinct. Host identity, privilege, Site arbitration, cancellation, deadline, fencing and recovery remain Host/platform responsibilities. The OPF contract must be able to convey an unqualified/UNKNOWN result without manufacturing a PASS.

### Example Host compositions (integration targets, not claims of completed support)

| Host | Provider | Hardware path | Extra requirements |
| --- | --- | --- | --- |
| PC Linux/macOS/Windows | Python fake | subprocess / simulated transport | **First Host-only acceptance target**, no Bundle, PPU or C-3 |
| PC with ST-LINK | Existing OpenOCD | OpenOCD ST-LINK USB backend -> SWD -> MCU | USB access and compatible OpenOCD; **real HIL not qualified here** |
| PYNQ-Z2 PS-only | Compatible vendor/Python/Native Provider | Z2 Linux -> qualified USB/UART/other PS transport -> MCU | PPU Host authorization, device access and resource isolation |
| PYNQ-Z2 PS+PL | OpenOCD Reference Provider | Z2 PS-local OpenOCD -> WordPort/C-3 -> AXI -> FPGA SWD IP -> DUT | PPU Site Session/Lease/FPGA identity/SAFE_OFF; historical Site 2 reference evidence |

### PPU-specific integration (preserve current product boundary)

```text
SWPC Console / Manager (policy, Bundle and Job authorization)
  -> authorized PPU Job + verified, single Bundle v3 Active Asset Set
  -> PPU Runtime / Gateway (Job, Owner, Site/Lease/Deadline/SAFE_OFF)
  -> OPF selection / Provider execution boundary
  -> qualified PPU Host transport:
       Z2 PS-local OpenOCD / C-3 / WordPort -> optional PL SWD/SPI IP -> DUT
       OR PS-only qualified USB/UART etc. -------------------------> DUT
```

- **Bundle v3 is an independent deployment product.** For today's **PPU-managed Job**, the Provider, Profile, Driver, firmware and applicable FPGA Image are selected from its authorized, verified single Active Asset Set; no unverified cross-Bundle or source-tree fallback. That product policy **must not become a universal OPF dependency**. A PC may obtain a Provider through its own installed tools.
- **Host-owned authority:** PPU validates actual target identity, flash ranges, FPGA/Driver compatibility, Site ownership, permitted operations, electrical condition, privilege and uncertain-outcome recovery at the point of use. Generic OPF must not grant itself these rights.
- **Site policy is PPU-specific:** independent Site sessions, stale-worker fencing, PPU-wide FPGA reload guard and the current same-MCU/firmware concurrency policy remain in PPU integration. Do not impose them on independent PC OPF clients.
- **Physical Z2 reference boundary stays unchanged:** SWPC serves Web/Controller/BFF; Z2 PS runs live OpenOCD/WordPort; Z2 PL handles SWD/SPI I/O. No live per-bit SWD transport across Ethernet.
- **No security bypass via decoupling:** Python/Native Providers with direct `/dev/mem`, USB, SPI or MMIO access must not bypass Host-owned protection. Host-only mocks do not prove OS or hardware sandboxing.

## Minimal OPF programming selection (v1 proposal)

The JSON example below documents the **existing PLASMA PPU Bundle-bound selection**, not a universal OPF installation or discovery requirement. This is a data descriptor carried by an authorized Bundle Package, not new fields on the strict root Bundle v3 manifest. The current C-3 Flash route resolves it from the Active Asset Set; its names are Package IDs in that Set, not filesystem paths. A standalone Host may bind equivalent abstract Provider/Profile references without any Bundle.

```json
{
  "schema": "plasma.opf.programming.v1",
  "provider": "reference-provider",
  "profile": "target-profile",
  "timeout_ms": 1200000,
  "options": {"speed_khz": 2000}
}
```

**Only three universal programming selections:** `provider`, `profile`, and optional `timeout_ms`. `schema` identifies the contract version; `options` is an opaque Provider-specific JSON object, not a set of PPU Core knobs. The Provider declares a separate, versioned schema for its options and validates it **before** any hardware operation. Core must never interpret arbitrary Provider options as a waiver of a safety gate.

For the current C-3 `POST /api/jobs` `flash_cycle` route, the REST body accepts
`provider` and `profile` as Package IDs from the single Active Asset Set. Both
must be supplied together. A Job without them is accepted only when the Set
contains exactly one Programming Profile. Runtime checks the selected Profile's
Target and declared Provider before any Site Worker admission; the existing
hardware and SAFE_OFF checks still apply.

### PPU Job deadline integration (not a mandatory OPF-wide PPU timeout policy)

- PPU supplies `default_timeout_ms` and an independently enforced local **safety ceiling**. The Bundle provides only optional `timeout_ms` (positive integer, milliseconds). Missing override means PPU default.
- If override is present and valid, use it; if it exceeds the PPU ceiling, **reject** the Job rather than silently clamp it. No operation-specific, erase, verify, heartbeat or lease timeout parameters are introduced into the Bundle contract.
- The effective timeout is a single monotonic-clock Job deadline covering normal Probe/Erase/Program/Verify/Readback work. Any pending SAFE_OFF/recovery obligations survive deadline expiry; time expiry never proves the DUT safe.
- Record source (`ppu_default` / `bundle_override`), effective timeout, start/deadline and observed elapsed duration in future execution evidence. This PR only validates the selection; it does not implement execution-time enforcement.

## PPU-only Site Session Manager

This section specifies PPU Host authority and safety invariants, **not** OPF Core fields or mandatory interfaces for PC clients.

- Consolidate **Ownership / Lease / Lock** behind one atomic Site Session grant and one fencing generation/token. This is a *target state*, not a claim that today’s runtime has already been migrated.
- AVAILABLE → ACTIVE after resource admission. On normal completion, release only after verified safe termination. Timeout or cancellation triggers bounded cleanup and SAFE_OFF/owner verification; proven safe failures return to PPU Job policy. A stale owner or unverifiable SAFE_OFF denies new hardware admission and enters RECOVERY / SEALED as appropriate.
- `site<N>.sealed` is persistent safety evidence, not an expiring lease. It must not be deleted or ignored merely because the single Job deadline elapsed. Recovery uses the existing authorized operator procedure and independently verifies SAFE_OFF.
- PPU-wide image/reload guard remains separate in **scope**, but belongs to the same Resource/Safety authority; do not hand FPGA configuration authority to a Provider.

## Original OPF-1 through OPF-5 migration plan — historical PPU integration scope

This is the original PPU-integrated migration breakdown, retained for traceability. Several implementation PRs have since merged, but their CI and reference HIL evidence do **not** prove host-independent OPF. The [current S0–S5 roadmap](plasma-core-convergence-and-deletion-first-roadmap.md) is the authoritative forward backlog for decoupling, reconciliation and deletion-first work.

| Phase | Deliverable | Hardware / operational impact |
| --- | --- | --- |
| **OPF-1 (this PR)** | Normative OPF design, standalone programming-selection validator and host-only negative tests | None; no Runtime route change |
| OPF-2 | Provider capability descriptor, registry/discovery from one verified Active Set, Provider-specific options-schema validation, two host-only test Providers | Host-only, no DUT |
| OPF-3 | Single Site Session Manager contract/integration and one bounded Job deadline; preserve existing SAFE_OFF, SEALED, Recovery and PPU reload guard | Host-only simulation first; isolate from current Site 2 HIL |
| OPF-4 | Wrap existing OpenOCD/ABI-v5 as a Reference Provider; route execution via verified selected Provider/Profile/Driver rather than static registries | Requires staged integration and later HIL |
| OPF-5 | Remove superseded static programming gates, prove non-OpenOCD/PS-only alternative and run real authorized Site HIL / regression | Explicitly bounded hardware acceptance |

OPF phases must not revive legacy compatibility layers or create a separate execution pipeline. Their boundaries can be adjusted as actual code reveals cross-layer dependencies. Upstream Catalog research and qualification remain available but are not PPU programming admission prerequisites.

## Original OPF-1 acceptance / limitations (historical)

1. A minimal parser rejects absent/unknown schema, missing Provider/Profile references, unsupported fields, illegal Timeout, non-JSON `options`, and overrides beyond PPU policy.
2. It accepts a valid Bundle override or uses the PPU default when absent; accepts arbitrary *names* without built-in OpenOCD or brand allowlists.
3. No Provider code runs; no Profile is loaded, no Plugin sandbox/authorization is qualified, no Bundle v3 manifest/schema is modified, no Site Session Manager is replaced.
4. Focused host-only tests and PR CI are required. Mock PASS is not Z2/FPGA/DUT/HIL evidence.
5. Do not modify PR #1299, touch the Z2 installed release, clear `site2.sealed`, perform Flash POST, reload FPGA, merge this PR or change deployment.

## 2026-11-08 current evidence and next acceptance milestones

- **Merged foundation:** Provider selection, capability/options validation, C-3 Session integration and OpenOCD Reference Provider have landed through PRs #1301/#1302/#1303/#1306/#1307/#1311/#1316, with later PPU integration fixes. The historical Site 2 STM32F103C8T6 real Flash PASS is recorded in PR #1338; it is not evidence of portable OPF or all eight Sites.
- **S1-C Draft candidate:** PR [#1347](https://github.com/physicslu/plasma/pull/1347) migrates the original S1-01 additive bridge into per-Job PPU Host selection, removes Runtime `CompilerRegistry`/legacy routes, and retains the single SiteWorker, C-2/C-3 and Site safety. Production LOC delta versus latest baseline is +403/-361 (net +42), with no qualified non-OpenOCD physical programming outcome. Gate 2 and exact-HEAD CI are still required; isolated process success and mocked C-3 Probe never imply Flash PASS.
- **Host-independent evidence:** Merged [#1349](https://github.com/physicslu/plasma/pull/1349) established Linux Host-only Python fake Provider positive/negative tests without PPU Runtime, Bundle v3, C-3, FPGA, OpenOCD, Owner HMAC or PPU Lease. It does not establish macOS/PC ST-LINK hardware or real physical Flash qualification.
- **Next integration milestone:** Run the same OPF operation/result contract via the existing OpenOCD Reference Provider and a bounded Z2 Host Integration. Preserve all local Site/FPGA/SAFE_OFF/Recovery gates. For ST-LINK, use OpenOCD's built-in backend rather than implement duplicate USB protocol handling; a physical ST-LINK PASS requires separate evidence and authorization.
- **Deletion milestone:** S1-C #1347 removes the obsolete *Runtime* compiler routes while keeping offline Plan Compiler, Flash Geometry and ICPN qualification. Verify exact-HEAD tests, negative paths, route counts and hardware safety before Gate 2; do not equate a Host-only test with a physical HIL PASS.

**Approval scope:** This architecture update is documentation only. It does not rewrite the normative 2026-11-04 PPU Bundle flow or authorize code changes, merge, Z2 deployment, FPGA actions or DUT access. A changed executable boundary needs a separately bounded Gate 1, and each merge needs Gate 2.
