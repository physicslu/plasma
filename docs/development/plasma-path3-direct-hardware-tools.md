# PLASMA Path 3 — Codex 原生工具，適用所有設備

**2026-10-27 Gate 1 / Source-only 架構與相依盤點。** 本次不操作 SWPC、LA2016、Z2、FPGA 或 DUT；沒有新實機資格。實際硬體工作必須明列在經 Owner Gate 1 核准的 Work Order，遵循真實 Linux DAC/ACL、原生 Driver 占用結果、其他硬體資源互斥、電氣與 Root 安全。修改在 Draft PR 未合併前不是已部署的 Runner 行為。

## 現行呼叫鏈

```text
Owner Gate 1 / signed-off Work Order and pinned SHA
  -> Existing GitHub Actions Engineering Dispatcher / SWPC-plasma-codex
  -> codex exec --json -  (owner-scoped sandbox mode and real Linux privileges)
       |-- SWPC: directly execute sigrok-cli / pinned KINGST AppImage -> LA2016
       |-- SWPC: native USB, serial, UART, OpenOCD, JTAG and other installed tools
       |-- existing enrolled SSH -> PYNQ-Z2 PS
            -> protected FPGA Manager/Manifest/Root Guard
            -> PS-local OpenOCD + local UNIX WordPort/Remote Bitbang Bridge
            -> PL SWD pins -> DUT
```

**No intermediary hardware JSON command translation, fixed operation Adapter, extra Stage/Profile or device-specific Probe Gate.** Do not generate an `agent-request.json` capability schema for a Host Supervisor to map to an allowlisted instrument operation. Do not add a new per-device Workflow or Runner. The generic Dispatcher continues Work Order/Owner/PR SHA admission, Codex invocation and evidence processing. Codex independently chooses native CLI and SSH actions within the approved objective; it does not gain OS privilege from the Work Order text.

## Complete entrypoint / dependency inventory for this Gate

| Entrypoint or family | Actual role | Gate 1 action |
|---|---|---|
| `plasma-engineering-runtime-dispatch.yml` / `plasma_development_dispatch.py` | Active Owner Issue #981 gate, pinned candidate SHA, worker invocation, evidence publishing | **Retain one common gateway; remove special `session_resume` parser, second Job and fixed resume phase** |
| `plasma_engineering_monitor.py` | Basic Path 2/3 status, tmux and run evidence | Retain observability; not a hardware translator |
| `plasma_development_codex_sandbox.py` | Historical standalone rootless Bubblewrap builder, tested offline but **not imported or called** by the live shared Path 3 Dispatcher | No runtime middle layer; ordinary Codex instead directly pins its own `workspace-write` mode, and the exact Owner hardware Work Order selects `danger-full-access` |
| Legacy LA2016 Supervisor / JSON Relay / diagnosis launchers | Old instrument-specific Issue command handlers | Delete old Path 3 entrypoints, scripts and contract tests in PR #1181 |
| Cross-Job `plasma_path3_cross_job_resume.py` and `development-codex-resume` | Optional fixture-only two-Job runtime branch | Delete runtime Adapter and Job; historical standalone CPU-only `plasma_path3_session_resume_probe.py` is **not** on Path 3 call chain |
| `plasma-codex-pilot`, `z2-login`, `z2-readiness`, `swpc-preflight`, `hil-tool-inventory`, `software-mvp` Workflows | Historical standalone launchers or hosted contract tests | `on:` has only `pull_request` / `push`; old `issue_comment` jobs are inert and **must not** be used as Path 3 middleware. Existing offline tests and separately used SSH helper are not called by the shared Path 3 execution chain |
| `plasma-codex-hardware-parity.py` | Installation/readiness parity diagnostics | Independent maintenance tooling, not a required runtime Probe Gate |
| `plasma_development_stage_transport.py` / `plasma_path2_runtime_integration.py` | Path 2 SSH-to-Z2 protected Root Entry and exact receipt checks | **Retain for Path 2 only**; never route Path 3 hardware actions through it |
| `pl/hil/fpga_image_root.py`, protected Root Entry / Manifest, Linux locks | Actual privilege, image and resource safety boundaries | Retain unchanged; unknown hardware state requires explicit safe recovery |

The inventory distinguishes dead standalone programs from a live mandatory intermediary: deleting a diagnostic tool used outside Path 3 would not make Codex more direct, but could break independent offline contracts. New Path 3 device-specific dispatch paths are prohibited. This scope does **not** replace Linux DAC, SSH host authentication, FPGA root-owned guards or other hardware's required locks. For LA2016 only, native Driver Open/Claim is the availability decision rather than a separate PLASMA lock.

## LA2016 — direct CLI on SWPC

1. Read [LA2016 verified tool operations](la2016-tool-operations.md), [real archived PWM1→CH0 loopback](../evidence/la2016-pwm-loopback/2026-10-16/README.md) and [ST-LINK real SWD reference](../evidence/stlink-stm32f103-swd-reference/2026-10-23/README.md). Historical success cannot substitute for current USB readiness.
2. Verify the pinned AppImage `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage` and its SHA256. Preserve any inherited `SIGROK_FIRMWARE_PATH`; do **not** require separate LA instrument MCU/FPGA firmware file discovery, presence or SHA preflight. Dynamically resolve **one** current VID:PID `77a1:01a2` using sysfs; check the USB node's RW DAC/ACL. Never reuse historic USB bus/device or an unverified system sigrok.
3. Codex directly runs the pinned AppImage with `--appimage-extract-and-run` and `kingst-la2016:conn=<current-bus.device>`; the native Driver Open/Claim result determines availability. On Busy, record `DEVICE_BUSY`, native stderr and exit code, then stop without forced takeover or blind retry; other native initialization/acquisition failures are `RUNTIME_FAIL`. Ensure normal USB close and cleanup after acquisition. Do **not** impose a PLASMA-specific lock file/`flock` or mandatory `fuser` pre-open probe on LA2016. These are not a replacement for USB permissions, electrical safety, or other devices' protected locks. Native concurrency rejection has **not** been physically requalified by this source-only Gate; no claim of hardware PASS.
4. For Z2 SWD observation, use passive input CH0/CH1/CH2 with fresh per-run `.sr` evidence, timestamp, SHA256, actual capture metadata and command exit code. Verify that capture actually overlaps the hardware operation. Do not enable LA2016 PWM1 while wired to Blue Pill/Z2 SWD.
5. Physical PWM output on a separate **PWM1→same-device CH0** fixture is a different authorized electrical scope. **An independent, verified OFF fallback and fresh OFF-Low capture are mandatory** before such a test; an Agent prompt or simple `finally` cannot guarantee OFF after process or host failure. In absence of that protection, PWM emission is `NOT_RUN`, not a supposed PASS.

## Z2 — existing direct SSH / PS execution

1. Read [Z2 PS WordPort Bridge](../../scripts/bluepill-wordport-session.py), [Z2 PS runtime installer](../../scripts/plasmactl-z2-ps), [SWD tool operations](stlink-swd-tool-operations.md) and current `AGENTS.md` protected FPGA/Golden contract.
2. Use the enrolled SWPC SSH configuration, pinned Z2 host identity and owner-approved private credential source. Do not invent IP addresses, copy or print private keys, alter sudoers, or add a new gateway. Confirm effective SSH permission on the actual Runner before declaring availability.
3. On **Z2 PS only**, use existing OpenOCD connected to the **Z2 PS-local UNIX** WordPort/Remote Bitbang bridge. Do not move OpenOCD onto SWPC, forward Remote Bitbang to SWPC, or bypass the protected FPGA Root Entry, MMIO lease, image/Manifest/current-boot checks.
4. Before enabling the physical interface verify DUT identity, legal voltage/wiring, debugger exclusivity, FPGA image provenance and Golden recovery readiness. When a downstream SWD test fails, stop transactions; reap the PS-local OpenOCD/bridge and safely release ownership. **Keep Loaded** is appropriate only after a genuinely successful FPGA load and while current hardware state remains known safe. Restore is a protected explicitly selected or documented fault-recovery decision, not automatic on every functional failure.

## Retired code and evidence

The old Issue #981 LA2016 JSON Supervisor, LA-only Direct A/B and diagnosis Workflow/scripts/tests/docs are removed. Their three exact Issue commands no longer have working entrypoints; none are remapped. Existing 2026-10-16/23 evidence and offline verifiers remain. Return authentic command exits, SHA256, device/runner provenance and failure reports. Host-only CI is not proof of live USB/SSH/FPGA/DUT acceptance.
