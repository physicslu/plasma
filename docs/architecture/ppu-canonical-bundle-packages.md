# PLASMA Universal Bundle — Canonical Naming and Wire Schema

> **Term note:** in this document **B1/B2/B3 are Bundle stages** — B1 upload/commit, B2 admission, B3 install/verify plus standard Active selection. Independent legacy B4 recovery/backup remains separately governed. Not the FPGA/UIO or governance meanings; see [glossary](../glossary.md#b1b2b3).

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

User-authored v3 Bundles may originate entirely outside GitHub. Neither
`source_commit` nor a Publisher, signature or CI provenance is required for
B1/B2/B3. Optional `source_commit` is a lowercase SHA40 **claim**, retained
as untrusted provenance only; there is no repository lookup, comparison to
engineering HEAD, publisher whitelist or authorization derived from it.
Malformed optional metadata still fails schema validation. The canonical
verifier and B3 engine accept no caller-provided expected source commit.
Admission/install receipts emit `source_commit: null` when absent; consumers
must also tolerate omission of that informational field. Exact ZIP SHA256
and per-file hashes remain authoritative content identities.

Each action still requires authenticated owner authorization bound to the
physical PPU, exact ZIP bytes, current transaction and requested privilege.
Target and independent FPGA ABI/Identity qualification, Runtime ownership,
reload fences, SAFE_OFF, resource limits and Linux permissions remain in
force. The engineering Runtime Release, factory/CI artifact identity and
trusted GitHub Dispatcher Work Order source pins are separate contracts
and retain their existing mandatory source identity checks. The Bundle FPGA
Manifest is a checked declaration; Root hardware evidence and owner operation
authorization remain separate requirements. Publisher authenticity is not
independently established by the current paired owner authorization.

*The illustration is not a valid ZIP until real SHA256 and sizes are substituted.* Optional `actions` and `source_commit` declarations confer no execution permission. All other Manifest fields are denied; a v3 Manifest containing `components` is invalid. A v2 Manifest containing `packages` is also invalid.

## One admitted wire format: Bundle v3

| Schema | Current admission |
| --- | --- |
| `plasma.ppu.package.v1` | **RETIRED / REJECTED**; historical standalone Package fixture only |
| `plasma.ppu.bundle.v2` | **RETIRED / REJECTED**; historical `components` fixture only |
| `plasma.ppu.bundle.v3` | **ACCEPTED**; `packages`, `payload/packages/<package-id>/...` |

There is no v1/v2 admission or installation compatibility path. Existing historical
receipts are evidence, not permission to replay an obsolete transaction.

## Parser and Receipt boundaries

- Reuse `POST /v1/uploads` and `POST /v1/deployments`; canonical B2 admission uses `kind=bundle`. The separate `kind=ppu-runtime` deployment retains its distinct verified Release Kit and Coordinator path.
- `verify_host_only_artifact` accepts only v3. Its plan contains `bundle_schema: "plasma.ppu.bundle.v3"` and `packages`, never `components`. The Host-only receipt contains the v3 `bundle` envelope.
- `VerifiedBundle.packages`, `VerifiedBundlePackage`, and `MAX_BUNDLE_PACKAGES=32` define the Package graph. The resolver emits `plasma.ppu.bundle-resolution.v2` with `package_order` and `package_sha256`; this resolution schema version is **not** Bundle v2 admission.
- Package kinds `python`, `native-c` and `fpga-image` retain file-shape restrictions; `fpga-image` requires the paired BIN, HWH and `plasma.fpga.image.v1` manifest plus separate Root qualification. Opaque data Packages, including Catalog and Programming Profile, cannot carry executable files.
- A Python or native Package may carry `config/plasma-package-resources.json` for Site/time limits, and a Provider may carry `config/plasma-provider-options.json`. These resources grant no executable authority. SHA, ZIP/path, dependency DAG, target, Owner Authorization and privilege checks remain mandatory.

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

B1/B2/B3 continue to mean Receive, Admission, and Install/Verify.
Under the 2026-11-03 owner decision, **standard B3 success also selects the
verified Active Set**. The B3 HTTP body has exact `mode: "activate"` or
`mode: "stage_only"` plus mandatory boolean `fpga_load`. An exceptional
`stage_only` installs/verifies files but never publishes `active.json`.
For a Bundle with **no FPGA Image**, `mode: "activate", fpga_load: false`
atomically publishes the verified Set under the Coordinator's existing
`deployment.lock` and a connection-held Runtime Job quiescence lease;
it does not reload PL. A Bundle containing an FPGA Image cannot activate
with `fpga_load: false`: its caller must **explicitly** choose
`mode: "activate", fpga_load: true` and carry the separate
`bundle.activate-fpga-load` owner authorization. No server-side default or
`bundle.install` or `bundle.activate` authorization can infer this privilege.

**B3 FPGA load (owner decision 2026-11-02, [Gate 1](../deployment/ppu-bundle-v3-b3-fpga-load-gate1.md)).**
A B3 `mode: "activate"` request with an explicit `"fpga_load": true` for a Bundle that contains
exactly one `fpga-image` Package also loads that Image, in the same
`deployment.lock` transaction: install/verify → Runtime Job Quiesce
(connection-held) → protected Root Entry `bundle-load <asset_set_sha256>`
(Root re-derives the Set itself, runs the `/proc` `/dev/mem` `/dev/uio*`
census, promotes the companion Manifest keeping the previous one, then the
existing `download` and Identity `test`) → `active.json` is published only
after Identity PASS. Outcomes: `fpga_loaded`, `fpga_load_denied` (PL and
Active Set unchanged), `recovery_required` (explicit `restore` only) and
`fpga_identity_failed` (Image kept loaded; no automatic Golden Restore).
The receipt is `plasma.ppu.b3-deployment-receipt.v2` and reports
`runtime_site_readmission=REQUIRED`. It never triggers from upload or B2
alone and never performs a DUT operation. A PPU is READY only after the
selected Set and physical/runtime prerequisites are proven.

The current generic B3 installer stores immutable Sets in
`/opt/plasma/assets/staged/<archive_sha256>`, while the existing Active
Asset Set helper atomically publishes `/opt/plasma/assets/active.json`
(`os.replace` + fsync). Each receipt distinguishes
`bundle_install_and_activate`, `bundle_install_and_fpga_load` or
`bundle_staged_only`, reports `ready: false`, and records the
Coordinator transaction. Neither Active identity nor a successful B3
implies that a Programming Job is READY. Host-only tests are not Z2 HIL
evidence; unknown physical state requires guarded recovery and fresh
Site/FPGA admission.

**Terminology:** Bundle-as-Assets is a system-level classification; a
Bundle is **not identical to one** `Programming Asset` object from
the REST/domain model. A Per-Site Serial Number/MAC/Calibration input
may remain independent of the common PPU-wide Active Set.

See [PPU Single Active Asset Set — Controller-Driven Architecture](ppu-job-driven-package-resolution.md)
for ownership, update sequence, FPGA boundaries and non-goals.

## Execution and migration boundaries

Only new v3 Bundles should be produced. Do **not** convert historical on-device v2 bytes in place; generate a new v3 ZIP with updated path, Manifest, hashes and provenance. Keep legacy v1/v2 parsers until all old callers and archived evidence are accounted for. Package installation, activation, recovery, trust signing and real PPU v3 admission remain separate qualification gates. No FPGA or DUT operation is authorized by the naming migration.

## Programming execution boundary (owner decision 2026-11-04)

See [Unified Bundle-driven Programming Execution](unified-bundle-driven-programming-decision-2026-11-04.md).
**Bundle v3 is not an OpenOCD bundle** and its `python`, `native-c`,
`fpga-image` and opaque-data kinds are not intended as a fixed list of
programming technologies. Third-party FPGA/Driver/Provider and PS-only
programmers must be supportable by a standard, capability-declared Plugin
interface without editing PLASMA Core. A verified Bundle is not by itself
an entitlement to execute arbitrary code or hardware operations.

Engineering and Production use **the same programming execution pipeline**,
while retaining their existing distinct policies and approval requirements.
Console owns Bundle selection, target/operation policy admission and
delivery. PPU validates received bytes, selected Active Set identity,
applicability and the actual hardware safety/compatibility state; PPU
must not gate the Job on a central Device Catalog, a pre-registered ICPN,
a hardcoded Compiler/Backend/Image ID, or OpenOCD availability when the
selected valid Provider does not require it.

**Current implementation is incomplete:** existing B2 factory FPGA
contracts, static Runtime operation-admission projection and OpenOCD-only
Site adapter remain until replaced by trusted Bundle-derived equivalents.
This paragraph does **not** declare current Bundle v3 Parser capable of
executing an opaque Resource Package or bypass B1/B2/B3 and local safety gates.

