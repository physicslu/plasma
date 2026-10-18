# PLASMA Issue #981 — SWPC direct HIL tool readiness

Status: Gate 1 approved for passive inventory implementation. Gate 2 required to merge.
This does **not** create a HIL Gateway, Controller, driver, privileged daemon, or new product API.

## Reuse verified mechanisms

| Target | Existing method | Passive checks |
| --- | --- | --- |
| PYNQ-Z2 | SSH, UART over FT2232, JTAG / existing PS–PL tests | SSH/JTAG/serial CLI PATH, USB FT2232 0403:6010 metadata, *generic* UART node permissions |
| USB Hub | Direct USB commands / uhubctl | uhubctl PATH; hub 8564:4100 enumeration and device-node DAC |
| KINGST LA2016 | kingst-la2016 Driver + CLI / existing sigrok AppImage | LA 77a1:01a2 enumeration, DAC, system sigrok-cli and optional AppImage executable metadata |

The older [HIL hardware inventory](hil-hardware-inventory.md) documents USB controls and FT2232 but does not prove the **new** plasma-codex Linux account has access. The [2026-10-16 REAL KINGST PWM1→CH0 capture](../evidence/la2016-pwm-loopback/2026-10-16/README.md) already passed at two settings with real waveforms. Do not describe LA as merely USB-connected; equally, do not infer dedicated worker readiness or DUT/Z2 SWD success from that test.

## Strictly passive inspection

The script `scripts/plasma-codex-hil-tool-inventory.py` uses only Python standard library, PATH lookup, Linux eUID/group lookup, USB VID/PID text metadata in sysfs, and metadata/ACL assessment via `stat`/`os.access` of matching USB character device nodes and generic serial TTY candidates. It **does not open devices or run subprocesses**. Optional local `PLASMA_HIL_LA_CLI` checks existence and executable permission of a locally configured absolute AppImage path without printing the path.

It **never** opens SSH, reads credentials, starts UART/JTAG, executes uhubctl, sends USB transfers, touches FPGA manager, changes power/reset, records LA waveforms or programs ICs. Permission result `RW_BY_DAC_NOT_OPENED` indicates only likely POSIX DAC access; it is *not* a real driver or USB I/O test.

Sanitized output: fixed expected identity booleans, CLI presence labels, USB VID/PID match categories, permission categories, generic TTY counts, and explicit `NOT_RUN`. No IPs, unique USB serials, bus/device node numbers, SSH credentials, private paths, environment values, or full process lists.

The LA test used an independently built AppImage; a system `sigrok-cli` might not support `kingst-la2016`. `NOT_CONFIGURED` for the LA CLI override does not refute the previous real PASS.

## Approval, CI, and exact GitHub dispatch

GitHub-hosted PR CI only:
- `python3 scripts/plasma-codex-hil-tool-inventory.py --self-test`
- `python3 scripts/plasma-codex-hil-tool-inventory-contract.py check`
- Python syntax check.

**After Gate 2 merge only**, the repository owner can post on **Issue #981**:

    /plasma-codex hil-tools 981

The trusted GitHub-hosted `authorize` job requires exact owner/sender/comment/Issue/repository/action/main ref; it emits the **reviewed main commit SHA**. The dedicated `SWPC-plasma-codex` runner checks out that SHA (never untrusted PR content), verifies nonroot worker identity and prohibited groups, then writes only sanitized `report.json`, `exit_code`, `SHA256SUMS` (14-day Actions Artifact). Existing `SWPC-plasma-ci` / `plasma-integration` remains unchanged.

A successful workflow means inventory execution succeeded; missing tools, USB device mapping, DAC access, SSH authentication, CLI control and live HIL success remain distinguishable. Missing trusted runner identity is a hard failure.

## Interpret and follow up

- `cli_presence.*=FOUND_UNEXECUTED`: binary found, not executed or validated.
- `usb.*.enumeration=FOUND_BY_VID_PID`: metadata match only.
- `usb.*.node_dac=DENIED_BY_DAC`: dedicated account likely cannot open the node.
- `uart`: generic TTY candidate count only; mapping to Z2 is `NOT_CHECKED`.
- `tests.*=NOT_RUN` and `hardware_access_qualified=false`: no live access attempted.
- `identity_ready=false`: dedicated user/runner guard failed.

After actual evidence review, a later explicit Gate 1 may authorize minimum-scope device-specific ACL/udev and selected live SSH/UART/JTAG, USB hub and LA commands. Do not broaden sudo/docker privileges or copy another user's SSH keys. No additional Gateway is required.

The script can be invoked directly in the dedicated user shell for read-only manual diagnosis. Outside GitHub Actions `runner_name` will be false; interpret that as *outside runner context*, not an equipment failure. Do not paste private raw host inventories or credential files into public Issues.
