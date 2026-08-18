# Plasma Facility / PPU / Site Domain Model

## Canonical vocabulary

Plasma uses the following product and domain hierarchy:

```text
Plasma System
└── Facility
    └── PPU
        └── Site
```

- **Facility**: the deployment / administrative location that owns one or more PPUs, such as a factory, line, laboratory, or customer site.
- **PPU**: **Plasma Programming Unit**, one physical Plasma programming device and one local execution node.
- **Site**: **Programming Site**, one independently controlled programming position inside a PPU.
- **Socket**: the mechanical/electrical IC fixture attached to a Site. Site and Socket are deliberately not the same abstraction.

At the current prototype stage, one Site normally drives one Socket and one target IC. The model does not require that to remain true forever.

## Identity

A Site ID is local to its PPU. A durable fleet identity is therefore:

```text
(facility_id, ppu_id, site_id)
```

Do not flatten all Sites into one global integer namespace.

Changing terminology must not silently change a stable resource identity. For example, an existing PPU may retain the opaque ID `z2-dev-01`; the fact that the resource is now called a PPU does not require renaming its ID.

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
Site Manager
        |
        v
Programming Sites
```

Plasma Manager is an optional fleet control plane. Manager failure must not make a healthy local PPU unable to perform local programming work.

## Managed fleet

When multiple PPUs are managed centrally, the future topology is:

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
   |    +-- Site 0           |    +-- Site 0
   |    +-- Site 1           |    +-- Site 1
   |
   +-- PPU A2
        +-- Site 0
        +-- ...
```

The Manager owns fleet concerns such as registration, health, routing, aggregation, authentication and audit. A PPU owns local execution, safety and recovery.

## Canonical configuration

New configuration uses `ppu`, `facility_id`, and `sites`:

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
  - id: 0
    enabled: true
    interface: mock
  - id: 1
    enabled: true
    interface: mock
```

During the migration, the loader also accepts the legacy `programmer`, deployment `site_id`, `channels`, `max_supported_channels`, and `max_queue_depth_per_channel` names. Canonical and legacy forms for the same concept must not be mixed in one configuration block.

## Canonical status contract

The canonical local status shape is:

```json
{
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
      "site_id": 0,
      "enabled": true,
      "state": "idle"
    }
  ]
}
```

For a transition period the server also emits the legacy `programmer` and `channels` views so existing Web/UI and clients can migrate independently.

## REST boundary

The Plasma Web REST Gateway accepts canonical Site addressing:

```text
GET  /api/status?site=0
POST /api/jobs  { "site_id": 0, ... }
```

It temporarily accepts the legacy `channel` query and `channel_id` request field. If both canonical and legacy fields are supplied, they must resolve to the same Site.

## Plasma protocol v3.1 compatibility boundary

Plasma protocol v3.1 predates this vocabulary change and its wire metadata field is still named `channel_id`.

That field now means:

> the local **Programming Site ID** inside the already-selected PPU.

The domain rename does **not** rename the v3.1 wire field and does not bump the protocol version. The REST/domain layer translates `site_id` to v3.1 `channel_id` at the local protocol boundary.

A future protocol-version migration may rename the wire field, but that must be a separate explicit compatibility decision.

## Migration aliases

Canonical new code should use:

```text
PPUConfig
SiteConfig
SiteManager
SiteState
ppu
sites
facility_id
ppu_id
site_id
```

The following names remain compatibility aliases during migration:

```text
ProgrammerConfig
ChannelConfig
ChannelManager
ChannelState
programmer
channels
channel_id   # v3.1 wire compatibility
```

Compatibility aliases are not a license to introduce new code using the legacy vocabulary.
