# ABI-v5 OpenOCD `plasma_swd` → Blue Pill DPIDR HIL Runbook

Status: engineering runbook (Direct Execution / Route B). It records the
procedure first executed on 2026-11-02 and how to repeat it after the FPGA
sample-point fix. It grants no Gate 1 scope, FPGA load, Flash operation or
production qualification by itself.

## 1. Architecture under test

```text
SWPC (CI artifact, SSH helper)
  └─ Route B engineering SSH ──► Z2 PS (root)
        plasma_swd_site_admission.py  ── protected Root tree (pin) G5 live admission
              │ writes /run/plasma-z2-swd05/swd-site<N>-admission (0600, 300 s)
              ▼
        OpenOCD 5088db4c + plasma_swd (PS-local owner)
              │ reload fence LOCK_SH + Site lock, record + live facts per MMIO word
              ▼ /dev/mem one 4 KiB Site page
        PL ABI-v5 Site N engine ──► PMOD ──► Blue Pill SWD
```

| Site | AXI base | PMOD | SWCLK | SWDIO |
|---|---|---|---|---|
| 1 | `0x43C01000` | PMODA JA1/JA2 | Y18 | Y19 |
| 2 | `0x43C02000` | PMODB JB1/JB2 | W14 | Y14 |

The development Blue Pill is wired to **PMODB = Site 2** (owner confirmed
2026-11-02). Confirm the connector on site before every run.

## 2. Preconditions (do not repeat what is already proven)

- The FPGA Image is loaded and held by the protected Root Loader: Root Journal
  `status=IMAGE`, current Boot ID, FPGA Manager `operating`, and the Root
  `test` identity check passes for both Sites (`0x00050001`, `0x00050002`).
- The protected Root tree's hashes match `PROTECTED_FILES` in
  `scripts/z2/plasma_swd_site_admission.py`. When the Root pin changes, update
  those constants in a reviewed commit **before** the next run.
- No `openocd` process is running, and no stale `swd-site<N>-admission` record exists.
- The owner has confirmed DUT supply, common ground, 3.3 V signalling and the
  exact connector.

## 3. Procedure

All Z2 steps run as root through `scripts/z2/hil/abi5_openocd_dpidr/z2run.py`,
which uses the pinned SSH/sudo helper. Templates contain `@...@` placeholders.
Fill them with `sed` into a separate evidence directory. Never edit them in place.

1. **Build (CI).** Push to the PR. The workflow
   `swd-openocd5088-armv7-candidate.yml` builds OpenOCD `5088db4c` + `plasma_swd`
   on ARMv7. It fails if the binary is not ELF32 ARM, if `plasma_swd` is missing,
   if unselected or unadmitted init is not denied, or if a library outside
   libc/libm/libudev/libusb is linked. Z2 has no libftdi1/hidapi.
2. **Verify the artifact.** `gh run download <run> -n plasma-openocd5088-armv7-candidate`,
   then `sha256sum -c` the tarball sidecar, then check `openocd.sha256` and
   `candidate-evidence.json`.
3. **Read-only state.** Run `z2run.py z2_state_ro.py` and save the result. It
   records Boot, Manager, Journal, Root pin, tree hashes and the installed OpenOCDs.
4. **Transfer (Route B).** Z2 cannot pull HTTP from SWPC. Repack the artifact
   (`gzip -dc … | xz -9e > payload.tar.xz`), then run `upload.py payload.tar.xz`.
   The upload is chunked base64 into `/root/.plasma-swd-upload`, and Z2 verifies
   the SHA256.
5. **Side-by-side install.** Fill `deploy_tpl.py` (payload SHA, binary SHA,
   admission SHA, PLASMA SHA, CI run). Install to
   `/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154-plasma-swd-<sha12>`.
   The script refuses to overwrite and rechecks the existing `5088db4c`,
   `9ea7f3d` and Root Entry hashes before and after. It then runs Z2 negatives:
   no Site, no record, non-root and Site 3 must all be denied.
6. **Owner attestation.** Fill `attest_tpl.py` with the Site, connector and
   owner statement. It writes `/root/plasma-swd-electrical/site<N>-attestation.json`
   (0600, 4 h). This is an attestation, never a measurement.
7. **One bounded DPIDR.** Fill `dpidr_tpl.py` (Site, install dir, SHAs). It runs
   the precheck, the admission (`admit <N>`), then OpenOCD with no target, no
   ports, `dap init` and `dpreg 0`, under a 45 s timeout. It then revokes the
   record and post-checks: Journal byte-identical, no OpenOCD process, record
   gone. PASS requires every `SWD DPIDR` and `dpreg 0` value to equal `0x1BA01477`.
8. **Evidence.** Keep every `Z2JSON` output, generated script and
   `EVIDENCE.sha256`. Report PASS/FAIL/NOT_RUN honestly.

No Flash Erase/Program/Verify, FPGA reload or Golden Restore is part of this
procedure.

## 4. Reading failures

On a failed run, `plasma_swd` logs
`run rc=<rc> meta=0x<tag:16|link|attempts|data_valid|ack:3|status:4> levels=…`.

| Observation | Meaning |
|---|---|
| status 2 (NEED_RESET), ACK 0 | DPIDR was sent before the RTL line-reset command. Fixed in `737834890`. |
| status 5, ACK `0b111` | SWDIO high during ACK: no target on that Site/connector, unpowered, or not wired. |
| status 4, ACK `0b100` on the first DPIDR | A valid OK ACK sampled one bit late (see §5). |
| `PS_OWNER_*` denial | Admission, lock or live-fact failure before MMIO. The code names the failed check. |
| `PS_OWNER_STALE_SITE_NOT_RECOVERABLE` | The Site is busy, invalid or uncertain and was left untouched. Manual review required. |

`SAFE_OFF_MODE_OFF_VERIFIED` must appear at the end of every run.

## 5. 2026-11-02 result and open blocker

The binary `fa1dcb7a…` (CI run 41453746037) was deployed, and admission plus
PS-owner attach passed on Sites 1 and 2. **DPIDR: FAIL.** Site 1 returned
ACK `0b111` (no target on PMODA). Site 2 returned ACK `0b100`.

Root cause: `pl/rtl/swd/plasma_swd_transaction_engine.sv` samples SWDIO at the
end of SWCLK HIGH, after the rising edge on which the target changes data. The
target drives ACK[0] from the turnaround clock, and the engine discards that bit
as turnaround. The OpenOCD bitbang reference, used by the earlier DPIDR PASS,
samples before the rising edge. Fixing this needs an RTL sample-point change,
a matching fix to the RTL simulation target model, a new Vivado BIN/HWH/Manifest,
and an FPGA reload under a revised Gate 1.

## 6. After the FPGA fix: can it be loaded through the HTTP API?

**Delivery yes, load no (today).**

| Step | HTTP Bootstrap API (Route A) today | Notes |
|---|---|---|
| B1 upload/commit | Yes | `fpga-image` Package: exactly one BIN, one HWH and one `plasma.fpga.image.v1` Manifest |
| B2 admission | Yes (static) | Needs a reviewed entry for the new image in `ppu-fpga-image-contracts.json`. B2 never loads the FPGA. |
| B3 install/verify | Yes (files only) | Files land in `/opt/plasma/bundles/<name>`. No Active Asset Set. |
| B4 activation / FPGA load | **Not implemented** | `validate_bundle_fpga_handoff` is Host-only and has no production caller |

The fixed FPGA can therefore be delivered and statically qualified through the
HTTP API. The actual load still goes through the protected Root FPGA Loader:
install the reviewed Manifest + BIN into the protected tree, update the Root pin,
then run `z2-path2-root-entry download <pin>` and `test <pin>`. That path uses
Route B (engineering SSH) until a separate Gate 1 implements a Controller-authorized
B4 activation that calls the Root Loader from the immutable Bundle install,
under full Site quiescence and Golden recovery. When the image hash changes,
also update the admission record's expected image identity (the `RELEASE_NOT_ABI5_INDEPENDENT`
check in `plasma_swd_site_admission.py`) in the same reviewed change.

OpenOCD itself remains an engineering module. Packaging it into the Route A
Runtime kit replaces the whole Runtime and is a separate decision.
