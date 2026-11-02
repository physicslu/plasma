# PPU Job-Driven Package Resolution — Architecture Direction

**Decision recorded:** 2026-11-02 (owner discussion).  
**Status:** Agreed architectural principles; detailed execution contracts and implementation **NOT DECIDED / NOT IMPLEMENTED**.  
**Scope:** PLASMA PPU PS programming resource selection after Bundle v3 delivery. This document does **not** authorize runtime changes, deployment, activation, FPGA/DUT operation, or a new Gate 1.

## Core decision — Bundle = Assets, Controller = actions

**An incoming Bundle represents Assets, not a runnable workflow.** A Bundle
is a transport/inventory grouping of resource Packages and Files. Source code,
Parser implementations, Firmware Images, Programming Profiles, IC metadata,
and other payloads remain **assets/resources** merely by being packaged or
installed. A code-bearing Package is not an instruction to execute that code.

**The Controller owns initiation and sequencing of programming operations.**
In PLASMA's current intended control-plane placement, the SWPC upper-level
Controller (or its approved job/batch orchestration) initiates a Programming
Job with explicit operation intent and Site/PPU context. The Controller,
not the Bundle, controls *whether and when* to Erase / Program / Verify / Read
and any separately defined sequence or cancellation.

**The PPU PS owns resource selection and authorized execution of each admitted
command.** Once the Controller has sent a Job, the PS resolves *only the
necessary available Assets/Packages* for that operation, validates their
compatibility and execution qualifications, and performs the requested action
through the qualified Programming Route. Resolving assets **must not invent
extra operations or an autonomous workflow**; for example, a PROGRAM Job
does not implicitly authorize ERASE or VERIFY.

This is a separation of authority: **Controller → Job intent/sequence;
Bundle → Assets; PPU → resolve Assets and execute admitted Job**. It is a
design decision, not an assertion that a complete hardware runtime exists.

The intent is to keep the programming control plane *Job-driven*:

```text
Resource delivery / availability                   Programming operation
──────────────────────────────────                  ──────────────────────────
SWPC / controlled source                            Controller: ERASE / PROGRAM /
         |                                                VERIFY / READ
         v                                                     |
Bundle v3 / other agreed input mechanism                      v
         |                                         Web / Gateway / PLASMA33
         v                                                     |
B1 Receive → B2 Admission → B3 Install/Verify                  v
         |                                            Z2 PS: Job Admission
         v                                                     |
PPU-owned verified Package/resource inventory <─────── Package/resource resolver
                                                               |
                                                     Operation-specific resources
                                                               |
                                               Parser (if required) / Normalized Image
                                                               |
                                                  Qualified Programming Route
                                                               |
                                             Site Worker → PS backend → PL → DUT
```

The diagram is a **target architecture**, not an assertion that its end-to-end
non-Mock execution is already operational.

## Responsibility boundaries

| Layer / phase | Responsibility | Explicit non-responsibility |
| --- | --- | --- |
| **B1 Receive** | Receive a concrete Bundle/archive and verify transfer integrity | Do not select the programming operation or execute a payload |
| **B2 Admission** | Validate canonical Bundle v3 manifest, files, hashes, target and dependency DAG | Admission does not authorize execution or device programming |
| **B3 Install/Verify** | Make the specifically authorized Package files available and verify installation | Do not automatically invoke Parser, Program, Verify or FPGA operations |
| **Bundle / installed Assets** | Deliver and inventory resource Packages/Files (data or code-bearing assets), with identity/version and provenance | No workflow/action owner; no automatic Parser invocation or PROGRAM trigger |
| **Controller (SWPC orchestration)** | Initiate an explicit operation and, where applicable, sequence of Jobs for selected PPU/Sites | Does not infer execution authority from Bundle content or substitute for PS qualification checks |
| **PPU resource inventory** | Represent available assets, their identities/versions and their reviewed qualifications | Mere presence of an asset does not grant runtime or hardware authority |
| **Programming Job Admission** | Validate a Controller-initiated command, target exact ICPN, selected PPU/Sites and required execution ownership | Do not invent operations or infer unsupported route capability from a Package claim |
| **Job-driven Package/resource resolution (future)** | Find the minimal eligible Assets/Packages *for the Controller-requested Job*, resolve compatible versions and identities, reject missing/conflicting/unsupported resources | Cannot change the Controller's requested operation/sequence; not Bundle admission or installation ordering |
| **Programming Runtime (future integration)** | Parse/normalize only when required, select a qualified Programming Profile/Backend, carry out admitted Site operations, report per-Site results | Must not let user-provided Parser/Package bypass the qualified route or electrical guards |

**Deployment dependency vs. Job requirement are different contracts.**
`packages[].requires` in Bundle v3 defines a *closed installation/ordering
dependency* among Packages in one Bundle. A Job may require a different subset
of already available resources. The latter should be resolved from the
requested operation, target and trusted runtime capability, **not** by
automatically executing every Package present in a Bundle.

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

## Decisions deliberately left open

1. **Resource distribution:** whether firmware data and Parser arrive in one
   Bundle, different Bundles, a Programming Asset transfer, or another
   controlled mechanism. Do not prematurely require redeploying software for
   every firmware update.
2. **Resolver location and inventory:** exact PPU-side component boundary,
   inventory lifecycle, persistent storage/reuse and how already installed
   resources are discovered.
3. **Capability contract:** how a Job expresses needs, how installed Packages
   advertise *reviewed* capabilities, and how the PS chooses compatible
   versions/resources for an exact ICPN and operation.
4. **Parser execution model:** Python, native code, library/plugin or service;
   sandboxing, process lifecycle and whether/how it produces sparse
   address-bearing memory segments for HEX/SREC/ELF.
5. **Activation and updates:** whether a B4-style activation is appropriate
   for a class of Package, when activation is required, and how in-flight
   Jobs are insulated from resource replacement. No answer is implied here.
6. **Qualification and failures:** authorization boundaries, resource/version
   pinning per Job, recovery, missing-resource handling, evidence/Receipt
   format, and actual PS → PL → DUT acceptance.
7. **Concurrency:** eight-Site scheduling and which shared resources need
   PPU-wide serialization vs independent per-Site execution, consistent with
   current ownership and image-leasing invariants.

The ownership model above leaves the exact Controller API, Job/Recipe sequencing
contract and PS resource-resolution mechanism open; the existing E/P/V/R
semantics and real PPU hardware gates remain authoritative.

No new API fields, `kind` strings, Manifest keys, execution permissions, or
wire schemas are established by this architecture note.

## Current evidence and non-goals

- Canonical Bundle v3 uses **Bundle → Packages → Files**, with 1–32 Packages
  and `packages[].requires` for Bundle-internal dependencies.
- PR #1241 Gate 2 was merged at
  [a6e7d4c4fb48d77f173d828db78a57b943ee1208](https://github.com/physicslu/plasma/commit/a6e7d4c4fb48d77f173d828db78a57b943ee1208).
  Its real Z2 PS B1/B2/B3 test installed an **exact reviewed three-Package
  Smoke Bundle**, then **an explicit separate test invocation** ran Python
  smoke as an unprivileged user. This is not arbitrary Parser dispatch.
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
