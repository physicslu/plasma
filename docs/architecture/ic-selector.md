# IC Selector Architecture

Status: current IC Selector runtime contract under ADR-0002

> **ADR-0002 canonical boundary (2026-10-15):** IC Selector visibility is owned by
> **Phase 1 `IDENTIFIED` exact ICPN identity**. Phase 2 Programming and Phase 3
> PLASMA Compatibility are independent displayed states and are not visibility
> filters. Job/Batch execution remains a separate fail-closed policy surface.

Related evidence model: [`device-support-validation.md`](./device-support-validation.md).
Related composed-profile model: [`selected-ic-profile-v1.md`](./selected-ic-profile-v1.md).

## Purpose

IC Selector is a shared Plasma capability for finding and inspecting IC catalog records. It is **not** a third Product Mode and does not belong to either Production Mode or Engineering Mode.

The same catalog and search semantics serve three contexts:

```text
Device Catalog
    |
IC Search Service
    |
IC Selector
    +-- standalone lookup (/devices)
    +-- Production Mode picker
    +-- Engineering Mode picker
```

The Selector answers **which IC record did the user mean?** Product-mode policy separately answers **may this configuration execute in this mode?**

## Product-mode boundary

Plasma continues to expose only two Product Modes:

- Production Mode
- Engineering Mode

`/devices` is a global read-only utility. It must remain available while PPU or Batch execution prevents switching between Product Modes because catalog lookup does not own programming resources and does not mutate execution state.

Production and Engineering workflows reuse the same `ICSelector` component in picker form rather than maintaining separate IC databases or search algorithms.

## Canonical source and runtime service

The runtime loads the checked-in Production exact-ICPN manifest and its content-locked manufacturer sources. Production rows have already passed authoritative exact-manufacturer-part-number admission, so the runtime projects them as Phase 1 `IDENTIFIED` without creating a second identity authority.

The browser does not parse source CSV files directly. The Python Web REST Gateway owns the read-only runtime catalog and exposes:

```text
GET /api/devices/search?q=<identifier>&limit=<1..100>
```

The service reports the canonical catalog size with each search response. The browser must not hard-code that count.

Search responses also distinguish pagination from filtered cardinality:

- `count` = number of rows returned in this response after applying `offset` and `limit`;
- `total_count` = number of admitted rows matching the query before pagination;
- `offset` = zero-based position of the first requested row in the deterministic ranked result set;
- `limit` = maximum rows requested for this page;
- `catalog_size` = total number of admitted rows in the Production Catalog.

The browser must present the visible range and total matches separately, for example `1–30 / 1,400`, and provide explicit previous/next navigation when `total_count > limit`. Changing the query resets `offset=0`; changing pages clears a prior selection so the detail panel never implies that an off-page row is still selected. The ranked ordering contract is stable across pages, so repeated `query + offset + limit` requests must return the same identifiers while the underlying catalog revision is unchanged.

The research CSV is an import/source artifact, not a permanent storage contract. A future database-backed catalog may replace it without changing Selector semantics.

## ICPN semantics

`ICPN` means **IC Part Number**.

The source column historically named `part_number` contains identifiers at different granularities, so Phase 1 normalizes it as:

```text
identifier
identifier_kind
icpn
```

`icpn` is populated only when the source proves an exact manufacturer part number (`manufacturer_part_number`). CMSIS/vendor device names, ordering patterns, and family aliases remain searchable identifiers but must not be presented as exact ICPNs.

Primary human-facing taxonomy is:

```text
Vendor
└── Family
    └── ICPN / device identifier
```

Manufacturer subfamily and Plasma series remain supporting context. Users are never required to choose Vendor, Family, Subfamily, or Plasma Series before searching.

## Search contract

Search is case-insensitive and ranks identifier matches in this order:

1. exact identifier match;
2. identifier prefix match;
3. other identifier substring match.

Within the same match rank, exact manufacturer part numbers receive priority over broader identifier kinds.

Phase 1 deliberately searches the normalized identifier field first. Vendor/family filters and broader fuzzy search can be added later without changing the exact/prefix/partial precedence.

## Evidence and status boundary

Catalog identity, programming-backend mapping, and physical validation are independent dimensions. Detailed configuration fingerprints, PPU/Socket model-versus-instance identity, engineering validation, and field-use evidence remain governed by the shared device-support validation architecture rather than being redefined by the Selector.

An OpenOCD relationship uses its actual backend mapping state, for example:

```text
no_mapping
mapping_candidate
mapped
rejected
```

The Production exact-ICPN UI uses **three display states within the existing OpenOCD Tag** (not a fifth Tag): `mapped` (green) when the Production Catalog backend says `mapped`; `candidate` (amber) only when Production remains `no_mapping` and independent, immutable, source-locked `backend_candidate` research evidence exists; `no_mapping` (neutral) otherwise. A source candidate is never an executable programming route; `backend.mapping_status` and `backend.target_config` remain the server's authority. The other three Tags (PPU, Socket, manufacturer part) are unaffected and never infer real hardware validation. Candidate evidence is optional in slim PPU bundles; missing evidence displays `no_mapping` without breaking catalog searches.

ADR-0002 Phase 2 adds a separate **Programming Qualification** badge. It is not a
replacement for the OpenOCD CFG tag: `CFG mapped` answers whether a Provider route exists,
while `SUPPORTED / CANDIDATE / UNKNOWN / UNSUPPORTED` answers whether that exact ICPN has
completed the version-locked Programming qualification transaction. In particular,
a mapped CFG with an unreviewed exact ICPN must render `Software · UNKNOWN`, never
`SUPPORTED`. The canonical API field is `programming_qualification`; the historical
`openocd_software_qualification` field is compatibility-only.

The older `mapping_candidate` relationship state remains a separate architecture concept; UI `candidate` is a **read-only projection**, not a change to the canonical mapping data.

## Backend Provider, version and validation evidence in the detail panel

The four row Tags remain unchanged except for the OpenOCD three-state display. The selected exact ICPN detail view shows **Backend Provider**, source repository, source version/commit, pinned release runtime ID, **installed** runtime ID / executable SHA-256 and evidence scope separately.

For the existing 4,164 mapped Upstream OpenOCD rows, the source version and pinned release runtime ID are looked up from the checked-in `release/openocd.json` when present. If the slim PPU package omits this source authority, the version is explicitly **not attested** rather than hardcoded. Mapping is still only Catalog routing evidence.

For H5/C5 candidates, the source commit, driver and target config source path come from the existing source-locked Candidate Registry. An ST source commit is **not an installed runtime ID**. These candidates remain `research_only`, `executable=false`; display the source version as unknown unless an independent version attestation exists. Both installed runtime ID and binary SHA-256 remain null; real PPU runtime attestation is a future separate interface. A build on Host / ARMv7 QEMU cannot stand in for a real ARMv7 PS installation or validated target flash transaction.

The new optional backend_providers array allows the detail panel to list independently attributed Upstream/ST Provider options, each with source version/commit and build-specific architecture, CI run, runtime ID, artifact/payload SHA-256 and software-test scope. If that newer array is absent (older Gateways and slim packages), the original backend_source_reference single-source view remains in place. Source build evidence is never installed-runtime or physical validation.

This UI evidence is read-only metadata and must not be copied into Job/Batch, resolver or execution admission. Future multi-provider support must preserve independent source, runtime and per-configuration qualification identities.


PPU and Socket verification require physical evidence for a specific Programming Configuration. The current canonical research catalog does not contain that evidence, so Phase 1 returns and displays `no_evidence` for both instead of inferring support from OpenOCD data.

A future physical validation record binds at least the relevant device/ICPN, package, programming interface/profile, PPU model and hardware revision, Site interface, Socket model/revision, voltage/settings, software and algorithm revisions.

## Package boundary

Package is part of the target domain model because Socket compatibility depends on it. The current canonical research snapshot does not reliably provide package data. Phase 1 therefore exposes `package = null` rather than deriving package from an ICPN suffix heuristically.

Package enrichment is a separate authoritative-data task.

## Selected IC information layers

The same search result can carry three independent additive projections:

- `manufacturer_device_basic_profile` — operator-facing Basic Device information.
- `selected_profile` — deeper manufacturer/programming composition, only where the
  Programming Profile evidence chain exists.
- `programming_qualification` — canonical ADR-0002 Phase 2 exact-ICPN Programming
  qualification. It may be `SUPPORTED` even when `selected_profile` is absent, because
  the qualification ledger binds the reviewed Programming Profile and exact geometry
  independently from the legacy deep-detail projection. The current Provider is OpenOCD;
  future NXP/Microchip or other Brand qualifications must reuse this interface instead of
  adding Brand-specific Phase 2 fields.

For Manufacturer Device Basic Profile v1, IC Information uses a fixed ten-field contract:

```text
ICPN
Base Device
Package
Pin Count
Flash
RAM
Operating VDD
I/O Supply
VDDA
Operating Temperature
```

Memory Map, I/O supply, VDDA, Flash-controller registers and programming algorithms are not
part of this Basic IC Information surface. Detailed address maps may still exist internally
for execution-oriented research.

The browser presents three primary information layers:

1. IC Information — the Basic Device Profile above.
2. Programming — Phase 2 software qualification state first, then qualified
   Provider/operations/electrical/Flash geometry, with deeper manufacturer interface/pin
   and programming-flow detail where `selected_profile` exists.
3. PLASMA Compatibility — Site/Socket/electrical/hardware/physical qualification state.

A Basic Device Profile does **not** imply Programming Profile authority. Thus an STM32F1,
STM32C0, STM32G0, or STM32G4 target may have `manufacturer_device_basic_profile != null` while
`selected_profile == null`. I/O Supply and VDDA remain visible in the contract but render as `—` when the
allowed ST Product Selector/eStore sources do not directly establish them. They are never
copied from VDD or inferred from family/OpenOCD data. STM32G4 demonstrates the positive
case: ST eStore directly states a VDD/VDDA range, so VDDA is populated while I/O Supply
continues to render as unavailable.

OpenOCD mapping also cannot promote Basic Device information
into Programming support.

Manufacturer programming interfaces remain heterogeneous. A debug transport such as
SWD/JTAG can carry a `clock_hz` object, while a documented-but-not-expanded interface such
as a system bootloader can carry only status/boot-source metadata. Browser rendering must
treat `clock_hz` as optional.

Advanced Backend / Evidence remains available separately so provider runtime/build
provenance is not confused with IC characteristics or physical qualification.

## Reusable UI contract

`ICSelector` supports two usage forms:

```text
lookup
picker
```

`lookup` is the standalone `/devices` experience.

`picker` exposes the same search/results/evidence presentation and an `onSelect` callback for Production or Engineering workflows. Mode-specific eligibility must be evaluated by the calling workflow/policy layer, not by hiding catalog records in the shared Selector.

## Phase 1 non-goals

Phase 1 does not:

- claim that all 7,657 canonical identifiers are exact ICPNs;
- create PPU or Socket verification evidence;
- infer package from naming conventions;
- make the IC Selector a Product Mode;
- change PPU, Site, Batch, programming, or hardware execution behavior;
- define Production eligibility policy inside the Selector.
