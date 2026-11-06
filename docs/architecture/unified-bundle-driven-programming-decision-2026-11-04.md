# PLASMA — Unified Bundle-driven Programming Execution (Owner Decision)

**Decision date:** 2026-11-04 (owner).  
**Status:** Normative target architecture; **implementation is incomplete**.  
**Scope:** The **IC programming execution flow** only. Existing Engineering Mode
and Production Mode, their unrelated policies, authorities, qualification
workflows, evidence and deployment requirements **remain unchanged**.

## 1. One programming execution path, no mode-specific engine

Engineering and Production use the same:
`Console -> selected Bundle v3 / Active Asset Set -> PPU Runtime -> execution
Provider -> PS/PL/Site -> E/P/V/R/readback/SAFE_OFF`.

Mode-specific **Console policy** can differ (for example, admitting an
experimental versus formally released programming package); accepted Jobs must
not select a different PPU execution pipeline by mode. Console decides whether
to **offer, authorize and deliver** a Bundle and whether to **dispatch** the
Job. Catalog research/ICPN governance, L0/L1/L2 ranking and pre-registered
ICPN lists must not be prerequisites for the actual programming operation.

The PPU is **not** a secondary central qualification authority. It validates
the actual received bytes against the selected authorized Bundle identity,
package dependencies, locally selected compatible Provider/ABI and hardware
state. Only the Console-approved, single Active Asset Set supplies programming
Profiles, Provider code/configuration and FPGA resources for the Job; no
cross-Bundle or source-tree fallback.

**Important:** "Bundle consistency" means digest, schema and dependency
correctness, **not** automatic trust or physical safety. Console authorization
must bind the selected Bundle, PPU, intended Job and allowed resources. The
PPU must still enforce its local protections against tampering, unauthorized
execution, privilege escalation, contested Site ownership, incompatibility,
out-of-range memory access, unverifiable device identity, and unsafe/unknown
electrical state. A Console observation cannot eliminate those race conditions.

## 2. Plugin interoperability is the product contract

OpenOCD, ST STM32F103, the existing ABI-v5 plasma_swd FPGA design and its
C/Python drivers are **first-party reference implementations**, **not**
the PLASMA Core programming model.

Third-party authors may independently provide:
- an FPGA Image and accompanying declarative ABI/capability manifest,
- a compatible PS driver or transport adapter (or a PS-only transport),
- a Programming Provider with a declared operation set and execution entrypoint
  (OpenOCD is optional),
- exact-target application data: geometry, address/erase/program constraints,
  reset/probe requirements, target config and image handling, and
- firmware assets and inter-Package dependencies.

The Plugin contract must be defined in terms of **capabilities and validated
interfaces**, not hardcoded compiler IDs, Image IDs, Git commits, manufacturer
names, OpenOCD versions or specific file paths. The **host platform/physical
interface** may be fixed by the PPU hardware; providers must declare
compatibility with the actual platform and FPGA/Driver ABI.

A Job requesting `flash_cycle` requires a Provider that actually implements
its required steps and returns an independently checkable result. For other
operations, advertise and validate only the operations actually implemented.
The Runtime owns scheduling, leases, bounded operation execution and result
recording; Provider implementation details remain behind the interface.

## 3. Console gate versus PPU last-mile gate

| Check | Console before delivery/dispatch | PPU after receipt/before hardware |
| --- | --- | --- |
| IC Catalog availability / catalog row / L0-L1-L2 level | **Not a programming prerequisite** | **Never** an execution gate |
| Target Programming Profile and Provider presence | Require complete selected Bundle/Job contract | Verify selected Active Set contains usable files and required operation entrypoint; **no built-in ICPN registry needed** |
| Bundle and source authorization | Authorize selected source, PPU and operation before transmission | Verify received payload, authorized identity, hashes, trust boundary and no path/privilege abuse |
| FPGA/Driver/Provider compatibility | Evaluate declarations against known PPU capabilities before selection | Verify **actual** loaded ABI/part/Site capabilities and driver interface at point of use |
| Memory/firmware bounds and image identity | Reject impossible declared requests | Independently check real selected geometry/ranges/hash before writes |
| Site/PPU contention, cancelled jobs or changing hardware | Best-effort reject before dispatch | **Enforce** lease, exclusive Site ownership, no unsafe concurrent OpenOCD or direct hardware consumer |
| Uncertain post-write state / SAFE_OFF | Surface UNKNOWN and require operator recovery policy | Halt, seal/recover as necessary; no automatic repeat or unverified PASS |

A failed package signature/digest or missing runtime safety capability is
not a "Catalog gate": it is mandatory trusted execution/safety enforcement.
A profile whose required operation implementation is absent is **not** a
complete or usable Bundle for that requested Job, even if ZIP hashes match.

## 4. Deployment and runtime resource separation

- **Bundle v3** (Bundle -> Packages -> Files) is the transport/install
  container. Receive (B1), non-executing admission (B2), install/verify (B3)
  and authorized activation remain separate transactions. These are
  **not** steps repeated for every programming Job.
- **Console** chooses exactly one intended Asset Set and checks whether
  the PPU already reports the same trustworthy Active Set identity; only
  transfer the complete Bundle when needed.
- **PPU Runtime** derives one Job route **exclusively** from that Active Set.
  A Bundle with a new IC or FPGA does not need code patches or factory-side
  per-IC/per-Image whitelisting.
- **Runtime/C3** is a generic, constrained hardware-resource/execution
  interface. It must not require OpenOCD, ABI v5, the two-Site Z2 adapter
  or a predefined compiler profile as universal prerequisites.
- **Engineering vs Production:** keep existing differentiated Console
  policies, permissions, evidence and release procedures; use the **same**
  PPU Job and Provider execution mechanics.

## 5. Existing blockers that this decision supersedes (target behavior)

| Existing implementation | Why it impedes valid new Bundle | Required migration |
| --- | --- | --- |
| `plasma_web.gateway` Catalog call in REST Job admission | A non-Microchip or not-yet-catalogued target can fail on unrelated Catalog integrity | Remove Catalog dependency from all programming Job/Batch submission paths; retain Catalog for research/search |
| `plasma_core.ic_support` default repository-owned root | New exact ICPN requires preinstalled repository dataset | Resolve selected Target Profile from the Active Asset Set |
| `plasma_server.execution_router` static `ROUTABLE_PROGRAMMING_PROFILES` and compiler binding | New Provider/Profile requires editing Core | Load validated Provider/operation capability from selected Set |
| `plasma_interfaces.compiler_registry` static STM32 operation-admission projection and backend lock | New Provider cannot qualify dynamically | Bind required operations and selected Backend identity to the authorized Set instead |
| `ppu_fpga_qualification.py` factory `contracts.get(manifest.image_id)` | New independently compiled FPGA can fail solely because its Image ID is unknown | Validate verified Bundle manifest, target and actual FPGA/Driver ABI; retain trusted publisher/owner authorization |
| `ppu_site_adapter_abi5.py` `supported_sites={1,2}`, fixed `plasma_swd` adapter | A third-party FPGA with a different Site count/physical transport cannot be used | Enumerate declared and **hardware-proven** capabilities via a generic Driver/adapter boundary |
| `ppu_site_engine.py` OpenOCD-only engine selection | Non-OpenOCD Provider has no runtime entrypoint | Generic Provider selection, install/verify and bounded process/transport model |
| Runtime per-Site hardcoded C3 socket configuration | Newly installed Provider may be unusable without editing PPU config | Generic Runtime-to-Executor service discovery/admission |

**Do not remove all these checks in one patch.** Replace static product and
registry gates with equivalent **Bundle-bound**, trusted runtime checks
incrementally, with negative tests and no fail-open transition. Legacy
OpenOCD/ABI-v5 reference implementation must continue to work.

## 6. Required acceptance evidence

1. **Catalog independence:** disable or remove the entire Device Catalog
   data tree in Host-only testing; a valid ST/Microchip/third-party Job with
   an executable, authorized Profile/Provider from the selected Set is
   still admitted. A malformed or missing Provider is rejected based on
   its **own** contract, not a Catalog lookup.
2. **New IC from a Bundle:** a PPU without an existing IC Support/Compiler
   registration can deploy a valid selected Bundle and execute its
   authorized Job after real hardware compatibility checks.
3. **Alternative provider:** a third-party FPGA+driver+SPI provider executes
   the same Job API without OpenOCD or changes to Core; an optional PS-only
   provider proves FPGA is not universally mandatory.
4. **Safety:** invalid package hash, unsupported ABI, size/geometry mismatch,
   occupied Site, changing FPGA identity, unauthorized resources and unknown
   SAFE_OFF each fail closed with a distinct reason.
5. **Physical HIL:** on a safely controlled Site, the OpenOCD reference
   Bundle completes a real `flash_cycle` with exact readback, safe-off and
   separate firmware/CDC observation.

These are future acceptance criteria; no completed feature or HIL PASS is
implied by this decision alone.

## 7. Immediate Gate 1 versus later migration

**Immediate unblock:** remove Device Catalog as a REST Job execution
dependency (candidate PR #1297). Complete Host-only regression and CI, then
separately authorize a source-pinned deployment and a **single** REST Site 2
HIL attempt, with Job reconciliation rather than retry when uncertain.
Path 2 CLI/receipt tracking lives in PR #1296. Do not treat either PR's CI
as physical programming evidence.

**Later architecture work:** resolve Active-Set Profile/Provider/Image
dynamically, standardize Plugin APIs and capability negotiation, then
deprecate factory per-Image/per-Compiler allowlists. Preserve existing
Engineering/Production policy boundaries; do not conflate policy-mode
unification with this **execution-flow-only** decision.
