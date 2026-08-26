# Plasma Mock Synthetic Image Contract

Status: Mock Runtime software contract extension. This behavior applies only to the Shared Image Mock execution path and does not relax real PPU Programming Image requirements.

Canonical parent specification: `docs/architecture/mock-runtime-v1.1.md`.

## 1. Purpose

Mock Runtime must be able to exercise Program and Verify without requiring an operator to prepare an arbitrary BIN file first. The server may therefore create one deterministic **Mock Synthetic Image** when a Mock execution needs an Image and the operator did not select one.

This is test infrastructure, not customer Image generation and not a substitute for a real customer Programming Image.

## 2. Selection precedence

For Program or Verify:

```text
Explicit operator Programming Image
  > Mock Synthetic Image
  > fail closed
```

Rules:

- If the operator selected a Programming Image, that Image is used. Synthetic generation is not involved.
- If no Image was selected and the execution provider is the canonical Shared Image Mock provider, the server creates one Mock Synthetic Image.
- If no Image was selected and the provider is not Synthetic-Image-capable Mock execution, submission must fail closed.
- Erase and Read do not create or carry a Synthetic Image.

The browser may advertise the Synthetic Image fallback only for Mock execution. Server enforcement remains authoritative.

## 3. Size source and immutable execution semantics

Synthetic Image size comes from:

```text
Mock Profile snapshot
  -> default_image_size_bytes
```

The size is not read from mutable settings after execution has started.

For a server-side Batch:

1. Allocate the Batch ID.
2. Freeze the Mock execution context for that Batch ID.
3. Read `default_image_size_bytes` from that frozen profile.
4. Generate one Synthetic Image.
5. Bind that Image as the immutable Batch Programming Asset/Image snapshot.
6. Dispatch independent Site Jobs from the same frozen Batch context.

Changing Mock Settings after Batch creation must not change the Synthetic Image size or content for that Batch.

For a direct Engineering Job, the provider freezes a direct-job execution snapshot at submission time and generates the Synthetic Image from that snapshot.

## 4. Deterministic content

The current Synthetic Image generator uses a deterministic repeated byte pattern:

```text
00 01 02 ... FE FF 00 01 02 ...
```

The payload is truncated exactly at `default_image_size_bytes`.

Consequences:

- identical configured sizes produce identical bytes and SHA-256;
- content is easy to inspect and reproduce;
- no random source is required to create the payload;
- Mock error/timing randomness remains controlled separately by the Mock execution seed contract.

The Synthetic Image is represented as a normal `ProgrammingAsset` with binary Image type/format so downstream normalization and shared-image execution use the same contracts as an uploaded Image.

## 5. Shared-image and memory behavior

The Synthetic Image does not create one full persistent Image per Site.

Execution remains:

```text
one Synthetic Programming Asset/Image snapshot
  -> normalized Image
  -> content-addressed shared Blob
  -> local_mock_blob ExecutionImageRef
  -> per-Site logical Mock Flash backing/overlay
```

A 4 MiB Synthetic Image used by 160 Sites is therefore intended to exercise the same shared-image memory model as one uploaded 4 MiB Programming Image.

This does not by itself prove the SWPC memory acceptance gate; actual RSS/high-water measurement remains a separate deployment acceptance step.

## 6. Server-side Batch behavior

`MockAwareBatchRuntimeManager` is responsible for the Mock-specific fallback.

Generic `BatchRuntimeManager` remains unchanged in principle: Program/Verify requires a Programming Asset/Image. The Mock-aware adapter may synthesize that Asset before entering the generic Batch execution path.

This separation is deliberate. Future real PPU and Manager adapters must not gain an implicit fake Image merely because Mock Runtime supports one.

Batch snapshots expose the generated Asset metadata just like an explicit Asset. The operator log may therefore record the generated filename and byte size.

## 7. Engineering direct-job REST behavior

The canonical Engineering REST contract normally requires `session_id` and `asset_sha256` for Program/Verify.

For the Shared Image Mock provider only, the canonical Gateway permits a Program/Verify request with:

```json
{
  "site_id": 1,
  "operation": "program",
  "session_id": "<engineering-session-id>"
}
```

The omitted `asset_sha256` means "use the Mock Synthetic Image for this execution snapshot".

For non-Synthetic providers, omitting `asset_sha256` remains a request error. The Gateway must not infer Synthetic capability from a generic real-provider path.

## 8. UI behavior

Production and Engineering Programming views follow the same operator rule:

- Program/Verify + no selected Image + Mock provider -> show `Mock Synthetic Image` and allow execution.
- Selecting a file replaces the display with the user filename and that file takes precedence.
- Non-Mock provider + no selected Image -> show normal missing-Image readiness and keep Execute disabled.

This UI behavior is convenience only. The server remains the final enforcement boundary.

## 9. Validation requirements

Merge-ready validation must cover at least:

- deterministic bytes and exact configured size;
- one frozen Mock Profile determining the Batch Synthetic Image;
- settings edits after Batch creation not mutating that Batch Image;
- explicit user Image precedence;
- Program/Verify Batch success with no uploaded Image;
- direct Engineering Mock Job success without `asset_sha256`;
- non-Synthetic provider REST failure without `asset_sha256`;
- Production browser readiness using Synthetic Image;
- Engineering browser readiness using Synthetic Image;
- non-Mock browser readiness remaining `IMAGE REQUIRED`;
- full existing Mock CD and browser-runtime acceptance remaining green.

## 10. Non-claims

Synthetic Image support does not mean:

- Plasma can generate a customer Programming Image;
- a real PPU may omit its Programming Image;
- a real IC algorithm is validated;
- Synthetic data models real application contents;
- Mock timing predicts hardware throughput.

Its purpose is narrower: remove an irrelevant manual file prerequisite from Mock software validation while preserving the same Image, Batch, shared-memory, Verify, and provider-boundary contracts used by the rest of Plasma.
