# ABI-v5 OpenOCD `plasma_swd` → Blue Pill DPIDR HIL Runbook

Status: engineering runbook (Direct Execution / Route B). It records the
procedure first executed on 2026-11-02, how to repeat it after the FPGA
sample-point fix, and (§8) the #1252/#1266 privileged-code-root contract that
the templates follow since 2026-11-03, and (§9) the Blue Pill Flash procedure
and adapter contract of PR #1285. It grants no Gate 1 scope, FPGA load, Flash
operation or production qualification by itself.

## 1. Architecture under test

```text
SWPC (CI artifact, SSH helper)
  └─ Route B engineering SSH ──► Z2 PS (root)
        OpenOCD 5088db4c + plasma_swd (PS-local owner)
              │ reload fence LOCK_SH + Site lock; once: FPGA Manager operating +
              │ Root journal IMAGE in this boot; Site ID; no per-word file checks
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
- The #1252 privileged code root `/opt/plasma/privileged/fpga-root` is
  installed and `ppu_privileged_source.py` reports `VERIFIED_NOT_EXECUTED`
  (file SHA256 is checked at install time; there is no Git source pin or
  `PROTECTED_FILES` table any more). The Root journal is
  `/var/lib/plasma-privileged/fpga-deployment-state.json` and every ancestor
  is root-owned and not group/other writable (#1266).
- No `openocd` process is running.
- The owner has confirmed DUT supply, common ground, 3.3 V signalling and the
  exact connector. Since PR #1285 this is an operator step only: no attestation
  file is written or checked, and DUT voltage is not measured.

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
   records Boot, Manager, Root journal and its ancestor chain, Root Entry,
   privileged code manifest and verification, the installed Bootstrap's
   Owner Operation Authorization module (and any leftover retired Bundle
   Authority v2 file) and the installed OpenOCDs.
4. **Transfer (Route B).** Z2 cannot pull HTTP from SWPC. Repack the artifact
   (`gzip -dc … | xz -9e > payload.tar.xz`), then run `upload.py payload.tar.xz`.
   The upload is chunked base64 into `/root/.plasma-swd-upload`, and Z2 verifies
   the SHA256.
5. **Side-by-side install.** Fill `deploy_tpl.py` (payload SHA, binary SHA,
   admission SHA, PLASMA SHA, CI run, and `@ENTRY_SHA@` = the installed Root
   Entry from step 3). Install to
   `/opt/plasma/programming-engines/openocd/0.12.0-5088db4c9154-plasma-swd-<sha12>`.
   The script refuses to overwrite and rechecks the existing `5088db4c`,
   `9ea7f3d` and Root Entry hashes before and after. It then runs Z2 negatives
   that never reach Site MMIO: no Site, non-root and Site 3 must all be denied.
6. *(Retired by PR #1285: the owner electrical attestation file.)*
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
| `PS_OWNER_*` denial | Lock or loaded-Image precheck failure before MMIO (`PS_OWNER_PL_IMAGE_NOT_LOADED`, `PS_OWNER_SITE_LOCK_UNAVAILABLE`, …). The code names the failed check. |
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

## 6. Loading the fixed Image through the HTTP API (B3 `fpga_load`)

Since PR #1261, Bundle v3 B3 with `fpga_load=true` loads an FPGA Image through
the protected Root Entry (`bundle-load <asset_set_sha256>`). The Root still
admits only reviewed Images:

| Trust point | File | What must list the Image |
|---|---|---|
| B2 static qualification | `scripts/ppu-fpga-image-contracts.json` (Bootstrap) | BIN/HWH/Manifest SHA-256, identities, geometry |
| Root devmem backend | `DEVMEM_INDEPENDENT_IMAGES` in `pl/hil/fpga_image_admission.py` (protected tree) | `image_id` → BIN SHA-256 |
| Site admission | `scripts/z2/plasma_swd_site_admission.py` | reads the same table from the privileged code root |
| Golden recovery | `GOLDEN_RECOVERY_*` in `pl/hil/fpga_image_guard.py` (protected tree) | nothing: the Manifest must restate `base.bin` / `c6768695…e19c` exactly (Stage B-1) |
| B2/B3 operation authorization | per-request `plasma.ppu.owner-operation-authorization.v1` from the paired client | nothing pre-listed; each request binds device, exact Bundle SHA-256, transaction and action |

The current Image is `z2-independent-swd-v5-d0add58c` (PR #1285 head
`d0add58c3`, Vivado Host Build run 41648270405: adds `0x68 IDLE_CYCLES`).
Its paired Manifest is
`pl/hil/releases/swd-independent-d0add58c/plasma-image-manifest.json`. The BIN
is the bootgen-equivalent Zynq word-swapped payload of the run's
`system_wrapper.bit` plus the trailing `0x20000000` NOP word. The earlier
sample-point Image `bd976140` (PR #1255) is retired: the current adapter
writes `0x68`, which that Image rejects.

To load a newly listed Image: refresh the Bootstrap and re-provision the
privileged code root from it (§8), then run B1 → B2 → B3 `fpga_load=true` over
HTTP with the paired client (`BootstrapAPIClient` issues a fresh owner
authorization for each stage; no Bundle SHA-256 is pre-listed on the device). The DPIDR procedure in §3 then runs with
`@IMAGE_ID@` set to the loaded Image.

OpenOCD itself remains an engineering module. Packaging it into the Route A
Runtime kit replaces the whole Runtime and is a separate decision.

## 7. 2026-11-03 result: DPIDR PASS on Site 2

Image `z2-independent-swd-v5-bd976140` was loaded through HTTP B1 → B2 → B3
`fpga_load=true` (Identity PASS, Root pin `f56f85fd7`). The first OpenOCD run
(binary `fa1dcb7a…`) read `SWD DPIDR 0x1ba01477` and then failed in `dap init`:
OpenOCD `dap_dp_init()` queues a DP CTRL/STAT read with a NULL destination,
which the FIFO core rejected at queue time (no wire transfer, so no `run rc=`
line). After the fix (binary `800213ae…`, CI run 41484966257), Site 2 returned
`SWD DPIDR 0x1ba01477` and `dpreg 0 = 0x1ba01477`, with
`SAFE_OFF_MODE_OFF_VERIFIED`, the Journal unchanged and the record revoked.
That run used the retired Root pin `f56f85fd7`; see §8 for the current contract.

## 8. #1252 / #1266 contract and 2026-11-03 migration

PR #1252 retired the Path 2 Git source pin (`/root/plasma-path2-approved`,
`.plasma-path2-source-commit`, `PROTECTED_FILES`). PR #1266 moved the Root
journal out of the runtime-owned `/var/lib/plasma` (uid `plasma`), whose owner
could otherwise rename or replace a root-owned child directory.

| Item | Path / value |
|---|---|
| Root Entry | `/usr/local/libexec/plasma/z2-path2-root-entry`: `download\|test\|restore` (no argument), `bundle-load <asset_set_sha256>` |
| Privileged code root | `/opt/plasma/privileged/fpga-root`, `.plasma-privileged-code.json` (root `0600`), 5 code files |
| Root journal | `/var/lib/plasma-privileged/fpga-deployment-state.json` (dir root `0700`, file `0600`) |
| Bundle authority | Retired after this contract: per-request Owner Operation Authorization (`ppu-owner-operation-authorization.md`). The Z2 file `/etc/plasma/ppu-bundle-authority.json` (v2) stays in place but unused until an approved Bootstrap refresh |
| Site admission record | schema `plasma.swd.ps-admission.v2` (`trusted_code_sha256`, code-manifest stat identity) |
| OpenOCD | must be built from a tree containing #1266 (ps_owner reads the new journal path) |

Migration order used on 2026-11-03 (Route B, one root script with automatic
rollback; evidence `.work/z2-1252-migration-20261103/`):

1. Read-only preflight (old pin/tree/entry/journal, Manifest, Golden, no
   `/dev/mem`/uio/fence holders, no OpenOCD, Bootstrap idle, ancestors root).
2. Back up Root Entry, Bundle Authority v1, `/opt/plasma/bootstrap` and the old
   journal under `/var/backups/plasma-1252-migration-<ts>/` (root `0700`).
3. Bootstrap refresh-only from the CI factory kit (all files == SHA256SUMS).
4. Bundle Authority v2, generation 1, empty list (deny by default). *(Historical:
   superseded by Owner Operation Authorization; not part of future migrations.)*
5. `ppu-privileged-source-install.py` (refuses to overwrite) and
   `ppu_privileged_source.py` → `VERIFIED_NOT_EXECUTED`.
6. Create `/var/lib/plasma-privileged` and **copy** the old journal (the old
   tree is kept for rollback, never deleted in this step).
7. Install the new Root Entry from the Bootstrap copy.
8. Validate the new Root reads the copied journal; old entry syntax denied;
   restart `plasma-bootstrap`.
9. Install the new OpenOCD side by side (`deploy_tpl.py`).

Rollback: restore the backed-up Root Entry, Bundle Authority v1 and Bootstrap,
then restart `plasma-bootstrap`. The old tree and its journal are intact, but
the new journal is authoritative after the first new-contract FPGA operation.

Result (main `7746822f4`, Bootstrap kit run 41568139965, OpenOCD `954344c5…`
from run 41565552942): all migration steps PASS; B2 of an unapproved Bundle was
denied with `BUNDLE_AUTHORITY_DIGEST_NOT_APPROVED`; HTTP B1 → B2
`STATIC_QUALIFIED` → B3 `fpga_load=true` reloaded `z2-independent-swd-v5-bd976140`
with `IDENTITY_PASS`, receipt v2 and Active Set generation 3; Site 2 admission
v2 + OpenOCD read `SWD DPIDR 0x1ba01477` and `dpreg 0 = 0x1ba01477` with
`SAFE_OFF_MODE_OFF_VERIFIED`, journal unchanged and record revoked. No Flash
operation or Golden Restore. Electrical state is an owner on-site attestation,
not a measurement.

## 9. 2026-11-03: Blue Pill Flash through `plasma_swd` (PR #1285) — PASS

### Adapter contract (OpenOCD 5088 `struct swd_driver`)

The adapter executes what OpenOCD queues and reports the exact outcome;
ADI policy (reconnect, sticky-error handling, posted reads) stays in OpenOCD.

| Duty | Behaviour |
|---|---|
| `read_reg`/`write_reg` | Queued (256 entries, one 1-KiB TAR block); a full queue is executed immediately, its failure is also returned by the next `run()` |
| `run()` (PR #1287) | Pipelined: up to 16 commands outstanding in the RTL command FIFO, completions consumed in order. Mid-batch WAIT: drain, ABORT, re-push from the waited command (relies on ORUNDETECT; a later OK completion is reported, never retried). PARITY/TIMEOUT/ABORT: `CONTROL=4` discards unexecuted commands before RW1C `ERROR` |
| `ap_delay_hint` | AP transfers use `max(8, hint)` (≤ 255) trailing idle clocks via `0x68 IDLE_CYCLES`, written only on change |
| ACK WAIT | Completion popped, DP ABORT `0x1E`, same transfer retried (64 max, then blocked) |
| ACK FAULT, no ACK, NEED_RESET | Completion popped, error returned, Site stays usable so OpenOCD can reconnect |
| PARITY / TIMEOUT / ABORT | As above, plus RW1C `ERROR` to clear the RTL fault latch |
| No completion, tag mismatch, CONFIG, MMIO failure | Fail closed (Site blocked) |
| `adapter speed` | `HALF_PERIOD = ceil(50000 / kHz)` (4…65535); default 500 kHz from `plasma_swd site N` unless set. `target/stm32f1x.cfg` sets 1000, so pass `adapter speed 500` after sourcing it |
| Completion tags | 16-bit, wrap 65535 → 1 (one command in flight) |

### Procedure

Templates in `scripts/z2/hil/abi5_openocd_flash/`:

- `act_tpl.py` (Z2, root): one OpenOCD session per action
  (`dpidr|erase|write|verify|read`), `init; halt; poll off; sleep 300; <action>;
  sleep 300; shutdown`. The two SWCLK-idle gaps mark the action. `read` dumps
  the Flash, then `reset run`.
- `la_action.py` (SWPC): arms the LA2016 (50 MHz, CH0 rising trigger, 3 s),
  runs one action through `z2run.py`, and crops exactly 200 ms starting 1 ms
  before the first CH0 edge after the first ≥ 250 ms gap.

Run order: DPIDR → erase `0x08000000 0x4c00` → write → verify → read + reset
→ USB CDC heartbeat on SWPC (`cdc_heartbeat.py after_reset`).

### Result

Image `d0add58c`, OpenOCD `plasma-swd-b916b9f3f9bd` (CI run 41663509036,
source `4f107b10d`), 500 kHz: DPIDR `0x1ba01477`; erase 0.454 s; write 18,768 B
0.758 s; verify 0.062 s; readback `8d3ffb02…`; 14 heartbeats in 6 s after
reset. LA2016 + sigrok SWD decode: every request ACK OK, 0 WAIT/FAULT,
54 clocks per transaction, 2.000 µs period, SWCLK active ~76 % during
write/read (ST-LINK reference: 1,288 WAIT, 86 %). Evidence (local):
`.work/z2-bluepill-heartbeat-flash-20261103/`.

## 10. 2026-11-04: pipelined adapter and `reset halt` (PR #1287) — PASS

Whole flow in **one** OpenOCD session (`flow_tpl.py`), LA2016 recording the
entire flow continuously (`la_full.py`, 50 MHz, 8 s, ~1.6 MB `.sr`):
`init; reset halt; poll off; flash probe` → DPIDR → erase → write → verify →
read → `reset run`, separated by 300 ms SWCLK-idle gaps.

**Use `reset halt`, not `halt`.** With `halt` the write failed whenever the
heartbeat firmware was running when halted (100 % correlation over 13 runs,
pipelined and non-pipelined alike): the stm32f1x async algorithm never
started (`rp` stayed at the FIFO start, `timeout waiting for algorithm`), with
the application's clocks/peripherals still configured. After a SYSRESETREQ
`reset halt` it passed 5/5 from a running firmware. CPU then runs at 8 MHz
HSI, so on-target write/verify algorithms are slower than after `halt`.

Same flow, 500 kHz, SWCLK active fraction per action (LA, sigrok-decoded,
every request ACK OK):

| Action | Non-pipelined `b916b9f3` | Pipelined `b8a7db67` |
|---|---|---|
| erase | 453 ms | 436 ms (Flash BSY polling dominates) |
| write 18,768 B | 755 ms, 77 % | **686 ms, 93 %** |
| verify | 291 ms, 75 % | 286 ms, 84 % |
| read (dump) | 665 ms, 77 % | **530 ms, 96 %** |
| requests / ACK | 13,398, all OK | 14,146, all OK |

ST-LINK reference: 86 % (program), 94 % (verify) at 100 kHz.
