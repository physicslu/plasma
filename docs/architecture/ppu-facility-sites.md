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

At the current prototype stage, one configured Site normally drives one Socket and one target IC. The model does not require that relation to remain permanently one-to-one.

## Identity

Canonical Site identity is one-based:

```text
SITE 1 -> site_id = 1
SITE 2 -> site_id = 2
...
SITE N -> site_id = N
```

There is no canonical `SITE 0`.

A Site ID is local to its PPU. Durable fleet identity is:

```text
(facility_id, ppu_id, site_id)
```

Do not flatten all Sites into one global integer namespace.

## Capacity versus current topology

Plasma deliberately separates **capacity** from **configured topology**:

```text
max_supported_sites = capability ceiling
site_count           = number of Sites currently configured/reported
enabled_site_count   = configured Sites currently enabled
sites                = current Site topology
```

Therefore this is a valid PS-only PPU state:

```text
max_supported_sites = 8
site_count           = 0
enabled_site_count   = 0
sites                = []
```

A zero Site count means no Site topology is currently configured. It does **not** mean the appliance can never support Sites, and it does **not** introduce `Site 0`. Once any Site is present its `site_id` must still be an integer >=1.

This distinction is required for early PS software-node commissioning: Manager may trust a real PPU identity and ready PS execution before PL-backed physical Sites are configured. Fabricating Sites to make a PS-only node look populated is an evidence-boundary violation.

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

Manager owns fleet concerns such as registry, health aggregation, routing policy and fleet audit. Each PPU owns its Gateway, local execution, deterministic protocol timing, Site arbitration, hardware safety and recovery.

## Canonical configuration

A populated example:

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

A PS-only closed-hardware example is also canonical:

```yaml
server:
  max_supported_sites: 8

sites: []
```

Unknown/retired configuration fields remain errors rather than migration aliases.

## Canonical status contract

A populated status reports current topology, for example:

```json
{
  "ppu": {
    "ppu_id": "z2-dev-01",
    "facility_id": "lab-01",
    "model": "PYNQ-Z2",
    "display_name": "Plasma Z2 Prototype",
    "site_count": 2,
    "enabled_site_count": 2,
    "capabilities": {
      "max_supported_sites": 8,
      "operations": ["erase", "program", "verify", "read"]
    }
  },
  "sites": [
    {"site_id": 1, "enabled": true, "state": "idle"},
    {"site_id": 2, "enabled": true, "state": "idle"}
  ]
}
```

For PS-only commissioning the consistent status is:

```json
{
  "ppu": {
    "ppu_id": "z2-dev-01",
    "facility_id": "lab",
    "model": "PYNQ-Z2",
    "site_count": 0,
    "enabled_site_count": 0,
    "capabilities": {"max_supported_sites": 8}
  },
  "sites": []
}
```

Manager must require internal consistency (`len(sites) == site_count`, `0 <= enabled_site_count <= site_count`) while accepting `site_count == 0` as a legitimate topology state.

## REST boundary

When Sites exist, Gateway addressing is one-based:

```text
GET  /api/status?site=1
POST /api/jobs  { "site_id": 1, ... }
```

REST v3 accepts canonical Site fields only; zero-based addressing is not an alternate contract.

## Network terminology boundary

Do not confuse:

```text
Plasma Gateway Endpoint  http://192.168.2.99:18080
Default Gateway          e.g. 192.168.2.1 router / next hop
```

The PPU network JSON field `gateway` means **Default Gateway** for wire compatibility.

## Plasma Protocol v3.3

```text
magic:            PLASMA33
protocol_version: 3.3
identity:         site_id = 1..N when a Site exists
execution data:   Normalized Image
```

A programming request uses `site_id`; PS-only PPU-level health/identity observation does not invent a Site identity.

## Canonical runtime names

Canonical code uses `PPUConfig`, `SiteConfig`, `SiteManager`, `SiteWorker`, `SiteState`, `ppu`, `sites`, `facility_id`, `ppu_id`, and `site_id`.

Retired Programmer/Channel vocabulary is not a compatibility surface for current runtime code.
