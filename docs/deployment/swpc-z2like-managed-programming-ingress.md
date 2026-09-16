# SWPC Z2-like Secure Managed Programming Ingress

> Status: **SUPERSEDED / RETIRED AS AN ACTIVE TOPOLOGY**.

This document records the former Render Control Station -> SWPC x86 `swpc-z2like` mock-Programming ingress. It is retained only as architectural history. Current public `z2like-demo` ownership is documented in `docs/deployment/z2like-demo-qemu.md`.

## Retired boundaries

The former SWPC host diagnostics ingress:

```text
127.0.0.1:18081
```

was retired by Issue #549. No diagnostics/status/PS-loopback listener or public hostname may be recreated there.

The historical x86 managed-Programming use of host `18082` has also been migrated away from the x86 surrogate. Current `z2like-demo` uses:

```text
Render z2like-demo Control Station
  -> ppu-managed-lab.open4th.com
  -> Cloudflare Access/Tunnel
  -> SWPC 127.0.0.1:18082 bounded managed ingress
  -> QEMU ARMv7 simulated Z2 172.30.77.2:18080 Plasma Gateway
```

The exact Manager-owned Bootstrap maintenance allowlist is projected through the same host `18082` boundary to:

```text
QEMU private 172.30.77.2:18081 Bootstrap/recovery
```

This private Bootstrap service is not the retired SWPC host listener.

## Current SWPC x86 surrogate boundary

The `swpc-z2like` engineering surrogate retains only its local full Gateway:

```text
127.0.0.1:18080  full local Plasma Gateway
127.0.0.1:18081  retired / must remain unused
```

Local Control Station may target the full `18080` Gateway. Public z2like-demo traffic must use the maintained QEMU path through host `18082`.

## Security invariant

Do not expose the SWPC x86 full Gateway `127.0.0.1:18080` directly to the Internet. Do not recreate a public/restricted listener on host `18081`.

For the current z2like-demo managed ingress, the Nginx allowlist remains bounded; Cloudflare Access provides transport service identity, while Plasma Gateway remains the final application authorization, Site scope, idempotency and execution authority.

## Current operator references

Use these instead of the historical procedure previously contained here:

- `docs/deployment/port-profile-matrix.md`
- `docs/deployment/local-control-station.md`
- `docs/deployment/z2like-demo-qemu.md`
- `scripts/plasmactl-z2like-demo`
- `scripts/plasmactl-z2like-demo-managed-ingress`

Historical handover records may describe the previous x86 managed ingress. They are evidence of prior deployment state, not current operational instructions.
