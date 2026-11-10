# OPF Programming Resource Set / Job Firmware Asset Identity v1 (OFE-1A Gate 1)

Status: **Contract v1, Host-only.** Informational identity only. It is **not**
an execution, activation or admission authority. Resource reuse is **not**
implemented and must not be claimed until OFE-1B passes its own Gate.

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
| `firmware_package_kind` | Bundle v3 kind of the Job Firmware Package (route data, e.g. `firmware-asset`); may not be a Resource kind |
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

Driver: the current route-built Bundle has no Driver Package. The Driver is
identified by `abi.driver_abi` (also inside the Profile capabilities file whose
SHA256 is pinned); the actual Driver ABI is still verified by the PPU at Job
time. FPGA: current routes require `fpga_package: null`; FPGA-bearing Resource
Sets are representable in the descriptor but `identity_from_manifest` refuses
them (`BUNDLE_PACKAGE_SET_UNSUPPORTED`) until a reviewed contract version
covers them.

### 3.2 Job Firmware Asset — `plasma.opf.job-firmware-asset.v1`

`{format, sha256, size, load_address, icpn}`. `format` is `binary` only (same
vocabulary as `plasma_core.assets.ProgrammingAssetFormat.BINARY`, the only
validated Image normalizer); a raw binary is one contiguous segment at
`load_address`, so no segment list exists in v1. HEX/SREC/ELF segments require a
new contract version. `verify_firmware_asset` fails closed unless the bytes
match `sha256`/`size` and the declaration fits the Resource constraints:
same ICPN, `size ≤ max_image_bytes`, `load_address` inside flash and aligned
to `erase_granularity`, end within `flash_size`.

### 3.3 Job Binding — `plasma.opf.job-firmware-binding.v1`

`{resource_set_sha256, firmware_asset_sha256, ppu_id, site_id, icpn, profile}`.
`site_id` must be in the Profile's `sites`; Firmware must be applicable.
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
`resource_set_sha256` / `firmware_asset_sha256`, and its `summary()` (the
Manager plan's `bundle` block) states `identity_authority: archive_sha256`.

## 4. What stays authoritative (unchanged)

- One Bundle v3 writer; archive bytes are unchanged (historical Site 2 Bundle A
  `71e9a044…946a` reproduced in tests).
- `archive_sha256` is the only Active Asset Set identity; `activation_required`
  and the post-activation check compare only `archive_sha256`.
- B1/B2/B3, owner authorization, Site lease, PPU-wide execution lease / FPGA
  reload exclusion, SAFE_OFF, SEALED, OUTCOME_UNKNOWN, no Job auto-retry,
  Site 2 STM32F103C8T6 `flash_cycle`: unchanged.
- Gateway `_job_request` does not accept any new identity field (undeclared
  keys rejected); `resolve_active_firmware` refuses a Resource SHA presented as
  an Active Set.

## 5. Replacement / deletion list

| Old | Action |
|---|---|
| Inline Provider/Profile member construction and nested `package()` closure in `build_image_bundle` | **Replaced** by `_resource_members` / `_package_entry` / `_resource_packages`, shared by the writer and the identity derivation (one serialization, no duplicate) |
| `user_image_identity` (`img-<sha16>` Package id, `<profile>-img-<sha12>` name) | **Kept**: it names Bundle v3 Packages, not an identity; v1 forbids using it as one. Candidate for deletion in OFE-1B if the Firmware leaves the Bundle |
| Bundle-embedded Firmware Package (`firmware-asset` in the Active Set) | **Kept** as the only execution path until OFE-1B replaces it |
| Nothing deleted in OFE-1A | No retired path exists yet; deleting the embedded Firmware path is OFE-1B scope |

## 6. OFE-1B minimal integration plan (design only; not implemented)

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
   bytes. Add only the `firmware_asset` + `job_binding` descriptors to the Job
   request, as an exclusive third source (not combinable with the Bundle
   reference or legacy inline asset), `flash_cycle` only, `max_retries=0`.
   No new staging cache in 1B; the Job carries its bytes once.
3. **Binding checks at admission.** Inside `SiteManager.enqueue` under the
   existing execution lease (`site_manager.py:479-541`): pin the Active Set,
   re-derive `resource_set_sha256` from it, `verify_job_binding` with this
   PPU's `ppu_id` and the Job `site_id`, `verify_firmware_asset` over the
   received bytes and the PPU-derived Resource descriptor. Any mismatch →
   `OPERATION_UNSUPPORTED` before the Site Worker starts.
4. **No Package mixing.** Provider/Profile/Driver come only from the single
   pinned Active Set; the Job names Provider/Profile ids that must equal the
   Active Set's Packages, and the Resource SHA256 covers their content. A
   Firmware Asset never carries Provider/Profile/Driver/FPGA content.
5. **Crash / cancel / UNKNOWN.** Manager journal stores plan Resource SHA,
   Firmware SHA and binding SHA; Job submission stays exactly-once with the
   existing `OUTCOME_UNKNOWN` latch. Receipt `_verify` adds checks that the PPU
   echoed the same binding SHA256 and Firmware SHA256 (readback SHA256 must
   equal Firmware SHA256 — already enforced). No replay.
6. **Firmware-only Job does not reinstall.** Manager computes
   `activation_required = PPU Active resource_set_sha256 ≠ plan resource_set_sha256`
   **only** when the PPU reports a verified Resource SHA256 and the Job uses the
   new Firmware source; otherwise it keeps today's archive comparison. B3 is
   never invoked for a Firmware-only change; `fpga_load` stays `false`.
7. **Single Active Resource Set / FPGA reload lock.** Unchanged: the Active Set
   pointer remains the only Resource authority, and the PPU-wide execution
   lease still excludes activation and FPGA reload for the whole Job.

Risks and dependencies for 1B: Runtime + Control-plane redeploy on Z2 (owner
Gate); Gateway request schema addition must be signed under the G13 write
signer path unchanged; `read_active` cost (manifest + 3 small files) on every
admission; existing Bundles whose Profile bytes are non-canonical will be
refused (`BUNDLE_RESOURCE_NOT_CANONICAL`) — only writer-built Bundles qualify;
two-Site HIL evidence (plan §5 item 3) is required before any reuse claim.

## 7. Evidence status

| Item | Status |
|---|---|
| Host-only identity tests (`software/python/tests/test_opf_resource_firmware_identity.py`) | Host-only |
| Existing Bundle v3 / Site 2 workflow regression tests | Host-only |
| PPU-side Resource verification, Firmware-only Job, HIL | **NOT_RUN** (OFE-1B) |
