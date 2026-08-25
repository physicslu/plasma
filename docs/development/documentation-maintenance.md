# Documentation Maintenance

## Purpose

Documentation is part of the Plasma contract. A behavior change is incomplete when code, UI labels, tests and operator guidance disagree.

## Source priority

When resolving a conflict, use this order:

1. executable protocol/schema validation and runtime code;
2. automated contract tests;
3. architecture/API Current documents;
4. operator and deployment guides;
5. plans, notes and historical documents.

This priority is diagnostic, not permission to leave the lower layer stale. Correct every affected layer in the same PR.

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

- Mark descriptions of implemented behavior **Current** in [the documentation index](../README.md).
- Mark incomplete designs **Plan** and state what is not implemented.
- Mark migration-only material **Historical** and explicitly deny runtime compatibility authority.
- Delete a superseded document when a current canonical document fully replaces it; repair all inbound links in the same change.
- Track executable technical debt in the [Development Debt Register](todo.md), not as an ambiguous sentence hidden in a Current contract.

## Local validation

Run:

```bash
python scripts/tests/test-documentation-integrity.py
python scripts/tests/test-canonical-terminology-guard.py
python -m pytest -q software/python/tests/test_documentation_baseline.py
```

The integrity guard verifies headings, relative links, index coverage, canonical protocol/config/error facts, removed-document references, and the Gateway base-module naming invariant. The terminology guard checks only repository source files, excluding ignored dependency/build output. CI and the repository test script run these guards.
