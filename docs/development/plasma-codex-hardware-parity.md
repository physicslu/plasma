# PLASMA Issue #981 — reproduce working Codex hardware capabilities

**Gate 1 approved for source, SWPC access migration and bounded nondestructive verification. Gate 2 required for merge.**
No additional HIL Gateway, Controller, device driver or REST API.

## Previous proof and gaps

- [Z2 Codex HIL assignment](codex-z2-hil-development-command.md) documents owner-authorized SSH/UART, Z2 account and a local private SSH/sudo credential interface. **Credentials are not in the repository.**
- [KINGST PWM1→CH0 real loopback (2026-10-16)](../evidence/la2016-pwm-loopback/2026-10-16/README.md) passed 1 kHz/50% and 2 kHz/25% plus shutdown using the `kingst-la2016` sigrok AppImage; original SHA-256 `b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475`. Do NOT assume system `sigrok-cli` includes that driver.
- USB Hub direct commands (`uhubctl`) and FT2232 JTAG/UART were exercised previously. USB2/USB3 identities can represent one physical Hub.
- New worker inventory [Actions #38948008008](https://github.com/physicslu/plasma/actions/runs/38948008008) saw the tools but **FT2232 and LA USB nodes denied by DAC**, 2 generic UART candidates with zero RW access, and no `plugdev` membership. Actual previous Codex execution UID is **not definitively recorded** in sanitized evidence. `<trusted-operator>` is the trusted operator account to compare locally, but do not assume the historical tests all ran under that UID.

## Exact scope of root-only host installer

`scripts/plasma-codex-hardware-parity.py` provides `--audit`, `--self-test` and opt-in root-only `--apply`. GitHub Actions cannot apply it; PR CI runs only offline synthetic tests.

With `--apply` on trusted **SWPC**:
- Creates dedicated group `plasma-codex-io`, adds both existing operator `<trusted-operator>` and `plasma-codex`, preserving original operator usability.
- Creates `/etc/udev/rules.d/99-plasma-codex-io.rules` with `GROUP=plasma-codex-io`, `MODE=0660` for **all USB device nodes** plus `ttyACM*` and `ttyUSB*`, with **no VID/PID restriction** in existing DEVELOPMENT MODE. This explicitly includes unrelated USB devices plugged into SWPC; read/write capabilities depend on driver and Linux DAC/ACL. No global 0666, `sudoers`, `docker` or blanket `dialout` membership. This broad access is intentional for the owner-operated prototype, not a production multi-tenant default.
- Reloads udev rules **without** re-enumerating devices, changing active device-node modes, opening USB, operating power/FPGA, or restarting the Runner. The trusted root-only installer atomically upgrades only the **byte-exact, root-owned 0644 previous managed rule**; unexpected edits, owner/mode mismatch and symlinks fail closed. A historical PR #1136 candidate is not applied or merged as part of this work.
- Optional `--la-appimage <OWNER_LOCAL_PATH>` verifies exact previously proven binary digest and atomically copies it to `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage`, exposing wrapper `/usr/local/bin/plasma-la2016-sigrok`. It does not invent a new firmware path. `SIGROK_FIRMWARE_PATH` may still need to be configured privately.

`--audit` compares the operator and worker against all enumerated USB and USB-serial node permission mode bits (not ACL/LSM), retains historical FT2232/LA subgroups, groups, managed rules, installed LA digest and **file metadata only** for the existing private Z2 credential-store convention. It never reads, parses, displays or copies passwords, SSH keys, environment values, unique USB serial numbers or machine-specific paths.

## Deployment after Gate 2 (operator terminal; not PR workflow)

Use **reviewed main** on SWPC; preserve local work. Read current context without making changes first:

```sh
cd "${PLASMA_REPO:?set trusted SWPC checkout path}"
git status --short
git fetch origin main
git merge --ff-only origin/main
python3 scripts/plasma-codex-hardware-parity.py --audit
```

Compare `<trusted-operator>` group/permission baseline against `plasma-codex` and verify the previously used AppImage (do not assume the root-run audit proves original Codex's historical UID).

Then apply from the owner's **trusted administrative terminal** (not from GitHub Actions):

```sh
sudo python3 scripts/plasma-codex-hardware-parity.py --apply
# If the verified source AppImage is present locally:
# sudo python3 scripts/plasma-codex-hardware-parity.py --apply --la-appimage "$SIGROK_APPIMAGE"
```

**This only stages udev rules and group membership.** Existing USB/TTY device nodes retain their old permission metadata until a carefully selected re-enumeration/udev event; no automatic USB disconnect or port toggle is allowed. Newly added group membership also requires a new login/service process. When the dedicated Runner shows **Idle**, restart **only** `actions.runner.physicslu-plasma.SWPC-plasma-codex.service` through an authorized operator channel, not the existing `SWPC-plasma-ci` service. Re-audit both worker and operator access.

Z2 SSH access: configure a **separate owner-authorized worker credential or key** in the `plasma-codex` private HOME using the established Z2 credential interface. Do not blindly copy the operator's whole `.ssh` or private credential file. The host script never accesses secrets.

## Bounded nondestructive acceptance

1. Re-run dedicated-worker inventory to verify actual USB and tty permissions, and query `uhubctl` status **without toggling power**.
2. Under `plasma-codex`, perform a trusted Z2 SSH read-only command after the worker's own credentials are provisioned. UART console/open only if no other owner holds the TTY. JTAG link/identity only if a non-reset, non-halt action is supported; otherwise NOT_RUN.
3. For the specific owner-approved test, verify the pinned tools, current device identity, correct wiring, driver ownership and safe recovery. Perform **one minimum sufficient real test** (for example, read-only ST-LINK target identify or a single LA2016 capture) and stop on a genuine PASS. Do not repeat previous PWM/Flash experiments solely to obtain three matching rounds; on FAIL analyze and perform only justified targeted rechecks. If wiring/recovery is unknown, NOT_RUN.
4. Record source revision, identity, results as PASS/FAIL/NOT_RUN, and verify no regression of the original operator's access.

**Not implicitly authorized by device permissions:** Hub port ON/OFF, FPGA reconfiguration, DUT power changes, USB ethernet reset, JTAG reset/halt or Flash programming. Ordinary experimental DUT Program/Readback/Verify may be performed autonomously **when that specific Gate 1 includes them**, without a numerical retry quota. Privileged Z2/root actions retain the existing protected transport; no GitHub PR merge without Gate 2.

## Risk and rollback

Allowing a dedicated development Runner group to access every USB device attached to SWPC is a **deliberate increase in privilege**, not merely a visibility change. The operator must ensure private storage, unrelated USB peripherals and production DUTs are not exposed on the dedicated engineering host while Codex is active. Device permissions on a self-hosted Runner are a meaningful departure from the initial read-only hardware-isolated pilot. The existing workflow guard is owner-only, but **Runner labels alone are not a security boundary**; avoid running untrusted PR checkout or freeform Issue commands on this hardware-capable account. Sandbox `read-only` does not itself guarantee USB isolation after OS group access is granted.

If host activation or access fails, STOP, preserve original operator and device access, restore only this project's managed rule/group changes after reviewing dependencies, and reload udev. Do not automatically delete shared groups, rotate unrelated credentials, or touch the live board. A successful offline CI run does NOT mean host access was changed or physical tests passed.
