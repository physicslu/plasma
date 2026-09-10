# STM32G4 Phase 4.9D — Capability / Canonical Admission Planning

Status: bounded read-only admission plan

## Purpose

Phase 4.9D intersects the closed Phase 4.9C manufacturer-backed metadata set
with the current guarded OpenOCD ordering-pattern route surface. It determines
which retained exact STM32G4 commercial identities are eligible for a later
controlled canonical/publication transaction.

This phase does **not** write the canonical STM32G4 CSV or the Production
manifest.

## Upstream authority boundary

Commercial identity and lifecycle remain owned by the retained Phase 4.9B
official-ST evidence. Metadata semantics remain owned by the Phase 4.9C
official-ST ordering-information authority.

OpenOCD is used only as an independent route/capability-mapping surface. A
positive `stm32g4x.cfg` mapping is not manufacturer evidence and does not prove
Flash geometry, Flash algorithm equivalence, option-byte/security semantics,
electrical behavior, physical target operation, HIL qualification, or runtime
programming support.

CMSIS aliases do not participate in commercial identity or canonical route
admission.

## Current exact-identity route observation

Before hard-coding the Phase 4.9D expected set, a branch-only observation run
replayed the closed 4.9C baseline and independently resolved all 25 exact ICPNs
against the then-current `openocd-parts-canonical.csv`.

Observed result:

- metadata-ready exact ICPNs: 25
- strict unique ordering-pattern mappings: 25
- ambiguous: 0
- unmapped: 0
- capability-unresolved exact ICPNs: 0
- required target config: `tcl/target/stm32g4x.cfg`

The admission planner therefore freezes `EXPECTED_ADMITTABLE_COUNT = 25` and an
empty capability-unresolved set. Future mapping loss is fail-closed; the planner
must fail rather than silently shrink the admission candidate set.

## Commercial-surface incompleteness remains explicit

Phase 4.9D does not erase the three deterministic Phase 4.9B current-source
404 dispositions:

- `STM32G411C6`
- `STM32G414CB`
- `STM32G471CC`

They remain source-unavailable Base Devices, not historical nonexistence claims.
They cannot enter the 4.9D candidate set because no retained manufacturer-verified
Active exact identity was established for them.

The following non-Active Proposal identities also remain excluded:

- `STM32G441CBT3`
- `STM32G441CBU3`
- `STM32G484CET3`

Thus `25/25 capability-admittable` means all **retained Active identities** are
routable. It does not mean the bounded 11-target commercial discovery surface is
complete.

## Canonical row policy

Each planned canonical row must simultaneously preserve:

1. the exact manufacturer identity retained in 4.9B;
2. the official ordering metadata decoded in 4.9C;
3. one current unique OpenOCD `ordering_pattern` mapping;
4. exactly `tcl/target/stm32g4x.cfg` as the route target;
5. no CMSIS alias as canonical commercial identity.

The package-specific 4.9C semantic is preserved through admission:
`STM32G441CBY6TR` remains WLCSP, 49 balls, `TR`, and maps uniquely to
`STM32G441CBYx`. It must not be normalized to a 48-pin C-package assumption.

## Frozen transaction result

The deterministic plan contains:

- manufacturer-verified Active exact identities: 25
- canonical admission candidates: 25
- decision `admit`: 25
- `already_present`: 0
- `manual_review_required`: 0
- `reject`: 0
- capability unresolved: 0
- canonical rows before admission: 0 / absent
- `canonical_dataset_admission`: `planned`
- canonical write applied: false
- Production write applied: false

Production remains the frozen Phase 4.9C prestate:

- exact ICPNs: 610
- Base Devices: 209
- Production families: STM32F0/F1/F2/F3/F4/F7/G0
- STM32G4 exact ICPNs in Production: 0

## Immutable bindings

- Phase 4.9D admission-plan SHA-256:
  `4ba41c97414ca4eb45b069f08b0200e2e53faaaed2cd5e4e57e7ac260d3d1291`
- Phase 4.9C policy-baseline SHA-256:
  `23e83659d694ad8428eda19d7c570372c86ad40d75be8c6bbb8c16007bd398fd`
- OpenOCD canonical mapping catalog SHA-256:
  `43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3`
- frozen Production prestate SHA-256:
  `0dbb7df5a3ddc771326507fb42a47416d892d1d17f4e4141dde37cde23e95ddf`

## Trust boundary

The following claims remain false after a clean Phase 4.9D plan:

- canonical write applied
- Production write applied
- programming-algorithm equivalence
- Flash-geometry equivalence
- option/security semantic equivalence
- physical target qualification
- HIL qualification
- runtime programming support
- full STM32G4 surface coverage

A later Phase 4.9E may perform a separate controlled catalog publication
transaction for the planned 25 identities. Publication itself must still not be
interpreted as programmer/runtime qualification.
