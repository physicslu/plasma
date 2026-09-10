# Vendor-neutral IC admission governance

Status: **Current governance contract; no runtime integration**

## Purpose

The admission framework defines how reviewed manufacturer knowledge becomes an operation-specific software candidate while keeping target semantics in separately versioned payloads. Its generic layer owns identity, lineage, integrity, coverage, and explicit state transitions. It does not interpret registers, command encodings, memory rules, or other target behavior.

The governed chain is:

```text
Manufacturer Evidence
  -> Review
  -> Disposition
  -> Candidate Review
  -> Vendor Canonical Payload
  -> Canonical Admission Envelope
  -> Operation Admission
  -> Backend Binding
  -> Compiler
  -> Software Executor
```

Each arrow is an explicit content-addressed binding. A later artifact names the earlier artifact's identity, type, schema where applicable, and canonical SHA-256 digest. Replacing content while retaining an old reference fails validation.

## Trust boundaries

The framework preserves these independent decisions:

```text
reviewed != canonical admitted
canonical admitted != operation admitted
operation admitted != production routed
production routed != hardware runtime ready
```

Review status is data supplied by the review process. The generic validator confirms that the review artifact is exactly the artifact named by its binding; it does not hard-code a particular review outcome or infer semantic truth.

A disposition covers every reviewed source fact and records one generic action plus one projection state. Every non-rejected row must identify its candidate artifacts. Candidate review then covers that exact candidate set and binds each candidate to evidence from the named source lock. Deterministic validation checks coverage, identity, lineage, and evidence digests. A reviewer remains responsible for semantic support, citation entailment, atomicity, scope, terminology, and any additional review dimensions.

## Canonical admission

The canonical admission envelope identifies a target by `vendor_id` and `icpn`. It references an opaque vendor canonical payload and records the source lock, review binding, disposition, and candidate review used to admit it. An admitted envelope cannot retain unresolved requirements.

Generic governance does not imply generic silicon semantics. Each vendor payload selects its own schema and contains its own domain fields. The generic validator verifies the payload's artifact identity and digest without examining those fields.

## Operation admission

Admission is evaluated per request operation. Each row binds:

- request operation;
- operation contract identity and digest;
- canonical admission digest;
- backend identity and lock digest;
- compiler identity;
- canonical and unresolved requirements;
- admission state;
- `hardware_runtime_ready`.

This prevents one high-level request name from silently inheriting the semantics admitted for a different target or operation contract. An admitted row requires resolved canonical requirements, an exact backend lock, and a compiler registered for that backend binding.

## Backend binding

A backend implementation binding records an implementation identity and revision, implementation evidence references, and an opaque vendor constraint payload reference. The lock digest covers those fields. The generic validator verifies the constraint payload reference but does not parse its semantics.

## Current integration boundary

The v1 schemas and deterministic validator are governance infrastructure only. They are not selected by production resolution or routing code. No compiler selection, catalog record, runtime launcher, deployment job, programmable-logic component, or hardware readiness flag is changed by this framework.

Migration of existing target artifacts requires separate work. A migration must construct target-owned payload schemas and prove equivalence without rewriting historical evidence or review records.
