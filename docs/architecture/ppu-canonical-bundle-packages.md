# PLASMA Universal Bundle — Canonical Naming and Wire Schema

> **Term note:** in this document **B1/B2/B3/B4 are Bundle stages** — B1 upload/commit, B2 admission, B3 install/verify, B4 activation (incl. previous-version backup). Not the FPGA/UIO or governance meanings; see [glossary](../glossary.md#b1b2b3).

**Architecture Decision (2026-10-31, merged in PR #1225):** One deployment format, **Bundle → Packages → Files**. This document defines the only canonical vocabulary for future PLASMA PPU packaging. It does not grant install, activation, publisher authority, FPGA, DUT, or production-security qualification.

## Terminology (normative)

| Term | Definition | Canonical v3 key |
|---|---|---|
| **Bundle** | One versioned deployment ZIP/transaction envelope containing 1–32 Packages and one overall target/purpose | `plasma.ppu.bundle.v3` |
| **Package** | Independently identified, typed, versioned and dependency-addressable deployment unit in a Bundle | `packages[]`: `id`, `kind`, `version`, `requires`, `files` |
| **File** | Data, source, binary, configuration or FPGA artifact belonging to exactly one Package | `payload/packages/<package-id>/...` |
| **Dependency** | A Package-ID reference in another Package's `requires`; all required Packages must appear in this Bundle (closed Bundle) | `requires: [package-id]` |
| **Bundle Admission** | Parse, validate entire ZIP, files, SHA-256, target, unique Package IDs and dependency DAG; produce non-executing Admission Receipt | `kind=bundle`, `stage=package_admission_only` |
| **Bundle Resolution** | Deterministic Package ordering and safe inventory reuse plan; NOT an install grant | `package_order`, `package_sha256`, `stage`, `reuse` |

**Do not use Component as the name of a Package.** Historical v2 uses `components` as an immutable *on-wire legacy field*, not the product terminology. Every new API/schema, object, document and test uses Package.

### Canonical v3 Manifest

```json
{
  "schema": "plasma.ppu.bundle.v3",
  "name": "example-programming-route",
  "version": "1.0.0",
  "purpose": "programming",
  "source_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "target": {
    "platform": "linux-armv7",
    "board": "pynq-z2",
    "fpga_part": "xc7z020clg400-1"
  },
  "packages": [
    {
      "id": "ic-catalog",
      "kind": "ic-catalog",
      "version": "1.0.0",
      "requires": [],
      "files": [{
        "path": "payload/packages/ic-catalog/data/catalog.json",
        "sha256": "<actual 64-character SHA256>",
        "size": 1234,
        "executable": false
      }]
    },
    {
      "id": "programming-profile",
      "kind": "programming-profile",
      "version": "1.0.0",
      "requires": ["ic-catalog"],
      "files": [{
        "path": "payload/packages/programming-profile/data/geometry.json",
        "sha256": "<actual 64-character SHA256>",
        "size": 345,
        "executable": false
      }]
    }
  ]
}
```

*The illustration is not a valid ZIP until real SHA256 and sizes are substituted.* An optional `actions` declaration is descriptive, not execution permission. All other Manifest fields are denied; a v3 Manifest containing `components` is invalid. A v2 Manifest containing `packages` is also invalid.

## Explicit version transition, not a silent rename

| Wire format | Status | Exact accepted field and path |
|---|---|---|
| `plasma.ppu.package.v1` | Legacy single-kind Package input; retained for compatibility, not the canonical new authoring format | `files`, original v1 `payload/...` |
| `plasma.ppu.bundle.v2` | Legacy read/admission compatibility, including historical PR2/PR3 / PR #1224 evidence | `components`, `payload/components/<id>/...` |
| `plasma.ppu.bundle.v3` | **Only canonical format for all new Bundle authors** | `packages`, `payload/packages/<id>/...` |

Changing `components` to `packages` on an existing `plasma.ppu.bundle.v2` is **invalid**, because a published Schema version is an interface contract. Existing physical B1 and B2-v1 receipts do not change; B2-v2 remains **NOT_QUALIFIED** on the installed Z2 until independently attested. A Host-only v3 PASS is not a physical Z2 v3 PASS.

## Parser and Receipt boundaries

- The existing `POST /v1/uploads`, chunk/commit and `POST /v1/deployments` API and `kind=bundle` remain unchanged. No new Manager, Installer, Lock, Journal or transport.
- Canonical v3 admission Plan emits `bundle_schema: "plasma.ppu.bundle.v3"` and **`packages` only**; v2 Plan emits the historical **`components` only**. Malformed mixed responses must be rejected.
- The Python model exposes `VerifiedBundle.packages: tuple[VerifiedBundlePackage]`, `MAX_BUNDLE_PACKAGES=32`, `bundle_package_identity`, and Package-based DAG resolution. Legacy attribute/function aliases remain narrowly for v2 consumers and cannot be used for new schema authoring.
- New v3 Bundle Resolution emits `schema=plasma.ppu.bundle-resolution.v2`, `package_order`, `package_sha256`; v2 continues the old `component_order` and `component_sha256` Receipt shape.
- Host-only transaction returns a top-level `bundle` envelope containing `packages` for v3; legacy v2 and Package v1 continue to return their historical `package` envelope. This is only a simulated transaction Receipt, not proof of device installation.
- Code types `python`, `native-c`, `fpga-image` have reviewed file-shape restrictions (`fpga-image` = exactly one BIN + HWH + `plasma.fpga.image.v1` Manifest, statically qualified at B2 per [Master Authority and FPGA Static Qualification](../deployment/ppu-bundle-v3-master-authority-gate1.md)); opaque data kinds such as IC Catalog and Programming Profile cannot carry executable files. File/path limits, unique IDs, SHA, ZIP protections and target compatibility remain enforced.
- Component/Package hashing only establishes content identity; a Bearer token, checksum or Manifest `source_commit` does not prove Publisher/Master authorization.

## Asset-only Bundle semantics and single Active Asset Set

**Owner decision (2026-11-02):** Bundle is an **Assets delivery container**;
it is NOT a Programming Recipe, self-starting workflow, FPGA load command
or authority to execute included Python/Native code. A PPU shall have
**one effective Active Asset Set at any instant**. That logical Set may
contain multiple Packages (data, Parser, Profile, FPGA Image, Firmware);
"one Set" does **not** mean one physical file.

**Console selects the exact Asset Set** and its bound FPGA Image and
Programming Profile, then owns E/P/V/R operation initiation and sequencing.
Before Jobs, Console compares the required Set identity/SHA256 against
the PPU's reported Active Set. On mismatch or untrusted/missing identity,
Console transfers the **complete selected Set**, not a mix of convenient
Packages already present on the PPU. A match skips redundant transfer,
not runtime/FPGA qualification.

The PPU shall resolve needed resources **only within the single Active
Set**; no cross-Bundle automatic Package version negotiation, independent
fallback to an alternate Profile/Image, or requirement for long-term
multi-version package co-installation. Existing v3 `packages[].requires`
continues to describe **dependencies inside one delivered Bundle**, not
the set of operations in a Job.

B1/B2/B3 continue to mean Receive, Admission, and Install/Verify. Installation
does NOT immediately activate the Set, reconfigure the FPGA, or execute
a Programming Job. Future Set switching needs isolated Staging and an
atomic effective Active Set transition without disrupting active Jobs;
FPGA loading is a distinct, explicitly Controller-authorized,
PPU Hardware Manager-controlled operation, with full Site quiescence
and hardware ABI/identity/safety verification. A PPU is READY only
after the selected Set and physical/runtime prerequisites are proven.

The existing B3 install path `/opt/plasma/bundles/<bundle-name>` has
**no generic Active Asset Set feature today**, and B3 physical acceptance
covers only the approved Smoke Bundle from PR #1241. The canonical Set
identity algorithm, activation API, persistence and recovery remain
unimplemented, despite this architecture choice.

**Terminology:** Bundle-as-Assets is a system-level classification; a
Bundle is **not identical to one** `Programming Asset` object from
the REST/domain model. A Per-Site Serial Number/MAC/Calibration input
may remain independent of the common PPU-wide Active Set.

See [PPU Single Active Asset Set — Controller-Driven Architecture](ppu-job-driven-package-resolution.md)
for ownership, update sequence, FPGA boundaries and non-goals.

## Execution and migration boundaries

Only new v3 Bundles should be produced. Do **not** convert historical on-device v2 bytes in place; generate a new v3 ZIP with updated path, Manifest, hashes and provenance. Keep legacy v1/v2 parsers until all old callers and archived evidence are accounted for. Package installation, activation, recovery, trust signing and real PPU v3 admission remain separate qualification gates. No FPGA or DUT operation is authorized by the naming migration.
