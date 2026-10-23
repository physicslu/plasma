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
- Creates an exact guarded `/etc/udev/rules.d/99-plasma-codex-io.rules` with GROUP `plasma-codex-io`, MODE 0660 only for FT2232 0403:6010, Hub 8564:4100, LA2016 77a1:01a2, and FT2232-descendant ttyUSB nodes. No wildcard all-USB, `sudoers`, `docker`, or blanket `dialout` membership.
- The Blue Pill development extension adds STLINK-V3SET `0483:374f`, the firmware's provisional `cafe:4001` USB device, and only `ttyACM*` descendants of `cafe:4001`. It does not grant access to ST-LINK's CDC interface or unrelated serial devices. The installer accepts an atomic upgrade only when the current rule file exactly matches its prior managed content; owner edits still fail closed. This is a new physical-device grant requiring owner review before root-side application.
- Reloads udev rules **without** re-enumerating devices, changing active device-node modes, opening USB, operating power/FPGA, or restarting the Runner. Existing conflicting files and symlinks fail closed.
- Optional `--la-appimage <OWNER_LOCAL_PATH>` verifies exact previously proven binary digest and atomically copies it to `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage`, exposing wrapper `/usr/local/bin/plasma-la2016-sigrok`. It does not invent a new firmware path. `SIGROK_FIRMWARE_PATH` may still need to be configured privately.

`--audit` compares the operator and worker against USB/FT2232-TTY permission mode bits (not ACL/LSM), groups, managed rules, installed LA digest and **file metadata only** for the existing private Z2 credential-store convention. It never reads, parses, displays or copies passwords, SSH keys, environment values, unique USB serial numbers or machine-specific paths.

For the Blue Pill task, the audit additionally reports ST-LINK, Blue Pill USB and its `ttyACM*` nodes. The observed 2026-10-23 SWPC state was: Host `gordon` could open ST-LINK and LA under existing ACL/group, but `/dev/ttyACM0` belonged to `dialout` and neither `gordon` nor `plasma-codex` was a member. The current App Codex sandbox also hides `/dev/bus/usb` and CDC TTY independently of Host DAC. A rule upgrade alone does not expose devices inside that sandbox or add a Blue Pill stage to the Z2-only development transport.

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

For the Blue Pill extension, owner review must cover the exact new rule diff, the root-side `--apply`, and a scoped way to activate only the specified device nodes. No broad `dialout` membership or unplug/replug is required. Before any Flash, independently verify target voltage, SWD wiring/exclusivity, device identity, rollback image and tool access. The Development stage transport currently allows only Z2 `download`, `test`, and `restore`; do not treat its existence as authorization for ST-LINK or LA. A Host-side Path 3 task must use an owner-approved device-capable context, not escape an App or Runner sandbox.

Z2 SSH access: configure a **separate owner-authorized worker credential or key** in the `plasma-codex` private HOME using the established Z2 credential interface. Do not blindly copy the operator's whole `.ssh` or private credential file. The host script never accesses secrets.

## Bounded nondestructive acceptance

1. Re-run dedicated-worker inventory to verify actual USB and tty permissions, and query `uhubctl` status **without toggling power**.
2. Under `plasma-codex`, perform a trusted Z2 SSH read-only command after the worker's own credentials are provisioned. UART console/open only if no other owner holds the TTY. JTAG link/identity only if a non-reset, non-halt action is supported; otherwise NOT_RUN.
3. Verify the **pinned** KINGST AppImage/Driver, current USB identity and optional firmware path. If the operator confirms the same PWM1→CH0 loopback wiring, repeat the historical 1 kHz/50% sample capture, shutdown PWM1 in a `finally` path, and verify nonempty waveform. If wiring is unknown, NOT_RUN.
4. Record source revision, identity, results as PASS/FAIL/NOT_RUN, and verify no regression of the original operator's access.

**Not covered:** Hub port ON/OFF, FPGA reconfiguration, DUT power changes, USB ethernet reset, JTAG reset/halt or Flash programming. No GitHub PR merge without Gate 2.

## Risk and rollback

Device permissions on a self-hosted Runner are a meaningful departure from the initial read-only hardware-isolated pilot. The existing workflow guard is owner-only, but **Runner labels alone are not a security boundary**; avoid running untrusted PR checkout or freeform Issue commands on this hardware-capable account. Sandbox `read-only` does not itself guarantee USB isolation after OS group access is granted.

If host activation or access fails, STOP, preserve original operator and device access, restore only this project's managed rule/group changes after reviewing dependencies, and reload udev. Do not automatically delete shared groups, rotate unrelated credentials, or touch the live board. A successful offline CI run does NOT mean host access was changed or physical tests passed.
