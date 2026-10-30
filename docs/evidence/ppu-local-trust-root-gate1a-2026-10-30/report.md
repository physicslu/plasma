# PPU Local Trust Root Gate 1A — Evidence

**Scope:** Path 3 source work in isolated `/tmp` checkout. Baseline PR #1214 `3d6e52c92916b7f0e6b27246550ae2a154365f87`, Draft PR #1215 `bd580d858b9fbb9c1513b1b67563439aedef470f`, main `a22c9cb04a9ea1361a39d2504fc83f510898390e`. New published commit and hosted CI are recorded in the PR after publication; this report's baseline is not a production release.

## Observed Host-only checks

- `test_ppu_local_trust_contract.py`: **26 PASS** locally in controlled Python 3.12 virtual environment. Pure policy model uses synthetic preverified operator/publisher facts; it covers positive admission, missing identity/permission, revocation, expiry, stale Master generation, wrong publisher key/source/digest/target/purpose, replay, rotation, unknown/corrupt state and ambiguous commit outcome. It does **not** test TLS, credential or signature verification, persistent atomicity or production queueing.
- Existing `test_ppu_package_api_bridge_gate1.py`: **12 PASS, 3 deselected, 26 subtests PASS** locally, including ordinary Bootstrap generic rejection. Local sandbox denies loopback socket creation (`PermissionError: [Errno 1] Operation not permitted`), so the three real HTTP cases are **NOT_RUN locally** and require GitHub-hosted Linux; they are never counted as local PASS.
- `scripts/tests/test-documentation-integrity.py`: **PASS (660 Markdown files)**. `git diff --check`: **PASS**. Exact-head hosted CI is pending until publication.

## Gate 2 readiness

| Item | State | Boundary |
| --- | --- | --- |
| Local trust root, dual trust chains, replay/recovery threat model | **PASS — contract** | [ADR-0004](../../adr/0004-ppu-local-trust-root-deployment-security.md), [security contract](../../architecture/ppu-local-trust-root-security-contract.md). |
| Synthetic policy transition negatives | **PASS — Host-only contract** | `software/python/tests/test_ppu_local_trust_contract.py`; no real credential. |
| HTTPS, PPU device identity, Master/publisher verification and durable replay | **BLOCKED** | Gate 1B production integration and provisioning review. |
| Eight-Site admission fence, generic activation, Root/FPGA recovery | **BLOCKED** | Separate production/HIL acceptance; no hardware operation in Gate 1A. |
| PR #1214 Host-only Gate 2 | **BLOCKED** | PR remains Draft. |

## Decisions awaiting implementation review

Factory key custody and provisioning procedure; certificate profile and rotation window; client credential type; publisher signature algorithm and canonical envelope; secure clock and replay retention; protected local storage and crash consistency; Factory Recovery authority and audit. None is silently selected by the Host-only model.
