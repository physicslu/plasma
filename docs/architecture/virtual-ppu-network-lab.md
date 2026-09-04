# Virtual PPU Network Lab

## Status and purpose

This document defines the current integration-host acceptance for Manager-owned Static IPv4 commissioning across an actual Linux endpoint migration without using PYNQ-Z2 hardware.

The lab exists to close one specific evidence gap between the existing PPU Network Phase 2 acceptance and later native Z2 qualification:

```text
PPU Phase 2 isolated activation acceptance
        |
        | proves PPU activation semantics + real lab IPv4 mutation
        v
Virtual PPU Network Lab
        |
        | adds the production Plasma Manager commissioning transaction
        v
future PYNQ-Z2 native network backend acceptance
```

The lab is not a replacement for Z2 hardware-in-the-loop validation.

## Ownership model

The Linux integration host owns the production Plasma Manager process. Two packaged ARMv7 PPUs run inside one isolated Docker bridge. Each PPU has two addresses with different owners:

```text
Linux host
  |
  +-- Plasma Manager (real production code, no CAP_NET_ADMIN)
  |
  `-- isolated Docker bridge 192.168.78.0/24
        |
        +-- Virtual PPU A
        |     Docker control IPv4: 192.168.78.40
        |     managed IPv4:        192.168.78.10 -> 192.168.78.21
        |     ppu_id:              virtual-ppu-a
        |     Gateway:             no CAP_NET_ADMIN
        |     helper:              CAP_NET_ADMIN only
        |
        `-- Virtual PPU B
              Docker control IPv4: 192.168.78.41
              managed IPv4:        192.168.78.11
              ppu_id:              virtual-ppu-b
              Gateway:             no CAP_NET_ADMIN
              helper:              CAP_NET_ADMIN only
```

The Docker control IPv4 is deliberately outside the property under test. The helper owns only the lab-managed IPv4 on the shared PPU `eth0` network namespace. The host Manager connects directly to the managed addresses; the acceptance does not hide routing behind a probe container.

The host uplink, normally SWPC `eth0`, is fingerprinted before the isolated lab starts and must remain unchanged during commissioning.

## Canonical runner

The one-command acceptance is:

```bash
source software/python/.venv/bin/activate
python scripts/virtual-ppu-network-lab.py
```

Default outputs are:

```text
.work/virtual-ppu-network-lab/
.work/reports/virtual-ppu-network-lab.json
```

The runner can reuse an already validated PPU runtime:

```bash
python scripts/virtual-ppu-network-lab.py \
  --runtime-dir /path/to/plasma-release/runtime
```

CI uses the already clean-extracted and validated ARMv7 release runtime so this acceptance does not rebuild the release a second time.

## Production Manager path under test

The test does not call the PPU activation API as its orchestration entry point. It starts the real Plasma Manager server with a durable runtime registry containing `ppu-a` and `ppu-b`, waits for current trusted fleet observations, and sends the production commissioning request:

```text
POST /api/registry/ppu-a/network-commissioning
```

with an `Idempotency-Key` and desired Static IPv4 state.

The expected production path is:

```text
Manager registry = old endpoint
-> trusted fleet observation for ppu-a and ppu-b
-> Manager reads canonical ppu_id on old endpoint
-> Manager saves PPU desired static network
-> Manager starts PPU activation
-> helper mutates real lab-managed IPv4 on PPU A eth0
-> old managed endpoint disappears
-> candidate managed endpoint appears
-> Manager reconnects candidate
-> Manager verifies same immutable ppu_id
-> Manager commits PPU activation
-> Manager persists activation_committed
-> Manager compare-and-swaps registry old -> candidate
-> Manager persists registry_reconciled
-> Manager persists completed
```

A pass requires all of those boundaries to agree. Merely reaching the candidate address is not sufficient.

## Required acceptance evidence

The JSON report records explicit PASS evidence for at least:

- isolated Docker network creation;
- two distinct immutable PPU identities;
- old PPU A managed endpoint reachability;
- both PPU Gateway processes without `CAP_NET_ADMIN`;
- both helper processes with `CAP_NET_ADMIN`;
- host Plasma Manager without `CAP_NET_ADMIN`;
- current trusted two-PPU Manager fleet observation;
- Manager registry initially pointing `ppu-a` to the old managed endpoint;
- production Manager commissioning state `completed`;
- candidate endpoint returning the same `ppu_id`;
- actual old managed endpoint removal;
- PPU activation state `committed`;
- Manager registry compare-and-swap to the candidate endpoint;
- unrelated `ppu-b` registry entry remaining unchanged;
- durable Manager commissioning journal state `completed`;
- host uplink address signature unchanged.

## Why two Virtual PPUs exist now

Phase 1 of this lab commissions only `ppu-a`. `ppu-b` is intentionally real and independently identified even though it is not mutated in the happy path.

That second endpoint is infrastructure for the next P0 Static IPv4 fault-injection slice, including duplicate candidate ownership and wrong-device identity scenarios. Keeping the second PPU in the base lab prevents the fault-injection PR from inventing a different topology and therefore changing both the test harness and failure semantics at the same time.

## Privilege boundary

The acceptance is invalid if it uses any of these shortcuts:

- Docker `--network host` for a PPU;
- `sudo` inside the Plasma Gateway;
- `CAP_NET_ADMIN` on the Plasma Gateway;
- `CAP_NET_ADMIN` on Plasma Manager;
- host-uplink address mutation to simulate a PPU;
- a Browser- or test-script-supplied arbitrary candidate URL.

Only the helper sidecar receives `CAP_NET_ADMIN`, and it shares the target PPU network namespace. The helper contract remains the existing `snapshot` / `apply(settings)` / `restore(snapshot)` Unix-socket boundary.

## CI integration

The `PPU release artifact` workflow runs three distinct network acceptance layers:

```text
Phase 1 packaged ARMv7 desired-state acceptance
        ↓
Phase 2 packaged ARMv7 activation / rollback acceptance
        ↓
Virtual PPU + production Manager commissioning acceptance
```

Changes under `software/python/plasma_manager/**` also trigger the release workflow because Manager commissioning behavior is now part of this acceptance surface.

The Virtual PPU lab reuses the already clean-extracted release runtime produced earlier in the workflow. This preserves the packaged PPU evidence while avoiding a redundant release build.

## Evidence boundary

A PASS proves:

- production Plasma Manager commissioning code can drive the existing packaged PPU Phase 2 activation contract;
- Manager can reconnect across a real Linux lab-managed IPv4 migration;
- candidate identity verification is based on the same immutable `ppu_id`;
- activation commit and Manager registry reconciliation complete in the correct order;
- Manager and PPU journals/registry state converge to `completed`;
- privilege separation is preserved;
- the integration-host uplink is not used as the PPU network mutation target.

A PASS does **not** prove:

- PYNQ-Z2 MAC, PHY, carrier, or switch behavior;
- the final PYNQ-Z2 Linux network-manager backend;
- DHCP endpoint migration;
- production DNS or Default Gateway mutation;
- boot-time network persistence;
- Static IPv4 fault-injection or crash recovery cases;
- PS-to-PL communication;
- FPGA timing or Site I/O;
- target power control;
- real IC programming.

Those remain separate acceptance gates.
