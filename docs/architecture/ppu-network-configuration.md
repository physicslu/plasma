# PPU Network Configuration

## Purpose

This document defines the PPU-owned network configuration contract used by the `PPU / SITE Configuration` commissioning workflow.

The ownership boundary is:

```text
Control Console / Manager
        |
        | future commissioning orchestration
        v
PPU Web REST Gateway
        |
        +--> desired PPU network settings (Phase 1)
        |
        `--> Linux network activation (Phase 2, not implemented here)
```

PPU network configuration is separate from Gateway communication policy. In particular:

```text
/api/settings/gateway       Gateway-to-PPU timeout/retry policy
/api/settings/ppu-network   this PPU's desired Linux eth0 configuration
```

The two resources must not be merged merely because both contain the word "gateway" in operator terminology.

## Phase 1 scope

Phase 1 provides a validated, persistent desired-state contract only. It does **not** mutate the running Linux network stack.

Canonical routes:

```text
GET  /api/settings/ppu-network
POST /api/settings/ppu-network
```

The configured interface is fixed to:

```text
eth0
```

Supported modes are:

```text
dhcp
static
```

The server owns `revision` and `interface`. Clients write exactly:

```json
{
  "mode": "static",
  "address": "192.168.10.21",
  "prefix_length": 24,
  "gateway": "192.168.10.1",
  "dns_servers": ["192.168.10.1", "8.8.8.8"]
}
```

For DHCP mode, all static fields must be empty:

```json
{
  "mode": "dhcp",
  "address": null,
  "prefix_length": null,
  "gateway": null,
  "dns_servers": []
}
```

The Phase 1 response deliberately states that OS activation is unavailable:

```json
{
  "ok": true,
  "rest_contract_version": "3",
  "ppu_network_settings": {
    "revision": 1,
    "interface": "eth0",
    "mode": "dhcp",
    "address": null,
    "prefix_length": null,
    "gateway": null,
    "dns_servers": []
  },
  "activation": {
    "supported": false,
    "state": "not_implemented"
  }
}
```

A successful Phase 1 POST therefore means **the desired configuration was validated and durably stored**. It does not mean that `eth0`, routes, DNS, DHCP client state, or the current PPU endpoint changed.

## Validation

The PPU fails closed on malformed desired state.

Static mode requires:

- a valid IPv4 address;
- `prefix_length` in the range `1..32`;
- no network/broadcast address for prefixes where those addresses are reserved;
- an optional gateway that is on the configured subnet and is not the PPU address;
- at most three unique IPv4 DNS server addresses.

DHCP mode rejects static address, prefix, gateway, and DNS values. Unknown and missing POST fields are rejected rather than silently ignored.

## Persistence

The default persistence file is:

```text
<output-root>/ppu-network-settings.yaml
```

Updates use temporary-file write, flush, `fsync`, and atomic replacement. The in-memory desired state changes only after persistence succeeds.

An invalid existing persistence file fails closed during Gateway startup. It is not silently replaced with DHCP defaults because doing so would discard operator commissioning intent.

## Secure Gateway policy

When the secure Gateway boundary is active:

- read access uses `settings.read`;
- write access uses `settings.ppu_network.write`;
- the built-in `admin` role owns PPU network write permission;
- operator, engineer, viewer, and service roles do not receive this write permission by default;
- POST is a state-changing command and therefore requires the existing `Idempotency-Key` durable command ledger.

This is intentionally stricter than ordinary Programming Job operation permissions because a future Phase 2 network activation can remove the PPU from its current management path.

## Phase 1 packaged ARMv7 acceptance

The canonical one-command acceptance runner is:

```bash
source software/python/.venv/bin/activate
python scripts/ppu-network-phase1-acceptance.py
```

The runner is intentionally broader than a unit test. From the repository revision under test it:

```text
build PPU runtime
-> validate runtime
-> build canonical linux-armv7l release
-> verify detached SHA-256
-> clean-extract and verify the release
-> validate the clean runtime
-> preflight QEMU/binfmt ARMv7
-> run the packaged release in an ARMv7 container
-> start packaged Plasma Server + Gateway
-> exercise /api/settings/ppu-network
-> restart the Gateway and prove persistence
-> run negative validation tests
-> prove actual eth0 IPv4 did not change
-> emit human-readable + JSON evidence
```

The ARMv7 acceptance container is started without `CAP_NET_ADMIN` and with `no-new-privileges`. The runner also reads the actual container `eth0` IPv4 before and after the desired-state writes. A PASS therefore requires both:

```text
desired PPU network state changes and persists
actual Linux eth0 state does not change
```

The default machine-readable report is:

```text
.work/reports/ppu-network-phase1-acceptance.json
```

The terminal summary contains the Git SHA, product version, release SHA-256, ARMv7 architecture, each acceptance check, actual/desired IPv4 values, final settings revision, and the final PASS/FAIL result. Operators normally need to paste only this summary for review.

A Phase 1 PASS does **not** claim PYNQ-Z2 hardware, Linux network activation, DHCP activation, route/DNS mutation, Manager reconnect, same-`ppu_id` revalidation, or rollback. Those remain Phase 2 acceptance work.

The PPU release workflow also executes this same one-command runner so the acceptance tool itself is continuously exercised rather than existing only as an operator-side script.

## Phase 2 boundary

Phase 2 will add Linux network activation semantics. It must not reinterpret a Phase 1 desired-state write as an already-applied configuration.

Phase 2 is expected to own:

```text
validate candidate
-> acknowledge candidate
-> apply eth0
-> reconnect using the new endpoint
-> verify the same canonical ppu_id
-> commit on success
-> rollback on bounded reconnect failure
```

The Linux backend (`systemd-networkd`, NetworkManager, or another mechanism) must be selected from the actual PYNQ-Z2 image rather than assumed by the browser/API contract.

## Validation environments

The Phase 1 contract is architecture-independent Python and can be exercised on the SWPC ARM virtual machine for API, validation, persistence, restart, and security behavior.

The canonical packaged acceptance above uses SWPC/QEMU ARMv7 userspace as software evidence. That result does not prove PYNQ-Z2 Linux network activation. Actual `eth0` changes, reconnect behavior, rollback, boot-time network restoration, and PYNQ-Z2 image integration remain Phase 2 / Z2 acceptance work.
