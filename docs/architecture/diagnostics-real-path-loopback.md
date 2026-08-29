# Production Real-Path Loopback Diagnostics

## Status

Phase 1 implements the **PS endpoint only**. PL and IC endpoints remain explicit extension points and must fail closed until their real hardware paths exist.

This diagnostic is not a Mock feature. A Mock result must never be substituted for a production real-path result.

## Purpose

The Loopback Test is a fault-isolation diagnostic. A PASS at endpoint `X` is valid only if the test payload actually crosses into `X`, is processed by the implementation assigned to `X`, and returns through the expected path.

Phase 1 therefore proves this path:

```text
Browser
  -> Plasma Web REST Gateway
  -> Plasma Protocol v3.3 TCP connection
  -> Plasma Server / PS diagnostic handler
  -> Plasma Protocol v3.3 TCP response
  -> Plasma Web REST Gateway
  -> Browser verification
```

The PS handler does **not** enqueue a programming Job and does **not** enter `SiteManager` execution or a Site Interface. In particular, it does not call `MockInterface` even when the development configuration contains Mock Sites.

## Web REST contract

Phase 1 endpoint:

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

The Gateway validates the Browser payload before forwarding it. Phase 1 accepts at most 4 MiB per REST request as a transport safety limit; this value is not a claim about a future PL FIFO, DMA, IC buffer, or programming-device boundary.

The Gateway sends the decoded bytes to the local Plasma Server using a Protocol v3.3 `diagnostic_request` frame. There is no Engineering Provider or Mock fallback.

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

- **Browser RTT**: Web -> Gateway -> PS -> Gateway -> Web.
- **PPU RTT**: Gateway -> Plasma Server -> Gateway.

## Deterministic data

The Browser owns test-data generation so the tested bytes originate before the Web/Gateway boundary. Supported deterministic patterns include `00`, `FF`, `AA`, `55`, incrementing byte, Walking-1, Walking-0 and PRBS. PRBS uses an explicit seed so failures are reproducible.

Boundary mode expands `N` to `N-1`, `N`, `N+1`. These lengths become diagnostically meaningful only when `N` maps to an actual architecture boundary; the UI must not imply that a preset is a hardware boundary without evidence.

## Security boundary

The secure Gateway authenticates the caller before looking up local PPU identity. Phase 1 PS loopback is non-destructive and uses the existing `STATUS_READ` authorization scope. Future PL/IC diagnostics that alter hardware state, power, routing, reset or I/O behavior require a separate security review and must not inherit this Phase 1 authorization assumption automatically.

## Fail-closed extension rules

- `endpoint=pl`: unsupported until the payload actually crosses PS <-> PL.
- `endpoint=ic`: unsupported until the payload actually crosses PL <-> IC and is processed/responded to by compatible IC diagnostic firmware.
- unavailable local Plasma Server: return an execution error; never use Mock.
- Mock Engineering Provider enabled: irrelevant to this route and must not be consulted.

Cloud/CI validation can prove protocol, API and software path behavior, but does not prove SWPC deployment, Z2 PS/PL integration, FPGA behavior, electrical behavior, or IC behavior.
