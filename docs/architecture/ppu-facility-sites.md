# Plasma Facility / PPU / Site Domain Model

## Canonical vocabulary

Plasma uses one product/domain hierarchy:

```text
Plasma System
└── Facility
    └── PPU
        ├── SITE 1
        ├── SITE 2
        └── ... SITE N
```

- **Facility**: deployment / administrative location that owns one or more PPUs.
- **PPU**: **Plasma Programming Unit**, one physical autonomous programming device and local execution node.
- **Site**: **Programming Site**, one independently controlled programming position inside a PPU.
- **Socket**: mechanical/electrical IC fixture attached to a Site. Site and Socket are separate abstractions.
- **Plasma Gateway**: the PPU-local northbound API service.
- **Plasma Gateway API**: the REST contract exposed by Plasma Gateway.
- **Plasma Gateway Endpoint**: the network location used to reach a Plasma Gateway.

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

A Site ID is local to its PPU. Durable fleet identity is therefore:

```text
(facility_id, ppu_id, site_id)
```

Do not flatten all Sites into one global integer namespace.

## Standalone invariant

A PPU MUST remain independently operable without Plasma Manager.

```text
Browser / local client
        |
        v
PPU-local Plasma Gateway
        |
        | Plasma Gateway API
        v
Plasma Server
        |
        v
SiteManager / SiteWorker
        |
        v
Programming Sites
```

Plasma Manager is an optional fleet control plane. Manager failure must not make a healthy local PPU unable to perform local programming, maintenance, or diagnostics.

## Managed fleet

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

The Manager owns fleet concerns such as registry, health aggregation, routing policy and fleet audit. Each PPU owns its Plasma Gateway, local execution, deterministic protocol timing, Site arbitration, hardware safety and recovery.

## Canonical configuration

Configuration uses `ppu`, `facility_id`, and one-based `sites` only:

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

The development-phase canonical loader does not provide a second zero-based device model. Unknown/retired configuration fields are configuration errors rather than migration aliases.

## Canonical status contract

Protocol v3.3 STATUS exposes `ppu` and `sites` using one-based Site identity:

```json
{
  "protocol_version": "3.3",
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

## REST boundary

The Plasma Gateway API uses canonical one-based Site addressing:

```text
GET  /api/status?site=1
POST /api/jobs  { "site_id": 1, ... }
```

REST v3 accepts canonical Site fields only; retired zero-based addressing is not an alternate REST contract.

## Network terminology boundary

The Plasma Gateway service must not be confused with Linux routing configuration:

```text
Plasma Gateway Endpoint  http://192.168.2.99:18080
Default Gateway          e.g. 192.168.2.1 router / next hop
```

The PPU network JSON field `gateway` is retained for wire compatibility and means **Default Gateway**.

## Plasma Protocol v3.3

The canonical TCP execution wire protocol is:

```text
magic:            PLASMA33
protocol_version: 3.3
identity:         site_id = 1..N
execution data:   Normalized Image
```

A request uses `site_id`, never a second identity field. Program/Verify carry normalized execution Image data and `image_size` / `image_sha256` according to `software/python/docs/protocol.md`.

## Canonical runtime names

Canonical code uses:

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

Retired Programmer/Channel vocabulary is not a compatibility surface for current runtime code. Historical documents may describe prior migrations, but current product contracts and executable code must use Facility / PPU / Site only.
