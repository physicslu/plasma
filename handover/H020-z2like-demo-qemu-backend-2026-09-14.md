# H020 — z2like-demo QEMU ARMv7 Backend

Date: 2026-09-14

Status: QEMU backend implementation exists; the original public-routing assumption in this handover was corrected during the Render/QEMU convergence transaction. Do not use the historical `z2like-demo -> SWPC :18390` route.

## Corrected decision

Plasma has one simulation environment: **SWPC**.

`z2like-demo` has one canonical PPU backend: **QEMU ARMv7 simulated Z2 running on SWPC**.

`swpc-z2like` remains a separate x86_64 engineering surrogate and is not the public `z2like-demo` backend.

The public `z2like-demo` Control Station remains **Render-hosted**. QEMU replaces only its PPU backend.

## Canonical topology

```text
https://z2like-demo.open4th.com
  -> Render Console/BFF
  -> Render Plasma Manager
  -> https://ppu-managed-lab.open4th.com
  -> Cloudflare Access/Tunnel
  -> SWPC 127.0.0.1:18082 bounded managed ingress
  -> private Docker bridge
  -> QEMU ARMv7 simulated Z2 172.30.77.2
       :18080 Gateway
       :18081 Bootstrap
       :9900  Server
```

The QEMU target publishes no Docker host ports.

SWPC `127.0.0.1:18380/18390` are retained only as an internal Bootstrap maintenance/acceptance fixture. They are not public hostname origins.

SWPC host `127.0.0.1:18081` remains the legacy `ppu-lab.open4th.com` diagnostics/status ingress pending retirement. It is unrelated to QEMU private `172.30.77.2:18081` Bootstrap.

## Implemented repository path

- `scripts/z2like-demo-qemu.py` — SWPC QEMU backend + internal maintenance fixture orchestrator.
- `scripts/z2like-demo-qemu-target.py` — persistent ARMv7 userspace target/supervisor.
- `scripts/z2like-demo-qemu-kit.py` — canonical Z2 kit verifier/consumer for simulation.
- `scripts/z2like-demo-qemu-installer.py` — simulation-only activation adapter reusing kit-local installer core.
- `scripts/z2like-demo-qemu-e2e.py` — Manager → Bootstrap → chunk upload → deployment → Runtime acceptance.
- `scripts/z2like-demo-qemu-build-kit.py` — local canonical ARMv7 Runtime/Z2-kit builder for the one-command deployment flow.
- `scripts/z2like-demo-qemu-deploy.py` — persistent Manager Bootstrap deployment/lifecycle helper.
- `scripts/plasmactl-z2like-demo-managed-ingress` — host `18082` bounded QEMU managed ingress.
- `scripts/plasmactl-z2like-demo` — deploy/update/verify/status orchestration.
- `.github/workflows/z2like-demo-qemu.yml` — static contracts + QEMU ARMv7 E2E.
- `docs/deployment/z2like-demo-qemu.md` — current operator/security/qualification contract.

## Operator path

After this convergence transaction is merged, the intended SWPC command is:

```bash
sudo ./scripts/plasmactl update z2like-demo
```

That command owns the source fast-forward, QEMU Runtime deployment, `18082` reconciliation and full health verification. It does **not** move `z2like-demo.open4th.com` away from Render.

## Qualification boundary

A green QEMU acceptance may qualify the software path through Manager/Bootstrap/kit/deployment coordinator/ARMv7 packaged Runtime. It does not qualify PYNQ-Z2 hardware, real product Python installation, physical systemd/DAC behavior, real Z2 reboot persistence, PL, Site electrical behavior, target power or real IC programming.

Exact retained statement:

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

## External deployment evidence after merge

Repository CI cannot prove live Render, Cloudflare or SWPC deployment state. Post-merge host acceptance must verify:

```text
z2like-demo.open4th.com remains Render-hosted
Render Manager alias = z2like-qemu
ppu-managed-lab.open4th.com reaches SWPC host :18082
SWPC :18082 reaches QEMU 172.30.77.2:18080
QEMU Runtime is active/ready
```

Do not change the `z2like-demo.open4th.com` DNS CNAME to SWPC.
