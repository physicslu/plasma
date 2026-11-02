# PPU Single Active Asset Set — Controller-Driven Programming Architecture

**Decision recorded:** 2026-11-02 (owner discussion).  
**Status:** Owner-approved architecture decision (2026-11-02); implementation, wire/API details and hardware qualification **NOT IMPLEMENTED / NOT VERIFIED**.  
**Scope:** PLASMA PPU PS programming resource selection after Bundle v3 delivery. This document does **not** authorize runtime changes, deployment, activation, FPGA/DUT operation, or a new Gate 1.

## Accepted decision — one Active Asset Set per PPU

**A PPU has exactly one effective Active Asset Set at a time.** This is a
*logical set* of resources, **not** one file or one Package. The set can
contain Firmware Images, Parsers, Programming Profiles, FPGA bitstream/HWH
pairs, IC data and necessary configuration. Bundle v3 is the **Assets
delivery container** (Bundle → Packages → Files), not an executable
workflow. Package presence never triggers a programming action.

**Console/Controller is the authority for Asset Set selection and all
programming actions.** Console specifies the **exact intended Asset Set
identity** for a PPU. That selection binds the intended FPGA Image and
Programming Profile and their exact identities; PPU must not silently
select substitute images/profiles from other Bundles or older versions.
Console separately initiates the E/P/V/R commands, Job/Batches and
their sequencing. PPU resolves only the necessary resources *inside the
single Active Asset Set* to carry out the admitted command.

**PPU is the admission, verification and execution authority**, not the
choice of an alternate set. It verifies exact provenance/digest, target and
ICPN applicability, compatible FPGA ABI/capabilities, resource availability,
Site/PPU ownership and hardware qualification. If validation fails it must
reject the command; no fallback to a different FPGA Image, Profile or
Package version.

**One active set does not mean one physical copy at all times.** During a
controlled update, a separately isolated staging area is required. It is
acceptable to have Active + Staging concurrently; only one may be Active.
A Job may not observe a partially installed/mixed Asset Set. Version and
package dependencies stay internal to the selected Asset Set; there is no
requirement to build a global, cross-Bundle multi-version Package Registry
or allow Jobs to mix assets from several installed sets.

### Console-to-PPU reconciliation

1. Console chooses the required Asset Set and its exact **Asset Set SHA256**
   (or a future equivalently strong canonical identity binding all files,
   package versions and relevant metadata). Name or version alone is NOT
   a sufficient match.
2. Console reads PPU's reported Active Asset Set identity and operational
   readiness. **If SHA256 matches**, no redundant transfer is needed, but
   PPU still validates runtime/FPGA/Profile readiness before a real Job.
3. **If SHA256 differs, is absent, or cannot be trusted**, Console sends
   the selected **complete Asset Set** using the approved transfer contract.
   It does not ask PPU to construct a mix of old Package versions.
4. PPU performs **B1 Receive → B2 Admission → B3 Install/Verify** in an
   isolated staging/install area; failure leaves the existing Active Set
   unchanged and records the real error/recovery state.
5. After verification and when **no active or cancelling Jobs / Site
   hardware users** can observe an inconsistent configuration, a separately
   authorized Asset Set activation makes exactly one verified Set Active.
   Activation must be atomic from the perspective of readers and Jobs:
   never overwrite live files or switch the pointer mid-Job.
6. **Asset activation is not FPGA reconfiguration.** If the FPGA Image
   required by the Active Set is not already loaded and proven compatible,
   Console must authorize a distinct controlled FPGA configuration
   operation. The single PPU Hardware Manager checks Site quiescence,
   all hardware consumers, actual FPGA part, Image/Build ID, ABI,
   capabilities, driver bindings, electrical safe state and recovery
   prerequisites. If these cannot be proven, PPU remains NOT_READY.
7. Controller initiates E/P/V/R only after the PPU reports the selected Set
   **READY**. Every accepted Job pins that Set identity until terminal
   completion. A newly delivered Set may be staged while Jobs exist only
   if independent isolation can be guaranteed; **activation/configuration
   switching is prohibited while Jobs are active**.

These are required **architecture invariants**, not claims of existing B4,
Generic B3, console reconciliation or real hardware functionality. The
exact canonical Set SHA construction, activation API, state persistence and
crash recovery mechanism need subsequent implementation decisions.

### Proposed PPU Asset Set state model

```text
EMPTY -> RECEIVING -> VERIFIED -> ACTIVE -> READY
             |           |         |        |
             v           v         v        v
          ERROR        ERROR     NOT_READY  NOT_READY
```

- **EMPTY**: no verified Active Asset Set is usable.
- **RECEIVING**: new complete Asset Set transfer is in progress; an existing
  Active Set, if present, stays logically separate.
- **VERIFIED**: new staged Set passed B1/B2/B3 and integrity checks, but is
  **not** selected for jobs.
- **ACTIVE**: single selected verified Set is the only job resource universe;
  FPGA may still require separately authorized configuration/validation.
- **READY**: selected Set, exact FPGA Image, Programming Profile, target
  qualification, available hardware and operational ownership satisfy
  admission to begin Jobs. Readiness is rechecked; not inferred solely
  from Asset Set SHA.

This is a **conceptual lifecycle**, not a new executable state machine or
a retrofit of existing Bootstrap B1/B2/B3 receipt states. In practice the
PPU may need to report the *current Active state* and a *pending staged
update* independently rather than replace current READY with RECEIVING.

### Target control flow

```text
Console: selected Asset Set SHA and Controller-owned workflow
            |
            v
  PPU reports Active Set SHA + readiness
            |
       SHA mismatch? ----- no -----> check actual FPGA/Profile READY
            | yes                                |
            v                                    |
   full Bundle v3 Asset Set delivery             |
            |                                    |
      B1 → B2 → B3 to Staging                    |
            |                                    |
  verified → safe single Active Set switch       |
            |                                    |
  separate FPGA configuration if needed          |
            |                                    |
  verify FPGA + Profile + Job readiness <---------+
            |
        Controller starts Job: E/P/V/R
            |
 PPU loads ONLY required resources FROM Active Set
            |
 qualified PS Backend / PL / Site DUT → Job evidence
```

A source Firmware/Parser/FPGA file is an **Asset**, not an instruction to
execute its content. An explicit PROGRAM Job does not implicitly authorize
ERASE or VERIFY. One PPU-wide full FPGA Image and one Active Asset Set are
shared by its Sites; per-Site serial numbers, MAC addresses, calibration or
other unique DUT data remain separate Job-level inputs and do not require
a different Asset Set per device.

### Responsibility boundaries

| Owner / phase | Required role | Forbidden inference |
| --- | --- | --- |
| **Console/Controller** | Select exact Asset Set, compare identity, transfer entire Set on mismatch, explicitly request FPGA configuration if needed, initiate operations and sequencing | Never treat mere transfer as a PROGRAM command |
| **Bundle v3 / Packages** | Carry a complete logical Asset Set with file hashes, typed resources and dependency declarations | Does not own a workflow, activation, FPGA configuration or job execution |
| **B1/B2/B3 on PPU** | Receive, admit and install/verify the authorized incoming Set | B3 does not itself make Set Active, READY or execute Parser |
| **Asset Set manager (future)** | Enforce one Active Set, isolated Staging and safe atomic activation; publish exact identity/state | Cannot overwrite running Jobs or synthesize a hybrid set |
| **PPU Programming Runtime** | Verify the requested Job against Active Set and exact ICPN, select *necessary resources within it* | No independent search for alternate versions/Profiles/FPGA Images across Bundles |
| **FPGA Hardware Manager** | Sole configuration owner; perform explicitly authorized image transition, ABI/capability and safety validation | No implicit FPGA reload inside a SiteWorker or PROGRAM Job |
| **Site workers / backends** | Execute admitted operations and return actual per-Site results | No authority to select/activate a different Asset Set |

The `packages[].requires` graph remains an **internal Bundle install
dependency**, not the Controller's Job sequence or a grant to execute every
Package. The Controller's explicit Set selection determines the resource
universe; the PPU's operation-specific lookup only selects required files
*within that Set*.

## Operation-specific resolution examples (illustrative only)

| SWPC operation | Resource categories the PS may need | Should not be assumed |
| --- | --- | --- |
| **ERASE** | Exact ICPN, Flash geometry, admitted erase profile/backend | Input firmware file or firmware Parser |
| **PROGRAM** | Firmware Image input, applicable Parser/normalizer when necessary, geometry, programming profile and qualified backend | Every installed Package; a Parser always being required for raw binary |
| **VERIFY** | Expected Image or another explicitly supported verification reference, geometry and qualified backend | Mandatory erase or automatic program |
| **READ** | Exact device geometry and permitted memory region, qualified read backend | A firmware input file or Parser |

Examples are architectural guidance, not a finalized Package taxonomy or an
on-wire `Job Requirements` schema. The canonical `R` operation currently means
**Read Entire Main Flash**; do not silently include option, OTP, security or
other special regions.

## Asset vocabulary and normalized execution data

**Bundle-as-Assets is an architectural classification, not a schema rename.**
Canonical wire format stays `plasma.ppu.bundle.v3` with
`Bundle → Packages → Files`. The existing `Programming Asset` REST/domain
object is an individual source-input concept (`image`, `key`, `option`,
`serial_number`, `calibration`). Bundled resource files may be consumed as
Programming Assets through a future explicit mapping, but they do not
automatically become a Programming Asset record, a trusted Parser, a Recipe,
or an executable Job. **Programming Recipe** remains separate control-plane
instructions, not an Asset.

PLASMA already distinguishes:

```text
Programming Asset (source input, identified by Asset SHA256)
          |
          | optional parser / normalizer, chosen by trusted runtime
          v
Normalized Image (actual target-memory data / Image SHA256)
          |
          v
Program / Verify Job at a qualified Site
```

A Parser's purpose is to **transform/validate input data**, not to own the
Programming Job lifecycle, select an unqualified IC profile, control FPGA I/O
or arbitrarily start programming. Different source Assets can produce the same
Normalized Image; preserve the existing PPU-wide normalized Image lease and
single active execution-owner boundaries. Multiple Sites of one authorized
owner may share an appropriate Image without re-uploading it for every Site.

**Existing implementation boundary:** `ProgrammingAsset.normalize_image()`
currently implements only `image + binary`. Intel HEX, S-Record, ELF, and
other inputs require independently implemented and verified normalizers.
Likewise, the current non-Mock Site execution routing still has explicit
hardware-runtime qualification gates. This decision does not declare either
capability complete.

## Implementation decisions still open

**Settled:** single Active Asset Set per PPU; full Set transfer on Console/
PPU identity mismatch; Controller-selected exact Set/Image/Profile; Job
operations initiated by Controller; PPU resolves only assets in that Set;
isolated staging, safe activation and distinct controlled FPGA configuration;
no mid-Job Set change.

**Not settled (requires implementation planning and evidence):**

1. Canonical `asset_set_sha256` input/algorithm versus Bundle ZIP digest,
   immutable Set identity storage and completeness checks. A Manifest-declared
   or user-provided hash alone cannot establish authorization.
2. Console reconciliation and transfer APIs; how a full Set maps to
   canonical Bundle v3 and whether any standalone Programming Asset transport
   is used without compromising the one-Set identity.
3. Atomic Active pointer, staging paths, existing-Job pinning, failure/rollback
   semantics, power-loss/crash recovery and storage cleanup. A fallback
   retained recovery copy is not an additional Active Set.
4. When and how separate Asset Set activation and FPGA configuration are
   requested, coordinated with all Site/driver/PS-PL consumers, without
   automatic reconfiguration during a PROGRAM Job.
5. Parser language/execution and Normalized Image details (including sparse
   HEX/SREC/ELF memory address regions); no arbitrary code entitlement.
6. Exact Programming Profile, FPGA Image, IC qualification and target identity
   binding; end-to-end AuthN/AuthZ, Job receipts and real PS/PL/DUT evidence.
7. Batch/Job concurrency across up to eight Sites and isolation of unique
   Serial Number, MAC, Key or calibration data from shared Set identity.

This note adds **no new on-wire API/schema or executable permission**.
Existing E/P/V/R and Hardware Guard contracts continue to apply.

## Current evidence and non-goals

- Canonical Bundle v3 uses **Bundle → Packages → Files**, with 1–32 Packages
  and `packages[].requires` for Bundle-internal dependencies.
- PR #1241 Gate 2 was merged at
  [a6e7d4c4fb48d77f173d828db78a57b943ee1208](https://github.com/physicslu/plasma/commit/a6e7d4c4fb48d77f173d828db78a57b943ee1208).
  Its real Z2 PS B1/B2/B3 test installed an **exact reviewed three-Package
  Smoke Bundle**, then **an explicit separate test invocation** ran Python
  smoke as an unprivileged user. This is not arbitrary Parser dispatch.
- **Current B3 uses** `/opt/plasma/bundles/<bundle-name>/`, without
  an Active Asset Set pointer or production-ready FPGA Image switching.
  The proposed `assets/active` and `assets/staging` layout is **not built**.
- The B3 real-device Installer's current permission is restricted to the
  reviewed Smoke Bundle; a ZIP with a new firmware Parser is **not**
  automatically authorized for installation or execution.
- Successful data delivery, Package presence or Python Smoke does **not**
  prove that an actual IC has been erased/programmed/verified; independent
  qualification and physical evidence are required.

## Related normative contracts

- [Canonical Bundle v3 schema and installation dependency](ppu-canonical-bundle-packages.md)
- [Engineering Programming Workspace and Programming Asset/Normalized Image model](engineering-programming-workspace.md)
- [Web REST API Programming Job shape](web-rest-api-contract.md)
- [Bundle v3 B3 real PS Install-only evidence](../deployment/ppu-bundle-v3-b3-path2.md)
- [Root autonomous development and approval boundaries](../../AGENTS.md)
