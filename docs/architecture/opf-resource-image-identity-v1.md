# OPF Programming Resource Set / Job Image Asset Identity v1 (OFE-1A Gate 1)

Terminology: the owner request's "Job Firmware Asset" is named **Job Image
Asset** in code and schemas, following the canonical Programming Asset /
Normalized Image vocabulary enforced by
`scripts/tests/test-canonical-terminology-guard.py`.

Status: **Contract v1; OFE-1B Gate 1 integration implemented, Host-only.**
OFE-1A defined the identities. OFE-1B (§8) makes the PPU derive the Resource
identity from its own verified Active Set and admits an independent Job Image
under an exact Job Binding. Resource reuse is **Host-only PASS, NOT_RUN on
hardware**; it must not be claimed as hardware-verified before HIL (§8.6).

Base: `main` `efaf3609be23568d4f907fc81c166c2c31cd5328` (same as the OFE-0
audit base). Plan of record: OPF Frontend post-LOM plan (PR #1377, §4.1 OFE-1).

## 1. Problem

The canonical Bundle v3 writer (`plasma_opf.bundle_v3.build_image_bundle`)
puts Provider, Profile and the Firmware Package in one archive, so
`archive_sha256 = H(Provider + Profile + Firmware)`. A Firmware-only change
yields a new archive SHA256, the Manager sees a different Active Asset Set and
runs B1/B2/B3 again. OFE-1A defines the identities that make "same resources,
different Firmware" provable, without changing any execution path.

## 2. Current call chain (verified on the base commit)

| # | Step | Source |
|---|---|---|
| 1 | Console → Manager plan / run | `software/web/app/engineering/bundle-programming-api.ts:90,130` → `software/python/plasma_manager/bootstrap_server.py:480-495` → `BundleProgrammingWorkflow.plan` `software/python/plasma_manager/programming.py:327` / `.start` `:390` |
| 2 | Canonical Bundle v3 | `programming.py:350` → `bundle_v3.build_user_image_bundle` → `build_image_bundle` (single writer) |
| 3 | Active Set comparison | `programming.py:362-367` (`activation_required` = Active `asset_set_sha256` ≠ `archive_sha256`); rechecked after activation `:459-462` |
| 4 | Bootstrap B1/B2/B3 | `BundleProgrammingWorkflow._activate` `programming.py:479-559` via `ManagerBootstrapCoordinator` (`create_upload`/`append_chunk`/`commit_upload`/`start_deployment`, `fpga_load=False`) |
| 5 | Gateway `POST /api/jobs` | `programming.py:561-597` → `gateway_base.py:780` → `_job_request` `gateway_base.py:440-569` (Bundle reference `asset_set_sha256`/`asset_package_id`/`bundle_asset_sha256` is complete, exclusive, `flash_cycle` only) |
| 6 | Active Firmware resolution | `SiteManager.enqueue` `site_manager.py:430-563` (pins Active Set under the PPU-wide execution lease, `:483-541`) → `package_actions.py:108` → `scripts/ppu_asset_set.py:resolve_active_firmware` `:185-249` |
| 7 | Provider `flash_cycle` | `execution_router.py:84-93` (C-3 OpenOCD route) → `plasma_interfaces/openocd.py:112` `flash_cycle` |
| 8 | Receipt / readback / SAFE_OFF | `programming.py:_poll_job` `:599-615`, `_verify` `:617-650` |

## 3. Identity contract v1

All three identities are `sha256(canonical_json(descriptor))` using the existing
`bundle_v3.canonical_json` / `sha256_hex`. Unknown, missing, extra, mistyped or
inconsistent fields fail closed with a fixed `BundleBuildError` reason code.

### 3.1 Programming Resource Set — `plasma.opf.programming-resource-set.v1`

| Field | Meaning |
|---|---|
| `target` | `{platform, board, fpga_part}` (Bundle v3 target profile) |
| `abi` | `{driver_abi, transport}`; `transport` must be `fpga` |
| `constraints` | `icpn`, `sites`, `operations`, `max_image_bytes`, `target_config`, `flash_base`, `flash_size`, `erase_granularity` |
| `fpga_package` | `null`, or the id of exactly one `fpga-image` Package in `packages` |
| `image_package_kind` | Bundle v3 kind of the Job Firmware Package (route data, e.g. `firmware-asset`); may not be a Resource kind |
| `packages[]` | Bundle v3 Package entries exactly as the manifest stores them: `id`, `kind`, `version`, `requires`, `files[{path,size,sha256,executable}]` |

Rules: exactly one `platform-provider` and one `programming-profile` (the
Profile requires the Provider), at most one `fpga-image`; Package ids and file
paths unique (`RESOURCE_PACKAGE_CONFLICT`); every `requires` entry must name an
earlier Package (`RESOURCE_DEPENDENCY_MISSING`, also excludes cycles); every
file pinned by a 64-hex SHA256. Ids/versions are labels; **content SHA256 is
the identity** — a changed byte in any Provider/Profile file, a changed
version, dependency, target, Driver ABI, FPGA Package or constraint changes the
Resource SHA256. Firmware bytes, Firmware filename, Firmware Package id, Bundle
name and Bundle version never enter it.

Operations: `constraints.operations` is a non-empty, duplicate-free subset of
`OPERATIONS = (erase, program, verify, read, flash_cycle)` — exactly the
programming members of `plasma_core.enums.Operation` (`status`/`cancel` are
control operations and are refused). A Resource descriptor is **not** required
to declare `flash_cycle`. Declaring an Operation is a capability claim only and
grants no execution: the Bundle-building Programming Route (`parse_route`)
still requires `flash_cycle`, and the PPU Runtime route admission
(`execution_router.py:84-93`, C-3 OpenOCD = `flash_cycle` only) and the Gateway
Bundle reference (`flash_cycle` only) remain the execution authorities.

Driver: the current route-built Bundle has no Driver Package. The Driver is
identified by `abi.driver_abi` (also inside the Profile capabilities file whose
SHA256 is pinned); the actual Driver ABI is still verified by the PPU at Job
time. FPGA: current routes require `fpga_package: null`; FPGA-bearing Resource
Sets are representable in the descriptor but `identity_from_manifest` refuses
them (`BUNDLE_PACKAGE_SET_UNSUPPORTED`) until a reviewed contract version
covers them.

### 3.2 Job Image Asset (Firmware) — `plasma.opf.job-image-asset.v1`

`{format, sha256, size, load_address, icpn}`. `format` is `binary` only (same
vocabulary as `plasma_core.assets.ProgrammingAssetFormat.BINARY`, the only
validated Image normalizer); a raw binary is one contiguous segment at
`load_address`, so no segment list exists in v1. HEX/SREC/ELF segments require a
new contract version. `verify_image_asset` fails closed unless the bytes
match `sha256`/`size` and the declaration fits the Resource constraints:
same ICPN, `size ≤ max_image_bytes`, `load_address` inside flash and aligned
to `erase_granularity`, end within `flash_size`.

### 3.3 Job Binding — `plasma.opf.job-image-binding.v1`

`{resource_set_sha256, operation, range{address,length}, image_asset_sha256,
ppu_id, site_id, icpn, profile}`; every field enters the canonical SHA256.

| Operation | Image Asset | `range` |
|---|---|---|
| `program`, `verify`, `flash_cycle` | required (`JOB_IMAGE_ASSET_REQUIRED`), must be applicable | exactly the Image range (`load_address`, `size`); a caller-supplied range must equal it (`JOB_RANGE_MISMATCH`) |
| `erase` | refused (`JOB_IMAGE_ASSET_NOT_ALLOWED`); `image_asset_sha256: null` | required (`JOB_RANGE_REQUIRED`); inside flash; start and length aligned to `erase_granularity` (`JOB_RANGE_INVALID`); whole-chip erase = `(flash_base, flash_size)` |
| `read` | refused; `image_asset_sha256: null` | required; inside flash, `length > 0` |

`operation` is selected by the user and must be in `OPERATIONS`
(`JOB_OPERATION_UNSUPPORTED`) and declared by the Resource Profile
(`JOB_OPERATION_NOT_IN_PROFILE`). Addresses are absolute target addresses. v1
has one contiguous range per Job; multi-section reads (Gateway
`map_data.sections`) need a new contract version.
`site_id` must be in the Profile's `sites`.
`verify_job_binding` recomputes the expected binding and accepts only an exact
match (`JOB_BINDING_MISMATCH` otherwise). No PPU Job id exists before
submission; OFE-1B binds the accepted Job id in the receipt.

### 3.4 Derivation from stored bytes

`identity_from_manifest(manifest, read_file)` derives both descriptors from a
programming Bundle v3 manifest and its stored files (ZIP or B3 staged tree,
`identity_from_archive` for ZIP bytes). Every read is SHA256/size-checked
against the manifest, the stored Provider/Profile files are re-validated by the
existing `parse_route`, and the Resource Packages must be byte-identical to the
canonical writer output (`BUNDLE_RESOURCE_NOT_CANONICAL`). It does **not**
replace B3 whole-archive verification. `verify_resource_set(expected, …)` is
the comparison a consumer must use; a descriptor that did not come from
verified bytes is never trusted on its own.

### 3.5 Implementation

`software/python/plasma_opf/bundle_v3.py` (no new module, no Bundle v4, no
`plasma.ppu.bundle.v3` wire change). `ProgrammingBundle` gains informational
`resource_set_sha256` / `image_asset_sha256`, and its `summary()` (the
Manager plan's `bundle` block) states `identity_authority: archive_sha256`.

## 4. What stays authoritative (unchanged)

- One Bundle v3 writer; archive bytes are unchanged (historical Site 2 Bundle A
  `71e9a044…946a` reproduced in tests).
- `archive_sha256` is the only Active Asset Set identity; `activation_required`
  and the post-activation check compare only `archive_sha256`.
- B1/B2/B3, owner authorization, Site lease, PPU-wide execution lease / FPGA
  reload exclusion, SAFE_OFF, SEALED, OUTCOME_UNKNOWN, no Job auto-retry,
  Site 2 STM32F103C8T6 `flash_cycle`: unchanged.
- (OFE-1A only; superseded by §8.2) Gateway `_job_request` did not accept any new identity field (undeclared
  keys rejected); `resolve_active_firmware` refuses a Resource SHA presented as
  an Active Set.

## 5. Replacement / deletion list

| Old | Action |
|---|---|
| Inline Provider/Profile member construction and nested `package()` closure in `build_image_bundle` | **Replaced** by `_resource_members` / `_package_entry` / `_resource_packages`, shared by the writer and the identity derivation (one serialization, no duplicate) |
| `user_image_identity` (`img-<sha16>` Package id, `<profile>-img-<sha12>` name) | **Kept**: it names Bundle v3 Packages, not an identity; v1 forbids using it as one. Candidate for deletion in OFE-1B if the Firmware leaves the Bundle |
| Bundle-embedded Firmware Package (`firmware-asset` in the Active Set) | **Kept** as the only execution path until OFE-1B replaces it |
| Nothing deleted in OFE-1A | No retired path exists yet; deleting the embedded Firmware path is OFE-1B scope |

## 6. OFE-1B minimal integration plan (OFE-1A design; implemented as §8)

1. **PPU verifies the Active Resource Set.** Extend `ppu_asset_set.read_active`
   (or one helper next to `resolve_active_firmware`) to return
   `resource_set_sha256` computed with `identity_from_manifest` over the
   already-verified staged tree (`verify_staged` first). Same B3 Set, same
   generation check before/after. The Manager compares this PPU-reported value
   (never its own claim) with the plan's Resource SHA256.
2. **Independent immutable Job Firmware Asset.** Reuse the Gateway Programming
   Asset path that already exists (`_inline_asset` →
   `ProgrammingAsset.from_upload` → `normalize_image`, `gateway_base.py:420-438,
   557-566`): declared name/type/format/size/SHA256 are checked against the
   bytes. Add only the `image_asset` + `job_binding` descriptors to the Job
   request, as an exclusive third source (not combinable with the Bundle
   reference or legacy inline asset), `max_retries=0`. The Job `operation` is
   the **user-selected** Operation carried in the Binding (not a fixed
   `flash_cycle`); `program`/`verify`/`flash_cycle` carry the Image bytes,
   `erase`/`read` carry only the Binding range. No new staging cache in 1B;
   the Job carries its bytes once.

   **2a. User-selected Operation + Provider Capability Validation.** Console
   offers only Operations declared by the resolved Route Profile; the Manager
   builds the Binding with `job_image_binding(operation=…, address/length)`
   and refuses undeclared Operations before any PPU write. The PPU re-checks
   the same Binding against the Profile of its pinned Active Set **and** the
   Runtime route admission (`ExecutionRouter.resolve_route`): an Operation the
   Profile declares but the Site's Provider route does not implement (today:
   anything except `flash_cycle` on C-3 OpenOCD) fails closed with the
   existing `OPERATION_UNSUPPORTED`. Enabling another Operation on hardware is
   a separate Provider change with its own Gate and HIL evidence; the Route
   parser's `flash_cycle` requirement is relaxed only together with it.
3. **Binding checks at admission.** Inside `SiteManager.enqueue` under the
   existing execution lease (`site_manager.py:479-541`): pin the Active Set,
   re-derive `resource_set_sha256` from it, `verify_job_binding` with this
   PPU's `ppu_id` and the Job `site_id`, `verify_image_asset` over the
   received bytes and the PPU-derived Resource descriptor. Any mismatch →
   `OPERATION_UNSUPPORTED` before the Site Worker starts. The Job's
   `operation` and range (`map_data` for `read`) must equal the Binding's.
4. **No Package mixing.** Provider/Profile/Driver come only from the single
   pinned Active Set; the Job names Provider/Profile ids that must equal the
   Active Set's Packages, and the Resource SHA256 covers their content. A
   Firmware Asset never carries Provider/Profile/Driver/FPGA content.
5. **Crash / cancel / UNKNOWN.** Manager journal stores plan Resource SHA,
   Firmware SHA and binding SHA; Job submission stays exactly-once with the
   existing `OUTCOME_UNKNOWN` latch. Receipt `_verify` adds checks that the PPU
   echoed the same binding SHA256 and Firmware SHA256 (readback SHA256 must
   equal Firmware SHA256 — already enforced). Receipt checks become
   Operation-specific (e.g. `read` returns readback SHA256 of the bound range,
   `erase` reports the erased range; SAFE_OFF required for every Operation).
   No replay.
6. **Firmware-only Job does not reinstall.** Manager computes
   `activation_required = PPU Active resource_set_sha256 ≠ plan resource_set_sha256`
   **only** when the PPU reports a verified Resource SHA256 and the Job uses the
   new Firmware source; otherwise it keeps today's archive comparison. B3 is
   never invoked for a Firmware-only change; `fpga_load` stays `false`.
7. **Single Active Resource Set / FPGA reload lock.** Unchanged: the Active Set
   pointer remains the only Resource authority, and the PPU-wide execution
   lease still excludes activation and FPGA reload for the whole Job.

OFE-1B fix list (known, intentionally not changed in OFE-1A):

- `programming.py:626-627` — the Manager receipt dict literal repeats
  `image_sha256` / `image_size`; the plan-side values are silently overwritten
  by the PPU-reported values, so the receipt does not record both. `_verify`
  still compares them in its checks, so the PASS/FAIL decision is unaffected.
  Fix: distinct keys (e.g. `expected_image_*` vs `reported_image_*`).
- Manager `_submit_once` hardcodes `"operation": "flash_cycle"`; replace with
  the Binding's Operation once 2a lands.

Risks and dependencies for 1B: Runtime + Control-plane redeploy on Z2 (owner
Gate); Gateway request schema addition must be signed under the G13 write
signer path unchanged; `read_active` cost (manifest + 3 small files) on every
admission; existing Bundles whose Profile bytes are non-canonical will be
refused (`BUNDLE_RESOURCE_NOT_CANONICAL`) — only writer-built Bundles qualify;
two-Site HIL evidence (plan §5 item 3) is required before any reuse claim.

## 7. Evidence status

| Item | Status |
|---|---|
| Host-only identity tests (`software/python/tests/test_opf_resource_image_identity.py`) | Host-only |
| Existing Bundle v3 / Site 2 workflow regression tests | Host-only |
| OFE-1B Host-only (`test_ofe1b_resource_reuse_job_image.py`, `test_bundle_programming_workflow.py`) | Host-only PASS |
| PPU-side Resource reuse, Firmware-only Job on Z2, user-selected non-`flash_cycle` Operation on hardware, HIL | **NOT_RUN** |

## 8. OFE-1B Gate 1 — Resource reuse + Operation-aware Job Image (implemented)

Same Programming Resources + different Firmware + user-selected Operation,
without B1/B2/B3, Driver/Provider reinstall or FPGA reload, under a Single
Active Asset Set. No new Bundle schema, Job router, execution engine or
staging store; `plasma.ppu.bundle.v3` is unchanged.

### 8.1 PPU Resource identity (`scripts/ppu_asset_set.py`)

`read_active_resource_identity(product_root)` → `plasma.ppu.active-resources.v1`
`{state: VERIFIED, asset_set_sha256, generation, resource_set, resource_set_sha256}`.
It runs `read_active` (→ `verify_staged`: B3 receipt, every file size/SHA256,
no symlink/extra file), derives the descriptor with `identity_from_manifest`
over **manifest-declared paths only**, and re-reads `active.json`: a changed
pointer or generation fails closed (`ASSET_SET_RESOURCE_ACTIVE_SET_CHANGED`).
EMPTY Set, non-canonical/hand-built Provider-Profile Packages, Packages from
different Bundles (only one pinned Set is read) and a missing `plasma_opf`
(Bootstrap process) all fail closed. Wired by `PackageActionRuntime` into
`SiteManager._active_resource_resolver` (same rule as the Bundle Firmware
resolver: trusted control plane, never from a Job or ZIP).

### 8.2 Job Image source (Gateway `POST /api/jobs`)

A third, **exclusive** Job source (not combinable with the Bundle reference
`asset_set_sha256/asset_package_id/bundle_asset_sha256`, the legacy inline
`asset_name/...`, `session_id`, `offset/length/map_data`):

| Operation | Required fields |
|---|---|
| `flash_cycle`, `program`, `verify` | `site_id, operation, target, provider, profile, job_binding, image_asset, asset_base64` |
| `erase`, `read` | `site_id, operation, target, provider, profile, job_binding` (range only from the Binding) |

The Gateway checks the Binding's self-consistency (schema, Operation, Site,
ICPN, Profile, `image_asset_sha256` = H(`image_asset`)) and the Image bytes via
the existing `ProgrammingAsset.from_upload` → `normalize_image` path (SHA256,
size, `binary` format, payload unchanged). `read` gets exactly one
`map_data` section = the Binding range. `max_retries = 0`. The Operation is
passed through unchanged. The request is still signed through the unchanged
G13 Gateway write path; owner authorization, Site admission and Provider
capability are not bypassed.

 **Job write address (OFE-1B PR-A).** Two addresses are distinct: the
 Profile `flash_base` is only the physical start of the Flash bank; the Job
 Binding `range.address` (= Image `load_address`) is where this Job writes. An
 Image is applicable only when its whole erase window — `size` rounded up to
 `erase_granularity` — starts on an erase boundary inside the bank and ends at
 or before `flash_base + flash_size` (`IMAGE_ASSET_ADDRESS_INVALID`). Execution
 uses only the admitted Binding address, end to end:

 1. `SiteManager._admit_job_binding` stores the verified Binding on the Job;
    the Runtime passes it to `OpenOCDInterface.bind_runtime_job`.
 2. `ppu_opf_reference_openocd.job_flash_window` (preflight and execution)
    re-proves the window against the pinned Bundle Profile and requires the
    Binding's operation, Site, Profile and length to match this Job
    (`JOB_BINDING_RANGE_MISMATCH`, `JOB_FLASH_RANGE_INVALID`).
 3. C-3 `bind_image {session_id, image_sha256, image_size, load_address}`
    (wire `plasma.ppu.site-worker.v3`; the address is mandatory, there is no
    default) — the Worker re-derives the erase window from the session Profile
    and never trusts the Runtime value (`FLASH_RANGE_INVALID`). Concurrent
    Sessions must also agree on the address (`PPU_IMAGE_OR_TARGET_CONFLICT`).
 4. The ABI-v5 Adapter erases, writes, verifies and dumps at that address and
    reports the range it **executed**: erase address/length from OpenOCD's own
    `erased address … (length …)` output (must equal the command; `wrote` /
    `verified` byte counts must equal the Image), write/verify/readback
    addresses from the executed commands. Otherwise `FLASH_RANGE_NOT_OBSERVED`
    (FAIL, SAFE_OFF proven) — never a copy of the request.
 5. The Worker seals the Site (`FLASH_RANGE_NOT_VERIFIED`, existing
    OUTCOME_UNKNOWN contract) if an Adapter PASS reports any other range; the
    Runtime (`run_flash_cycle`) and the Manager receipt (`FLASH_RANGE_MISMATCH`,
    `expected_flash_range` / `observed_flash_range`, Binding echo `range`)
    refuse PASS on any difference.

 A Job without a Binding (inline `asset_base64` or Bundle-reference) is the
 separate legacy contract and writes at `flash_base` explicitly; it is not a
 fallback for a Binding Job. A Manager Resource-reuse Job always carries a
 Binding and its receipt requires the PPU Binding echo, so dropping the Binding
 can never yield a reuse PASS. Console still always plans `load_address =
 flash_base`; user-selected addresses are out of scope (separate Gate 1). Real
 non-base programming is HIL-unqualified.

### 8.3 PPU admission (`SiteManager.enqueue` → `_admit_job_binding`)

Inside the existing PPU-wide execution lease (which excludes Asset activation
and FPGA reload for the whole Job), after pinning `read_active`:

1. resolver output must be `VERIFIED` with the same `asset_set_sha256` and
   `generation` as the pinned Set (`JOB_RESOURCE_ACTIVE_SET_CHANGED`);
2. Job `provider`/`profile` = the Set's Provider/Profile Package ids
   (`JOB_RESOURCE_PACKAGE_MISMATCH`), Job `target` = Profile ICPN;
3. `verify_image_asset` over the received bytes (image Operations) and
   `verify_job_binding` with **this PPU's** `ppu_id` and the Job `site_id`
   against the **PPU-derived** Resource descriptor (`JOB_BINDING_DENIED:<code>`);
4. `read`: the single section must equal the Binding range;
5. then the unchanged `ExecutionRouter`: C-3 OpenOCD admits only
   `flash_cycle`; every other Operation fails `OPERATION_UNSUPPORTED`
   (`C-3 supports only flash_cycle`) and is never rewritten.

All denials are `OPERATION_UNSUPPORTED` before the Site Worker starts.
The accepted Binding is echoed in the Job snapshot as `job_binding`
`{job_binding_sha256, resource_set_sha256, image_asset_sha256, operation,
range, ppu_id, site_id, icpn, profile, asset_set_sha256, generation}`.
`/api/status?site=N` (Site-scoped only) adds `ppu.active_resources`
(`VERIFIED` summary, `UNAVAILABLE` + reason, or `UNSUPPORTED` when not wired).

### 8.4 Manager workflow (`plasma_manager/programming.py`)

Plan `plasma.manager.bundle-programming-plan.v3` requires a user-selected
`operation` (one of `erase/program/verify/read/flash_cycle`; anything else,
including `blank_check`/`probe`, is 400). The Operation must be declared by
the Route Profile (`operation_not_in_profile`, 422). Image Operations take
exactly one **Programming Source**: `image_base64` (Image) or
`bundle_base64` (Bundle); `erase`/`read` take `address`/`length` and no
source. The plan reports `source` = `image` / `bundle` / `range`.

**Bundle source** (Unified Programming Integration, 2026-11-11). The user
supplies their own canonical Bundle v3. `bundle_v3.route_bundle_from_archive`
admits it against the Route resolved from the selected IC and Site only when:

1. the archive is bounded (`MAX_BUNDLE_ARCHIVE_BYTES`, ≤ 64 members) and
   `identity_from_archive` proves manifest / Packages / Files / SHA256;
2. the Bundle's Programming Resource Set — target platform, Provider,
   Profile, driver ABI, transport, FPGA requirement, Operations, Sites and
   flash geometry — is **byte-identical** to the committed Route's
   (`BUNDLE_IC_MISMATCH`, `BUNDLE_TARGET_MISMATCH`, otherwise 422
   `bundle_resource_not_qualified` / `BUNDLE_RESOURCE_NOT_ROUTE`). A Bundle
   declaration never replaces hardware qualification;
3. the shared writer reproduces the exact archive bytes from the Route and
   the Bundle's single Image (`BUNDLE_NOT_CANONICAL`).

A Bundle with several Image Packages or an FPGA Package fails closed with
`BUNDLE_PACKAGE_SET_UNSUPPORTED`: this contract version has neither an Image
selection field nor a Bundle-source FPGA Load path. An admitted Bundle then
takes the same decision table below; on a cache miss B1/B2/B3 carry the
user's own archive bytes (its `archive_sha256` becomes the Active Set). All
Bundle-source denials happen at plan time, before any PPU contact.

| PPU `active_resources` | Bootstrap Active Set | Decision |
|---|---|---|
| `VERIFIED`, same Set, Resource SHA = Route Resource SHA | ACTIVE | **Reuse**: skip B1/B2/B3 (`RESOURCE_REUSE`), no FPGA load |
| `VERIFIED`, different Resource SHA | ACTIVE | Canonical Bundle v3 → B1/B2/B3 (`fpga_load=false`) |
| `UNAVAILABLE` (EMPTY, non-canonical Set) | any | Canonical Bundle v3 → B1/B2/B3 |
| `VERIFIED` but different Set than Bootstrap | — | 409 `active_set_report_inconsistent` |
| `UNSUPPORTED` / unknown state | — | 409 `ppu_runtime_resource_identity_unsupported` |
| status read fails | — | 503 `ppu_resource_identity_unknown` |

Activation needed but no Image (`erase`/`read`) → 409
`resource_activation_requires_image`. Before submission the Manager requires
the Bootstrap Active Set to be the activated archive (or, for reuse, the
Set seen at plan time: `ACTIVE_SET_CHANGED_SINCE_PLAN`) **and** the PPU to
report `VERIFIED` with the plan Resource SHA and the bound `ppu_id`
(`RESOURCE_IDENTITY_NOT_CONFIRMED`). Exactly one `POST /api/jobs` with the
Job Image source; OUTCOME_UNKNOWN latch, no auto-retry, journal (no Image
bytes), SEALED/Recovery: unchanged.

### 8.5 Receipt `plasma.manager.programming-receipt.v2`

Fixes the duplicate `image_sha256`/`image_size` keys (old `programming.py:626-627`).
Distinct fields: `expected_image_sha256/size` (Manager), `observed_image_sha256/size`
(PPU Job result), `readback_sha256`/`bytes_verified`, `expected_/observed_resource_set_sha256`,
`expected_/observed_job_binding_sha256`, `expected_/observed_image_asset_sha256`,
`active_asset_set_sha256`/`active_generation`, `operation`/`target`/`site_id`/`ppu_id`,
`resource_reuse`, `safe_off`/`flash_result`. PASS requires, in order:
SAFE_OFF, an Operation with a qualified receipt (`flash_cycle` only —
others `OPERATION_RECEIPT_UNSUPPORTED`), Job success, Job Site/Operation,
the PPU-echoed Binding (SHA, Resource, Image Asset, Operation, Site, PPU),
expected = observed Image, one attempt, flash PASS, readback = expected SHA,
verified bytes = expected size. HTTP 200/202 or a Provider "success" alone is
never PASS.

### 8.6 Deletion / replacement, deployment and HIL

| Old | Action |
|---|---|
| Manager `_submit_once` hardcoded `operation: flash_cycle` + Bundle reference | **Replaced** by the user Operation + Job Image source |
| Manager receipt duplicate keys / `ALREADY_ACTIVE` archive-only decision | **Replaced** by receipt v2 / PPU-derived Resource decision |
| Gateway/SiteManager Bundle reference + `resolve_active_firmware` | **Kept**: still used by `scripts/plasma_program.py` (CLI) and the root Package Action path; candidate for deletion when those migrate |

Deploy (owner-approved, separate from Gate 2): PPU Runtime + control plane
(`ppu.pyz` with `plasma_server`, `plasma_web`, `plasma_opf`;
`ppu_asset_set.py`), Manager (`plasma_manager`, `plasma_opf`) and Console
together. A new Manager against an old Runtime fails closed (409
`ppu_runtime_resource_identity_unsupported`); it never falls back.

Minimal HIL (NOT_RUN): on Z2 Site 2, (1) Firmware A → `flash_cycle` PASS
(B1/B2/B3 if the Active Set is the old hand-built Set), (2) Firmware B →
plan `RESOURCE_REUSE`, no B1/B2/B3, no FPGA load, Active Set/generation
unchanged, readback = B, (3) a tampered Binding (`ppu_id`) is refused with no
OpenOCD spawn, (4) `erase` is refused `OPERATION_UNSUPPORTED`.
