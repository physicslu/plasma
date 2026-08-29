# Production Real-Path Loopback Diagnostics

## Status

Phase 1 implements the **PS endpoint only**. PL and IC endpoints remain explicit extension points and must fail closed until their real hardware paths exist.

The current PS implementation predates the approved managed-route consolidation: it proves the Browser / Gateway / Plasma Server / PS path directly. The approved target for Managed Mode is documented in [Control Plane Routing Architecture](control-plane-routing-architecture.md) and requires Programming and Loopback to share the same `Control Console -> BFF -> Manager -> PPU Gateway -> Plasma Server` production prefix.

This diagnostic is not a Mock feature. A Mock result must never be substituted for a production real-path result.

## Purpose

The Loopback Test is a fault-isolation diagnostic. A PASS at endpoint `X` is valid only if the test payload actually crosses into `X`, is processed by the implementation assigned to `X`, and returns through the expected production boundaries.

The diagnostic must not invent a parallel transport that bypasses the route used by the production operation it is intended to qualify.

## Current Phase-1 implementation

The currently implemented PS endpoint proves this direct path:

```text
Browser
  -> Plasma Web REST Gateway
  -> Plasma Protocol v3.3 TCP connection
  -> Plasma Server / PS diagnostic handler
  -> Plasma Protocol v3.3 TCP response
  -> Plasma Web REST Gateway
  -> Browser verification
```

The PS handler does **not** enqueue a Programming Job and does **not** enter `SiteManager` execution or a Site Interface. In particular, it does not call `MockInterface` even when the development configuration contains Mock Sites.

When the narrow Manager Loopback relay is used, the request can additionally traverse Manager before the target PPU Gateway, but general Programming currently does not yet share that same managed route. Therefore a current Manager-mediated PS Loopback PASS must not be claimed as proof that Managed Programming routing is complete.

## Approved Managed Mode route

The target shared prefix is:

```text
Control Console
      |
      v
BFF
      |
      v
Plasma Manager
      |
      v
PPU Gateway @ selected PPU
      |
      v
Plasma Server
```

Programming and Loopback are allowed to diverge only after this point.

### Loopback enabled / diagnostic operation selected

`Loopback enabled` here means the operator has selected a Loopback diagnostic request. It does not replace the normal runtime globally.

```text
Control Console
 -> BFF
 -> Manager
 -> PPU Gateway
 -> Plasma Server
      |
      v
    Diagnostic Dispatcher
      |
      +--> PS endpoint  -> echo / validate at PS
      +--> PL endpoint  -> PS -> PL -> return        [future]
      +--> IC endpoint  -> PS -> PL -> IC -> return  [future]
```

### Loopback disabled / normal Programming selected

When the requested operation is normal Programming, the same managed prefix is used and dispatch continues into the Programming runtime:

```text
Control Console
 -> BFF
 -> Manager
 -> PPU Gateway
 -> Plasma Server
      |
      v
    Programming Job Runtime
      |
      v
    SiteManager / SiteWorker
      |
      v
    PS -> PL -> Site -> IC
```

The shared prefix is the architectural requirement that prevents a misleading state where Loopback passes only because it tested a different routing path from Programming.

## What each PASS can prove

A diagnostic claim must stop at the deepest endpoint actually traversed.

```text
PS Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS

PL Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS -> PL

IC Loopback PASS
Console -> BFF -> Manager -> PPU Gateway -> Server -> PS -> PL -> IC
```

Examples:

```text
PS PASS + PL FAIL
=> investigate PS <-> PL or PL diagnostic endpoint

PL PASS + IC FAIL
=> investigate PL <-> Site / target IC boundary
```

Even after the managed route is unified, a PS Loopback PASS does **not** prove Programming Job semantics, PL behavior, electrical behavior, socket behavior or real-IC Programming.

## Web REST contract — current Phase 1

Current endpoint:

```text
POST /api/engineering/diagnostics/loopback
```

Request fields:

```text
endpoint          ps
test_id           caller-generated run identity
sequence          monotonically increasing case identity
pattern           deterministic Browser pattern identifier
seed              deterministic seed; empty when unused
payload_length    decoded payload bytes
payload_base64    Browser-generated payload
tx_crc32          lowercase CRC32 of decoded payload
timeout_ms        per-case Gateway -> Plasma Server timeout
```

The Gateway validates the Browser payload before forwarding it. Phase 1 accepts at most 4 MiB per REST request as a transport safety limit; this value is not a claim about a future PL FIFO, DMA, IC buffer, Programming Asset or target-device boundary.

The Gateway sends the decoded bytes to the local Plasma Server using a Protocol v3.3 `diagnostic_request` frame. There is no Engineering Provider or Mock fallback.

The future Manager-facing route must preserve the diagnostic payload and provenance while resolving the target by canonical PPU identity / alias. It must not accept a caller-controlled arbitrary PPU URL.

## Diagnostic Protocol v1

Request metadata:

```text
protocol_version     3.3
message_type         diagnostic_request
diagnostic_type      loopback
diagnostic_version   1
endpoint             ps
test_id              string
sequence             non-negative integer
transform            echo
payload_length       positive integer
tx_crc32             lowercase CRC32
pattern              optional string
seed                 optional string
```

The payload is carried in the normal Protocol v3.3 binary field.

Response metadata must prove the actual processing point:

```text
message_type         diagnostic_response
source               ps
endpoint             ps
test_id              same request ID
sequence             same sequence
transform            echo
payload_length       exact returned byte count
tx_crc32             validated request CRC32
rx_crc32             CRC32 of returned bytes
```

The response binary is the PS echo payload.

## PASS criteria

The Browser independently checks all of the following before displaying PASS:

1. HTTP request completed successfully.
2. response `endpoint == ps` and `source == ps`;
3. `test_id` and `sequence` match the request;
4. response transform is `echo`;
5. returned length matches the Browser-generated payload;
6. returned bytes exactly match the Browser-generated payload;
7. Browser TX CRC32 equals returned RX CRC32;
8. response CRC metadata agrees with Browser-computed CRC32.

A failed check is FAIL/ERROR/TIMEOUT; it must not be converted to PASS by a fallback path.

Two latency observations are intentionally distinct:

- **Browser RTT**: browser-visible end-to-end request time for the route actually used.
- **PPU RTT**: PPU Gateway -> Plasma Server -> PPU Gateway.

After managed routing is consolidated, Manager relay latency may be reported separately but must not replace either of these meanings.

## Deterministic data

The Browser owns test-data generation so the tested bytes originate before the Web/Gateway boundary. Supported deterministic patterns include `00`, `FF`, `AA`, `55`, incrementing byte, Walking-1, Walking-0 and PRBS. PRBS uses an explicit seed so failures are reproducible.

Boundary mode expands `N` to `N-1`, `N`, `N+1`. These lengths become diagnostically meaningful only when `N` maps to an actual architecture boundary; the UI must not imply that a preset is a hardware boundary without evidence.

## Programming Asset / Image coverage

The PS echo payload is **not** a substitute for Programming Asset / Image path validation.

The approved Phase-1 Managed Programming direction sends Programming Asset / Image data through:

```text
Control Console
 -> BFF
 -> Manager
 -> selected PPU Gateway
 -> PPU Asset Service / Cache
```

Programming acceptance must verify the real production Asset path and bind the accepted Asset / normalized Image identity to the Job that consumes it. A dedicated diagnostic Asset transport that bypasses production Asset APIs would recreate the same false-confidence problem that routing consolidation is intended to remove.

Loopback and Asset validation are therefore complementary evidence:

```text
Loopback
=> routing + requested endpoint evidence

Programming Asset validation
=> production Image transfer / integrity / provenance evidence

Programming acceptance
=> Job runtime + Site + downstream execution evidence
```

## Security boundary

The secure Gateway authenticates the caller before looking up local PPU identity. Current Phase-1 PS Loopback is non-destructive and uses the existing `STATUS_READ` authorization scope.

Future Manager-routed Programming and future PL/IC diagnostics alter the security boundary. They require explicit authorization, auditability, replay/idempotency, timeout and failure semantics. PL/IC diagnostics that alter hardware state, power, routing, reset or I/O behavior must not inherit the Phase-1 PS authorization assumption automatically.

Manager must not be generalized into an arbitrary reverse proxy as part of this migration.

## Fail-closed extension rules

- `endpoint=pl`: unsupported until the payload actually crosses PS <-> PL.
- `endpoint=ic`: unsupported until the payload actually crosses PL <-> IC and is processed/responded to by a compatible target path.
- unavailable local Plasma Server: return an execution error; never use Mock.
- Mock Engineering Provider enabled: irrelevant to this route and must not be consulted.
- unavailable Manager in Managed Mode: the centrally routed diagnostic fails; do not silently bypass Manager by switching to a direct PPU URL.
- unsupported managed write route: fail explicitly until the production route exists.

## Validation boundary

Cloud/CI validation can prove protocol, API and software-path behavior, but does not prove SWPC deployment, Z2 PS/PL integration, FPGA behavior, electrical behavior or real IC behavior.

After the managed-route implementation lands, runtime acceptance should show that PS Loopback, PMode Programming, EMode Programming and Programming Asset transfer select the same PPU through the same Manager routing ownership before any downstream endpoint-specific claim is made.
