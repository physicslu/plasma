# Documentation Maintenance

## Purpose

Documentation is part of the Plasma contract. A behavior change is incomplete when code, UI labels, tests and operator guidance disagree.

## Source priority

When resolving a conflict, use the order defined in root [AGENTS.md](../../AGENTS.md):

1. executable code and checked-in configuration;
2. `scripts/plasmactl` for integration-host and deployment operations;
3. Python/Web package manifests;
4. automated tests;
5. current documents (Current architecture/API contracts, then operator and deployment guides);
6. plans, notes and historical documents.

This priority is diagnostic, not permission to leave the lower layer stale. Correct every affected layer in the same PR.

## Directory placement

| Directory | Holds |
| --- | --- |
| `docs/adr/` | Architecture Decision Records: one decision per file, superseded by a new ADR rather than rewritten. |
| `docs/architecture/` | Current or planned product architecture and interface contracts (PPU, runtime, ABI, protocol, catalog). |
| `docs/development/` | Engineering process and governance contracts, developer guides, tool runbooks and HIL procedures. |
| `docs/deployment/` | How to build, package, install, upgrade and roll back Control Station and PPU software. |
| `docs/operator/` | End-user / operator behaviour of the product. |
| `docs/testing/` | Acceptance procedures that span components. |
| `docs/engineering/` | CI and repository engineering analyses. |
| `docs/evidence/` | Dated observations and hardware/test evidence tied to an exact commit or run; evidence never lives in the other directories. |
| `docs/archive/` | Archived non-Markdown material (for example retired workflow files). |
| `docs/glossary.md` | Term definitions only; no rules. |

A dated work record (Gate 1 report, audit, measurement) belongs in `docs/evidence/` or is deleted once its result is absorbed into a current document. Older Gate 1 reports still under `docs/architecture/` and `docs/development/` predate this rule; they are indexed as Reference or Historical until migrated.

## Required update set

For any contract change, search and update as applicable:

- root and component READMEs;
- `docs/architecture/` contract;
- `docs/operator/` user behavior;
- REST/wire examples and configuration schema/version;
- UI labels, help text and localization;
- automated tests and acceptance matrix;
- deployment guide and rollback/health-check instructions.

Keep historical test IDs stable even when wording changes. For example, `OAT-FW-*` remains a stable identifier while current prose says Programming Image. Do not retain a retired filename merely to preserve an ID.

## No static test snapshots

Do not commit hand-maintained `TEST_REPORT.md` files that contain a test count or dated PASS result. They become false evidence as soon as the suite changes. Use reproducible commands, CI checks, and release/PR artifacts tied to an exact commit instead.

## Document lifecycle

Every entry in [the documentation index](../README.md) is written as ``- **Status** · `tag` — <link>: summary`` (zero or more tags), and Status is exactly one of:

- **Current** — implemented behavior or a contract that must be followed now.
- **Reference** — background, work records, verification boundaries or maintenance notes; never overrides a Current contract.
- **Plan** — an approved direction not fully implemented; state what is not implemented.
- **Historical** — superseded or retired material; explicitly deny runtime compatibility authority.

Status never contains PR numbers, Draft/merge state, Gate, Path or hardware verdicts; put those in tags (for example `PR #1225`, `Host-only`, `M1 NO-GO`). A PR's merge state changes after the document is written, so it must not be part of Status. The integrity guard enforces the allowed statuses and rejects duplicate index entries.

- Under the Replace-by-Default policy in root `AGENTS.md`, delete a superseded document when a current canonical document fully replaces it and repair all inbound links in the same change. Keep it as **Historical** only while code, tests or workflows still reference it.
- Track executable technical debt in the [Development Debt Register](todo.md), not as an ambiguous sentence hidden in a Current contract.

## Local validation

Run:

```bash
python scripts/tests/test-documentation-integrity.py
python scripts/tests/test-canonical-terminology-guard.py
python -m pytest -q software/python/tests/test_documentation_baseline.py
```

The integrity guard verifies headings, relative links, index coverage, canonical protocol/config/error facts, removed-document references, and the Gateway base-module naming invariant. The terminology guard checks only repository source files, excluding ignored dependency/build output. CI and the repository test script run these guards.
