# H020 — z2like-demo QEMU ARMv7 Backend

Date: 2026-09-14

Status: implementation/CI transaction in progress; do not claim SWPC public deployment until host acceptance and external Cloudflare routing are executed.

## Decision

Plasma has one simulation environment: **SWPC**.

`z2like-demo` has one canonical PPU backend: **QEMU ARMv7 simulated Z2 running on SWPC**.

`swpc-z2like` remains a separate x86_64 engineering surrogate and is not the public `z2like-demo` backend.

## Canonical topology

```text
z2like-demo public hostname
  -> SWPC 127.0.0.1:18390 dedicated Console/BFF
  -> SWPC 127.0.0.1:18380 dedicated Manager
  -> private Docker bridge
  -> QEMU ARMv7 simulated Z2
       :18081 Bootstrap
       :18080 Gateway
       :9900 Server
```

The QEMU target publishes no Docker host ports. Existing host `18080/18081/18082` remain owned by `swpc-z2like` and must not be widened or repurposed.

## Implemented repository path

- `scripts/z2like-demo-qemu.py` — SWPC scenario orchestrator.
- `scripts/z2like-demo-qemu-target.py` — persistent ARMv7 userspace target/supervisor.
- `scripts/z2like-demo-qemu-kit.py` — canonical Z2 kit verifier/consumer for simulation.
- `scripts/z2like-demo-qemu-installer.py` — simulation-only activation adapter reusing kit-local installer core.
- `scripts/z2like-demo-qemu-e2e.py` — Manager → Bootstrap → chunk upload → deployment → Runtime acceptance.
- `.github/workflows/z2like-demo-qemu.yml` — static contracts + QEMU ARMv7 E2E.
- `docs/deployment/z2like-demo-qemu.md` — operator/security/qualification contract.

## Qualification boundary

A green QEMU acceptance may qualify the software path through Manager/Bootstrap/kit/deployment coordinator/ARMv7 packaged Runtime. It does not qualify PYNQ-Z2 hardware, real product Python installation, physical systemd/DAC behavior, real Z2 reboot persistence, PL, Site electrical behavior, target power or real IC programming.

Exact retained statement:

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

## External deployment work after merge

Repository automation cannot prove the operator-managed Cloudflare DNS/Tunnel/Access state. On SWPC, after deploying the merged source and activating the scenario, the public `z2like-demo` hostname must be routed **only** to `http://127.0.0.1:18390` and then verified from outside the host.
