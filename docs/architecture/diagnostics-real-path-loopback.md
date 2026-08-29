# Production Real-Path Loopback Diagnostics

## Status

Phase 1 implements the **PS endpoint only**. PL and IC endpoints remain explicit extension points and fail closed until their real hardware paths exist.

In Managed Mode, PS Loopback now uses the same production routing prefix as PMode/EMode Programming:

```text
Control Console
 -> BFF
 -> Plasma Manager
 -> selected PPU Gateway
 -> Plasma Server
```

Only after Plasma Server receives the request does Loopback dispatch differ from normal Programming.

This is software architecture evidence only until the deployed Management Host -> PPU route is runtime-accepted. It is not Z2/FPGA/real-IC evidence.

## Purpose

Loopback is a fault-isolation diagnostic. A PASS at endpoint `X` is valid only if the test payload actually crosses into `X`, is processed by the implementation assigned to `X`, and returns through the expected production boundaries.

A diagnostic transport must not bypass the route used by the production operation it is intended to qualify. This requirement prevents the misleading condition previously possible when Manager-mediated Loopback could PASS while Programming used an unrelated direct Gateway `apiBase` and failed.

## Shared Managed Mode route

The common prefix is:

```text
Control Console
      |
      v
BFF
      |
      v
Plasma Manager
      |
      | resolve configured ppu_alias
      v
PPU Gateway
      |
      v
Plasma Server
```

PMode, EMode and Loopback share the Workspace API base. When Manager routing is configured, that base is the same-origin Managed PPU BFF path. Managed Mode never silently falls back to a stored direct PPU URL.

### Loopback selected

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
      +--> PL endpoint  -> PS -> PL -> return        [not implemented]
      +--> IC endpoint  -> PS -> PL -> IC -> return  [not implemented]
```

### Normal Programming selected

```text
Control Console
 -> BFF
 -> Manager
 -> PPU Gateway
 -> Plasma Server
      |
      v
    Programming Job / Batch Runtime
      |
      v
    SiteManager / SiteWorker
      |
      v
    PS -> PL -> Site -> IC
```

The shared prefix proves route ownership, not downstream equivalence. PS Loopback does not enqueue a Programming Job and does not exercise SiteManager, PL or target-IC programming semantics.

## Current PS endpoint

Current PPU-side PS execution remains:

```text
PPU Gateway
  -> Plasma Protocol v3.3 diagnostic_request
  -> Plasma Server / PS diagnostic handler
  -> diagnostic_response
  -> PPU Gateway
```

The PS handler does **not** enqueue a Programming Job and does **not** enter a Site Interface. It does not call `MockInterface`, even when the development configuration contains Mock Sites.

The Managed Mode request reaches this same production PPU endpoint through BFF and Manager. Manager adds relay evidence to a successful response so the browser can verify that the configured Manager boundary was actually crossed.

## Browser-facing and Manager routing

Managed browser request:

```text
POST <workspace-api-base>/api/engineering/diagnostics/loopback
```

For a Managed Workspace base, the same-origin BFF forwards the request to the configured Manager. Manager resolves the configured PPU alias from its registry and forwards only the explicitly allowlisted PPU diagnostic route.

Neither BFF nor Manager accepts a caller-controlled destination URL.

The legacy fixed Manager PS Loopback route may remain for compatibility, but the Control Console diagnostic uses the same managed PPU route family as Programming.

## Web REST request contract

Current PS request fields:

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

The PPU Gateway validates the payload before forwarding it to Plasma Server. There is no Engineering Provider or Mock fallback.

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

Payload bytes use the normal Protocol v3.3 binary field.

Response metadata proves the actual processing point:

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

Managed Mode success additionally carries Manager relay evidence:

```text
manager.relay          pass-through
manager.ppu_alias      configured selected PPU
manager.manager_rtt_ms observed Manager relay RTT
```

## PASS criteria

The browser independently checks all of the following before displaying PASS:

1. HTTP request completed successfully.
2. Manager relay evidence is present and identifies the configured managed PPU.
3. response `endpoint == ps` and `source == ps`.
4. `test_id` and `sequence` match the request.
5. transform is `echo`.
6. returned length matches the Browser-generated payload.
7. returned bytes exactly match the Browser-generated payload.
8. Browser TX CRC32 equals returned RX CRC32.
9. response CRC metadata agrees with Browser-computed CRC32.

Any failed check is FAIL/ERROR/TIMEOUT and must never become PASS through fallback.

Latency measurements are distinct:

- **Browser RTT**: browser-visible end-to-end time through the actual route.
- **Manager RTT**: Manager relay observation for the selected PPU request.
- **PPU RTT**: PPU Gateway -> Plasma Server -> PPU Gateway.

These values are observations, not substitutes for endpoint correctness.

## Deterministic data

The Browser generates deterministic test payloads before the managed route begins. Supported patterns include `00`, `FF`, `AA`, `55`, incrementing byte, Walking-1, Walking-0 and PRBS with explicit seed.

Boundary mode expands `N` to `N-1`, `N`, `N+1`. A preset becomes a hardware-boundary test only when architecture evidence identifies `N` as a real boundary.

## Evidence depth

A claim stops at the deepest endpoint actually crossed:

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
=> investigate PS <-> PL / PL endpoint

PL PASS + IC FAIL
=> investigate PL <-> Site / target IC boundary
```

PS PASS does not prove Programming Job semantics, PL behavior, electrical/socket behavior or real-IC Programming.

## Programming Asset / Image coverage

Loopback payload validation is **not** Programming Asset validation.

Managed Programming Asset/Image transfer uses the production route:

```text
Control Console
 -> BFF
 -> Manager
 -> selected PPU Gateway
 -> PPU Asset Service / Cache
```

Production acceptance must separately prove:

```text
Browser source SHA-256
        =
PPU cached Asset identity
        =
Job-referenced asset_sha256
```

A diagnostic-only Asset upload route would recreate false confidence and is prohibited. Loopback, Asset integrity and Programming execution are complementary evidence layers.

## Security boundary

The PPU secure Gateway remains the execution authorization authority. Managed BFF and Manager preserve required `Authorization` and `Idempotency-Key` headers; they do not grant permissions or widen resource scope.

Current PS Loopback is non-destructive and uses its existing authorization contract. Future PL/IC diagnostics that change hardware state, power, routing, reset or I/O require their own authorization/safety review.

Manager is explicitly allowlisted and must not become an arbitrary reverse proxy.

## Fail-closed rules

- `endpoint=pl`: unsupported until payload actually crosses PS <-> PL.
- `endpoint=ic`: unsupported until payload actually crosses PL <-> IC and reaches a compatible real target path.
- unavailable Plasma Server: execution error; never use Mock.
- Mock Engineering Provider enabled: irrelevant to PS real-path Loopback and must not be consulted.
- unavailable Manager in Managed Mode: fail; do not bypass Manager.
- non-allowlisted Manager route: reject before contacting the PPU.

## Validation boundary

Cloud/CI can prove protocol/API behavior, same-route ownership, Manager allowlisting and software-path integrity. Integration-host runtime acceptance must separately prove the deployed Control Console -> Manager -> PPU route. Z2 PS/PL, FPGA, electrical and real-IC behavior remain separate validation domains.
