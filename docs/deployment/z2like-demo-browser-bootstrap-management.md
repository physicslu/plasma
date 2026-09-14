# z2like-demo Browser Runtime Deployment Management Path

## Scope

This profile enables the Render-hosted `z2like-demo` Control Station to perform
QEMU ARMv7 Runtime maintenance through the independent PPU Bootstrap without
publishing the Bootstrap service itself.

Canonical management path:

```text
Browser
  -> Render Console/BFF
  -> Render Bootstrap-capable Manager
  -> https://ppu-managed-lab.open4th.com/__plasma/bootstrap/...
  -> Cloudflare Access service-token policy + Tunnel
  -> SWPC 127.0.0.1:18082
  -> fixed Bootstrap route/method allowlist
  -> QEMU 172.30.77.2:18081 Bootstrap
```

The existing Product Runtime / Programming path remains:

```text
Browser
  -> Render Console/BFF
  -> Render Manager
  -> https://ppu-managed-lab.open4th.com
  -> Cloudflare Access service-token policy + Tunnel
  -> SWPC 127.0.0.1:18082
  -> QEMU 172.30.77.2:18080 Gateway
```

The two QEMU services remain independent. Sharing the protected external origin
does not merge the device services: SWPC maps only a fixed
`/__plasma/bootstrap` maintenance prefix to `:18081`; all other product API
traffic remains mapped to `:18080`.

## Security boundary

The browser never receives a QEMU Bootstrap endpoint or stored Bootstrap bearer
token. Browser Bootstrap requests terminate at the Render BFF and are converted
to Manager-owned operations.

The path requires both transport and device authorization:

1. Render Manager owns the Cloudflare Access service identity for the exact
   configured `ppu-managed-lab` origin.
2. Manager stores the device-local Bootstrap pairing token separately from the
   registry and binds it to the Bootstrap `device_id`.
3. SWPC exposes only the exact Bootstrap status/upload/deployment route set under
   `__plasma/bootstrap`; arbitrary Bootstrap paths and direct public `:18081`
   access are not part of the profile.
4. Manager lifecycle admission remains fail-closed. A commissioned PPU must be
   disabled for maintenance, and a disabled PPU requires a current trusted idle
   observation before normal Runtime mutation.
5. The public `z2like-demo` registry is a fixed target. The BFF permits lifecycle
   changes only for the canonical `z2like-qemu` alias and rejects registry add,
   remove, endpoint mutation, and unrelated PATCH fields.

The Manager registry endpoint remains the protected HTTPS reachability identity.
The device Runtime bind address is separate Manager-owned deployment state and is
validated as a private, non-loopback IPv4 address (`172.30.77.2` for the canonical
simulation profile).

## Port boundary

Do not conflate these uses of port `18081`:

```text
SWPC host 127.0.0.1:18081
  = legacy/restricted diagnostics ingress
  = not used by this management path

QEMU 172.30.77.2:18081
  = independent Bootstrap
  = used only behind the fixed managed prefix

Real Z2 <IP>:18081
  = Bootstrap/recovery
  = unchanged by this simulation profile
```

## Qualification boundary

This work qualifies only the software/simulation control path after live
acceptance. It does not establish any claim for physical hardware.

> **Real PYNQ-Z2 deployment/reboot/rollback HIL: NOT QUALIFIED.**

No claim is made for PL/FPGA behavior, target power behavior, real IC
programming, or physical multi-Site concurrency.
