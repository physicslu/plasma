# Plasma Multi-Programmer / Multi-Site Architecture

## Purpose

Plasma is evolving from one multi-channel programmer into a fleet-capable programming platform.
The resource hierarchy is:

```text
Plasma
└── Site
    └── Programmer
        └── Channel
```

A Channel is not globally unique. The durable identity of a channel at fleet scope is the tuple:

```text
(site_id, programmer_id, channel_id)
```

## Architectural boundary

Each embedded Plasma Server represents exactly one physical Programmer.
The local programming path remains:

```text
Browser / local client
        |
        v
Programmer-local REST Gateway
        |
        v
Plasma Server v3.1
        |
        v
ChannelManager
        |
        v
Channels
```

The local v3.1 programming protocol continues to address work by `channel_id` because it is already connected to one known Programmer.
Do not add `site_id` or `programmer_id` to every local JobRequest merely for fleet routing.
Fleet routing belongs above the Programmer boundary.

The future fleet path is:

```text
Browser / Operator Console
          |
          v
Plasma Manager / Fleet Gateway
          |
    +-----+-------------------+
    |                         |
    v                         v
Site A                    Site B
    |                         |
    +-- Programmer A1         +-- Programmer B1
    |      +-- CH0            |      +-- CH0
    |      +-- CH1            |      +-- CH1
    |                         |
    +-- Programmer A2         +-- Programmer B2
           +-- CH0                   +-- CH0
           +-- ...                   +-- ...
```

The Manager will resolve `(site_id, programmer_id, channel_id)` to the correct Programmer endpoint, while the embedded Programmer continues to execute a local `channel_id` job.

## Programmer identity and capability discovery

Each Programmer has configuration metadata:

```yaml
programmer:
  id: z2-dev-01
  site_id: swpc-lab
  model: PYNQ-Z2
  display_name: Plasma Z2 Prototype
```

`programmer.id` must be unique within a Site. `site_id` identifies the administrative/production Site that owns the Programmer.
Production deployments must assign stable IDs rather than reusing repository example values.

The normal STATUS response now exposes a top-level `programmer` object next to `channels`:

```json
{
  "programmer": {
    "programmer_id": "z2-dev-01",
    "site_id": "swpc-lab",
    "model": "PYNQ-Z2",
    "display_name": "Plasma Z2 Prototype",
    "channel_count": 8,
    "enabled_channel_count": 2,
    "capabilities": {
      "max_supported_channels": 8,
      "operations": ["erase", "program", "verify", "read"]
    }
  },
  "channels": []
}
```

`channel_count` is the number of channels actually described by the Programmer configuration. It is deliberately different from `max_supported_channels`, which is the software implementation ceiling.
This allows 2-channel, 4-channel, and 8-channel Programmer products to use the same software architecture without pretending every unit physically contains eight channels.

## Compatibility policy

This phase is intentionally backward compatible:

- Existing local jobs still use `channel_id`.
- Protocol version remains v3.1.
- Existing REST `/api/status` continues to return `channels` and gains `programmer` metadata.
- Existing clients that ignore unknown response fields continue to work.
- Multi-Programmer routing is not implemented inside `ChannelManager`.

This separation avoids turning a local hardware execution service into a fleet scheduler.

## Delivery phases

### Phase 1 — Programmer abstraction

Implemented in this change:

- Programmer identity in configuration.
- Site ownership metadata.
- Dynamic actual `channel_count` derived from configured channels.
- Programmer capability discovery in STATUS.
- Programmer/Site identity in key server event logs.
- Backward-compatible local protocol behavior.

### Phase 2 — Dynamic Programmer Console

The Web Console should stop assuming eight channels in its UI model and build the channel matrix from STATUS discovery.
The current eight-channel screen then becomes a Programmer Detail view rather than the fleet root page.

### Phase 3 — Multi-Programmer Manager

Add a Manager/Fleet Gateway with responsibilities such as:

- Programmer registration/discovery.
- Heartbeat and online/offline state.
- Routing by `(site_id, programmer_id, channel_id)`.
- Aggregated job/event state.
- Stable browser endpoint independent of Programmer count.

### Phase 4 — Multi-Site Console

Add Site and Programmer overview pages, permissions, fleet health, production statistics, audit history, and deployment/firmware-management boundaries.

## Design constraint

Do not make Channel globally unique by inventing one large channel number space.
A local `CH0` is meaningful only inside its Programmer.
Fleet-level code must preserve the hierarchy instead of flattening it.
