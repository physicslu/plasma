# PLASMA Issue #981 — Z2 SSH-only PS/PL Readiness

**Gate 1 owner-approved; Gate 2 required to merge.** UART auto-login remains a non-blocking backlog item and is not part of this execution.

## Scope and trust boundaries

Reuse the existing SWPC dedicated worker login and pinned known_hosts credentials via the reviewed `plasma-codex-z2-login.py` helper, with no new enrollment. A fixed unprivileged Python process is invoked through SSH. The owner Issue body cannot supply arbitrary remote commands or targets.

The remote probe checks only:
- Linux, ARMv7 and Zynq-7000 Device Tree compatible. A family compatible is not exact PYNQ-Z2 identity.
- `/sys/class/fpga_manager/fpga*/state`: whitelisted OPERATING, NOT_OPERATING or NO_MANAGER. OPERATING does NOT establish exact image, Build ID, PS/PL register ABI or recovery.
- `/sys/class/uio/uio*/name` (bounded at 32 entries), recognized fabric/audio-codec names and device driver symlink visibility. No `/dev/uio` opens or MMIO mapping.
- FCLK0 rate ONLY when an unprivileged read from `/sys/kernel/debug/clk/fclk0/clk_rate` succeeds, else NOT_OBSERVED_UNPRIVILEGED. No root/sudo, clock changes or debugfs mounts.
- `systemctl is-active --quiet` of four fixed PLASMA services. This is service presence, not service correctness or HIL capacity.

No root, UART, USB Hub, JTAG, FPGA reconfiguration, service restarts, SWD/DUT/IC burn, reset, FPGA registers, `/dev/mem`, `/dev/uio` reads/writes or other hardware operations. This code has logical read-only boundaries; hardware-capable Runner Linux groups are NOT by themselves an OS sandbox.

## Relationship with existing HIL architecture

Existing PSPL-02, SWD-00, SWD-05, Linux MMIO and FPGA Manager HIL runners remain unchanged and NOT RUN. The present task validates **only the SSH-controlled observation path**, not FPGA programming, Bitstream identity, eight-channel ownership, MMIO access or recovery. Further PS/PL internal-loopback needs a later scoped Gate 1 with current safe ownership, known-good firmware/recovery and the authoritative PSPL Runbook.

## Trusted dispatch and SWPC observation

Only after this PR obtains explicit Gate 2 merge approval, owner physicslu can write the **exact command** on Issue #981:

`/plasma-codex z2-readiness 981`

The GitHub-hosted authorizer validates repository/actor/sender/comment/issue/default branch, pins reviewed main SHA, then schedules dedicated Runner `SWPC-plasma-codex`. No PR code runs on the hardware runner. Credentials are stored in the worker-owned 0600 private file and matched via the previously pinned SSH host key, not printed or uploaded.

During the run, operator `gordon` can attach (with the real GitHub Run ID):

`tmux -S /run/plasma-codex/z2-readiness-<RUN_ID>.sock attach-session -r -t plasma-z2-readiness-<RUN_ID>`

Detach with Ctrl+B then D. The socket is temporary, and status is sanitized. The `plasma-monitor` group requires trusted operators; `tmux -r` alone is not a cryptographic read-only security control.

## Explicit evidence classifications

- `BASELINE_PASS_PARTIAL`: authenticated SSH and fixed remote identity indicate Linux/ARMv7/Zynq-7000, FPGA Manager state OPERATING; other fields may remain unobserved.
- `BASELINE_BLOCKED`: Linux/ARMv7/Device Tree/Manager readback does not meet expected baseline.
- `BLOCKED_SSH_OR_PROBE`: private credentials, host key, SSH, JSON marker or schema validation failed. No raw remote stdout/stderr is exposed.

Always `hardware_go=false`; exact board identity and firmware Build ID `NOT_QUALIFIED`; `mmio_access=NOT_RUN`, `fpga_reload=NOT_RUN`, `uart=NON_BLOCKING_NOT_RUN`. UIO sysfs name and driver symlink visibility are NOT authority to open devices. Unknown FCLK or inactive services must be reported, not invented.

Evidence artifacts are only sanitized report.json, exit_code and SHA256SUMS. They may prove limited remote state observations but not a fully functional PS/PL loopback. Hosted PR CI runs offline contract/test and shell syntax only; it does not touch Z2.

## Next stage

After SSH-only baseline acceptance, inspect the actual result for FCLK, UIO driver bindings, service conflicts and exact FPGA firmware identity gaps. Establish a separate recoverable, approved HIL plan referencing `docs/development/pspl02-swd00-hil-runbook.md` before MMIO or programming. UART parser work stays non-blocking.
