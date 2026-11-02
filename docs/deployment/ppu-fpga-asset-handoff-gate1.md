# PPU FPGA Image Asset Handoff — P2 Gate 1 (Host-only)

**Decision:** Console explicitly selects one PPU Active Asset Set, an exact FPGA Image, and a Programming Profile. PPU validates the choice; it must never silently select a different Image or Profile. Bundle is an Assets delivery container, never a programming or FPGA-load command.

**Dependencies:** [P0 PR #1245](https://github.com/physicslu/plasma/pull/1245) → [P1 PR #1246](https://github.com/physicslu/plasma/pull/1246) → this P2 Draft. No component is merged without Gate 2.

## First read-only vertical slice

The existing PPU Asset Set helper now supports read-only FPGA Handoff resolution:

1. Independently verify the PPU's single Active Asset Set identity (complete canonical Bundle v3 ZIP SHA256).
2. Match **exact Controller-requested** FPGA Package ID/version and FPGA Image ID/BIN SHA256. Never choose a fallback.
3. Require exactly one **prebuilt BIN + HWH** in the selected FPGA Package; a BIT-only artifact is not directly ready for the current Z2 FPGA Manager.
4. Require a paired FPGA Image Manifest (existing schema: plasma.fpga.image.v1), including exact Image ID, BIN filename/hash, board, FPGA part and protected Recovery claim.
5. Match the requested Programming Profile Package ID, version and its **complete descriptor SHA256**, including all component file digests and internal dependency declarations.
6. Return only relative content-identified file names, source hashes and status VERIFIED_NOT_LOADED. Report Root validation, FPGA install/load, DUT and READY as **NOT_RUN / false**.

### Control sequence

    Console: Active Set SHA, FPGA Image ID/BIN SHA, Profile ID/SHA
                       |
                  PPU Active Set
                       |
               resolve_active_fpga_handoff
                       |
              VERIFIED_NOT_LOADED
                       |
              [FUTURE ROOT HANDOFF]
                       |
            Existing protected FPGA Loader
                       |
             FPGA Manager -> PL -> DUT

The last three transitions are **NOT IMPLEMENTED** in this PR.

## Protected Root Loader compatibility (next Host-only integration slice)

The existing `pl/hil/fpga_image_root.py` now exposes its **same full Image
Manifest parser** as `parse_image_manifest_bytes()`. Its ordinary
`read_image_manifest()` continues to enforce the root-owned, protected
`/lib/firmware/plasma-image-manifest.json` path and then calls this same
parser. The parser still enforces exact board, FPGA part, AXI aperture,
ABI/Identity words, UIO layout, expected maps and Recovery metadata;
there is no second, weaker FPGA format validator.

A new **read-only** `validate_bundle_fpga_handoff()` accepts the PPU
Active Set selection receipt and exact BIN/HWH/Manifest bytes. It checks
the bound Asset Set SHA, Image ID, Package identity, selected Profile
identity, relative file roles, all three byte hashes and the *entire*
Root Image Manifest schema, returning
`ROOT_FORMAT_VERIFIED_NOT_INSTALLED`. It **does not** change the root
manifest, copy files to protected firmware storage, touch FPGA Manager,
run any privileged operation or claim hardware READY.

A future explicit Controller-authorized installation still needs a
protected privileged bridge into the existing Root Loader, with atomic
and crash-safe candidate staging, firmware-name collision prevention,
permission/ownership checks, Golden `base.bin` protection, existing
global FPGA lock and verified Site/PS/PL quiescence. An arbitrary file
path supplied by Console or Bundle must never be treated as Root
authority. The current protected Root Entry's `download|test|restore`
allowlist is **unchanged**; this PR is not a new Root command.

Host-only positive/negative tests cross the **actual** P2 Active Set
resolver with the **existing** Root parser and check bad ABI, UIO,
unexpected Image/Profile/Set IDs, symlink-style path traversal, manifest
duplicates and SHA mismatches. Tests assert neither FPGA Manager
nor protected Root hardware calls execute.

## Reuse the existing protected FPGA Loader

- pl/hil/fpga_image_root.py: protected FPGA Download, full Image Manifest checks, Identity Test, guarded Restore.
- pl/hil/fpga_image_guard.py: root-only /lib/firmware files, exclusive FPGA Manager owner, physical provenance.
- pl/hil/fpga_image_admission.py: live boot, UIO/driver, proc owner census and MMIO admission.
- Golden Recovery base.bin remains independently protected **outside the incoming Asset Set**. Console cannot replace it through a Bundle.

A future privileged Asset Handoff must move only the independently verified BIN/Manifest into the existing Root-protected inputs **without** weakening Source Pin, Manifest schema, root ownership or FPGA Manager guards. It must prove every Site Job **and separate PS/PL/kernel hardware consumer** quiesced before the Controller's explicit FPGA Configuration request. The P1 cross-process Job lease is necessary but not sufficient for hardware readiness.

No new Installer, Loader, daemon, special Smoke/F1-B product directory, FPGA reconfiguration API or on-wire command is introduced here.

## Scope and evidence

Only Host-only resolution, integrity and negative tests are within this PR. This does **not** qualify arbitrary SWD Image ABI/clock/electrical timing, physical Blue Pill DPIDR, eight-Site execution, production Publisher authorization, Root hardware operations, recovery on Z2 or real IC programming. No Z2 deployment, FPGA loading, DUT action or merge.
