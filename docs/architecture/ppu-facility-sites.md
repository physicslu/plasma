# Plasma Facility / PPU / Site Domain Model

## Canonical vocabulary

Plasma uses the following product and domain hierarchy:

```text
Plasma System
└── Facility
    └── PPU
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

- **Facility**: deployment / administrative location that owns one or more PPUs, such as a factory, line, laboratory, or customer location.
- **PPU**: **Plasma Programming Unit**, one physical Plasma programming device and one autonomous local execution node.
- **Site**: **Programming Site**, one independently controlled programming position inside a PPU.
- **Socket**: mechanical/electrical IC fixture attached to a Site. Site and Socket are deliberately different abstractions.

At the current prototype stage, one Site normally drives one Socket and one target IC. The model does not require that relation to remain permanently one-to-one.

## Identity

Canonical Site identity is one-based:

```text
SITE 1 -> site_id = 1
SITE 2 -> site_id = 2
...
SITE N -> site_id = N
```

There is no canonical `SITE 0`.

A Site ID is local to its PPU. A durable fleet identity is therefore:

```text
(facility_id, ppu_id, site_id)
```

Do not flatten all Sites into one global integer namespace. Renaming a domain concept also must not silently mutate a stable PPU resource ID.

## Standalone invariant

A PPU MUST remain independently operable without Plasma Manager.

```text
Browser / local client
        |
        v
PPU-local Plasma Web REST Gateway
        |
        v
Plasma Server
        |
        v
SiteManager / SiteWorker
        |
        v
Programming Sites
```

Plasma Manager is an optional future fleet control plane. Manager failure must not make a healthy local PPU unable to perform local programming, maintenance, or diagnostics.

## Managed fleet

When multiple PPUs are managed centrally, the target topology is:

```text
Browser / Fleet UI
        |
        v
Plasma Manager (optional)
        |
   +----+--------------------+
   |                         |
Facility A                Facility B
   |                         |
   +-- PPU A1                +-- PPU B1
   |    +-- SITE 1           |    +-- SITE 1
   |    +-- SITE 2           |    +-- SITE 2
   |
   +-- PPU A2
        +-- SITE 1
        +-- ... SITE N
```

The Manager owns fleet concerns such as registration, health aggregation, routing, authentication, audit and reconnect policy. Each PPU owns local execution, deterministic protocol timing, Site arbitration, hardware safety and recovery.

The current Web Console is a single-PPU console. A future fleet UI should reuse the same PPU-detail concepts rather than creating an unrelated second control model.

## Canonical configuration

New configuration uses `ppu`, `facility_id`, and one-based `sites`:

```yaml
ppu:
  id: z2-dev-01
  facility_id: lab-01
  model: PYNQ-Z2
  display_name: Plasma Z2 Prototype

server:
  max_supported_sites: 8
  max_queue_depth_per_site: 16

sites:
  - id: 1
    enabled: true
    interface: mock
  - id: 2
    enabled: true
    interface: mock
```

Legacy YAML rooted at `programmer` / `channels` may still be accepted only through the compatibility loader. Legacy Channel IDs are zero-based and translated exactly once at the configuration boundary:

```text
channel 0 -> SITE 1
channel 1 -> SITE 2
```

After loading, canonical Python domain code must not contain Site 0.

## Canonical status contract

Protocol v3.2 STATUS exposes canonical `ppu` and `sites` only. Example:

```json
{
  "protocol_version": "3.2",
  "ppu": {
    "ppu_id": "z2-dev-01",
    "facility_id": "lab-01",
    "model": "PYNQ-Z2",
    "display_name": "Plasma Z2 Prototype",
    "site_count": 8,
    "enabled_site_count": 2,
    "capabilities": {
      "max_supported_sites": 8,
      "operations": ["erase", "program", "verify", "read"]
    }
  },
  "sites": [
    {
      "site_id": 1,
      "enabled": true,
      "state": "idle"
    }
  ]
}
```

The legacy `programmer/channels` shape belongs to v3.1 compatibility responses. It is not emitted as an additional canonical view inside v3.2 STATUS.

## REST boundary

The Plasma Web REST Gateway uses canonical one-based Site addressing:

```text
GET  /api/status?site=1
POST /api/jobs  { "site_id": 1, ... }
```

Legacy `channel` / `channel_id` input may be accepted at an explicit compatibility boundary as zero-based identity. It must be translated before entering the canonical domain; new Web/REST clients must send `site_id` only.

## Plasma Protocol v3.2

The canonical TCP wire protocol is v3.2:

```text
magic:            PLASMA32
protocol_version: 3.2
identity:         site_id = 1..N
```

A v3.2 request must not dual-send `channel_id`. A v3.2 response uses `site_id`, `ppu`, and `sites` according to the applicable message shape.

## Protocol v3.1 compatibility boundary

Protocol v3.1 is a legacy adapter, not a second domain model:

```text
v3.1                         canonical / v3.2
PLASMA31                     PLASMA32
channel_id = 0       ->      site_id = 1
channel_id = 1       ->      site_id = 2
...
channel_id = N-1     ->      site_id = N
```

A v3.1 request receives a v3.1 response. Its legacy STATUS shape may use `programmer/channels`, and E4001/E4002/E4003 error names may serialize as `CHANNEL_INVALID`, `CHANNEL_DISABLED`, and `CHANNEL_BUSY`.

Do not use `site_id == channel_id` as an invariant.

## Migration aliases

Canonical new code should use:

```text
PPUConfig
SiteConfig
SiteManager
SiteWorker
SiteState
ppu
sites
facility_id
ppu_id
site_id
```

The following names may exist only where required for legacy compatibility:

```text
ProgrammerConfig
ChannelConfig
ChannelManager
ChannelState
programmer
channels
channel_id
```

Compatibility aliases are not permission to introduce new product/domain code using the retired vocabulary.
