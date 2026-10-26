# PLASMA Path 3 — Codex 直接操作 SWPC LA2016 與 Z2 PS

**2026-10-26 Source-only 架構整理。** 本次不操作 SWPC、LA2016、Z2、FPGA 或 DUT；沒有新實機資格。實際硬體工作必須明列在經 Owner Gate 1 核准的 Work Order，遵循真實 Linux DAC/ACL、資源互斥、電氣與 Root 安全。

## 現行呼叫鏈

```text
Owner Gate 1 / signed-off Work Order and pinned SHA
  -> Existing GitHub Actions Engineering Dispatcher / SWPC-plasma-codex
  -> codex exec --json -  (inherited Codex config and Linux privileges)
       |-- SWPC: directly execute sigrok-cli / pinned KINGST AppImage -> LA2016
       |-- existing enrolled SSH -> PYNQ-Z2 PS
            -> protected FPGA Manager/Manifest/Root Guard
            -> PS-local OpenOCD + local UNIX WordPort/Remote Bitbang Bridge
            -> PL SWD pins -> DUT
```

**No intermediary hardware JSON command translation.** Do not generate an `agent-request.json` capability schema for a Host Supervisor to map to an allowlisted instrument operation. Do not add a new per-LA, per-Z2 Workflow or Runner. The generic Dispatcher continues Work Order/Owner/PR SHA admission, Codex invocation and evidence processing. Codex independently chooses CLI and SSH actions within the approved objective; it does not gain OS privilege from the Work Order text.

## LA2016 — direct CLI on SWPC

1. Read [LA2016 verified tool operations](la2016-tool-operations.md), [real archived PWM1→CH0 loopback](../evidence/la2016-pwm-loopback/2026-10-16/README.md) and [ST-LINK real SWD reference](../evidence/stlink-stm32f103-swd-reference/2026-10-23/README.md). Historical success cannot substitute for current USB readiness.
2. Verify the pinned AppImage `/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage`, SHA256 and existing `SIGROK_FIRMWARE_PATH`/firmware resources. Dynamically resolve **one** current VID:PID `77a1:01a2` using sysfs; check device RW ACL and `fuser`. Never reuse historic USB bus/device or an unverified system sigrok.
3. Hold `/run/lock/plasma-la2016.lock` across the entire capture and verify ownership; an advisory lock does not exclude noncooperating clients. Codex directly runs the pinned AppImage with `--appimage-extract-and-run` and `kingst-la2016:conn=<current-bus.device>`. The runbook provides verified arguments, not a new Host Supervisor forwarding API.
4. For Z2 SWD observation, use passive input CH0/CH1/CH2 with fresh per-run `.sr` evidence, timestamp, SHA256, actual capture metadata and command exit code. Verify that capture actually overlaps the hardware operation. Do not enable LA2016 PWM1 while wired to Blue Pill/Z2 SWD.
5. Physical PWM output on a separate **PWM1→same-device CH0** fixture is a different authorized electrical scope. **An independent, verified OFF fallback and fresh OFF-Low capture are mandatory** before such a test; an Agent prompt or simple `finally` cannot guarantee OFF after process or host failure. In absence of that protection, PWM emission is `NOT_RUN`, not a supposed PASS.

## Z2 — existing direct SSH / PS execution

1. Read [Z2 PS WordPort Bridge](../../scripts/bluepill-wordport-session.py), [Z2 PS runtime installer](../../scripts/plasmactl-z2-ps), [SWD tool operations](stlink-swd-tool-operations.md) and current `AGENTS.md` protected FPGA/Golden contract.
2. Use the enrolled SWPC SSH configuration, pinned Z2 host identity and owner-approved private credential source. Do not invent IP addresses, copy or print private keys, alter sudoers, or add a new gateway. Confirm effective SSH permission on the actual Runner before declaring availability.
3. On **Z2 PS only**, use existing OpenOCD connected to the **Z2 PS-local UNIX** WordPort/Remote Bitbang bridge. Do not move OpenOCD onto SWPC, forward Remote Bitbang to SWPC, or bypass the protected FPGA Root Entry, MMIO lease, image/Manifest/current-boot checks.
4. Before enabling the physical interface verify DUT identity, legal voltage/wiring, debugger exclusivity, FPGA image provenance and Golden recovery readiness. When a downstream SWD test fails, stop transactions; reap the PS-local OpenOCD/bridge and safely release ownership. **Keep Loaded** is appropriate only after a genuinely successful FPGA load and while current hardware state remains known safe. Restore is a protected explicitly selected or documented fault-recovery decision, not automatic on every functional failure.

## Retired code and evidence

The old Issue #981 LA2016 JSON Supervisor, LA-only Direct A/B and diagnosis Workflow/scripts/tests/docs are removed. Their three exact Issue commands no longer have working entrypoints; none are remapped. Existing 2026-10-16/23 evidence and offline verifiers remain. Return authentic command exits, SHA256, device/runner provenance and failure reports. Host-only CI is not proof of live USB/SSH/FPGA/DUT acceptance.
