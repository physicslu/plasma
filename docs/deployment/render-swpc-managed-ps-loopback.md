# Render Control Station -> SWPC Z2-like PPU Managed PS Loopback

> Status: **RETIRED — Issue #549 (2026-09-16)**. Do not deploy this topology.

## Retired topology

The former integration-qualification path was:

```text
Render Control Station
  -> public HTTPS restricted PPU hostname
  -> Cloudflare Tunnel
  -> SWPC 127.0.0.1:18081 restricted diagnostics/status/PS-loopback ingress
  -> SWPC x86_64 surrogate Gateway 127.0.0.1:18080
```

Issue #549 retired both the public `ppu-lab.open4th.com` route and the SWPC host `127.0.0.1:18081` listener. Repository deployment tooling must not recreate them.

## Current supported paths

### Linux Local Control Station

```text
Browser
  -> SWPC Control Station 127.0.0.1:18190
  -> Local Manager 127.0.0.1:18280
  -> configured full Plasma Gateway
```

When the co-resident SWPC engineering surrogate is selected, its full Gateway is `127.0.0.1:18080`.

### Public z2like-demo

```text
z2like-demo.open4th.com (Render Control Station)
  -> ppu-managed-lab.open4th.com
  -> Cloudflare Access/Tunnel
  -> SWPC 127.0.0.1:18082 bounded managed ingress
  -> QEMU ARMv7 simulated Z2 172.30.77.2:18080 Gateway
```

The bounded host `18082` ingress also projects the exact Manager-owned Bootstrap maintenance allowlist to QEMU private `172.30.77.2:18081`.

## Port 18081 boundary after retirement

```text
SWPC host 127.0.0.1:18081     retired; must remain unused
QEMU private 172.30.77.2:18081 Bootstrap/recovery; retained
Real Z2 <Z2-IP>:18081          Bootstrap/recovery; retained
```

The retirement applies only to the legacy SWPC host diagnostics/public ingress. It does not retire the Z2 Bootstrap/recovery service identity.

## Historical evidence

Historical handover records may still describe the former `ppu-lab` qualification topology. They are evidence of previous state, not current deployment guidance. Current operator contracts are defined by:

- `docs/deployment/port-profile-matrix.md`
- `docs/deployment/local-control-station.md`
- `docs/deployment/z2like-demo-qemu.md`
- `scripts/plasmactl-swpc-z2like`
- `scripts/plasmactl-z2like-demo-managed-ingress`
