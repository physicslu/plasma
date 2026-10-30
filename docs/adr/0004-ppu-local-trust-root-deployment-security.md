# ADR-0004: PPU local trust root for deployment

- **Status:** Accepted architecture, implementation pending
- **Date:** 2026-10-30
- **Scope:** PPU deployment trust and offline operation
- **Related:** [Security contract](../architecture/ppu-local-trust-root-security-contract.md), [ADR-0001](0001-pynq-system-python-plasma-runtime-separation.md), PR #1214 and Draft PR #1215

## Context

The current Bootstrap service is commissioning HTTP with a device-local Bearer token. It has no production TLS server identity, revocable Master principal, or verified publisher chain. Generic package admission remains denied in the normal service. The Host-only Master planning contract and generic package fixture cannot grant production authority.

## Decision

Each PPU has a unique factory-provisioned device identity and initial local trust material. The PPU stores and enforces its own Master principals, generations, purpose/target policy and revocation state. Normal deployment works while a central service is offline. Engineering SWPC and User PC use one HTTPS Bootstrap Deployment API and one on-device DeploymentCoordinator. The commissioning token has no production deployment privilege.

The operator credential authorizes *who may deploy*; an independently verified publisher signature authorizes *what package source and bytes may be installed*. Both chains, target compatibility, policy generation and durable replay admission must pass before queueing. SHA256 proves byte consistency only. Unknown trust, revocation, transaction or hardware state denies activation.

Factory recovery is a physically protected, audited trust-rebuild procedure outside the normal network Deployment API. A normal client can never reset the trust anchor, clear revocation or advance Master generation by presenting a package or API request.

This ADR concerns the deployment API. The programming Web/Controller/BFF boundary in `AGENTS.md` stays normative; Draft PR #1215 describes deployment clients and must be reconciled before a programming runtime location change. No second installer, daemon, lock, journal or SSH deployment path is introduced.

## Consequences and migration gap

Factory identity/provisioning, HTTPS certificate lifecycle, principal credential validation, publisher signature verification, durable policy and replay store, secure recovery, and production integration are **not implemented** by this ADR. Gate 1A only adds a pure Host-only policy transition with synthetic preverified facts and tests. Gate 1B must implement the production code path and qualify its failure behavior before generic admission changes. Production certificates or device trust data are not generated here. PR #1214 remains Draft; PR #1215 remains independent.
