# Optional Plasma Manager Control Plane

## Architectural invariant

A Plasma PPU is a complete autonomous execution node. Plasma Manager is an optional fleet control plane and MUST NOT become a runtime prerequisite for local programming.

The dependency direction is one-way:

```text
Plasma Manager -> PPU
```

A PPU must never require a live Manager connection in order to start its local Plasma Server, expose its local Web Console, execute jobs, recover a Site, or perform maintenance and diagnostics.

## Mode A: standalone PPU

```text
Browser / local client
        |
        v
PPU-local Web Console
        |
        v
Plasma Web REST Gateway
        |
        v
Plasma Server
        |
        v
SiteManager / SiteWorker
        |
        v
SITE 1 .. SITE N
        |
        v
PS / PL / target IC
```

No Manager, central PC, registration service, heartbeat service, or external scheduler is required.

## Mode B: managed fleet

```text
Browser / Fleet UI
        |
        v
Plasma Manager
        |
   +----+--------------------+
   |                         |
   v                         v
PPU A                       PPU B
   |                         |
local REST API             local REST API
   |                         |
local execution            local execution
```

The Manager may own fleet-level concerns such as discovery, registration, health aggregation, routing, authentication policy, audit aggregation, deployment orchestration, and firmware catalog management. It does not replace local deterministic execution.

## PPU northbound contract

The PPU exposes a small Manager-friendly contract through the existing Plasma Web REST Gateway. These endpoints are additive; existing standalone endpoints remain unchanged.

### `GET /api/health/live`

Reports whether the REST Gateway process itself is alive. This endpoint deliberately does not contact the local Plasma Server.

Example:

```json
{
  "ok": true,
  "service": "plasma-web-rest-gateway",
  "gateway": "alive"
}
```

This distinction matters operationally: a Manager can tell the difference between a dead Gateway process and a live Gateway whose local execution backend is unavailable.

### `GET /api/health/ready`

Checks whether the Gateway can reach the local Plasma Server and obtain canonical PPU identity.

Healthy example:

```json
{
  "ok": true,
  "service": "plasma-web-rest-gateway",
  "gateway": "alive",
  "execution": "ready",
  "ppu_id": "z2-dev-01"
}
```

If local execution is unavailable, the endpoint returns HTTP 503 while the Gateway liveness endpoint may still return HTTP 200.

### `GET /api/node`

Returns the stable fleet-facing node descriptor.

Example:

```json
{
  "ok": true,
  "contract_version": "1",
  "node_role": "ppu",
  "manager_required": false,
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
  "links": {
    "status": "/api/status",
    "jobs": "/api/jobs",
    "liveness": "/api/health/live",
    "readiness": "/api/health/ready"
  }
}
```

All links are relative. The same PPU therefore works when addressed directly in standalone mode or through a future Manager routing layer.

## What is intentionally not implemented here

This contract does not add Manager registration, mDNS discovery, authentication, remote firmware rollout, central audit storage, or fleet scheduling. Those belong above the PPU boundary and must be introduced without moving local job execution into the control plane.

The PPU also does not contain a `manager_host` requirement or a mandatory Manager heartbeat. If future managed-mode configuration is added, loss of that control-plane connection must degrade fleet visibility only; it must not disable an otherwise healthy local execution node.

## Failure-domain rule

The design target is explicit fault containment:

```text
Manager failure
    -> fleet UI / aggregation unavailable
    -> local PPU execution remains available

Gateway failure on one PPU
    -> that PPU loses REST access
    -> other PPUs remain independent

Plasma Server failure on one PPU
    -> readiness for that PPU fails
    -> Gateway liveness can still distinguish the failure
    -> other PPUs remain independent
```

This separation is required for production equipment. A centralized control plane may improve observability and orchestration, but it must not create a new single point of failure for programming execution.
