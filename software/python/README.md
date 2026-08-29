# Plasma Python Services

Plasma's Python stack provides the PPU execution runtime, REST Gateway, client tooling, and the Plasma Manager control-plane service.

## Service roles

- `plasma_server`: local PPU execution server.
- `plasma_web`: PPU Web REST Gateway.
- `plasma_manager`: management-host fleet service. Current fleet observation remains read-only, with one deliberately narrow Phase-0 write exception for PS Loopback pass-through.

## Manager Phase-0 PS Loopback pass-through

The first Manager command path is intentionally limited to PS diagnostics:

```text
Central Web Console / BFF
        -> Plasma Manager
        -> enrolled PPU Gateway
        -> Plasma Server
        -> PS diagnostic handler
```

Manager resolves the destination from its configured PPU alias. Callers do not supply an arbitrary PPU URL, and Manager does not expose a generic HTTP proxy.

The Manager route is:

```text
POST /api/ppus/{ppu_alias}/diagnostics/loopback
```

It relays only the existing PPU Gateway route:

```text
POST /api/engineering/diagnostics/loopback
```

Phase 0 accepts only `endpoint = "ps"`. PL/IC, Programming Job routing, Batch scheduling, Programming Image distribution, generic write forwarding, retries, and orchestration policy remain outside this slice.

A successful response preserves the PPU diagnostic response and adds Manager relay evidence:

```json
{
  "manager": {
    "relay": "pass-through",
    "ppu_alias": "ppu-a",
    "manager_rtt_ms": 12.345
  }
}
```

This metadata proves that the response crossed the Manager command boundary; it does not replace the PPU's own `source = "ps"`, CRC, sequence, or Test ID validation.

## Development

Install the Python package from `software/python` and run the repository test suite before review.
