# Z2 single-device FPGA deployment: six necessary checks (proposed contract)

Status: **Draft / Host-only implementation**. FPGA Manager load and restore no longer require the fixed UIO index; MMIO identity admission retains the strict legacy mapping check. Real Device Tree/HWH Owner, ABI and HIL remain unverified. Applies to the engineering SWD Site 1 DPIDR smoke test, not Production qualification.

## Three independent transitions

1. **SWPC -> PPU staging**: authenticate the local authorized operator/transport and verify the exact BIN bytes/hash and safe staging path. Staging does not activate the FPGA and must not depend on UIO enumeration, SWD timing or DUT state.
2. **PPU -> FPGA PL activation**: require checks G1–G4, with the existing protected root entry and verified restoration capability. Do not assume an existing implementation can safely skip the current Root Admission.
3. **PS MMIO -> SWD IP -> DPIDR**: require G5–G6 and basic DUT voltage/pin safety; SWD ACK/parity/timeout are test outcomes, not deployment admission gates.

## Six checks

| ID | Necessary check | Required before | Failure |
| --- | --- | --- | --- |
| G1 | Image integrity, FPGA part/board compatibility, reviewed manifest | FPGA load | Reject image |
| G2 | Exclusive FPGA configuration ownership and no active programming operation | FPGA load | Defer load |
| G3 | Original/Golden image verified, recovery loader and restoration route usable | FPGA load | Reject load |
| G4 | Protected loader/root permission, target identity and nonpersistent load | FPGA load | Reject load |
| G5 | Verified physical MMIO address/size, platform identity, owner and nonconflicting access | MMIO activation | Deny MMIO; do not infer ownership from a numeric UIO index |
| G6 | PS adapter ABI, IP identity/version and register map compatible | SWD operations | Deny SWD operations |

**Important exception:** if the loader or recovery implementation uses MMIO/UIO, its actual ownership dependency remains a G3/G4 prerequisite until proved independent. No blanket removal of current checks is permitted.

## Observed mismatch (2026-10-30)

- PR #1189 HEAD: `ab79b04efb2c38401103876043e39d4745284163`.
- PR #1216 HEAD: `be68d264fbdb48e57dbedb7b2d1a0dac49c0f31e`.
- Z2 boot ID: `4cefdc0c-f586-4d19-b126-1d8e1108c8f1`.
- Candidate Manifest expects `uio1` at `0x43c00000/65536`; observed `uio0` maps that region, with device name `43c00000.audio-codec-ctrl`. Observed `uio1` maps `0x40000000/65536` with device name `40000000.fabric`.
- Site 1 SWD IP expected MMIO `0x43c01000`. Its location within the first window does **not** establish exclusive ownership or a valid Device Tree contract.
- `pl/hil/fpga_image_admission.py` currently enforces `uio == release.expected_uio` and further checks: process census, UIO overlap, platform overlap, fabric IRQ, firmware manager provenance and boot consistency.
- Do not simply change `uio1` to `uio0`, remove `check_exact()`, or write to `/dev/mem` to bypass ownership checks.

## Minimal implementation sequence (not yet executed)

1. Inventory the exact Root Loader callers of `collect_live()` and `check_exact()`, plus recovery entry, lock and active-image assumptions.
2. Confirm Vivado HWH AXI mapping, Device Tree ownership and any users of `43c00000.audio-codec-ctrl`. Identify whether an approved nonpersistent PL loader can operate independently of that MMIO owner.
3. Introduce separate **image-load admission** and **MMIO admission** contracts. Preserve G1–G4, including any actual loader/recovery dependency. Require G5–G6 before any MMIO/SWD transaction.
4. Change the manifest/device resolver to bind to verified physical address, region size and platform owner, not a fixed `uioN` index. Re-resolve after FPGA reconfiguration.
5. Add host-only positive/negative tests: swapped UIO numbering with same proven owner; wrong physical base; stale Device Tree owner; conflicting process; mismatched BIN; missing recovery; wrong ABI; changed boot; wrong FPGA part.
6. Only after CI and device-backed preflight evidence, separately authorize one bounded Site 1 FPGA load, MMIO read, DPIDR read and restore experiment.

## Explicit non-goals

No new deployment framework, extra supervisor/relay, production TLS or publisher policy prerequisite for local engineering staging, eight-site production scheduler qualification, DUT Flash write, automatic PR merge, or unsupported TIMING-18 waiver. External SWD timing qualification remains pending after the smoke test.

## Acceptance

- Staging can complete without UIO checks.
- A real load cannot proceed unless G1–G4 and all loader/recovery dependencies are satisfied.
- No MMIO transaction occurs without G5–G6.
- UIO enumeration changes alone cannot create false authorization or false denial when stable device identity is proven.
- Golden/previous-image restore remains verifiable; failures report the earliest actual cause.

## Verified root call chain (main @ a22c9cb0)

Source audit: `pl/hil/fpga_image_root.py`, `pl/hil/fpga_image_admission.py`, `pl/hil/fpga_image_guard.py`, and `scripts/tests/test_fpga_image_root.py`.

- `run(download|test|restore)` -> `_confirm_current()` -> `live_report()` -> `admission.collect_live()` -> `check_exact()`.
- All three operations currently share the same strict UIO/IRQ/platform-owner and process-census admission. Thus a candidate's UIO mismatch blocks **before** `manager_write()`.
- `download` writes `DOWNLOAD_IN_FLIGHT` before `guard.manager_write(candidate)`, then checks `live_report(candidate)`; failure records `UNKNOWN`. `restore` uses the corresponding guarded state path. The `UNKNOWN` fail-closed behavior must remain.
- `test` uses an identity child after `IMAGE` state; this is a distinct MMIO stage. `live_program_session_report()` separately uses `runtime_program_session=True` and must not be used as a shortcut to authorize FPGA reload.
- `guard.manager_write()` writes only a firmware basename through Linux FPGA Manager, then checks `operating` and current-boot load provenance. It does not itself require UIO; the admission caller does.
- `read_image_manifest()` currently mandates `uio_name` and `expected_uio` with an exact index, so fixing only `check_exact()` would leave the schema and identity-child callers inconsistent.

## Minimal code-change boundaries

1. Keep `trusted_local()`, `read_image_manifest()` board/hash validation, `RootZ2TargetPort.exclusive()`, process-conflict prevention, `_confirm_current()` checkpoint and `UNKNOWN` state behavior.
2. Introduce a **pre-load fact check** for G1–G4, using real kernel facts and image/recovery checks without requiring an already-active *candidate* UIO mapping. Do not confuse an old Golden mapping with the candidate's post-load mapping.
3. Before `manager_write(candidate)`, establish a working protected restoration route. A file hash and Manager `operating` alone are insufficient.
4. After load, re-enumerate Device Tree/UIO and validate G5–G6 **before** launching the identity child or SWD driver. Resolve by physical aperture and verified platform owner; reject ambiguous overlaps.
5. Preserve strict legacy behavior for existing callers until a new implementation and negative tests are in place. Do not silently change the meaning of `collect_live()` for WordPort/program sessions.
6. Add tests proving: wrong UIO index but correct proven owner does not falsely fail; wrong owner/base/size and competing consumers do fail; load rejection does not write Manager; a post-load MMIO failure leaves state `UNKNOWN` and does not pretend automatic restore succeeded.

**Current implementation status:** Root admission timing split is implemented and covered by Host-only tests. The legacy manifest and strict MMIO mapping contract remain; G5 Owner proof, G6 real ABI and Z2 HIL are blocked or not run. This source change does not authorize a Z2 FPGA load.
