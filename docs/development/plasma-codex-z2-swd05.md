# PLASMA Z2 SWD-05 one-shot: SSH, internal HIL01/HIL02, supervised base restore

**Issue #981. Gate 1 approved. Gate 2 merge approval required before any real hardware action.**

## Exact approved scope

One Z2 ARMv7 **four-aperture SWD-03 internal-only** candidate:
- Source Git SHA: `d39e85194f27e20f0ae7f2eb7c0623b293ff1108`
- Expected Build ID: `d39e85194f27e20f0ae7f2eb7c0623b2`
- Candidate BIN SHA256: `8f105de35bbe9a8c05c78e8318fcd06d3003a400978c7242c9f01d1346e47a64`
- Original recovery base.bin SHA256: `c6768695213c4a9725108351310dc2e23fa4029dbfe9120e155c676cce89e19c`
- Original base.hwh SHA256: `222898ef2c0ccc4a0c47608e99d8dc7c9c6cdfed5130964884ff35005827ef3a`

These constants come directly from `pl/hil/swd04/contract.py`. They are not interchangeable with PSPL-02 three-aperture or LT02 five-aperture images. Actual earlier Z2 HIL01, HIL02 and FPGA base restoration are recorded in `docs/evidence/mmio-development/2026-10-16.md`; **that historic PASS is not a fresh test**.

The owner explicitly prohibited external DUT, USB Hub power, JTAG reset, Flash Erase/Program. This code only uses Z2 FPGA Manager candidate/base load and the **existing** production `LinuxMMIO` + `SWDTransactionDriver` on the internal fixture; no physical SWD pins or IC operations. UART login is non-blocking and NOT RUN.

## Architecture

- SWPC hardware-capable worker: `scripts/plasma-codex-z2-swd05.py`, fixed reviewed code, existing private Z2 SSH password and pinned known_hosts key, **separate root-only route configuration**. No passwords in command arguments, Actions logs, local tmux or artifact.
- Host source verification: before attempting Z2 sudo, compute local reviewed SHA256 of all target supervisor/SWD-04 and production MMIO imported Python modules and check remote counterpart hashes, remote root UID, no group/world write, and remote source root root ownership. This does NOT stage source or target firmware.
- Z2 privileged supervisor: `pl/hil/swd04/one_shot.py`, root-owned private evidence directory and exclusive supervisor lock; exact CPython 3.12.13 ARMv7 runtime and known-good source/firmware/recovery hashes. Checks original FPGA Manager `operating`, original current-boot FPGA Manager load provenance `base.bin`, FCLK0 100 MHz/enabled, service states, UIO/driver and retained mappings. Existing `development.check_ownership` refuses conflicting UIO and other PL consumers; **no automatic driver unbind, service restart or privilege escalation**.
- Only with all gates passing does it write the reviewed candidate **basename** to FPGA Manager. Immediately records a current-boot root-protected load receipt. Invokes existing `native_qualify` **in separate child processes**: HIL01 identity, then HIL02 6 CONTROL/STATUS echoes and SWD-05 synthetic DPIDR `0x2BA01477`. These may SIGBUS/stall in the kernel; Python timeout or signals do NOT make the hardware safe.
- Before any candidate-load attempt, the supervisor marks recovery required. On normal errors, child signal termination (including SIGBUS) or stage failure, it attempts original `base.bin` restoration **only after checking no retained active PL consumer**. A still-unreaped stuck child makes reconfiguration unsafe; fail closed, require independent physical recovery, never claim automated restoration.
- After load-back, re-check current FPGA Manager provenance, `operating`, original boot ID, service and UIO/driver observations, FCLK0 and PL ownership. Overall internal-development PASS requires original FPGA restoration observed. This does not constitute external SWD or 8-Site qualification.

**Important limitation:** If current original `fabric` UIO kernel driver or any process maps the candidate aperture, the ownership check will **NO-GO** before FPGA load. It is not acceptable to quietly unbind a shared-service driver to obtain a green result. Such a change requires a revised Gate 1.

## Private source/artifact route provisioning — after Gate 2

Z2 must already contain approved artifacts and the exact reviewed source in root-owned, non-group/world-writeable directories. The source tree should be staged through a separately controlled trusted deployment procedure; SSH route enrollment does not install or copy code, and the Runner cannot infer SWPC private artifact paths.

On SWPC, operator in a trusted terminal may run:

`sudo -u plasma-codex -H python3 scripts/plasma-codex-z2-swd05.py --enroll`

This asks once for these **actual Z2 absolute paths**:
- `source_root`: reviewed Z2 source root under `/opt/plasma/`, containing `pl/hil/swd04/one_shot.py` and existing dependencies and `software/python/plasma_interfaces` (all match the pinned GitHub checkout; remote owned by root).
- `candidate_bit`, `candidate_hwh`, `manifest`: the exact pinned SWD-03 four-aperture files already retained on Z2.
- `candidate_bin`: pinned raw Zynq FPGA-Manager BIN directly under `/lib/firmware/`, not BOOT.BIN, not .bit.
- `recovery_bin`: original pinned `base.bin` directly under `/lib/firmware/`, plus `recovery_hwh` original `base.hwh`.
- `output`: fresh unique private directory below `/root/`; its parent must exist and be root-owned/non-group-writeable.
- `sudo_password`: Z2 sudo credential entered via hidden getpass; not assumed equal to SSH password, never posted to GitHub.

Worker file: `<dedicated-worker-home>/.config/plasma/z2-swd05-oneshot.json`, 0600; enrollment does not overwrite. If it is absent, invalid or remote source/artifacts are not staged and pinned, **NO_GO**; do not guess values or weaken checks. Development default `xilinx` SSH credentials are already separately enrolled; no recopy.

Before Gate 2, **do not enroll or dispatch unless expressly authorized as part of a trusted operator setup**. GitHub Actions PR events always run **hosted offline contract tests only**, not remote Z2 or Worker execution.

## Exact post-merge owner dispatch

Only after a separate explicit Gate 2 approval, the exact trusted physicslu owner comment on Issue #981 may trigger:

`/plasma-codex z2-swd05 981`

GitHub-hosted `authorize` confirms sender/comment/issue/repository and pins the latest reviewed main SHA; `oneshot` executes only this fixed pinned source on `SWPC-plasma-codex`.

View the run while active:

`tmux -S /run/plasma-codex/z2-swd05-<RUN_ID>.sock attach-session -r -t plasma-z2-swd05-<RUN_ID>`

Read-only observer displays only sanitized stages. Output artifact includes `report.json`, `exit_code` and `SHA256SUMS` (hashes protect artifact file integrity, not physical FPGA state). Root-local detailed HIL output remains on Z2 and must not be published raw to GitHub; a missing result/return status is a blocker, never PASS.

## Acceptance, rollback and unresolved risks

- `PASS_DEVELOPMENT_INTERNAL_FIXTURE`: verified candidate load, HIL01 + HIL02 via production driver, original base image reloaded, service/UIO/clock/ownership restored. Only one internal Site.
- `NO_GO`: missing route/secret/artifact/source, wrong firmware, stale/protected source mismatch, active UIO/shared consumer, absent recovery or failed preflight. No PL action occurs if blocked before load.
- `FAIL_OR_BLOCKED`, `FAIL_OR_UNKNOWN`: runtime failure or partial/uncertain recovery. No pass claim and no automatic rerun after any MMIO failure.
- FPGA/SOC hangs, Linux reboot, loss of SSH or a kernel D-state MMIO child may defeat in-process `finally` and remote timeouts. This prototype cannot guarantee physical recovery. **Independent, tested power/console rescue remains necessary for stronger qualification.** No USB Hub power/reset recovery is performed by this design.
- Verification of candidate image provenance remains a pinned-file + current-boot FPGA Manager load log + readback ID check, not an attestation of physical silicon contents.
- Manual or automatic use of prior common UIO/fabric ownership cannot be assumed safe; do not modify shared services or unbind drivers automatically.

Current code is a Gate 1 software candidate. **No fresh physical SWD-05, MMIO, FPGA load or restoration operation is claimed by host CI.**
