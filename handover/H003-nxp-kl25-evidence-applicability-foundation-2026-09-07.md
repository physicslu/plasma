# H003 — NXP KL25 Evidence Discovery & Applicability Binding Foundation

**Date:** 2026-09-07  
**Project:** Plasma Universal Multi-Site IC Programmer  
**Repository:** `physicslu/plasma`  
**Current main at handover creation:** `a43300b04a08ef3ed4a77400c0bef4676edf5198`  
**Active branch:** `agent/ic-evidence-nxp-kl25-discovery`  
**PR:** `#395` — `IC Support: add NXP KL25 deterministic evidence discovery`  
**Implementation head captured before H003 commit:** `4ed830208fbf8c9af5cc270705d1d96ba5637ef2`  
**PR state at handover creation:** open / draft / mergeable / not merged  
**Evidence Unit definitions:** REVIEWED, NOT ADMITTED CATALOG  
**Scope bridge admission:** NO  
**Applicability Binding admission:** NO  
**Evidence Pack admission:** NO  
**Semantic extraction admission:** NO  
**Canonical dataset admission:** NO  
**HIL admission:** NO  
**Production admission:** NO  
**Destructive security-operation admission:** NO

## 1. Purpose

This handover transfers the current state of the NXP KL25 cross-vendor IC-evidence workstream to another engineering session.

The work has progressed from source locking and deterministic discovery through reviewed Evidence Unit definitions and into the Applicability Binding foundation. The immediate problem is no longer finding programming-related pages. The immediate problem is proving, with manufacturer evidence and deterministic rules, that the reviewed KL25 Evidence Units apply to the commercial target `MKL25Z128VLK4`.

The current authority order remains:

```text
Manufacturer Evidence
    > Validated Canonical Spec
    > Generated Implementation
    > AI opinion
```

Do not promote navigational keyword hits, a shared Reference Manual, a family header, or an AI inference into target applicability without an evidence-backed scope bridge.

## 2. Relationship to H001 and H002

H001 is the IC Evidence / semantic extraction / deterministic canonicalization foundation.

H002 is an independent Render / Cloudflare / SWPC managed-PS qualification workstream.

H003 continues the H001 IC-evidence line and must not be conflated with H002 runtime/deployment work.

The current NXP KL25 work is a deliberate cross-vendor stress test of the architecture proven earlier on STM32F103C.

## 3. Plasma system context

Plasma is a universal multi-Site IC programming system:

```text
Plasma System
└── Facility
    └── PPU
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

Product direction:

- embedded Linux PS is the programmer main controller;
- FPGA PL provides timing-sensitive/custom programming peripherals;
- one programmer targets up to 8 simultaneous programming Sites;
- the host UI communicates with the programmer over Ethernet;
- long-term IC support must scale through reusable evidence/spec/profile infrastructure instead of one bespoke implementation per commercial PN.

This H003 work is research/engineering evidence infrastructure only. It does not admit real target programming, FPGA behavior, HIL, production, or destructive security operations.

## 4. Repository operating contract

`AGENTS.md` remains authoritative and defines the two-gate workflow:

```text
Request
  -> minimal read-only inspection
  -> Gate 1: Plan Approval
  -> autonomous implementation / validation / commit / PR / CI repair
  -> Gate 2: Merge Approval
  -> merge
```

There is no third approval gate.

Important rules:

- CI success is not HIL or production evidence.
- Hardware/runtime/deployment/destructive Git/security changes must be explicitly within approved scope.
- Do not merge PR #395 without Gate 2 approval.
- If this handover conflicts with newer executable code, tests, contracts, or `AGENTS.md`, the newer repository state wins.

## 5. Current repository / PR state

At H003 creation:

```text
main = a43300b04a08ef3ed4a77400c0bef4676edf5198
```

That main commit merged H002 via PR #397 and is independent of the KL25 branch.

KL25 branch:

```text
agent/ic-evidence-nxp-kl25-discovery
```

Implementation head before the H003 documentation commit:

```text
4ed830208fbf8c9af5cc270705d1d96ba5637ef2
```

PR #395 state before H003 commit:

```text
open       = true
draft      = true
mergeable  = true
merged     = false
```

PR #395 was originally branched before newer main changes. Do not casually merge/rebase/reset solely to make histories look aligned. Inspect actual divergence before any history-changing operation.

Latest CI observed on implementation head `4ed8302...`:

```text
Repository contracts : PASS
IC Support validation : PASS
```

## 6. NXP KL25 target and retained source lock

Commercial target:

```text
MKL25Z128VLK4
```

Source-lock ID:

```text
nxp-kl25-source-lock-v0
```

### 6.1 Data Sheet

```text
source_id       = nxp_kl25_ds_rev5
document_number = KL25P80M48SF0
revision        = 5
document_role   = datasheet
local_filename  = KL25P80M48SF0.pdf
sha256          = e42271b7f612ac1b0812001e62bef10d217be4a61dbee5bb0a1e5c4076209a3b
bytes           = 1280088
```

### 6.2 Reference Manual

```text
source_id       = nxp_kl25_rm_rev3
document_number = KL25P80M48SF0RM
revision        = 3
document_role   = reference_manual_programming_authority
local_filename  = KL25P80M48SF0RM.pdf
sha256          = 7911a7d9f8192fa317960feabc9377d0fd81a9b90d31f8070cae9612cb237241
bytes           = 6637765
pages           = 807 by pdfinfo / retained evidence
```

Local SWPC source directory:

```text
/storage/projects/plasma-benchmark/nxp-kl25/source
```

Important provenance principle:

```text
manufacturer document authority
    != acquisition location
```

The retained RM bytes were acquired from an NXP Community attachment after the presumed direct NXP RM URL returned an invalid 10-byte artifact in the user environment. Do not falsely state that the retained bytes were fetched successfully from the presumed direct RM URL.

## 7. Source-lock fail-closed hardening already completed

An earlier bad RM acquisition produced only 10 bytes, yet the old capture path could hash it and report completion.

That fail-open behavior was corrected. Current sanity guard includes:

```text
MIN_PDF_BYTES = 1024
```

A candidate source must:

- exist as a file;
- be at least the minimum plausible size;
- begin with `%PDF-`;
- pass exact byte-length and SHA-256 checks when used by deterministic discovery/construction tools.

Core lesson:

```text
URL looks correct
    != HTTP request succeeded
    != downloaded real PDF
    != document identity locked
```

SHA/size lock exact bytes, but semantic identity/revision still depends on manufacturer evidence and document metadata.

## 8. Cross-vendor research question

The NXP KL25 pilot exists to test whether Plasma contains hidden STM32 assumptions.

The central question is:

> Can Plasma preserve NXP's command-engine programming model as manufacturer-near evidence without projecting STM32 KEYR / FLASH_CR / PER / MER / PG semantics into NXP?

Expected NXP-native concepts, when supported by evidence, include:

```text
FTFA
FCCOB
FSTAT
Program Longword
Erase Flash Sector
Erase All Blocks
FSEC
SWD
MDM-AP
```

Do not force these into STM32-specific register/operation names.

## 9. Deterministic preprocessing

Pinned transform:

```text
pdftotext -layout -enc UTF-8
```

The discovery path preserves form-feed physical-page boundaries, normalizes text deterministically, and verifies locked PDF byte length / SHA before operating.

Separation of artifacts:

```text
Source Lock
  -> exact source bytes

Preprocessing contract
  -> deterministic source transform

Candidate discovery
  -> navigation candidates

Reviewed candidate boundary
  -> human-reviewed construction search ranges

Evidence Unit definitions
  -> logical manufacturer-section definitions

Applicability evidence
  -> candidate scope bridge evidence

Evidence Pack
  -> NOT YET ADMITTED
```

Keyword discovery is navigation evidence, not semantic authority.

## 10. Discovery evolution — first major heuristic failure

Initial deterministic discovery produced:

```text
candidates 864
DEVICE_IDENTITY 864
ORDERING 31
MEMORY_GEOMETRY 45
FLASH_COMMAND_ENGINE 53
PROGRAMMING_SEQUENCE 13
COMMAND_STATUS 27
DEBUG_PROGRAMMING_INTERFACE 30
SECURITY 18
CONFIGURATION 2
```

The `DEVICE_IDENTITY=864` result was wrong. Generic repeated `Kinetis KL25` / `KL25 Sub-Family` headers contaminated nearly every page.

This established an important invariant:

```text
deterministic
    != automatically correct
```

A deterministic heuristic can reproduce the same wrong answer perfectly.

Identity policy was tightened so generic family headers cannot establish commercial target identity.

## 11. Discovery v2 after identity correction

Second discovery run:

```text
candidates 129
DEVICE_IDENTITY 9
ORDERING 31
MEMORY_GEOMETRY 45
FLASH_COMMAND_ENGINE 53
PROGRAMMING_SEQUENCE 13
COMMAND_STATUS 27
DEBUG_PROGRAMMING_INTERFACE 30
SECURITY 18
CONFIGURATION 28
```

The result was sufficiently concentrated to review by page clusters rather than treating all hits as Evidence Units.

Two dominant RM clusters emerged:

```text
RM 419-456  -> Flash programming core candidate boundary
RM 149-157  -> Debug / security recovery candidate boundary
```

Scattered isolated hits outside these regions remain navigation/cross-reference noise unless separately reviewed.

## 12. Reviewed candidate boundaries

Retained reviewed construction inputs:

```text
flash_programming_core_candidate
  source = nxp_kl25_rm_rev3
  pages  = 419-456

debug_security_recovery_candidate
  source = nxp_kl25_rm_rev3
  pages  = 149-157
```

These ranges are not themselves Evidence Packs and are not automatically Evidence Units.

A 38-page search boundary is not a semantic unit.

## 13. Heading-aware Evidence Unit construction

The branch contains heading-aware construction tooling that:

- operates only inside reviewed candidate boundaries;
- re-verifies locked source bytes;
- records per-page normalized-text SHA-256 values;
- extracts heading candidates;
- preserves category hits;
- does not admit an Evidence Unit Catalog automatically.

Observed heading structure was sufficiently clear to create reviewed logical unit definitions.

## 14. Reviewed Evidence Unit definitions

Eight reviewed unit definitions currently exist:

| Unit | RM pages | Role |
|---|---:|---|
| `nxp-kl25-ftfa-register-model-v0` | 422-431 | `FLASH_COMMAND_ENGINE` |
| `nxp-kl25-ftfa-command-sequencing-v0` | 435-439 | `PROGRAMMING_SEQUENCE` |
| `nxp-kl25-program-longword-v0` | 444-445 | `PROGRAM_COMMAND` |
| `nxp-kl25-erase-sector-v0` | 446-448 | `ERASE_COMMAND` |
| `nxp-kl25-erase-all-blocks-v0` | 451-452 | `ERASE_COMMAND` |
| `nxp-kl25-flash-security-v0` | 454-455 | `PROTECTION_SECURITY` |
| `nxp-kl25-debug-security-interaction-v0` | 149-150 | `PROTECTION_SECURITY` |
| `nxp-kl25-swd-mdm-ap-v0` | 151-157 | `DEBUG_PROGRAMMING_INTERFACE` |

Status:

```text
reviewed_definitions_not_admitted_catalog
```

The definitions are engineering-reviewed logical boundaries, not an admitted Evidence Unit Catalog.

## 15. Heading extraction artifact and normalization rule

`pdftotext -layout` exposed numbering such as:

```text
27.33.1
27.33.2
...
27.33.5
```

The enclosing document hierarchy establishes these as section `27.3.3.x`, for example:

```text
27.3.3.5 Flash Common Command Object Registers
```

The branch records this explicitly as extraction normalization.

Rules:

- `CAUTION` is not a unit boundary;
- bit-name-only headings are not unit boundaries;
- `27.33.x` must not be silently treated as manufacturer section identity;
- normalization to `27.3.3.x` is allowed only because the enclosing section context establishes that hierarchy.

## 16. Applicability Binding foundation — why it exists

Finding and reviewing programming sections is not enough.

Plasma must prove:

```text
commercial target
  -> manufacturer document/device scope
  -> relevant family scope
  -> relevant module/interface presence
  -> reviewed Evidence Unit scope
  -> Applicability Binding
```

A shared Reference Manual does not prove every section applies to every orderable part described by that manual.

Absence of an exclusion cannot be inferred from keyword search.

Unknown applicability fails closed.

## 17. Applicability v0 — second ontology failure

The first applicability contract assumed an intermediate manufacturer expression:

```text
MKL25Z128VLK4
  -> MKL25Z128
  -> KL25 family
```

The first applicability run returned:

```text
TARGET_EXACT_IDENTITY    = 1
TARGET_DEVICE_EXPRESSION = 0
KL25_FAMILY_SCOPE        = 864
```

Two problems were exposed:

1. The locked documents did not directly support the assumed intermediate identity `MKL25Z128` under the exact-token rule.
2. Repeated `KL25 Sub-Family` page headers polluted the entire RM and therefore were not useful applicability evidence.

Do not patch either problem by fuzzy matching or inventing an identity layer.

## 18. Applicability v1 ontology correction

The current scope bridge no longer requires `MKL25Z128`.

Current conceptual bridge:

```text
exact MKL25Z128VLK4 manufacturer identity
  -> exact target membership in the locked KL25 Reference Manual
  -> explicit KL25 family/document section anchors
  -> section-bounded FTFA / SWD / MDM-AP / security presence
  -> reviewed Evidence Unit scope
  -> Applicability Binding
```

`TARGET_DEVICE_EXPRESSION` remains an optional observation with the policy:

```text
DO_NOT_INFER_OR_SYNTHESIZE
```

This is a cross-vendor architecture decision: different vendors may expose different numbers of explicit identity hierarchy levels. Plasma must not fabricate missing levels merely to force a uniform ontology shape.

## 19. Anchor-based applicability discovery

Applicability v1 rejects document-wide family-header matching and uses bounded anchors.

Examples:

```text
TARGET_EXACT_IDENTITY
  -> exact MKL25Z128VLK4 token
  -> DS + RM

RM_TARGET_MEMBERSHIP
  -> exact MKL25Z128VLK4 token
  -> RM only

KL25_FAMILY_SCOPE
  -> explicit RM section anchors around 2.3 / 2.5

FTFA_MODULE_PRESENCE
  -> bounded KL25 Flash configuration + Chapter 27 regions

SWD_DEBUG_PRESENCE
  -> bounded core/debug/security regions

MDM_AP_PRESENCE
  -> bounded Chapter 9 debug region

FLASH_SECURITY_MODEL
  -> bounded Chapter 8 + Chapter 27 security regions
```

Repeated page headers are not applicability evidence.

## 20. Latest SWPC applicability v1 observation

The latest SWPC summary observed immediately before this handover is:

```text
TARGET_EXACT_IDENTITY      7
TARGET_DEVICE_EXPRESSION   0
RM_TARGET_MEMBERSHIP       6
KL25_FAMILY_SCOPE          2
FTFA_MODULE_PRESENCE      34
SWD_DEBUG_PRESENCE        12
MDM_AP_PRESENCE            5
FLASH_SECURITY_MODEL      13
```

This is a healthy shape compared with v0 because applicability evidence is now concentrated rather than document-wide.

Important: this latest summary was transferred from the SWPC to the previous chat session and is an engineering observation. It is not itself retained repo authority. The deterministic JSON run should be regenerated/reviewed in the next session before retaining reviewed applicability claims.

### 20.1 Exact target evidence observed

`TARGET_EXACT_IDENTITY` was observed in:

```text
DS page 2
RM pages 1, 44, 73, 76, 79, 103
```

`RM_TARGET_MEMBERSHIP` observed exact `MKL25Z128VLK4` on six RM pages, including manufacturer sections such as:

```text
RM page 44  -> 2.5 Orderable part numbers
RM page 73  -> 3.6.1.2 Flash Memory Map / 3.6.1.3 Flash Security
RM page 76  -> SRAM size table
RM page 79  -> device instantiation table
RM page 103 -> device instantiation table
```

This direct RM target membership is more defensible than inventing a missing `MKL25Z128` layer.

### 20.2 Family scope anchors observed

```text
RM page 38 -> 2.3 KL25 Sub-Family Introduction
RM page 44 -> 2.5 Orderable part numbers
```

The old 864-page family-header contamination is gone.

### 20.3 FTFA presence observed

FTFA evidence is concentrated in:

```text
RM page 74
RM pages 419-437
RM page 439
RM pages 441-443
RM pages 445-447
RM page 449
RM pages 451-456
```

This aligns with the previously reviewed programming-core boundary.

### 20.4 SWD / MDM-AP presence observed

SWD evidence is concentrated in:

```text
DS pages 20-21
RM pages 40, 49-51, 149-152, 154-155
```

MDM-AP evidence is concentrated in:

```text
RM pages 152-156
```

This aligns with the reviewed debug/security boundary.

### 20.5 Flash security model observed

Security evidence is concentrated in Chapter 8 / Chapter 9 / Chapter 27 regions, including:

```text
RM page 149
RM pages 155, 157
RM pages 423-424
RM pages 427-429
RM page 449
RM pages 452-455
```

Do not interpret presence of `FSEC` or `security state` alone as approval for destructive security operations.

## 21. Applicability policy per reviewed unit

Current unit requirements conceptually map as follows:

```text
FTFA register model
  requires FTFA module presence

FTFA command sequencing
  requires FTFA module presence

Program Longword
  requires FTFA module presence

Erase Flash Sector
  requires FTFA module presence

Erase All Blocks
  requires FTFA module presence

Flash Security
  requires FTFA module presence + Flash security model

Debug / Security interaction
  requires SWD + MDM-AP + Flash security model

SWD / MDM-AP
  requires SWD + MDM-AP
```

These requirements are necessary but not sufficient for binding.

Before a unit can be bound, the policy still requires review of:

```text
scope_bridge_reviewed
module_or_interface_presence_reviewed
unit_section_within_applicable_manufacturer_document_reviewed
applicability_exclusions_reviewed
```

## 22. Current trust boundary

At H003 creation:

```text
Source Lock                               PASS
Document Role Model                       PASS
PDF sanity guard                          PASS
Deterministic candidate discovery         PASS
Reviewed candidate boundaries             PASS
Heading-aware construction tooling        PASS
Reviewed Evidence Unit definitions        PASS
Applicability candidate discovery v1      IMPLEMENTED
Latest v1 SWPC observation                HEALTHY / NOT YET RETAINED REVIEW

Scope bridge reviewed                     FALSE
Evidence Unit Catalog admission           FALSE
Applicability Binding admission           FALSE
Evidence Pack admission                   FALSE
Semantic extraction admission             FALSE
Canonical dataset admission               FALSE
HIL admission                             FALSE
Production admission                      FALSE
Destructive security-operation admission  FALSE
```

Do not collapse these states.

## 23. What is proven so far

The following claims are supported by the current engineering evidence:

- exact NXP DS/RM source bytes are locked by SHA-256 and byte length;
- deterministic preprocessing is reproducible with the pinned `pdftotext` mode;
- broad keyword discovery can be deterministically wrong and must be reviewed;
- generic family headers are not commercial identity evidence;
- NXP's programming model is command-engine based and materially different from the STM32 register-control vocabulary;
- the dominant KL25 Flash programming evidence is concentrated around RM 419-456;
- debug/security recovery evidence is concentrated around RM 149-157;
- eight logical NXP-native Evidence Unit definitions have been reviewed;
- exact `MKL25Z128VLK4` membership exists in the locked RM;
- an intermediate `MKL25Z128` identity expression is not required and must not be synthesized without evidence;
- anchor-based applicability discovery removes the 864-page family-header pollution;
- the latest v1 applicability candidate shape is suitable for reviewed-claim construction.

## 24. What is NOT proven

Do not claim any of the following yet:

- Evidence Unit Catalog admission;
- final Applicability Binding for `MKL25Z128VLK4`;
- Evidence Pack admission;
- canonical dataset validity for KL25;
- Qwen semantic extraction success for KL25;
- cross-vendor generality beyond this pilot;
- OpenOCD implementation correctness;
- actual SWD target access;
- erase/program/verify on hardware;
- security-state transition correctness;
- safe mass erase / unsecure behavior;
- HIL correctness;
- 8-Site concurrent programming correctness;
- production readiness.

A deterministic relationship or applicability derivation does not imply runtime safety.

## 25. AI / deterministic responsibility split

Do not bring AI into the current applicability review merely because the long-term pipeline uses AI later.

Current preferred split remains:

```text
Manufacturer evidence
  -> deterministic evidence boundary / applicability review
  -> Evidence Pack / TargetEvidenceBundle
  -> AI semantic extraction
  -> manufacturer-near facts
  -> deterministic relationship derivation
  -> deterministic canonicalization
  -> validated canonical spec
```

AI should not own:

- exact commercial identity equivalence;
- applicability binding;
- wildcard applicability;
- cross-target relationship derivation;
- fail-closed admission decisions.

Retained model for the earlier STM32 benchmark line is:

```text
qwen3.8:27b-mlx
```

Do not silently switch to Gemma or another model when the KL25 Evidence Pack stage is eventually reached.

## 26. Critical cross-vendor architecture lessons

### 26.1 Vendor identity hierarchies are not guaranteed to be isomorphic

STM32 evidence exposed expressions such as:

```text
commercial ICPN
  -> manufacturer applicability expression
```

NXP KL25 evidence currently supports a direct exact commercial target membership in the Reference Manual without requiring an explicitly written `MKL25Z128` layer.

Plasma should preserve evidence-backed vendor structure rather than inventing a common intermediate level.

### 26.2 Document role is semantic, not title-based

STM32 may use a document titled Programming Manual.

NXP KL25 uses a Reference Manual as the programming authority.

Canonical architecture must model the semantic authority role rather than require literal vendor document titles.

### 26.3 Discovery is navigation, not authority

```text
keyword hit
    != evidence unit
    != applicability
    != canonical fact
```

### 26.4 Security relationships are not security admission

A unit or relationship may be deterministically derived while destructive security operations remain explicitly forbidden.

## 27. Files to read first in the next session

On branch `agent/ic-evidence-nxp-kl25-discovery`, inspect at minimum:

```text
data/ic-support/benchmarks/nxp-kl25/source-lock.json
data/ic-support/benchmarks/nxp-kl25/source-acquisition-contract.json
data/ic-support/benchmarks/nxp-kl25/preprocessing-contract.json
data/ic-support/benchmarks/nxp-kl25/discovery-contract.json
data/ic-support/benchmarks/nxp-kl25/reviewed-candidate-boundary.json
data/ic-support/benchmarks/nxp-kl25/evidence-unit-construction-contract.json
data/ic-support/benchmarks/nxp-kl25/reviewed-evidence-unit-definitions.json
data/ic-support/benchmarks/nxp-kl25/applicability-contract.json
data/ic-support/benchmarks/nxp-kl25/discover_applicability.py
data/ic-support/benchmarks/nxp-kl25/summarize_applicability.py
data/ic-support/benchmarks/nxp-kl25/test_applicability.py
.github/workflows/ic-support-validation.yml
```

Also read PR #395 before modifying the architecture.

## 28. Exact SWPC reproduction commands

Use the KL25 branch and locked local PDFs:

```bash
cd /storage/projects/plasma

git checkout agent/ic-evidence-nxp-kl25-discovery
git pull --ff-only origin agent/ic-evidence-nxp-kl25-discovery

python3 data/ic-support/benchmarks/nxp-kl25/discover_applicability.py \
  --source-dir /storage/projects/plasma-benchmark/nxp-kl25/source \
  --output /tmp/nxp-kl25-applicability-v1.json

python3 data/ic-support/benchmarks/nxp-kl25/summarize_applicability.py \
  /tmp/nxp-kl25-applicability-v1.json \
  > /tmp/nxp-kl25-applicability-v1-summary.txt

cat /tmp/nxp-kl25-applicability-v1-summary.txt
```

Do not commit `/tmp` artifacts merely to move them between machines.

## 29. Recommended first task in the next session

Start the next session with:

```text
Read repo handover H003 and continue.
```

The first engineering task should be:

> Review the anchor-based v1 applicability candidate JSON against the locked DS/RM evidence, retain a reviewed applicability-claims artifact, then implement deterministic unit-binding derivation without yet admitting an Evidence Pack or invoking AI semantic extraction.

Recommended sequence:

```text
1. Verify current branch / PR / main SHAs.
2. Re-run or inspect `/tmp/nxp-kl25-applicability-v1.json` from exact locked PDFs.
3. Review TARGET_EXACT_IDENTITY and RM_TARGET_MEMBERSHIP anchors.
4. Review KL25_FAMILY_SCOPE anchors.
5. Review FTFA / SWD / MDM-AP / FLASH_SECURITY_MODEL anchors.
6. Explicitly review applicability exclusions / variant caveats.
7. Retain reviewed applicability claims with source_id + physical page + normalized-page SHA.
8. Implement deterministic scope-bridge derivation.
9. Implement deterministic per-unit binding derivation.
10. Keep UNKNOWN fail-closed.
11. Only then decide whether Evidence Unit Catalog / Applicability Binding admission can move from false to reviewed/admitted state.
```

Do not advance to AI extraction merely because all candidate counts are nonzero.

## 30. Acceptance criteria for the next phase

The next phase is not complete until the repository can deterministically demonstrate, for `MKL25Z128VLK4`:

```text
1. Exact commercial identity is evidence-backed.
2. Exact target membership in the locked RM is evidence-backed.
3. KL25 family/document scope is established by explicit section anchors, not repeated headers.
4. FTFA presence is established in target-applicable manufacturer context.
5. SWD / MDM-AP presence is established in target-applicable manufacturer context.
6. Flash security model presence is established in target-applicable manufacturer context.
7. Applicability exclusions / variant caveats have been explicitly reviewed.
8. Each of the eight reviewed Evidence Units has explicit deterministic binding prerequisites.
9. Any missing prerequisite produces UNKNOWN / no binding.
10. No fuzzy identity matching or synthesized `MKL25Z128` layer is introduced.
11. No STM32 KEYR/CR/PER/MER/PG vocabulary is projected into NXP evidence.
12. Evidence Pack, semantic extraction, HIL, production, and destructive-security admission remain false unless separately justified.
```

## 31. Failure modes to avoid

Do not repeat these already-observed errors:

```text
Generic family header
  -> commercial identity                 WRONG

Document-wide KL25 header hit
  -> applicability scope                 WRONG

Missing MKL25Z128 intermediate string
  -> synthesize / fuzzy-match it         WRONG

Shared Reference Manual
  -> all sections apply automatically    WRONG

Keyword hit
  -> Evidence Unit                       WRONG

Reviewed Evidence Unit
  -> Evidence Pack admitted              WRONG

Security relationship derived
  -> destructive operation safe          WRONG

CI green
  -> HIL / production ready              WRONG
```

## 32. One-line project state

> Plasma has moved the NXP KL25 pilot from deterministic PDF discovery to reviewed NXP-native Evidence Units and an anchor-based applicability foundation; the next gate is evidence-backed deterministic binding of those units to `MKL25Z128VLK4`, with all semantic/canonical/HIL/production admissions still fail-closed.
