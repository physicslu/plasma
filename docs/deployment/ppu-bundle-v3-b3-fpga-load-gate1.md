# HISTORICAL Gate 1 Plan — Bundle v3 B3 FPGA Load

> **Term note:** in this document **B1/B2/B3/B4 are Bundle stages** — B1 upload/commit, B2 admission, B3 install/verify, B4 activation (incl. previous-version backup). Not the FPGA/UIO or governance meanings; see [glossary](../glossary.md#b1b2b3).

**Historical evidence; superseded by [current B3 contract](ppu-bundle-v3-generic-assets-gate1.md).**
The 2026-11-02 behavior below records the earlier implementation plan;
P4-02 now requires explicit `mode: "activate"|"stage_only"` and standard
Active selection for verified non-FPGA Bundles. No Z2 acceptance is implied.

**State:** Gate 1 approved by the owner on 2026-11-02 (§3 implementation,
§4 Host-only verification and §4 physical HIL). Gate 2 (merge) is separate.
**Owner decision (2026-11-02):** an explicitly requested B3 of a Bundle that
contains an `fpga-image` Package must also load that FPGA Image. It should not
wait for a separate B4. This revises the boundary in
[Bundle → Packages → Files](../architecture/ppu-canonical-bundle-packages.md)
(PR #1225), where B3 never reconfigures the FPGA.
**Out of scope:** the ABI-v5 SWD RTL sample-point fix (separate Gate 1), DUT
operations, Flash, OpenOCD packaging, publisher signing.

## 1. Problem

The 2026-11-02 physical B1/B2/B3 acceptance proved upload, static FPGA
qualification and file installation (`fpga_loaded=false`, `activation=NOT_RUN`).
A new FPGA Image still needs Route B SSH to install the Manifest and BIN into
the protected Root tree and to run `z2-path2-root-entry download/test`. Most of
the parts already exist on `main` but are not connected:

| Existing part | Location | Status |
|---|---|---|
| B3 content-addressed install | `scripts/ppu-z2-installer-core.py::install_verified_bundle_v3` | Physical PASS |
| Active Set pointer + Runtime Job Quiesce | `assets/active.json`, `hold_asset_activation` ([P1](ppu-single-active-asset-set-gate1.md)) | Host-only |
| FPGA handoff resolution | `resolve_active_fpga_handoff` ([P2](ppu-fpga-asset-handoff-gate1.md)) | Host-only |
| Root format check + files-only staging | `pl/hil/fpga_image_root.py::validate_bundle_fpga_handoff`, `stage_bundle_fpga_files_only` | Host-only, no caller |
| Root load + Identity | `z2-path2-root-entry download|test <pin>` | Physical PASS (ab79b04e) |

## 2. Target behavior

`POST /v1/deployments` with `kind=bundle`, a matching B2 receipt and a new
explicit request field `"fpga_load": true` runs one Coordinator transaction
under the existing `deployment.lock` and `deployment.json` journal:

```text
B3 install/verify (unchanged)
  -> resolve FPGA handoff from the just-installed immutable Set
  -> hold Runtime Job Quiesce (existing socket, connection-held)
  -> Root Entry: bundle-load <asset_set_sha256>
       re-verify staged files + b3-install.json + handoff (Root side)
       hardware-consumer census (existing collect_live; /dev/mem, /dev/uio*, OpenOCD)
       Golden SHA, current boot, FPGA Manager state
       stage BIN/HWH/companion Manifest (stage_bundle_fpga_files_only)
       promote companion -> active Root Image Manifest (atomic, previous kept)
       download  (existing run("download"), Image A -> B allowed)
       test      (existing Identity read, both Site IDs)
  -> atomically publish assets/active.json = this Set
  -> release Quiesce; receipt stage=bundle_install_and_fpga_load
```

**Superseded:** Without an FPGA Package, current standard B3 `mode:activate`
publishes the verified Active Set under Runtime quiescence; `mode:stage_only`
explicitly preserves the old install-only behavior. An FPGA Bundle requires
caller-authorized `fpga_load:true` in `mode:activate`.

### Result states (journal, receipt)

| Outcome | Journal | FPGA state | Active Set | Golden Restore |
|---|---|---|---|---|
| Install + load + Identity PASS | `fpga_loaded` | new Image held | new Set | no |
| Denied before any PL write (busy Job, consumer present, Golden/Boot/pin mismatch, tamper) | `fpga_load_denied` | unchanged | unchanged | no |
| Download failed or uncertain | `recovery_required` | Root journal `UNKNOWN` | unchanged | only by explicit `restore` |
| Download PASS, Identity FAIL | `fpga_identity_failed` | new Image held (Keep Loaded) | unchanged | no (functional FAIL is not a restore trigger) |

## 3. Changes (one PR, every dependent migrated)

| Area | Files | Change |
|---|---|---|
| Protected Root | `scripts/z2/plasma-path2-root-entry`, `pl/hil/fpga_image_root.py` | Add allowlisted `bundle-load <asset_set_sha256>`. Root locates `/opt/plasma/assets/staged/<sha>/` itself (no caller path), re-verifies root ownership and hashes, stages files, promotes the Manifest atomically with backup, then runs the existing download and test. No other new operation. |
| Root handoff | `pl/hil/fpga_image_root.py::validate_bundle_fpga_handoff` | Programming Profile becomes optional (B3 FPGA-only Bundles); everything else unchanged. |
| B3 Coordinator | `scripts/ppu-bootstrap-deployment.py`, `scripts/ppu-bootstrap-service.py`, `scripts/ppu_deploy_api.py` | `fpga_load` request field, journal states in §2, call the Root Entry by fixed path with a timeout, new receipt `plasma.ppu.b3-deployment-receipt.v2`. |
| Active Set | Bootstrap Asset Set helper | Publish `active.json` only after Identity PASS, inside the same Quiesce hold. |
| Manager / Console BFF / Web | Manager bootstrap REST, Console Runtime Deployment / Assets view | An explicit "Install and load FPGA" control; show the v2 receipt (FPGA image, Identity words, journal state). Console never sends `idle=true` or a path. |
| Contracts and docs | `docs/architecture/ppu-canonical-bundle-packages.md`, `docs/deployment/ppu-owner-operation-authorization.md`, `ppu-fpga-asset-handoff-gate1.md`, `ppu-single-active-asset-set-gate1.md`, glossary B1B2B3 | Replace "B3 never loads FPGA" with the §2 rule. |
| Tests / CI | `software/python/tests/test_ppu_*`, `scripts/tests/test_fpga_image_root.py`, Root Entry allowlist tests | See §4. |

Unchanged: B1/B2 (authorization now per-operation, see `ppu-owner-operation-authorization.md`), FPGA static qualification, Root source-pin
model, Golden handling, `download|test|restore` semantics, OpenOCD,
ABI-v5 admission.

## 4. Verification

**Host-only (required before HIL):**
- Positive path with fake Root and fake Runtime: receipt v2, journal sequence,
  and `active.json` published only after Identity PASS.
- Negatives, each proving no PL write and an unchanged Active Set: busy Job; Quiesce
  socket absent; hardware consumer present; staged file tampered after B3; Golden
  mismatch; Boot changed; pin mismatch; Bundle without `fpga-image` but
  `fpga_load=true`; `fpga_load` omitted (install-only path unchanged).
- Download failure leads to `recovery_required`. Identity failure leads to
  `fpga_identity_failed` with the Image kept loaded and no auto-restore.
- Root Entry: `bundle-load` accepts only `<40-hex pin> <64-hex sha>`. Any caller-
  supplied path or extra argument is rejected.
- Existing B3, Bootstrap, Manager and Web CI stay green.

**Physical Z2 HIL (Path: Direct Execution or Path 3; requested in this Gate):**
1. One-time Route B install of the reviewed Root Entry + protected tree at
   the PR HEAD pin, with the previous tree backed up and the Golden SHA verified.
2. Refresh the Bootstrap kit from the same commit (existing single-Z2 R&D refresh).
3. Through the HTTP API only: B1 → B2 → B3 `fpga_load=true` with a Bundle that
   contains the **current** `ab79b04e` Image (re-load of a known-good Image).
   Expect `fpga_loaded`, Identity `0x00050001`/`0x00050002`, and `active.json`
   pointing at the Set.
4. Negatives on hardware: an OpenOCD/`/dev/mem` consumer running leads to
   `fpga_load_denied` with no PL write; a repeated identical B3 is idempotent
   (no second download unless requested).
5. No DUT/SWD operation. Keep the Image loaded at the end. Golden Restore
   only if a download is uncertain.

**Evidence:** HTTP request/response receipts, Coordinator journal, Root journal,
`dmesg` FPGA Manager line, Identity words, Boot ID, before/after SHA of the Root
tree, Golden and the existing OpenOCD installs.

## 5. Risks and safeguards

- **HTTP-triggered PL reconfiguration.** It requires an explicit `fpga_load` field,
  the device-bound Bootstrap pairing, a fresh owner `bundle.activate-fpga-load`
  authorization bound to the current B2 admission, and the
  protected Root pin. It never triggers from upload alone.
- **Active Jobs or OpenOCD during reload.** Runtime Quiesce covers Jobs, and the Root
  `collect_live` census covers `/dev/mem`, `/dev/uio*` and the FPGA device holders.
  Both must pass.
- **Partial state.** A Manifest promotion keeps the previous Manifest. Every
  uncertain write goes to `recovery_required`. There is no implicit rollback.
- **Runtime view of the new Image.** Runtime Site state must be re-admitted after
  reload. B3 v2 reports `runtime_site_readmission=REQUIRED`, and Site execution stays
  blocked until the existing Site admission runs.

## 6. Approval requested

- Gate 1 approval for §3 implementation and §4 Host-only verification.
- Authorization for the §4 physical Z2 HIL: one Route B Root tree/Entry install,
  Bootstrap refresh, and HTTP-triggered FPGA re-load of the known `ab79b04e`
  Image (no DUT).
- Gate 2 (merge) remains separate.

## 7. Implementation notes (as built)

- HTTP request: `POST /v1/deployments` body is now exactly
  `{"kind": "bundle", "upload_id": <32-hex>, "fpga_load": <bool>, "authorization": <owner-operation-authorization>}`
  (authorization added by Stage A, see `ppu-owner-operation-authorization.md`). The old
  `install_only` field is retired (Replace-by-Default); `fpga_load: false` is
  the install-only B3. The device-local `ppu-bundle-install-policy.json`
  (v1) is unchanged and still enables B3 as a whole.
- Coordinator journal states added: `fpga_loading`, `fpga_loaded`,
  `fpga_load_denied`, `fpga_identity_failed`. The last three are safe restart
  states; `fpga_loading`/`activating` interrupted by a crash become
  `recovery_required`. Bootstrap reports `fpga_load_denied` and
  `fpga_identity_failed` as API state `failed` with the Coordinator
  `error_code`; anything it cannot prove stays `recovery_required`.
- Root Entry output: one `PLASMA_BUNDLE_LOAD=<json>` line, exit 0 for
  `fpga_loaded` and 3 for a classified failure. A shell-level `PATH2_*`
  refusal (exit 2, before Python) is classified `fpga_load_denied`; any
  other unparseable result or timeout is `recovery_required`.
- Root stages files and promotes the Manifest (previous kept as
  `plasma-image-manifest.json.previous`) before the full read-only admission
  census; a census denial restores the previous Manifest before returning
  `fpga_load_denied`. Staged firmware files remain (no-overwrite, same SHA).
- `resolve_active_fpga_handoff` (Controller-selected, Active-only) is
  replaced by `resolve_staged_fpga_handoff`.
- Deviation from §4 step 4: a repeated identical `fpga_load=true` B3 is an
  explicit request and therefore downloads again; the Active Set is not
  re-published (`already_active=true`, same generation).
- Deviation from §5: `runtime_site_readmission=REQUIRED` is reported in the
  receipt and shown in the Console, but the Runtime has no existing per-Site
  re-admission gate that blocks execution after a reload. Enforcing that
  block is a Runtime change outside this Gate.

- HIL finding (2026-11-02): `plasma-bootstrap.service` runs with
  `ProtectHome=true`, so the Bootstrap/Coordinator cannot see the Root tree
  under `/root`. The Coordinator therefore starts the Root Entry through
  `systemd-run --wait --pipe --collect` as a transient root unit outside that
  sandbox, and `bundle-load` takes only `<asset_set_sha256>`: the Root Entry
  runs its own root-owned pinned source (the Coordinator had no independent
  pin source anyway). The Bootstrap sandbox is unchanged.
