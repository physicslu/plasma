# PLASMA Issue #981 — reproduce working Codex hardware capabilities

**Gate 1 approved for source, SWPC access migration and bounded nondestructive verification. Gate 2 required for merge.**
No additional HIL Gateway, Controller, device driver or REST API.

## Previous proof and gaps

- [Z2 Codex HIL assignment](codex-z2-hil-development-command.md) documents owner-authorized SSH/UART, Z2 account and a local private SSH/sudo credential interface. **Credentials are not in the repository.**
- [KINGST PWM1→CH0 real loopback (2026-10-16)](../evidence/la2016-pwm-loopback/2026-10-16/README.md) passed 1 kHz/50% and 2 kHz/25% plus shutdown using the `kingst-la2016` sigrok AppImage; original SHA-256 `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475`. Do NOT assume system `sigrok-cli` includes that driver.
- [KINGST LA2016 practical tool operation runbook](la2016-tool-operations.md) defines the pinned AppImage + native `kingst-la2016` driver, **no LA internal MCU/FPGA firmware provenance/path/SHA preflight**, passive SWD acquisition, and independent PWM1→CH0/mandatory OFF waveform contracts. [ST-LINK SWD tool operation runbook](stlink-swd-tool-operations.md) preserves the separately proven ST-LINK Flash/Readback and Golden Reference. These do not authorize hardware use or prove Z2 DPIDR.
- USB Hub direct commands (`uhubctl`) and FT2232 JTAG/UART were exercised previously. USB2/USB3 identities can represent one physical Hub.
- New worker inventory [Actions #38948008008](https://github.com/physicslu/plasma/actions/runs/38948008008) saw the tools but **FT2232 and LA USB nodes denied by DAC**, 2 generic UART candidates with zero RW access, and no `plugdev` membership. Actual previous Codex execution UID is **not definitively recorded** in sanitized evidence. `<trusted-operator>` is the trusted operator account to compare locally, but do not assume the historical tests all ran under that UID.

## Exact scope of root-only host installer

`scripts/plasma-codex-hardware-parity.py` provides `--audit`, `--self-test` and opt-in root-only `--apply`. GitHub Actions cannot apply it; PR CI runs only offline synthetic tests.

With `--apply` on trusted **SWPC**:
- Creates dedicated group `plasma-codex-io`, adds both existing operator `<trusted-operator>` and `plasma-codex`, preserving original operator usability.
- Creates `/etc/udev/rules.d/99-plasma-codex-io.rules` with `GROUP=plasma-codex-io`, `MODE=0660` for **all USB device nodes** plus `ttyACM*` and `ttyUSB*`, with **no VID/PID restriction** in existing DEVELOPMENT MODE. This explicitly includes unrelated USB devices plugged into SWPC; read/write capabilities depend on driver and Linux DAC/ACL. No global 0666, `sudoers`, `docker` or blanket `dialout` membership. This broad access is intentional for the owner-operated prototype, not a production multi-tenant default.
- Reloads udev rules **without** re-enumerating devices, changing active device-node modes, opening USB, operating power/FPGA, or restarting the Runner. The trusted root-only installer atomically upgrades only the **byte-exact, root-owned 0644 previous managed rule**; unexpected edits, owner/mode mismatch and symlinks fail closed. A historical PR #1136 candidate is not applied or merged as part of this work.
- Optional `--la-appimage <OWNER_LOCAL_PATH>` verifies the exact proven **Sigrok AppImage** digest and atomically copies it to `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage`, exposing wrapper `/usr/local/bin/plasma-la2016-sigrok`. It does not change or require any LA2016 internal MCU/FPGA firmware path, provenance or SHA; the native driver alone reports actual runtime missing-resource errors.

`--audit` compares the operator and worker against all enumerated USB and USB-serial node permission mode bits (not ACL/LSM), retains historical FT2232/LA subgroups, groups, managed rules, installed LA digest and **file metadata only** for the existing private Z2 credential-store convention. It never reads, parses, displays or copies passwords, SSH keys, environment values, unique USB serial numbers or machine-specific paths.

## Controlled SWPC access activation under the approved Gate 1 (operator terminal only)

The owner may validate and activate this **existing** generic SWPC hardware-parity policy on the **reviewed exact candidate PR HEAD** before Gate 2. This is not a third approval Gate, does not merge the PR, and does not route administrative access through the untrusted GitHub Actions Runner. Do **not** update the operator's main checkout just to obtain this script. Keep an isolated detached candidate worktree and require its clean state and exact owner-reviewed SHA before execution:

```sh
cd "${PLASMA_CANDIDATE_WORKTREE:?set the separately reviewed PR worktree}"
test -z "$(git status --porcelain --untracked-files=all)"
test "$(git rev-parse HEAD)" = "${REVIEWED_PR_HEAD_SHA:?pin the reviewed 40-hex SHA}"
python3 -B scripts/plasma-codex-hardware-parity.py --self-test
python3 -B scripts/plasma-codex-hardware-parity.py --audit
```

The `--audit` receipt now includes `managed_usb_rules_state`: `MISSING`, `CURRENT` or `EXACT_LEGACY` is eligible for managed activation. `OWNER_OR_MODE_DENIED` and `CONFLICT_REFUSED` must stop all changes. Do not overwrite other udev files, change unrelated modes, or apply a per-VID/PID exception.

Only after source identity and preflight checks pass, the owner may run this **root-only** administrative operation from the trusted local operator terminal (not Codex, not any CI job). The exact candidate source must be treated as privileged code and reviewed accordingly:

```sh
sudo -H python3 -B scripts/plasma-codex-hardware-parity.py --apply
sudo -H python3 -B scripts/plasma-codex-hardware-parity.py --audit
```

This applies the generic `GROUP=plasma-codex-io`, `MODE=0660` rule to **all USB device nodes** and `ttyACM*`/`ttyUSB*`, with **no VID/PID allowlist**. It stages rules and current group membership only; it does **not** re-enumerate devices, update existing device-node metadata, reboot, reset the board, disconnect USB, toggle Hub power, or restart a Runner. Device access is not PASS until the actual dedicated worker process confirms it. Do not interpret `udevadm control --reload` as a retroactive update of nodes that already exist. Future controlled device re-enumeration/trigger or an independently reviewed generic current-node mode update may be needed; do not perform one merely to force this test to PASS.

Compare operator/worker permissions and the existing KINGST AppImage state without reading any private credentials.

**This only stages udev rules and group membership.** Existing USB/TTY device nodes retain their old permission metadata until a carefully selected re-enumeration/udev event; no automatic USB disconnect or port toggle is allowed. Newly added group membership also requires a new login/service process. When the dedicated Runner shows **Idle**, restart **only** `actions.runner.physicslu-plasma.SWPC-plasma-codex.service` through an authorized operator channel, not the existing `SWPC-plasma-ci` service. Re-audit both worker and operator access.

Z2 SSH access: configure a **separate owner-authorized worker credential or key** in the `plasma-codex` private HOME using the established Z2 credential interface. Do not blindly copy the operator's whole `.ssh` or private credential file. The host script never accesses secrets.

## Current USB Hub / Z2 power topology (owner-reported, 2026-10-23)

This is a **current read-only observation**, not a fixed software port
allowlist and not authorization to switch power. It supersedes the **port
assignment**, not the historical evidence, from
[`hil-hardware-inventory.md`](hil-hardware-inventory.md) (2026-10-15).

- Transcend hub USB2 companion `1-1` and USB3 companion `2-1` are the
  same physical hub (8564:4100; `ppps`). `uhubctl` **without action
  arguments** reported `power` on all four ports of both companions.
- **Current** physical USB2 Port 1 = ST-LINK V3; Port 2 = PLASMA Blue Pill
  CDC; Port 3 = **Z2 FT2232 JTAG/UART** (`1-1.3`); Port 4 = KINGST
  LA2016 (`1-1.4`). Historic `Port 2 = Z2` is no longer valid.
- Z2 AX88179 USB Ethernet currently enumerates directly under SWPC `2-8`,
  **not under this Transcend hub**; avoid the old Port 3 = Ethernet assumption.
- **Owner confirmation (2026-10-24):** this Z2 setup is **USB powered**;
  interrupting and restoring its USB supply makes the Z2 boot again. This
  establishes the intended operational **USB-power-cycle recovery route** in
  the present owner-operated prototype. It is owner-reported wiring/behavior,
  **not** a newly executed instrumented Z2 power/boot qualification.
- Under the **observed current wiring**, Transcend physical **Port 3** is
  the Z2 USB power/control connection via FT2232 (`1-1.3`). Port 2 is
  **Blue Pill**, not Z2; Port 1 is ST-LINK, Port 4 is LA2016. Z2's separate
  Ethernet adapter on SWPC `2-8` is **outside** this hub; its own USB
  enumeration does not demonstrate that Z2 Linux has booted.
- Manufacturer documents describe J9 source selection and SW1 power
  switching ([PYNQ-Z2 setup](https://pynq.readthedocs.io/en/v2.5/getting_started/pynq_z2_setup.html);
  [TUL manual](https://dpoauwgwqsy2x.cloudfront.net/Download/PYNQ_Z2_User_Manual_v1.1.pdf)).
  The owner-confirmed **working USB-power-cycle arrangement** supersedes
  our previous speculative demand to re-check J9/SW1 before acknowledging
  that this setup can boot via USB. It does not prove rail discharge time,
  electrical VBUS zero, maximum load/current budget or independent emergency
  recovery under abnormal PS/PL faults.
- Any *future authorized* USB power-cycle shall resolve the **current physical
  hub/port mapping** rather than reuse historic Port 2 commands, stop if
  mapping changed or ambiguous, avoid toggling ST-LINK/Blue Pill/LA2016
  ports, and verify Z2 Linux readiness through its actual PS status rather
  than FT2232 enumeration alone. Interrupting Port 3 temporarily removes
  the Z2 JTAG/UART recovery path. No repeated power cycling on failure.

**Observed acceptance so far:** owner-reported generic USB/TTY worker ACL
`16/16 PASS`; passive `uhubctl` and current topology observed; owner
confirms USB Power OFF/ON boots Z2. **A newly witnessed Port 3 OFF/ON →
Z2 PS boot/identity and the real Codex-in-namespace command remain
NOT_RUN** for PR #1140. No hardware state was changed in this documentation
update. These are ordinary approved Development Mode capabilities, **not**
new USB VID/PID admission filters, Path/Mode/Session/Runner or merge permission.

## Bounded nondestructive acceptance

1. Re-run dedicated-worker inventory to verify actual USB and tty permissions, and query `uhubctl` status **without toggling power**.
2. Under `plasma-codex`, perform a trusted Z2 SSH read-only command after the worker's own credentials are provisioned. UART console/open only if no other owner holds the TTY. JTAG link/identity only if a non-reset, non-halt action is supported; otherwise NOT_RUN.
3. For the specific owner-approved test, verify the pinned tools, current device identity, correct wiring, driver ownership and safe recovery. Perform **one minimum sufficient real test** (for example, read-only ST-LINK target identify or a single LA2016 capture) and stop on a genuine PASS. Do not repeat previous PWM/Flash experiments solely to obtain three matching rounds; on FAIL analyze and perform only justified targeted rechecks. If wiring/recovery is unknown, NOT_RUN.
4. Record source revision, identity, results as PASS/FAIL/NOT_RUN, and verify no regression of the original operator's access.

**Not implicitly authorized by device permissions:** Hub port ON/OFF, FPGA reconfiguration, DUT power changes, USB ethernet reset, JTAG reset/halt or Flash programming. Ordinary experimental DUT Program/Readback/Verify may be performed autonomously **when that specific Gate 1 includes them**, without a numerical retry quota. Privileged Z2/root actions retain the existing protected transport; no GitHub PR merge without Gate 2.

## Risk and rollback

Allowing a dedicated development Runner group to access every USB device attached to SWPC is a **deliberate increase in privilege**, not merely a visibility change. The operator must ensure private storage, unrelated USB peripherals and production DUTs are not exposed on the dedicated engineering host while Codex is active. Device permissions on a self-hosted Runner are a meaningful departure from the initial read-only hardware-isolated pilot. The existing workflow guard is owner-only, but **Runner labels alone are not a security boundary**; avoid running untrusted PR checkout or freeform Issue commands on this hardware-capable account. Sandbox `read-only` does not itself guarantee USB isolation after OS group access is granted.

If host activation or access fails, STOP, preserve original operator and device access, restore only this project's managed rule/group changes after reviewing dependencies, and reload udev. Do not automatically delete shared groups, rotate unrelated credentials, or touch the live board. A successful offline CI run does NOT mean host access was changed or physical tests passed.
